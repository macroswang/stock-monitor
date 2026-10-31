"""Dated, read-only CFFEX index-option volume PCR reference."""
import hashlib
import json
import math
import re
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .option_pcr import add_bands, eligible_sessions, _available_at
from .provider import CN, now_cn

KINDS = {'IO': '沪深300股指', 'HO': '上证50股指', 'MO': '中证1000股指'}
KIND = 'option_pcr_cffex_index_v1'
HISTORY = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'fixtures/cffex-index-pcr-verified.json'
EXCHANGE = 'http://www.cffex.com.cn/sj/hqsj/rtj/'
ASSOCIATION = 'https://www.cfachina.org/report/api/variety/optionData?'


def parse_exchange(raw, day):
    expected = date.fromisoformat(day).strftime('%Y%m%d')
    root = ElementTree.fromstring(raw)
    if root.tag != 'dailydatas':
        raise ValueError('中金所日行情格式异常')
    groups = {key: {} for key in KINDS}
    for row in root.findall('dailydata'):
        kind, code, volume = row.findtext('productid'), row.findtext('instrumentid'), row.findtext('volume')
        if kind not in KINDS:
            continue
        if row.findtext('tradingday') != expected or not isinstance(code, str) or not re.fullmatch(kind+r'\d{4}-[CP]-\d+', code):
            raise ValueError('股指期权日期或合约异常')
        if code in groups[kind] or not isinstance(volume, str) or not volume.isdigit():
            raise ValueError('股指期权成交量缺失或重复')
        groups[kind][code] = int(volume)
    if any(not values for values in groups.values()):
        raise ValueError('股指期权品种缺失')
    return groups


def parse_association(payload, product, day):
    data = payload.get('data') if isinstance(payload, dict) and payload.get('errcode') == 0 else None
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) and data[k] for k in ('finList', 'delayList')):
        raise ValueError('期货业协会行情不完整')
    out = {}
    for row in data['delayList']:
        code, volume = row.get('tradeCode'), row.get('volume')
        if row.get('tradeDate') != day or not isinstance(code, str) or not re.fullmatch(product+r'\d{4}-[CP]-\d+', code):
            raise ValueError('期货业协会行情日期或合约不一致')
        if code in out or not isinstance(volume, str) or not volume.isdigit():
            raise ValueError('期货业协会成交量异常')
        out[code] = int(volume)
    contracts = [r.get('tradeCode') for r in data['finList'] if r.get('tradeDate') == day]
    if len(contracts) != len(data['finList']) or len(set(contracts)) != len(contracts) or set(contracts) != set(out):
        raise ValueError('期货业协会合约清单不一致')
    return out


def collect(day, now):
    d = date.fromisoformat(day)
    url = EXCHANGE + f'{d:%Y%m}/{d:%d}/index.xml'
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=12) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError('中金所日行情文件过大')
    exchange = parse_exchange(raw, day)
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    for product, kind in KINDS.items():
        query = urlencode({'kind': kind, 'flag': 1})
        req = Request(ASSOCIATION + query, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cfachina.org/servicesupport/sspz/?type=5'})
        with urlopen(req, timeout=12) as response:
            body = response.read(4_000_001)
        if len(body) > 4_000_000:
            raise ValueError('期货业协会行情文件过大')
        if parse_association(json.loads(body), product, day) != exchange[product]:
            raise ValueError('中金所与期货业协会合约或成交量不一致')
        call = sum(v for code,v in exchange[product].items() if '-C-' in code)
        put = sum(v for code,v in exchange[product].items() if '-P-' in code)
        if call <= 0:
            raise ValueError('认购成交量为零')
        rows.append({'date': day, 'product': product, 'call_volume': call, 'put_volume': put,
                     'total_volume': call+put, 'pcr': put/call, 'contracts': len(exchange[product]),
                     'collected_at': max(now, now_cn()).isoformat(), 'exchange_sha256': digest,
                     'basis': '中金所日统计；期货业协会逐合约对照'})
    return rows


def valid(row, now):
    try:
        day = row['date']
        if date.fromisoformat(day).isoformat() != day or row['product'] not in KINDS or not _available_at(row, now):
            return False
        stamp = datetime.fromisoformat(row['collected_at']).astimezone(CN)
        if stamp.date().isoformat() < day or (stamp.date().isoformat() == day and stamp.strftime('%H:%M') < '16:30'):
            return False
        call, put, total, count = (row[k] for k in ('call_volume', 'put_volume', 'total_volume', 'contracts'))
        ratio = row['pcr']
        return (all(type(n) is int for n in (call, put, total, count)) and call > 0 and put >= 0 and count > 0
                and total == call+put and isinstance(ratio, (int, float)) and not isinstance(ratio, bool)
                and math.isfinite(ratio) and math.isclose(ratio, put/call, rel_tol=1e-10, abs_tol=1e-12))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class IndexOptionPCR:
    def __init__(self, store):
        self.store, self.lock = store, threading.Lock()
        self.error, self.running = '', False

    def view(self, product, now=None):
        if product not in KINDS:
            raise ValueError('不支持的股指期权')
        now = now or now_cn()
        sessions = eligible_sessions(now, 1)
        latest = sessions[-1] if sessions else None
        history = json.loads(HISTORY.read_text(encoding='utf8')) if HISTORY.exists() else []
        rows = {r['date']:r for r in history if latest and r.get('product') == product and valid(r, now) and r['date'] <= latest}
        for cached in self.store.getcache('cffex-'+product, KIND):
            row = cached['data']
            if latest and isinstance(row, dict) and row.get('product') == product and row.get('date') == cached['day'] and cached['day'] <= latest and valid(row, now):
                rows[cached['day']] = row
        return {'days':add_bands([rows[d] for d in sorted(rows)]), 'running':self.running, 'error':self.error, 'latest_eligible':latest}

    def refresh(self, now=None):
        now = now or now_cn()
        with self.lock:
            if self.running:
                return
            self.running = True
        try:
            dates = eligible_sessions(now, 1)
            if not dates:
                raise ValueError('缺少交易日历')
            rows = collect(dates[-1], now)
            if len(rows) != 3 or any(not valid(row, max(now, now_cn())) for row in rows):
                raise ValueError('股指期权统计校验失败')
            records = [('cffex-'+row['product'], KIND, row['date'], json.dumps(row, ensure_ascii=False)) for row in rows]
            with self.store.lock, self.store.db:
                self.store.db.executemany('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)', records)
            self.error = ''
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else '股指期权统计获取失败：'+type(exc).__name__
        finally:
            with self.lock:
                self.running = False
