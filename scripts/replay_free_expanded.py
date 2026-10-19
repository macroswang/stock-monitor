"""Independent, cached Tencent data audit and frozen buy-rule replay. No App/Store imports."""
import collections, csv, hashlib, html, json, math, sys
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.provider import get, now_cn
from core.buy_supplement import evaluate, VARIANTS, TIMELINE
from core.buy_confirmation import evaluate as confirmation
from core.buy_research import outcomes
from scripts.evaluate_buy_net_profit import net_return, metrics

ROOT = Path('docs/buy-v1/free-expanded')
# Frozen before any outcomes: prior self-selected/recent pool plus the five app watches.
POOL = [('sh603002','宏昌电子'),('sz000815','美利云'),('sz300140','节能环境'),
        ('sh600392','盛和资源'),('sz000981','山子高科'),('sh603938','三孚股份'),
        ('sz300672','国科微'),('sh600580','卧龙电驱'),('sh600560','金自天正'),
        ('sh605358','立昂微'),('sh601929','吉视传媒'),('sh603366','日出东方'),
        ('sh600668','尖峰集团'),('sz002882','金龙羽'),('sz300033','同花顺'),
        ('sz300869','康泰医学')]
GROUPS = VARIANTS + ('ES','EW')
FILES = ['core/provider.py','core/rules.py','core/validated_engine.py','core/buy_rules.py',
         'core/buy_compare.py','core/buy_supplement.py','core/buy_confirmation.py']

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False))

def hashes():
    return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in FILES}

def fetch(code, kind, url, encoding='utf-8'):
    path = ROOT/'raw'/f'{code}-{kind}.json'
    if path.exists():
        return json.loads(path.read_text())['body']
    body = get(url, encoding)
    save(path, dict(retrieved_at=now_cn().isoformat(),url=url,body=body,
                    sha256=hashlib.sha256(body.encode()).hexdigest()))
    return body

def session(t):
    return '0930' <= t <= '1130' or '1300' <= t <= '1500'

def audit(code, name, raw, daily):
    clean={}; checks=[]
    expected={'0930','1300'} | {t.replace(':','') for t in TIMELINE}
    for day in raw['data'][code]['data']:
        ds=day['date']; dt=f'{ds[:4]}-{ds[4:6]}-{ds[6:]}'
        rows=[line.split() for line in day['data']]
        labels=[r[0] for r in rows]
        inside=[r for r in rows if session(r[0])]
        outside=[r[0] for r in rows if not session(r[0])]
        check=dict(code=code,name=name,date=dt,raw_rows=len(rows),removed_times=outside,
                   missing=sorted(expected-set(labels)),errors=[])
        def fail(message): check['errors'].append(message)
        if labels != sorted(set(labels)):fail('duplicate_or_unordered_time')
        if any(len(r)<4 for r in rows):fail('missing_columns')
        if check['missing']:fail('missing_session_minutes')
        dr=daily.get(dt)
        if not dr:fail('missing_daily_reference')
        if not inside or inside[0][0]!='0930' or inside[-1][0]!='1500':fail('missing_boundaries')
        if check['errors']:
            checks.append(check);continue
        # Daily raw volume and minute cumulative volume are independently reconciled.
        last=inside[-1]; cum=D(last[2]); amount=D(last[3])
        lo,hi=D(dr['low']),D(dr['high'])
        factors=[m for m in (1,100) if cum>0 and lo-D('.02')<=amount/(cum*m)<=hi+D('.02')]
        if factors != [100]:fail('unresolved_volume_unit')
        factor=factors[0] if len(factors)==1 else 100
        check.update(volume_multiplier=factor,minute_1500_shares=str(cum*factor),
                     daily_shares=str(D(dr['raw_volume'])*100),
                     volume_difference_shares=str(cum*factor-D(dr['raw_volume'])*100),
                     close_difference=str(D(last[1])-D(dr['close'])),
                     cumulative_amount_yuan=str(amount),vwap=str(amount/(cum*factor)))
        if cum*factor != D(dr['raw_volume'])*100:fail('daily_volume_mismatch')
        if D(last[1]) != D(dr['close']):fail('daily_close_mismatch')
        previous=D(0); cash_before=D(0); bars=[]; bad_price=0; active=0
        for t,p,v,a,*_ in inside:
            total,cash,price=D(v),D(a),D(p)
            dv,da=(total-previous)*factor,cash-cash_before
            if total!=int(total) or dv<0 or da<0:fail('nonintegral_or_decreasing_cumulative')
            if not lo-D('.01')<=price<=hi+D('.01'):fail('close_outside_daily_range')
            if dv>0:
                active+=1
                # Hands are integer-rounded, allow two hands of endpoint rounding.
                if not (lo-D('.01'))*max(D(0),dv-200)<=da<=(hi+D('.01'))*(dv+200):bad_price+=1
            average=cash/(total*factor) if total>0 else None
            if average is None or not lo-D('.02')<=average<=hi+D('.02'):fail('vwap_outside_daily_range')
            bars.append(dict(time=t[:2]+':'+t[2:],close=p,volume=int(dv),
                             average=str(average) if average else None,complete=True))
            previous,cash_before=total,cash
        check.update(active_minutes=active,incremental_amount_range_failures=bad_price,
                     normalized_rows=len(bars),auction_0930_shares=bars[0]['volume'])
        if bad_price:fail('incremental_amount_volume_mismatch')
        if sum(b['volume'] for b in bars)!=int(cum*factor):fail('volume_difference_not_telescoping')
        if not check['errors']:
            clean[dt]=dict(date=dt,bars=bars,previous_close=day.get('prec'),source='tencent',
                          volume_unit='shares',multiplier=factor,rule_compatible=True,
                          label_semantics='original_vendor_labels_no_shift')
        check['status']='passed' if not check['errors'] else 'excluded'
        checks.append(check)
    return clean,checks

def wilson(w,n):
    if not n:return None
    z=1.95996398454;p=w/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [mid-half,mid+half]

def run():
    ROOT.mkdir(parents=True,exist_ok=True)
    freeze=ROOT/'frozen-pool.json'
    if not freeze.exists():save(freeze,dict(created_at=now_cn().isoformat(),pool=POOL,selection='先固定名单，再取数与回放；原自选/最近列表，不按涨幅筛选',rule_hashes=hashes()))
    assert json.loads(freeze.read_text())['pool']==[list(x) for x in POOL]
    before=hashes(); asof=now_cn().isoformat(); today=asof[:10]
    assert json.loads(freeze.read_text())['rule_hashes']==before,'Research rules differ from frozen acquisition manifest'
    all_minutes={};all_daily={};checks=[];errors=[];quotes={}
    for code,name in POOL:
        try:
            raw=json.loads(fetch(code,'minute','https://web.ifzq.gtimg.cn/appstock/app/day/query?'+urlencode({'code':code})))
            rawd=json.loads(fetch(code,'daily','https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':f'{code},day,2026-10-09,{today},2000,'})))
            daily={r[0]:dict(date=r[0],open=r[1],close=r[2],high=r[3],low=r[4],raw_volume=r[5]) for r in rawd['data'][code]['day']}
            minutes,rows=audit(code,name,raw,daily);checks.extend(rows)
            qt=fetch(code,'quote','https://qt.gtimg.cn/q='+code,'gb18030')
            fields=qt.split('="',1)[1].rsplit('"',1)[0].split('~')
            assert fields[2]==code[2:]
            quotes[code]=dict(date=fields[30][:4]+'-'+fields[30][4:6]+'-'+fields[30][6:8],limit_up=fields[47],name=fields[1])
            for dt,data in minutes.items():
                if quotes[code]['date']==dt:data['limit_up']=quotes[code]['limit_up']
            all_minutes[code]=minutes;all_daily[code]=daily
            save(ROOT/'normalized'/f'{code}.json',minutes)
            print(code,name,'passed',len(minutes),'excluded',len(rows)-len(minutes),flush=True)
        except Exception as ex:
            errors.append(dict(code=code,error=str(ex)));print(code,'ERROR',str(ex),flush=True)
    save(ROOT/'quality.json',dict(as_of=asof,checks=checks,fetch_errors=errors))
    signals={v:[] for v in GROUPS};states={v:collections.Counter() for v in GROUPS};cooldowns=collections.Counter()
    for code,name in POOL:
        minutes=all_minutes.get(code,{})
        for dt,data in sorted(minutes.items()):
            # Historical close results require the actual next weekday's daily and minute records.
            following=date.fromisoformat(dt)+timedelta(days=1)
            while following.weekday()>4:following+=timedelta(days=1)
            following=following.isoformat()
            nd=all_daily[code].get(following) if following<=today else None
            for group in GROUPS:
                engine=confirmation if group in ('ES','EW') else evaluate
                result=engine(data,group,as_of='15:00')
                assert not result['error'],result['error']
                states[group].update(c['status'] for c in result['candidates'])
                cooldowns[group]+=len(result['cooldown_suppressed'])
                seen=set()
                for event in result['signals']:
                    identity=dt+'|'+code+'|'+event['key'];assert identity not in seen;seen.add(identity)
                    outcome=outcomes(event,data,minutes.get(following),nd,None)
                    entry=outcome['entry_price'];exit_price=float(nd['close']) if nd else None
                    scores={f'{fee:.2f}/{slip:.2f}':net_return(entry,exit_price,fee,slip)
                            for fee in (.10,.20) for slip in (.05,.10,.20)}
                    signals[group].append(dict(group=group,code=code,name=name,date=dt,identity=identity,
                        time=event['time'],entry_time=outcome['entry_time'],entry_price=entry,
                        next_date=following,next_close=exit_price,net_pct=scores['0.10/0.10'],
                        cost_scenarios=scores,execution=outcome['execution'],
                        observed_adverse_pct=outcome['observed_adverse_pct'],adverse_complete=outcome['adverse_complete'],
                        evidence=event['evidence'],key=event['key']))
    summary={}
    for group,events in signals.items():
        completed=[e for e in events if e['net_pct'] is not None]
        m=metrics([e['net_pct'] for e in completed]);m['wilson95']=wilson(m['wins'],m['samples'])
        risks=[e['observed_adverse_pct'] for e in completed if e['adverse_complete']]
        summary[group]=dict(signals=len(events),pending=sum(e['next_close'] is None for e in events),
            price_proxy=m,execution_verified_proxy=metrics([e['net_pct'] for e in completed if e['execution']=='close_proxy']),
            uncertain_completed=sum(e['execution']!='close_proxy' for e in completed),
            complete_risk_samples=len(risks),worst_sampled_adverse_pct=min(risks) if risks else None,
            cooldown_suppressed=cooldowns[group],candidate_states=dict(states[group]),
            sensitivities={key:metrics([e['cost_scenarios'][key] for e in completed]) for key in ('0.10/0.05','0.10/0.10','0.10/0.20','0.20/0.05','0.20/0.10','0.20/0.20')})
    assert before==hashes(),'Frozen core changed during research'
    report=dict(as_of=asof,pool=POOL,stock_days=len([x for x in checks if x.get('status')=='passed']),
        quality_status=dict(collections.Counter(x.get('status','excluded') for x in checks)),fetch_errors=errors,
        dates=sorted({d for mm in all_minutes.values() for d in mm}),summary=summary,signals=signals,
        unique_completed_structures=len({e['identity'] for es in signals.values() for e in es if e['net_pct'] is not None}),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'raw').glob('*.json'))},
        hashes_before=before,hashes_after=hashes(),notifications_sent=0,
        caveats=['全部价格为下一分钟收盘代理，不是实际成交；历史涨停状态未核实样本仅列价格代理盈利率，不冒充已验证可成交胜率',
                 '主情景假设往返总费用0.10%，买卖各0.10%滑点；零收益不算盈利；无次日结果不计入分母',
                 '仅5个相邻交易日，新增股票仍是旧自选/最近池；不是全市场或跨行情独立验证',
                 '不同组相同结构重复出现，不把跨组记录数当独立样本；同日股票收益相关，Wilson区间仅为样本量参考',
                 '按原始时间标签不平移；09:30包含开盘累计量，仅作差分基线，不进入09:31开始的买点判断；13:00为午间累计基线；15:00后排除',
                 '历史静态数据能核对标签顺序及量额，不能独立证明供应商分钟边界在实时盘中无延迟；缺少第三方逐笔对照',
                 '完整不利波动仅为分钟收盘采样，不是分钟内最低价或账户最大回撤',
                 '未修改正式行情源、自选池、通知配置、规则参数或正式数据库'])
    save(ROOT/'evaluation.json',report)
    fields=['group','name','code','date','time','entry_time','entry_price','next_date','next_close','net_pct','execution','observed_adverse_pct','adverse_complete']
    with (ROOT/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for es in signals.values():w.writerows(es)
    text=['# 免费扩样：腾讯分钟核验与固定买点规则回放','',f'分析截止：{asof}；原始采集时间见raw文件；{len(POOL)}只，{report["stock_days"]}个通过核验的股票交易日。',
          '区间：'+ '、'.join(report['dates'])+'。主情景：往返总费用0.10%，买卖各0.10%滑点。',
          '结论：只有1个去重后的已完成次日结构，国科微亏损；新增吉视传媒为10月19日信号，尚无次日结果。当前不能认定达到60%。',
          '所有已完成历史结构缺少历史涨停状态核实，严格执行状态已核验样本数为0；下表是可计算价格结果的代理统计。','',
          '|组别|信号|已完成次日价格|盈利|价格代理盈利率|平均净收益|待次日|',
          '|---|---:|---:|---:|---:|---:|---:|']
    for group,s in summary.items():
        m=s['price_proxy'];rate=f'{m["win_rate"]*100:.2f}%' if m['win_rate'] is not None else '不可计算'
        mean=f'{m["mean_net_pct"]:+.3f}%' if m['mean_net_pct'] is not None else '—'
        text.append(f'|{group}|{s["signals"]}|{m["samples"]}|{m["wins"]}|{rate}|{mean}|{s["pending"]}|')
    text+=['','规则说明：V1原始规则；A均价微小波动容差；B低价股突破门槛；AB两项合并；R破位后收复；E远离均价继续转强；RE两项补充合并；ES增加结构高点突破确认；EW增加下一分钟站稳确认。R/E/RE基于V1，ES/EW只过滤E补充信号，均保留原始V1信号。',
           '','## 数据核验',
           f'- {len(checks)}个股票交易日；截至15:00累计量×100与日K股数对账，15:00收盘价与未复权日K收盘价对账。',
           f'- 排除{sum(len(c["removed_times"]) for c in checks)}条非交易时段记录；09:30和13:00不作为规则确认柱，保留用于累计量边界检查。',
           '- 每分钟量=(当前累计量−上一标签累计量)×100；分时均价=当前累计成交额÷当前累计股数；未使用“分钟收盘价×分钟量”代替真实成交额。',
           '- 累计量额非负递增、无重复与缺失标签、分钟价和量额比处于当日日K价格范围内；量额增量范围允许整数手端点舍入。',
           '','## 股票名单','、'.join(n+'（'+c+'）' for c,n in POOL),'','## 去重结构与结果',
           '|股票|日期|确认时间及组别|下一分钟入场代理|次日收盘|主情景净收益|','|---|---|---|---:|---:|---:|']
    unique={}
    for group,es in signals.items():
        for e in es:
            unique.setdefault(e['identity'],[]).append(e)
    for es in unique.values():
        e=es[0];net=f'{e["net_pct"]:+.4f}%' if e['net_pct'] is not None else '待次日'
        groups='、'.join(x['group']+' '+x['time'] for x in es)
        text.append(f'|{e["name"]}|{e["date"]}|{groups}|{e["entry_price"]}|{e["next_close"] or "—"}|{net}|')
    text+=['','国科微该结构分钟收盘采样最大不利波动为−4.5561%；费用/滑点六组情景下净收益为−3.4107%至−3.8003%，均亏损。只有1笔，不能据此估计总体胜率或判断某组最高。']
    text+=['','## 限制']+['- '+x for x in report['caveats']]
    text+=['','## 数据核验详情','',json.dumps(dict(status=report['quality_status'],errors=errors),ensure_ascii=False)]
    (ROOT/'analysis.md').write_text('\n'.join(text))
    body='<h1>免费扩样：分钟数据核验与次日净盈利评估</h1><pre>'+html.escape('\n'.join(text))+'</pre><h2>逐笔信号与完整统计</h2><pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    (ROOT/'analysis.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:15px system-ui;margin:32px;line-height:1.7}pre{white-space:pre-wrap}</style>'+body)
    print(json.dumps(dict(quality=report['quality_status'],summary=summary,unique_completed=report['unique_completed_structures']),ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':run()
