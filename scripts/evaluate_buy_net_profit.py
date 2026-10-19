"""Offline next-session net-profit scoring. Never ranks unavailable win rates."""
import csv,hashlib,html,json,statistics
from decimal import Decimal as D
from pathlib import Path

FEE_PCTS=(.10,.20) # Hypothetical all-in round-trip fee, as percentage of entry notional.
SLIP_PCTS=(.05,.10,.20) # Applied separately to buy and sell prices.

def net_return(entry,exit,fee_pct,slip_pct):
 if entry is None or exit is None:return None
 p,q,c,s=map(lambda x:D(str(x)),(entry,exit,fee_pct,slip_pct))
 if p<=0 or q<=0:raise ValueError('Prices must be positive')
 return float((q*(1-s/100)/(p*(1+s/100))-1)*100-c)

def metrics(values):
 if not values:return dict(samples=0,wins=0,win_rate=None,mean_net_pct=None,equal_notional_net_sum_pct=None,profit_factor=None,worst_net_pct=None)
 wins=[x for x in values if x>0];losses=[x for x in values if x<0]
 return dict(samples=len(values),wins=len(wins),win_rate=len(wins)/len(values),mean_net_pct=statistics.mean(values),equal_notional_net_sum_pct=sum(values),profit_factor=sum(wins)/-sum(losses) if losses else None,worst_net_pct=min(values))

def grade(event):
 o=event['outcome']
 if o.get('entry_price') is None:return 'missing_entry'
 if o.get('next_close_gross_pct') is None:return 'pending_or_missing_next_close'
 if o['execution']!='close_proxy':return 'price_only_uncertain_execution'
 return 'eligible_proxy'

def run(root=Path('docs/buy-v1/net-profit')):
 base=json.loads((root/'supplement/full-day.json').read_text());extra=json.loads((root/'confirmation/full-day.json').read_text())
 events=dict(base['signals']);events.update({k:v for k,v in extra['signals'].items() if k in ('ES','EW')})
 scenarios=[dict(fee_pct=f,slip_per_side_pct=s,key=f'fee{f:.2f}_slip{s:.2f}') for f in FEE_PCTS for s in SLIP_PCTS]
 primary='fee0.10_slip0.10';groups={};rows=[]
 for group,es in events.items():
  scored=[]
  for e in es:
   o=e['outcome'];entry=o.get('entry_price');gross=o.get('next_close_gross_pct')
   exit_price=entry*(1+gross/100) if gross is not None and entry else None
   record=dict(group=group,name=e['name'],code=e['code'],date=e['date'],identity=e['identity'],signal_time=e['time'],entry_time=o.get('entry_time'),entry_price=entry,next_close=exit_price,grade=grade(e),execution=o['execution'],scenarios={s['key']:net_return(entry,exit_price,s['fee_pct'],s['slip_per_side_pct']) for s in scenarios},observed_adverse_pct=o.get('observed_adverse_pct'),adverse_complete=o.get('adverse_complete'),day_close_return_from_entry_pct=e['trajectory']['last_return_from_entry_pct'])
   if entry and o.get('observed_adverse_pct') is not None:
    adverse_price=entry*(1+o['observed_adverse_pct']/100)
    record['primary_cost_adjusted_sampled_adverse_pct']=net_return(entry,adverse_price,.10,.10)
   else:record['primary_cost_adjusted_sampled_adverse_pct']=None
   scored.append(record);rows.append(record)
  groups[group]=dict(signals=len(es),pending=sum(x['grade']=='pending_or_missing_next_close' for x in scored),uncertain_completed=sum(x['grade']=='price_only_uncertain_execution' for x in scored),scenarios={})
  full_risk=[x['observed_adverse_pct'] for x in scored if x['adverse_complete'] and x['observed_adverse_pct'] is not None]
  partial_risk=[x['observed_adverse_pct'] for x in scored if not x['adverse_complete'] and x['observed_adverse_pct'] is not None]
  groups[group]['risk_observation']=dict(complete_cases=len(full_risk),worst_complete_sampled_adverse_pct=min(full_risk) if full_risk else None,partial_cases=len(partial_risk),worst_partial_sampled_adverse_pct=min(partial_risk) if partial_risk else None)
  for s in scenarios:
   eligible=[x['scenarios'][s['key']] for x in scored if x['grade']=='eligible_proxy']
   price_only=[x['scenarios'][s['key']] for x in scored if x['scenarios'][s['key']] is not None]
   groups[group]['scenarios'][s['key']]=dict(primary_eligible=metrics(eligible),all_completed_price_proxies=metrics(price_only))
 eligible_rates={g:v['scenarios'][primary]['primary_eligible']['win_rate'] for g,v in groups.items() if v['scenarios'][primary]['primary_eligible']['win_rate'] is not None}
 completed_unique={x['identity']:x for x in rows if x['next_close'] is not None}
 pending_unique={x['identity'] for x in rows if x['grade']=='pending_or_missing_next_close'}
 result=dict(unique_completed_price_structures=len(completed_unique),unique_pending_structures=len(pending_unique),as_of=base['as_of'],watch=base['watch'],coverage=base['coverage_summary'],cost_scenarios=scenarios,primary_scenario=primary,groups=groups,signals=rows,highest_observed_eligible_win_rate=max(eligible_rates.values()) if eligible_rates else None,ranking_possible=bool(eligible_rates),notifications_sent=0,source_sha256=base['source_sha256'],notes=['以次日收盘净收益>0计盈利；零收益不计盈利；缺结果不作亏损、无信号不作100%','所有入场均为下一完整分钟收盘价代理，不是实际成交；交易状态不明的历史样本不纳入主胜率','往返费用0.10%/0.20%为假设的统一全包成本，按入场名义金额计；不是用户实际交割费用，不另加重复税费','滑点分别作用于买入及卖出；主情景为往返费用0.10%＋每边滑点0.10%；成本情景不用于选择策略参数','净收益=(次日收盘×(1−卖出滑点))/(入场代理价×(1＋买入滑点))−1−往返费用率','等额名义本金收益之和仅是单笔净收益的合计，不是组合收益率；无持仓资金安排不输出账户累计收益或账户回撤','不利波动从模拟入场到次日收盘按分钟收盘和次日开盘采样；未知后半段单列不完整，不代表真正逐笔最大不利波动','跨规则相同股票日期结构不能重复视为独立样本；EW确认延后仍属于同一原始结构','6个可回放交易日均参与过规则设计；本报告不估计未来胜率上限，也不通过缺失样本构造60%成功率'])
 (root/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
 with (root/'signals.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['组别','股票','日期','确认时间','代理入场价','次日收盘','分类','主情景净收益%','采样不利波动%','不利窗口完整'])
  for x in rows:w.writerow([x['group'],x['name'],x['date'],x['signal_time'],x['entry_price'],x['next_close'],x['grade'],x['scenarios'][primary],x['observed_adverse_pct'],x['adverse_complete']])
 def rate(v):return '不可计算' if v is None else f'{v*100:.1f}%'
 headers=['规则','信号数','缺次日结果','历史状态不明','主口径样本','主口径盈利率','仅价格代理已完成样本／盈利率']
 table=[]
 for g,s in groups.items():
  eligible=s['scenarios'][primary]['primary_eligible'];price=s['scenarios'][primary]['all_completed_price_proxies']
  table.append([g,s['signals'],s['pending'],s['uncertain_completed'],eligible['samples'],rate(eligible['win_rate']),str(price['samples'])+' / '+rate(price['win_rate'])])
 body='<h1>次日收盘扣成本：九组规则评估</h1><p>快照：'+html.escape(base['as_of'])+'；当前5只自选，含新增康泰医学；6个可用交易日。主情景：假设往返费用0.10%，买卖各0.10%滑点。</p><p>主口径没有已完成且交易状态资料足够的样本，因此不能排名或报告最高可达胜率。唯一已有次日价格的国科微结构为亏损，单列观察；其余有信号的结构等待次日，不以当天上涨替代次日结果。</p>'
 body+='<table><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in row)+'</tr>' for row in table)+'</table>'
 body+='<h2>成本敏感性、整体盈亏及不利波动</h2><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre><p>公开费用项目参见<a href="https://one.sse.com.cn/onething/gptz/">上交所股票投资指引</a>。本报告采用明确假设，不把公开费率当作用户实际费用。</p>'
 (root/'evaluation.html').write_text('<!doctype html><meta charset="utf-8"><title>次日净盈利评估</title><style>body{font:15px system-ui;line-height:1.7;margin:30px}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:9px}pre{white-space:pre-wrap;font-size:12px}</style>'+body)
 print(json.dumps(dict(groups={g:dict(signals=x['signals'],pending=x['pending'],uncertain=x['uncertain_completed'],primary=x['scenarios'][primary]) for g,x in groups.items()},highest=result['highest_observed_eligible_win_rate']),ensure_ascii=False,indent=2))
 return result
if __name__=='__main__':run()
