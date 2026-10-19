"""Prospective local research archive. Never opens the production database."""
import argparse, collections, contextlib, csv, hashlib, html, json, os, shutil, sys, time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.provider import get,now_cn,CN
from scripts.replay_free_expanded import audit
from research.ma20_study import CONFIG,parse_sina,finalized,audit_daily,crosscheck_daily,score_day,compare

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/'docs/buy-v1/ma20-study'
BROAD=BASE/'docs/buy-v1/free-broad-1000'
FROZEN_FILES=['core/rules.py','core/validated_engine.py','core/provider.py','core/buy_supplement.py',
              'scripts/replay_free_expanded.py','research/ma20_study.py']

def read(path,default=None):return json.loads(path.read_text()) if path.exists() else default
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));temp.replace(path)
def fingerprint(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def code_hashes():return {s:fingerprint(BASE/s) for s in FROZEN_FILES}
def interleaved(pool):
    groups={b:[x for x in pool if x['board']==b] for b in ('sh_main','sz_main','chinext')}
    return [groups[b][i] for i in range(max(map(len,groups.values()))) for b in groups if i<len(groups[b])]

def init(root=ROOT,asof=None):
    asof=asof or now_cn();path=root/'protocol.json'
    if path.exists():
        protocol=read(path)
        if protocol['config']!=CONFIG or protocol['frozen_code_sha256']!=code_hashes():raise RuntimeError('Frozen protocol or engine changed; do not auto-update the study')
        return protocol
    frozen=read(BROAD/'frozen-pool.json')
    protocol=dict(created_at=asof.isoformat(),validation_start=(asof.date()+timedelta(days=1)).isoformat(),
        config=CONFIG,pool=interleaved(frozen['pool']),pool_source_sha256=fingerprint(BROAD/'frozen-pool.json'),
        frozen_code_sha256=code_hashes(),daily_source='sina scale=240 unadjusted OHLC; shares',
        minute_source='tencent original day/query; unchanged minute audit',
        volume_precision='Sina shares converted to nearest whole hand, half-up; original shares retained; cross-source error must be <=50 shares',
        evaluation='Old dates diagnostic only. New dates must be >= validation_start. Missing MA20 is unknown, never a failed gate.',
        collection=dict(spacing_seconds=1.25,sina_requests_per_run=40,tencent_requests_per_run=60,
                        provider_cooldown_hours=24,collection_after='16:00',weekdays_only=True))
    save(path,protocol)
    # Preserve the old provider halt. A future post-cooldown probe uses the existing
    # Tencent minute endpoint, never a proxy host or protected daily endpoint.
    prior=read(BROAD/'network-halted.json')
    if prior:
        state=read(root/'network.json',{})
        state['tencent']=dict(blocked_until=(datetime.fromisoformat(prior['at'])+timedelta(hours=24)).isoformat(),reason='inherited Tencent access protection',last_probe_day=None)
        save(root/'network.json',state)
    # Seed immutable raw responses, not unaudited days labelled as qualified.
    for path in (BROAD/'raw').glob('*-minute.json'):
        raw=read(path);code=path.name.split('-')[0];stamp=raw['retrieved_at'][:10]
        dst=root/'raw/tencent'/code/(stamp+'.json')
        if not dst.exists():save(dst,dict(raw,seeded_from=str(path.relative_to(BASE))))
    initial=read(root/'sina-initial-probe.json')
    if initial:
        body=initial['body'];dst=root/'raw/sina'/initial['code']/(asof.date().isoformat()+'.json')
        if not dst.exists():save(dst,dict(body=body,url=initial['url'],retrieved_at=asof.isoformat(),sha256=hashlib.sha256(body.encode()).hexdigest(),seeded_probe=True))
    return protocol

class ProviderBlocked(RuntimeError):pass
class BudgetReached(RuntimeError):pass

class Collector:
    def __init__(self,root,protocol,asof,daily_limit,minute_limit):
        self.root,self.protocol,self.asof=root,protocol,asof
        self.network=read(root/'network.json',{});self.queue=read(root/'queue.json',{})
        self.limits={'sina':daily_limit,'tencent':minute_limit};self.counts=collections.Counter();self.errors=[];self.last=0
    def blocked(self,provider):
        state=self.network.get(provider,{})
        return bool(state.get('blocked_until') and self.asof<datetime.fromisoformat(state['blocked_until']))
    def fetch(self,provider,code):
        day=self.asof.date().isoformat();path=self.root/'raw'/provider/code/(day+'.json')
        if path.exists():return read(path)['body']
        if self.blocked(provider):raise ProviderBlocked(provider+' in cooldown')
        if self.counts[provider]>=self.limits[provider]:raise BudgetReached(provider)
        if provider=='sina':
            # Full history bootstraps MA20. Later responses are incremental tails.
            length=40 if list(path.parent.glob('*.json')) else 240
            url='https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?'+urlencode(dict(symbol=code,scale=240,ma='no',datalen=length))
        else:url='https://web.ifzq.gtimg.cn/appstock/app/day/query?'+urlencode(dict(code=code))
        state=self.network.get(provider,{})
        probing=bool(state.get('blocked_until'))
        if probing and state.get('last_probe_day')==day:raise ProviderBlocked(provider+' recovery probe already used today')
        if probing:
            state['last_probe_day']=day;self.network[provider]=state;save(self.root/'network.json',self.network)
        time.sleep(max(0,1.25-(time.monotonic()-self.last)));self.last=time.monotonic();self.counts[provider]+=1
        try:body=get(url)
        except HTTPError as ex:
            text=ex.read().decode(errors='replace')
            if ex.code in (403,429,501) or 'waf.tencent.com' in text.lower():
                self.network[provider]=dict(blocked_until=(self.asof+timedelta(hours=24)).isoformat(),reason=f'HTTP {ex.code} access protection',last_probe_day=day,response_sha256=hashlib.sha256(text.encode()).hexdigest())
                save(self.root/'network.json',self.network)
                raise ProviderBlocked(provider+' protection; stop all requests to this provider') from ex
            raise
        if 'waf.tencent.com' in body.lower():
            self.network[provider]=dict(blocked_until=(self.asof+timedelta(hours=24)).isoformat(),reason='provider protection HTML',last_probe_day=day)
            save(self.root/'network.json',self.network);raise ProviderBlocked(provider+' protection HTML')
        if probing:
            self.network[provider]=dict(recovered_at=self.asof.isoformat(),last_probe_day=day)
            save(self.root/'network.json',self.network)
        save(path,dict(url=url,body=body,retrieved_at=self.asof.isoformat(),sha256=hashlib.sha256(body.encode()).hexdigest()))
        return body
    def order(self,provider):
        order={s['code']:i for i,s in enumerate(self.protocol['pool'])}
        def key(stock):
            code=stock['code']
            # Pair freshly cached daily data with minutes first. This uses only
            # data availability, never candidate counts, returns or MA20 results.
            fresh_daily=provider=='tencent' and (self.root/'raw/sina'/code/(self.asof.date().isoformat()+'.json')).exists()
            return (not fresh_daily if provider=='tencent' else False,self.queue.get(provider,{}).get(code,''),order[code])
        return sorted(self.protocol['pool'],key=key)
    def mark(self,provider,code):
        self.queue.setdefault(provider,{})[code]=self.asof.isoformat();save(self.root/'queue.json',self.queue)

def daily_archive(root,code,asof):
    combined={}
    for path in sorted((root/'raw/sina'/code).glob('*.json')):
        captured=read(path);rows=finalized(parse_sina(captured['body']),datetime.fromisoformat(captured['retrieved_at']))
        combined.update(rows)
    return finalized(combined,asof)

def reference_daily(code):
    path=BROAD/'normalized'/f'{code}.json'
    if path.exists():return read(path)['daily']
    path=BASE/'docs/buy-v1/free-expanded/raw'/f'{code}-daily.json'
    if path.exists():
        rows=json.loads(read(path)['body'])['data'][code]['day']
        return {r[0]:dict(open=r[1],close=r[2],high=r[3],low=r[4],raw_volume=r[5]) for r in rows}
    return {}

def calibrate(client):
    path=client.root/'source-calibration.json'
    old=read(path)
    if old and old['passed']:return old
    checks={}
    for code in ('sh601088','sz000815','sz300033'):
        client.fetch('sina',code)
        rows=daily_archive(client.root,code,client.asof);check=crosscheck_daily(rows,reference_daily(code))
        checks[code]=check
        if not check['checked'] or check['errors']:
            result=dict(passed=False,at=client.asof.isoformat(),checks=checks);save(path,result)
            raise ValueError('Sina calibration differs from frozen Tencent reference: '+code)
    result=dict(passed=True,at=client.asof.isoformat(),checks=checks,unit='shares',price_adjustment='none',volume_precision='<=50-share reference difference')
    save(path,result);return result

def collect(root,protocol,asof,daily_limit,minute_limit):
    client=Collector(root,protocol,asof,daily_limit,minute_limit)
    if asof.weekday()>4 or asof.strftime('%H:%M')<'16:00':
        return dict(skipped='outside after-close collection window',requests={})
    try:
        calibrate(client)
        client.fetch('sina','sh000001') # observed session calendar, not a guessed weekday calendar
        for stock in client.order('sina'):
            code=stock['code']
            if client.queue.get('sina',{}).get(code,'')[:10]==asof.date().isoformat():continue
            try:
                client.fetch('sina',code);daily_archive(root,code,asof)
                client.mark('sina',code)
            except BudgetReached:break
            except ProviderBlocked:raise
            except Exception as ex:
                client.mark('sina',code);client.errors.append(dict(provider='sina',code=code,error=str(ex)))
                if len(client.errors)>=3:break
    except (ProviderBlocked,BudgetReached,ValueError) as ex:client.errors.append(dict(provider='sina',error=str(ex)))
    calendar=daily_archive(root,'sh000001',asof)
    if asof.date().isoformat() not in calendar:
        result=dict(at=asof.isoformat(),requests=dict(client.counts),errors=client.errors,
                    network=client.network,tencent_skipped='No observed finalized session for today; no minute requests')
        save(root/'collection-latest.json',result);return result
    for stock in client.order('tencent'):
        code=stock['code']
        if client.queue.get('tencent',{}).get(code,'')[:10]==asof.date().isoformat():continue
        try:
            client.fetch('tencent',code);client.mark('tencent',code)
        except BudgetReached:break
        except ProviderBlocked as ex:
            client.errors.append(dict(provider='tencent',error=str(ex)));break
        except Exception as ex:
            client.mark('tencent',code);client.errors.append(dict(provider='tencent',code=code,error=str(ex)))
            if len([e for e in client.errors if e['provider']=='tencent'])>=3:break
    result=dict(at=asof.isoformat(),requests=dict(client.counts),errors=client.errors,network=client.network)
    save(root/'collection-latest.json',result);return result

def evaluate_archive(root,protocol,asof):
    calibrated=read(root/'source-calibration.json',{}).get('passed',False)
    calendar=sorted(daily_archive(root,'sh000001',asof))
    expected_new_dates=[d for d in calendar if d>=protocol['validation_start']]
    diagnostics=[];prospective=[];coverage=[];ready=0;archived_days=0
    for stock in protocol['pool']:
        code,name=stock['code'],stock['name'];daily=daily_archive(root,code,asof)
        if len(daily)>=20:ready+=1
        check=crosscheck_daily(daily,reference_daily(code)) if daily else dict(checked=[],errors=[])
        save(root/'daily-checks'/f'{code}.json',check)
        # Actual 20-bar readiness for a signal requires ma20_gate; a count alone is only inventory.
        if not calibrated or not daily or check['errors']:
            status='daily_not_ready' if not daily else 'daily_source_conflict' if check['errors'] else 'source_not_calibrated'
            for day in expected_new_dates or [None]:
                coverage.append(dict(code=code,date=day,status=status,cohort='prospective' if day else 'inventory'))
            continue
        qualified={}
        for rawpath in sorted((root/'raw/tencent'/code).glob('*.json')):
            try:
                captured=read(rawpath);payload=json.loads(captured['body'])
                clean,audits=audit(code,name,payload,audit_daily(daily))
                for c in audits:
                    if c['date']>asof.date().isoformat():continue
                    # Keep full audit details; a failed refresh never erases a previously qualified day.
                    save(root/'minute-checks'/code/(c['date']+'-'+rawpath.stem+'.json'),dict(c,daily_source='sina',daily_volume_precision='rounded whole hand'))
                for day,minute in clean.items():
                    if day in daily and day<=asof.date().isoformat():qualified[day]=minute
            except Exception as ex:
                coverage.append(dict(code=code,status='raw_minute_error',path=str(rawpath.relative_to(root)),error=str(ex)))
        for day,minute in sorted(qualified.items()):
            save(root/'archive/minute'/code/(day+'.json'),minute);archived_days+=1
            nextdays=[d for d in calendar if d>day];nxt=nextdays[0] if nextdays else None
            result=score_day(code,name,day,minute,daily,calendar,qualified.get(nxt))
            row=dict(code=code,date=day,status='qualified',cohort='prospective' if day>=protocol['validation_start'] else 'diagnostic',gate=result['gate']['passed'],source='tencent',daily_source='sina')
            coverage.append(row)
            target=prospective if row['cohort']=='prospective' else diagnostics
            target.extend(result['baseline'])
        for day in expected_new_dates:
            if day not in qualified:coverage.append(dict(code=code,date=day,status='missing_or_unqualified_minutes',cohort='prospective'))
    newdates=sorted({c['date'] for c in coverage if c.get('cohort')=='prospective' and c['status']=='qualified'})
    coverage_by_date={day:dict(collections.Counter(c['status'] for c in coverage if c.get('cohort')=='prospective' and c.get('date')==day)) for day in expected_new_dates}
    primary=compare(prospective);diagnostic=compare(diagnostics)
    status=dict(prospective_dates=len(newdates),E_completed=primary['E_comparable']['samples'],E_MA20_completed=primary['E_MA20']['samples'])
    enough=status['prospective_dates']>=30 and min(status['E_completed'],status['E_MA20_completed'])>=100
    result=dict(created_at=asof.isoformat(),validation_start=protocol['validation_start'],config=CONFIG,pool_size=len(protocol['pool']),
        source_calibrated=calibrated,daily_inventory_20_or_more=ready,qualified_stock_days=archived_days,
        prospective_coverage_by_date=coverage_by_date,
        prospective_dates=newdates,primary=primary,diagnostic=diagnostic,coverage=coverage,
        prospective_events=prospective,diagnostic_events=diagnostics,minimum_sample_status=status,minimum_samples_reached=enough,
        strategy_60pct_proven=False,notifications_sent=0,frozen_hashes_unchanged=protocol['frozen_code_sha256']==code_hashes(),
        source_notes=['Minutes Tencent only; Sina supplies unadjusted daily OHLC and observed session calendar.',
                      'Sina shares differ from Tencent rounded whole-hand totals by at most 50 in source calibration; original shares retained.',
                      'Old dates never enter the prospective denominator. MA20 unknown is not rejection or a loss.',
                      'All profits are next-minute-close entry proxies. Historical execution status is unverified.',
                      'No real-time buy notifications, production database, app configuration or production process changes.'])
    assert result['frozen_hashes_unchanged']
    save(root/'evaluation.json',result)
    fields=['code','name','date','time','entry_time','entry_price','next_date','next_close','net_pct','status','execution','ma20_passed','adverse_pct','adverse_complete']
    for name,events in [('prospective-signals',prospective),('diagnostic-signals',diagnostics),('missed-winners',primary['missed_winners'])]:
        with (root/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(events)
    rows=[]
    def fmt(v,suffix=''):return '不可计算' if v is None else f'{v:.3f}{suffix}'
    for group,label in [('E_all','E全部（含MA20资料不足）'),('E_comparable','E同口径可比较'),('E_MA20','E＋前一日收盘≥MA20')]:
        s=primary[group];rows.append([label,s['signals'],s['samples'],s['wins'],fmt(s['win_rate']*100 if s['win_rate'] is not None else None,'%'),fmt(s['mean_net_pct'],'%'),fmt(s['worst_sampled_adverse_pct'],'%'),s['pending']])
    def table(headers,body):return '<table><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in body)+'</table>'
    text=f'<h1>E与E＋MA20：新日期独立研究</h1><p>验证起始：{protocol["validation_start"]}；已有35笔和旧日期仅作诊断，不并入下表。</p><p>固定1000只，不按收益换股；日线20根以上库存{ready}只，量价审计合格股票日{archived_days}个；新日期{len(newdates)}个。库存20根不代表每个日期MA20均已齐备。</p>'
    text+=table(['组别','信号','完成次日','盈利','盈利率','平均净收益','最差采样不利波动','待次日'],rows)
    text+=f'<p>因MA20不通过而漏掉的已完成盈利信号{len(primary["missed_winners"])}个，过滤掉的亏损{len(primary["avoided_losers"])}个；MA20资料不足单独列出，不算过滤成功。信号保留率：{fmt(primary["known_gate_signal_retention"]*100 if primary["known_gate_signal_retention"] is not None else None,"%")}。</p><p>主成本：往返0.10%，买卖各0.10%滑点。样本成熟目标：≥30个新交易日期、两组各≥100个已完成结构；达到数量不等于证明真实胜率≥60%。缺数据不记零信号，未完成不计亏损。</p><p>当前报告是价格代理回放。正式监控未修改，买点通知未启用。<a href="prospective-signals.csv">新日期信号</a> · <a href="missed-winners.csv">漏掉盈利信号</a> · <a href="evaluation.json">完整统计</a></p>'
    text+='<h2>新日期数据覆盖</h2>'+table(['交易日','合格股票日／固定1000只','缺失或未通过分钟审计','日线未齐备或冲突'],
        [[d,f'{c.get("qualified",0)}/1000',c.get('missing_or_unqualified_minutes',0),sum(n for k,n in c.items() if k not in ('qualified','missing_or_unqualified_minutes'))] for d,c in coverage_by_date.items()])
    (root/'report.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;line-height:1.8;margin:32px;max-width:1200px}td,th{border:1px solid #ccd;padding:9px}table{border-collapse:collapse}th{background:#eef3f8}</style>'+text)
    save(root/'status.json',dict(at=asof.isoformat(),validation_start=protocol['validation_start'],source_calibrated=calibrated,daily_ready=ready,
        prospective_dates=len(newdates),completed_E=primary['E_comparable']['samples'],completed_filtered=primary['E_MA20']['samples'],
        missed_winners=len(primary['missed_winners']),ma20_unknown_signals=primary['ma20_unknown']['signals'],minimum_samples_reached=enough,
        network=read(root/'network.json',{}),buy_notifications_sent=0))
    return result

@contextlib.contextmanager
def locked(root):
    path=root/'run.lock';root.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        try:owner=int(path.read_text());os.kill(owner,0)
        except ProcessLookupError:
            path.unlink();fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        else:raise RuntimeError('Study collection already locked; do not start overlapping jobs')
    try:os.write(fd,str(os.getpid()).encode());os.close(fd);yield
    finally:path.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--collect',action='store_true');p.add_argument('--daily-budget',type=int,default=40);p.add_argument('--minute-budget',type=int,default=60);args=p.parse_args()
    if not 0<=args.daily_budget<=40 or not 0<=args.minute_budget<=60:raise ValueError('Do not exceed frozen collection limits')
    with locked(ROOT):
        asof=now_cn();protocol=init(ROOT,asof)
        if args.collect:collect(ROOT,protocol,asof,args.daily_budget,args.minute_budget)
        r=evaluate_archive(ROOT,protocol,asof)
        print(json.dumps(read(ROOT/'status.json'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
