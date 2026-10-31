"""外围报价只读快照；时间口径和延迟未核实，不用于自动交易。"""
import re
import threading
import time
from datetime import datetime,timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .provider import CN, get, now_cn

CODES=('hkHSI','us.IXIC','us.INX','hf_GC','hf_CL')
LABELS={'hkHSI':'恒生指数','us.IXIC':'纳斯达克','us.INX':'标普500','hf_GC':'纽约黄金','hf_CL':'纽约原油'}
CACHE_CODE='external-market';CACHE_KIND='snapshot-v1';REFRESH_SECONDS=120


def parse(text,now):
    """核对报价和涨跌幅；来源时间无时区时不假装确认实时性。"""
    now=now.astimezone(CN);rows=[];seen=set()
    for code,body in re.findall(r'v_([\w.]+)="([^"\n]*)";',text):
        if code not in CODES or code in seen:continue
        try:
            fields=body.split(',' if code.startswith('hf_') else '~')
            if code.startswith('hf_'):
                price,percent,previous=Decimal(fields[0]),Decimal(fields[1]),Decimal(fields[7])
                rawtime=fields[12]+' '+fields[6]
                stamp=datetime.strptime(rawtime,'%Y-%m-%d %H:%M:%S')
            else:
                price,previous,percent=Decimal(fields[3]),Decimal(fields[4]),Decimal(fields[32])
                rawtime=fields[30]
                stamp=datetime.strptime(rawtime,'%Y/%m/%d %H:%M:%S' if '/' in rawtime else '%Y-%m-%d %H:%M:%S')
            if not all(v.is_finite() for v in (price,previous,percent)) or price<=0 or previous<=0:continue
            if abs((price/previous-1)*100-percent)>Decimal('0.08'):continue
            # 源接口没有附时区；取两种可能时区都不在未来的记录。
            times=[stamp.replace(tzinfo=CN)]
            if code.startswith(('us.','hf_')):times.append(stamp.replace(tzinfo=ZoneInfo('America/New_York')))
            if max(t.astimezone(CN) for t in times)>now+timedelta(seconds=5):continue
            if min((now-t.astimezone(CN)).total_seconds() for t in times)>7*86400:continue
            rows.append(dict(code=code,name=LABELS[code],price=float(price),percent=float(percent),source_time=rawtime,
                             time_basis='来源时间，时区及延迟未核实'))
            seen.add(code)
        except (ValueError,IndexError,InvalidOperation,OverflowError,ZeroDivisionError):continue
    if not rows:raise ValueError('外围行情暂不可用')
    rows.sort(key=lambda r:CODES.index(r['code']))
    return dict(source='腾讯行情',source_url='https://gu.qq.com/',collected_at=now.isoformat(),quotes=rows)


def fetch(now):
    return parse(get('https://qt.gtimg.cn/q='+','.join(CODES),'gb18030'),now)


class ExternalMarket:
    def __init__(self,store,enabled=True):
        self.store=store;self.enabled=enabled;self.lock=threading.Lock();self.running=False;self.error='';self.last_attempt=float('-inf')

    def refresh(self):
        with self.lock:
            if self.running or time.monotonic()-self.last_attempt<REFRESH_SECONDS:return
            self.running=True;self.last_attempt=time.monotonic()
        try:
            data=fetch(now_cn());self.store.cache(CACHE_CODE,CACHE_KIND,'latest',data);self.error=''
        except Exception:self.error='外围行情更新失败'
        finally:
            with self.lock:self.running=False

    def view(self):
        if self.enabled and not self.running and time.monotonic()-self.last_attempt>=REFRESH_SECONDS:
            threading.Thread(target=self.refresh,daemon=True).start()
        items=self.store.getcache(CACHE_CODE,CACHE_KIND);snapshot=items[-1]['data'] if items else None
        if snapshot:
            try:
                stamp=datetime.fromisoformat(snapshot['collected_at']);age=(now_cn()-stamp).total_seconds()
                if stamp.tzinfo is None or age < -5 or age>7*86400:snapshot=None
            except (TypeError,ValueError,KeyError):snapshot=None
        return dict(snapshot=snapshot,error=self.error,running=self.running)
