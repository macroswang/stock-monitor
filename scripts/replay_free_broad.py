"""Frozen broad A-share sample; Tencent-only cached acquisition and offline replay.

Uses only pure research engines. No production database, App, Store, or notification imports.
"""
import collections, csv, hashlib, html, json, random, re, sys, time
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.provider import get, now_cn
from core.buy_supplement import evaluate, VARIANTS
from core.buy_confirmation import evaluate as confirmation
from core.buy_research import outcomes
from scripts.evaluate_buy_net_profit import metrics, net_return
from scripts.replay_free_expanded import audit, save, hashes, wilson, POOL as OLD_POOL

ROOT=Path('docs/buy-v1/free-broad-1000')
SEED='stock-monitor-buy-free-broad-20261019-v1'
QUOTAS={'sh_main':350,'sz_main':350,'chinext':300}
GROUPS=VARIANTS+('ES','EW')
GAP=.25 # Global sequential requests: at most 4 starts/sec, no concurrency.
last_request=0

class ProtectionStop(RuntimeError):
    pass

def protection_response(status, body):
    return status in (403,429) or 'waf.tencent.com' in body.lower()

def cached(path,url,encoding='utf-8'):
    global last_request
    if path.exists():return json.loads(path.read_text())['body']
    halted=ROOT/'network-halted.json'
    if halted.exists():raise ProtectionStop('Network acquisition halted; offline cached analysis only')
    time.sleep(max(0,GAP-(time.monotonic()-last_request)))
    last_request=time.monotonic()
    try:
        body=get(url,encoding)
    except HTTPError as ex:
        message=ex.read().decode('utf-8',errors='replace')
        if protection_response(ex.code,message):
            save(halted,dict(at=now_cn().isoformat(),http_status=ex.code,reason='Provider access protection; do not retry or switch hosts',
                             response_sha256=hashlib.sha256(message.encode()).hexdigest()))
            raise ProtectionStop('Tencent access protection; stopped all network acquisition') from ex
        raise
    save(path,dict(retrieved_at=now_cn().isoformat(),url=url,body=body,
                   sha256=hashlib.sha256(body.encode()).hexdigest()))
    return body

def board(code):
    if code.startswith(('sz300','sz301')):return 'chinext'
    return 'sh_main' if code.startswith('sh') else 'sz_main'

def rank(code):return hashlib.sha256((SEED+'|'+code).encode()).hexdigest()

def freeze_pool():
    path=ROOT/'frozen-pool.json'
    if path.exists():
        frozen=json.loads(path.read_text())
        assert frozen['rule_hashes']==hashes(),'Rule version changed since sample freeze'
        return frozen
    universe={};failures=[]
    prefixes=['sh600','sh601','sh603','sh605','sz000','sz001','sz002','sz003','sz300','sz301']
    for prefix in prefixes:
        for start in range(0,1000,100):
            codes=[prefix+f'{i:03}' for i in range(start,start+100)]
            try:
                text=cached(ROOT/'universe'/f'{prefix}-{start:03}.json','https://qt.gtimg.cn/q='+','.join(codes),'gb18030')
                for code,payload in re.findall(r'v_([a-z]{2}\d{6})="([^"]*)"',text):
                    f=payload.split('~')
                    if code not in codes or len(f)<49 or f[2]!=code[2:]:continue
                    # Define the sampling population as currently trading, with valid limit metadata.
                    # Delisted residual quotes have volume=0 and limit_up=-1; do not call them listed stocks.
                    if D(f[3])<=0 or D(f[6])<=0 or D(f[47])<=0:continue
                    universe[code]=dict(code=code,name=f[1],board=board(code),rank=rank(code),
                        quote_date=f[30][:4]+'-'+f[30][4:6]+'-'+f[30][6:8],limit_up=f[47],
                        quote_timestamp=f[30])
            except ProtectionStop:
                raise
            except Exception as ex:
                failures.append(dict(prefix=prefix,start=start,error=str(ex)))
        print('UNIVERSE',prefix,'eligible',len(universe),flush=True)
    save(ROOT/'universe.json',dict(created_at=now_cn().isoformat(),stocks=universe,failures=failures))
    if failures:raise RuntimeError('Universe incomplete: resolve failed batches before sampling')
    pool=[]
    for b,n in QUOTAS.items():
        rows=sorted((x for x in universe.values() if x['board']==b),key=lambda x:x['rank'])
        if len(rows)<n:raise RuntimeError(f'Insufficient {b}: {len(rows)} < {n}')
        for i,row in enumerate(rows[:n]):
            # Preassigned disjoint stock halves; no parameter choice based on either half.
            pool.append(dict(row,half='A' if i%2==0 else 'B',old_pool=row['code'] in dict(OLD_POOL)))
    frozen=dict(created_at=now_cn().isoformat(),seed=SEED,quotas=QUOTAS,pool=pool,
        population_counts=dict(collections.Counter(x['board'] for x in universe.values())),
        eligible_population=len(universe),rule_hashes=hashes(),planned_requests_per_stock=2,
        selection='只按代码哈希固定分层抽样；不按价格、涨幅、成交量大小、是否出现信号或回放收益排序。总体限于采样当日有成交且涨停元数据有效的沪深主板/创业板A股；未包含科创板和北交所。')
    save(path,frozen)
    return frozen

def acquire(frozen,offline=False):
    errors=[]; checks=[]; passed=0;today=frozen['created_at'][:10]
    for i,stock in enumerate(frozen['pool'],1):
        code,name=stock['code'],stock['name']
        if offline and not all((ROOT/'raw'/f'{code}-{kind}.json').exists() for kind in ('minute','daily')):continue
        try:
            minute=cached(ROOT/'raw'/f'{code}-minute.json','https://web.ifzq.gtimg.cn/appstock/app/day/query?'+urlencode({'code':code}))
            daily=cached(ROOT/'raw'/f'{code}-daily.json','https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':f'{code},day,2026-10-09,{today},2000,'}))
            raw=json.loads(minute);rows=json.loads(daily)['data'][code]['day']
            day_map={r[0]:dict(date=r[0],open=r[1],close=r[2],high=r[3],low=r[4],raw_volume=r[5]) for r in rows}
            clean,audits=audit(code,name,raw,day_map)
            for dt,data in clean.items():
                if dt==stock['quote_date']:data['limit_up']=stock['limit_up']
            save(ROOT/'normalized'/f'{code}.json',dict(minute=clean,daily=day_map))
            checks.extend(audits);passed+=len(clean)
        except ProtectionStop as ex:
            errors.append(dict(code=code,name=name,error=str(ex)))
            save(ROOT/'quality.json',dict(checks=checks,fetch_errors=errors))
            raise
        except Exception as ex:
            errors.append(dict(code=code,name=name,error=str(ex)))
        if i%25==0 or i==len(frozen['pool']):
            progress=dict(at=now_cn().isoformat(),stocks_processed=i,total=len(frozen['pool']),
                          passed_stock_days=passed,fetch_errors=len(errors))
            save(ROOT/'progress.json',progress)
            save(ROOT/'quality.json',dict(checks=checks,fetch_errors=errors))
            print('ACQUIRE',json.dumps(progress,ensure_ascii=False),flush=True)
    save(ROOT/'quality.json',dict(checks=checks,fetch_errors=errors))

def stats(events):
    completed=[x for x in events if x['net_pct'] is not None]
    result=metrics([x['net_pct'] for x in completed]);result['wilson95_naive']=wilson(result['wins'],result['samples'])
    result['unique_stocks']=len({x['code'] for x in completed})
    result['signal_dates']=sorted({x['date'] for x in completed})
    result['pending']=sum(x['next_close'] is None for x in events)
    result['signals']=len(events)
    result['missing_entry']=sum(x['entry_price'] is None for x in events)
    result['unverified_execution_completed']=sum(x['execution']!='close_proxy' for x in completed)
    complete_risk=[x['adverse_pct'] for x in completed if x['adverse_complete'] and x['adverse_pct'] is not None]
    result['risk_complete_samples']=len(complete_risk)
    result['worst_sampled_adverse_pct']=min(complete_risk) if complete_risk else None
    return result

def replay(frozen):
    before=hashes();assert before==frozen['rule_hashes']
    quality=json.loads((ROOT/'quality.json').read_text());signals={g:[] for g in GROUPS};cooldown=collections.Counter();candidates={g:collections.Counter() for g in GROUPS}
    today=frozen['created_at'][:10]
    for i,stock in enumerate(frozen['pool'],1):
        code=stock['code'];p=ROOT/'normalized'/f'{code}.json'
        if not p.exists():continue
        data=json.loads(p.read_text());minutes=data['minute'];daily=data['daily']
        for dt,day in sorted(minutes.items()):
            if dt>today:continue
            nxt=date.fromisoformat(dt)+timedelta(days=1)
            while nxt.weekday()>4:nxt+=timedelta(days=1)
            nxt=nxt.isoformat();nd=daily.get(nxt) if nxt<=today else None
            for g in GROUPS:
                engine=confirmation if g in ('ES','EW') else evaluate
                result=engine(day,g,as_of='15:00');assert not result['error']
                candidates[g].update(x['status'] for x in result['candidates']);cooldown[g]+=len(result['cooldown_suppressed'])
                seen=set()
                for event in result['signals']:
                    identity=dt+'|'+code+'|'+event['key'];assert identity not in seen;seen.add(identity)
                    o=outcomes(event,day,minutes.get(nxt),nd,None)
                    entry=o['entry_price'];exit_price=float(nd['close']) if nd else None
                    scores={f'{fee:.2f}/{slip:.2f}':net_return(entry,exit_price,fee,slip) for fee in (.10,.20) for slip in (.05,.10,.20)}
                    signals[g].append(dict(group=g,code=code,name=stock['name'],board=stock['board'],half=stock['half'],old_pool=stock['old_pool'],
                        date=dt,time=event['time'],identity=identity,entry_time=o['entry_time'],entry_price=entry,
                        next_date=nxt,next_close=exit_price,net_pct=scores['0.10/0.10'],scenarios=scores,execution=o['execution'],
                        adverse_pct=o['observed_adverse_pct'],adverse_complete=o['adverse_complete'],evidence=event['evidence']))
        if i%100==0:print('REPLAY',i,flush=True)
    summary={}
    for g,events in signals.items():
        summary[g]=dict(all=stats(events),new_stocks=stats([e for e in events if not e['old_pool']]),
            half={h:stats([e for e in events if e['half']==h]) for h in ('A','B')},
            board={b:stats([e for e in events if e['board']==b]) for b in QUOTAS},
            dates={d:stats([e for e in events if e['date']==d]) for d in sorted({x['date'] for x in events})},
            cooldown_suppressed=cooldown[g],candidate_states=dict(candidates[g]),
            sensitivity={k:metrics([e['scenarios'][k] for e in events if e['net_pct'] is not None]) for k in ('0.10/0.05','0.10/0.10','0.10/0.20','0.20/0.05','0.20/0.10','0.20/0.20')})
    assert before==hashes(),'Core files changed during replay'
    unique={e['identity']:e for es in signals.values() for e in es if e['net_pct'] is not None}
    checks=quality['checks']
    acquisition_counts=collections.Counter()
    acquisition_board={b:collections.Counter() for b in QUOTAS}
    for stock in frozen['pool']:
        c=stock['code'];m=(ROOT/'raw'/f'{c}-minute.json').exists();d=(ROOT/'raw'/f'{c}-daily.json').exists()
        status='both_cached' if m and d else 'minute_only' if m else 'daily_only' if d else 'not_cached'
        acquisition_counts[status]+=1;acquisition_board[stock['board']][status]+=1
    result=dict(created_at=now_cn().isoformat(),frozen_pool=frozen,summary=summary,signals=signals,
        acquisition_counts=dict(acquisition_counts),acquisition_board={b:dict(v) for b,v in acquisition_board.items()},
        network_halted=json.loads((ROOT/'network-halted.json').read_text()) if (ROOT/'network-halted.json').exists() else None,
        quality_counts=dict(collections.Counter(c.get('status','excluded') for c in checks)),
        quality_errors=dict(collections.Counter(x for c in checks for x in c['errors'])),
        removed_afterhours=sum(len(c['removed_times']) for c in checks),fetch_errors=quality['fetch_errors'],
        unique_completed_structures=len(unique),unique_completed_stocks=len({e['code'] for e in unique.values()}),
        hashes_before=before,hashes_after=hashes(),notifications_sent=0,
        caveats=['价格代理评估：入场为确认后的下一完整分钟收盘价，退出为次日收盘；不能证明真实成交。',
                 '历史涨停状态未核实的信号仍单列执行状态；本表盈利率是扣成本后的价格代理盈利率。',
                 '固定参数未调优；同一结构在不同组出现不当作多个独立样本。',
                 '主情景假设往返总费用0.10%、买卖各0.10%滑点；缺次日结果或缺入场价不进入盈利率分母。',
                 '样本按当前可交易股票抽取，存在存活者与可得数据偏差；不代表历史全市场。',
                 '只覆盖最近5个相邻交易日；即使信号数增加，也不能代替跨月、不同市场行情的检验。',
                 'A/B为提前分配的不同股票子样本，并非新的时间外验证；不据此改参数。',
                 '朴素Wilson区间未校正同日股票相关性；多组中最高观察值有选择偏差，不是未来胜率上限。',
                 '本轮日K接口返回访问防护页后停止网络取数；只回放已同时取得分钟与日K并通过原有核验的日期。未完成1000只采集，缺数不计无信号、不替换股票。',
                 '已完成配对缓存集中在沪市主板，尚不是原计划沪深创业板分层样本；不得推广为全市场胜率。',
                 '最大不利波动仅按分钟收盘价采样，不是盘中真实最低价或账户最大回撤。'])
    save(ROOT/'evaluation.json',result)
    fields=['group','name','code','board','half','old_pool','date','time','entry_time','entry_price','next_date','next_close','net_pct','execution','adverse_pct','adverse_complete']
    with (ROOT/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for es in signals.values():w.writerows(es)
    lines=['# 腾讯免费广泛扩样：固定1000只计划与实际已取得样本评估','',f'名单冻结：{frozen["created_at"]}；分析完成：{result["created_at"]}。',
        f'总体{frozen["eligible_population"]}只当前成交有效股票，计划按代码哈希抽样1000只：沪主350、深主350、创业板300；不按涨幅或信号筛选。',
        f'实际缓存：{dict(acquisition_counts)}；已配对缓存分板块：{result["acquisition_board"]}。访问防护后已停止网络，不把计划1000只当成实际完成。',
        f'数据通过/排除：{result["quality_counts"]}；采集失败{len(result["fetch_errors"])}只；剔除盘后记录{result["removed_afterhours"]}条。',
        f'跨组去重后，已有次日价格的结构{len(unique)}个，涉及{result["unique_completed_stocks"]}只股票；不可把各组样本数相加。','',
        '|规则|信号|完成|盈利|盈利率|平均净收益|盈亏比系数|待次日|A半组|B半组|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    def rate(x):return '—' if x is None else f'{100*x:.2f}%'
    for g,s in summary.items():
        a=s['all'];mean='—' if a['mean_net_pct'] is None else f'{a["mean_net_pct"]:+.3f}%'
        pf='—' if a['profit_factor'] is None else f'{a["profit_factor"]:.3f}'
        lines.append(f'|{g}|{a["signals"]}|{a["samples"]}|{a["wins"]}|{rate(a["win_rate"])}|{mean}|{pf}|{a["pending"]}|{rate(s["half"]["A"]["win_rate"])}|{rate(s["half"]["B"]["win_rate"])}|')
    lines+=['','“盈亏比系数”为盈利净收益之和÷亏损净收益绝对值之和，不是平均盈亏比。主情景为往返费用0.10%+买卖各0.10%滑点。',
        '','## 口径与限制']+['- '+x for x in result['caveats']]
    lines+=['','## 数据核验','- 沿用上一轮固定审计：累计量差分×100、累计成交额÷累计股数、截至15:00量价对日K、缺失重复标签检查、量额非负、分钟价与量额比处于日K区间。',
        '- 每次网络请求串行、间隔至少0.25秒；原始响应缓存，重跑不会重复下载已缓存股票。无正式数据库访问或通知调用。',
        '','## 组别','V1：原始；A：均价微小波动容差；B：低价股突破；AB：两者合并；R：破位后收复；E：远离均价继续转强；RE：两项补充合并；ES：E增加结构高点确认；EW：E增加下一分钟站稳。',
        'R/E/RE基于V1；ES/EW只约束E补充信号，保留原始V1信号。所有规则均包含既有冷却与去重。']
    (ROOT/'analysis.md').write_text('\n'.join(lines))
    body='<h1>腾讯免费广泛扩样 · 实际缓存样本评估</h1><pre>'+html.escape('\n'.join(lines))+'</pre><h2>完整分组与逐笔数据</h2><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>'
    (ROOT/'analysis.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:15px system-ui;margin:32px;line-height:1.7}pre{white-space:pre-wrap}</style>'+body)
    print('RESULT',json.dumps(dict(quality=result['quality_counts'],unique_completed=len(unique),summary={g:s['all'] for g,s in summary.items()}),ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    frozen=freeze_pool()
    if '--replay-only' not in sys.argv:acquire(frozen,offline='--offline' in sys.argv)
    replay(frozen)
