"""Source-bound plots and Chinese readout for the frozen experiment."""
import hashlib,json,math,shutil,sys
from datetime import datetime
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from research.ma250_optimization import OUT,POLICIES,digest


def plots(r):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.labelcolor':'#344357','text.color':'#243247','axes.edgecolor':'#b5beca','grid.color':'#e7ebf0'})
    names=[('raw415','415 stocks | raw'),('raw_matched217','Same 217 stocks | raw'),('qfq217','Same 217 stocks | adjusted proxy')]
    colors={'B0':'#23364c','E1':'#4e73ad','E2':'#247b58','E4':'#ad6d2f'}
    labels={'B0':'B0 current strong','E1':'E1 one more close','E2':'E2 close above signal high','E4':'E4 broader reclaim + breakout'}
    fig,axes=plt.subplots(1,3,figsize=(15,4.9),sharex=True,sharey=True)
    for ax,(name,title) in zip(axes,names):
        panel=r['panels'][name]
        for k,run in panel['runs'].items():
            if k not in colors:
                f=run['full'];ax.scatter(abs(f['max_drawdown']),f['total'],c='#b4bfca',s=26,alpha=.75,zorder=2)
        for k,color in colors.items():
            f=panel['runs'][k]['full'];x,y=abs(f['max_drawdown']),f['total']
            ax.scatter(x,y,c=color,s=76,marker='D' if k=='B0' else 'o',label=labels[k],zorder=4)
            offset={'B0':(8,-14),'E1':(-28,-16),'E2':(8,8),'E4':(8,6)}[k]
            ax.annotate(k,(x,y),xytext=offset,textcoords='offset points',fontsize=10,color=color,weight='bold')
        ax.axhline(0,color='#c4ccd7',lw=.8);ax.grid(True,alpha=.8);ax.set_title(title,loc='left',weight='bold',fontsize=11,pad=12)
        ax.set_xlim(0,30);ax.set_ylim(-20,78);ax.set_xlabel('Maximum drawdown magnitude (%)')
    axes[0].set_ylabel('2019-2026 cumulative portfolio proxy (%)')
    handles,legend_labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend_labels,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.055),fontsize=9)
    fig.suptitle('Frozen annual-line candidates: risk and return',x=.06,ha='left',fontsize=16,weight='bold',y=.98)
    fig.text(.06,.015,'Lower drawdown is left; higher return is up. Through 2026-11-13. Costs: 0.15% per side. Retrospective, not fresh OOS.',fontsize=9,color='#5f6b7a')
    fig.subplots_adjust(left=.06,right=.985,top=.82,bottom=.24,wspace=.09)
    fig.savefig(OUT/'risk-return.png',dpi=160,facecolor='white');plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(15,7.2),sharex=True,sharey='row')
    ymax=max(x[1]/10000 for name,_ in names for k in colors for x in r['panels'][name]['runs'][k]['full']['curve'])
    upper=max(180,math.ceil(ymax/10)*10+10)
    styles={'B0':'--','E1':':','E2':'-','E4':'-.'}
    for col,(name,title) in enumerate(names):
        for k,color in colors.items():
            curve=r['panels'][name]['runs'][k]['full']['curve'];dates=[datetime.fromisoformat(x[0]) for x in curve];equity=np.array([x[1]/10000 for x in curve])
            peaks=np.maximum.accumulate(np.r_[100.,equity])[1:];dd=(equity/peaks-1)*100
            axes[0,col].plot(dates,equity,color=color,lw=2 if k=='E2' else 1.5,ls=styles[k],label=labels[k])
            axes[1,col].plot(dates,dd,color=color,lw=1.8 if k=='E2' else 1.2,ls=styles[k])
        axes[0,col].set_title(title,loc='left',fontsize=11,weight='bold',pad=10)
        for row in range(2):
            axes[row,col].grid(True,alpha=.8);axes[row,col].xaxis.set_major_locator(mdates.YearLocator(2));axes[row,col].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        axes[0,col].set_ylim(72,upper);axes[1,col].set_ylim(-30,1)
    axes[0,0].set_ylabel('Equity proxy (start = 100)');axes[1,0].set_ylabel('Drawdown (%)')
    fig.suptitle('Equity and drawdown: same engine, same costs',x=.06,ha='left',fontsize=16,weight='bold',y=.985)
    handles,legend_labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,legend_labels,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.045),fontsize=9)
    fig.text(.06,.012,'Completed-close confirmations enter at the next tradable open. 10 slots. Raw and adjusted are return proxies; incomplete corporate-action ledger.',fontsize=9,color='#5f6b7a')
    fig.subplots_adjust(left=.06,right=.985,top=.86,bottom=.16,hspace=.15,wspace=.09)
    fig.savefig(OUT/'equity-drawdown.png',dpi=160,facecolor='white');plt.close(fig)


def f(v):return '—' if v is None else f'{v:+.2f}%'
def w(v):return '—' if v is None else f'{v:.1%}'


def main():
    r=json.loads((OUT/'results.json').read_text());a=json.loads((OUT/'robustness.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    assert a['results_digest']==digest(r) and r['plan_digest']==a['plan_digest']==digest(plan)
    plots(r)
    lines=['# 年线信号优化：独立回测研究（2026-11-14）','',
'**有值得继续验证的改善方向，但尚无通过全部稳健性检验、足以替换当前业务规则的方案。优先关注E2：强档后等待三日内收盘突破信号日高点，再于下一可交易日开盘入场。**','',
'本轮只增加独立研究脚本和研究测试；未修改客户端检测、提醒、交易、参数、原始数据或旧规则日志。当前基线仍为 `ma250-pullback-v3-4f393989872d`。','',
'## 研究范围与可信边界','',
f"预先写入 `plan.json` 的21个固定方案（含当前基线和宽口径对照），不做阈值网格搜索。检查{len(plan['production_and_input_hashes'])}份业务/输入文件，前后哈希一致。新引擎的当前强档基线与既有引擎逐笔成交、1,907个逐日权益点完全一致，三组样本全部通过。",'',
'- 未复权415只；另取共同217只分别用未复权与前复权计算，避免把股票范围不同误认为复权效果。',
'- 区间2019-01-02至2026-11-13；分2019–2023、2024–2025、2026年截至11月13日。历史此前已用于研究，时间切分和逐年滚动都不是新的独立样本外证明。',
'- 次一已核验交易日开盘入场；固定持有期含买入日；实验性退出信号一律完成收盘后才触发、下一可交易开盘执行，保留T+1及跌停顺延。原定到期退出在收盘执行；不把未来卖出款用于此前买入。',
'- 买卖各0.15%成本；加倍成本为各0.30%。10仓位、100股整数手、资金不足不透支。未到期继续估值，不伪造成交或零收益。',
'- 当前上市股票固定面板有存活者偏差；历史ST、盘口、冲击成本及完整分红送转账本不全。未复权与前复权均为收益代理，前复权用原始价确定股数再按复权价格归一化估值。','',
'## 1. 最值得继续验证：增加确认，而非继续堆叠过滤','',
'以下胜率是受仓位限制后**实际模拟完成交易**的净收益胜率；总收益是整段组合收益，不能读成单笔或年化收益。','',
'|股票/价格口径|方案|完成交易|胜率|组合收益代理|最大回撤|平均资金占用|','|---|---|---:|---:|---:|---:|---:|']
    names=[('raw415','415只未复权'),('raw_matched217','相同217只未复权'),('qfq217','相同217只前复权')]
    for name,label in names:
        for k in ['B0','E1','E2']:
            x=r['panels'][name]['runs'][k]['full'];label_k={'B0':'当前强档20日','E1':'多一次收盘确认','E2':'三日内收盘突破信号高点'}[k]
            lines.append(f"|{label}|{label_k}|{x['trades']}|{w(x['win'])}|{f(x['total'])}|{f(x['max_drawdown'])}|{w(x['exposure'])}|")
    lines += ['',
'**E2在三组样本中同时提高全期胜率和收益、降低至少20%的回撤幅度；但这只是历史初筛门槛。** 前复权年化由0.60%升至0.76%，提升约0.16个百分点，绝对增益不大。','',
'信号样本与组合成交须分开：415只E2确认107次、实际成交96次，单信号20日均值+1.57%、胜率46.7%；前复权E2确认并成交67次，均值+0.94%、胜率50.7%。当前强档分别有193/120个信号；延后确认显著减少入场次数。','',
'### E2的固定实验规则','',
'1. 保留现有强档事件，在信号日T收盘之后开始等待，不修改原始强档日期。',
'2. 仅观察随后3个已核验交易日；若日内最低价跌破原信号参考失效价，取消这次候选。',
'3. 首次收盘高于**T日最高价**，且仍高于MA250×1.01及MA5、沪深300仍在年线上时确认。这里不是盘中触及、也不是突破此前60日高点。',
'4. 在确认后的下一可交易日开盘尝试入场；涨停开盘、零量、停牌不假定成交。三日未确认就放弃，不无限等待。',
'5. 保持20个交易日退出、原成本与仓位设定；这是独立研究规则，没有加入现有提醒。','',
'E1则只等待下一交易日再次收在年线1%以上、MA5以上且不低于原信号收盘，再于次日开盘入场；其415只全期收益仅+0.46%，成本加倍即转负，优先级低于E2。','',
'![风险收益比较](risk-return.png)','',
'图中越左回撤越小、越上收益越高。灰点为其余固定方案；样本与价格口径分别列出，不能混成一条最优曲线。','',
'## 2. 稳健性：改善存在，但尚不稳定','',
'|检验|415只当前→E2|共同217只未复权当前→E2|共同217只前复权当前→E2|','|---|---|---|---|']
    diagnostic_rows=[('成本加倍后的全期收益','double_cost'),('剔除2025年入场后的全期收益','without_2025_entries')]
    for label,key in diagnostic_rows:
        cells=[]
        for name,_ in names:
            d=a['panels'][name]['policies'];cells.append(f"{f(d['B0'][key]['total'])} → {f(d['E2'][key]['total'])}")
        lines.append('|'+label+'|'+'|'.join(cells)+'|')
    cells=[]
    for name,_ in names:
        p=r['panels'][name]['runs'];cells.append(f"{f(p['B0']['periods']['late']['total'])} → {f(p['E2']['periods']['late']['total'])}")
    lines.append('|2026年截至11月13日收益|'+'|'.join(cells)+'|')
    cells=[]
    for name,_ in names:
        h=a['panels'][name]['policies']['E2']['stock_halves'];cells.append(' / '.join(f(h[str(g)]['total']) for g in (0,1)))
    lines.append('|E2代码哈希两半收益|'+'|'.join(cells)+'|')
    lines += ['',
'成本加倍后E2三组仍为正且优于各自基线，这是保留研究价值的原因。**剔除2025年入场后三组仍亏损；2026年共同217只的两种口径仍负；一组股票子样本也为负。** 尚不能据此认定跨市场阶段稳定。股票两半资金利用率与样本量不同，只作为敏感性诊断。','',
'回撤下降部分来自降低暴露：415只平均资金占用15.0%→9.5%，前复权11.4%→6.6%。简单半仓对照S3也能明显降低回撤，但胜率基本不变。E2的较高历史胜率及收益值得关注，不能把所有风险改善都解释为预测能力提高。','',
'### 不确定性与多重比较','',
'用连续3个月区块循环重采样1,000次，检验相对当前基线的月度组合收益差；对本轮20个备选方案做max-t家族校正。此校正不覆盖过去历次探索，也不能消除既有数据窥探。','',
'|E2样本|年化对数超额收益区间|本轮多重校正p值|','|---|---|---:|']
    for name,label in names:
        u=r['panels'][name]['uncertainty']['E2'];ci=u['ci'];lines.append(f"|{label}|[{ci[0]:+.2f}, {ci[1]:+.2f}] 个百分点|{u['family_adjusted_p']:.3f}|")
    lines += ['',
'三个区间均跨零，p值均未达0.05。它们不是未来获利概率；当前证据支持“候选方向”，不支持“已证实优势”。','',
'同一股票、同一原信号日、入场日和退出日的前复权/未复权E2配对只有38次：两者胜率均47.4%，均值约+1.22%/+1.43%。其余入场集合不同，价格口径会影响确认事件，不能只调整收益系数。','',
'## 3. 最高收益方案为何没有被推荐','',
'|方案|415只收益/回撤|前复权217只收益/回撤|主要问题|','|---|---|---|']
    for k,desc in [('E4','从指数在线上的首次收回事件起，等三日内突破信号日高点；2026年在共同股票两种口径都明显亏损，回撤也高于强档基线。'),('E3','首次收回后多一次收盘确认；历史收益较高，但前复权回撤扩大到15%左右，2026年仍亏损。'),('X2','强档持有40日；延长持有提升某些历史收益，也明显扩大回撤和2026年亏损。'),('F3','缩量回踩；前复权胜率58.1%，但仅43笔、总收益+1.34%，低于基线；不能只追胜率。'),('S2','按参考失效距离设0.25%权益风险预算；风险改善主要来自仓位，仍按20日退出，不是损失封顶保证。')]:
        x=r['panels']['raw415']['runs'][k]['full'];y=r['panels']['qfq217']['runs'][k]['full'];lines.append(f"|{k}|{f(x['total'])} / {f(x['max_drawdown'])}|{f(y['total'])} / {f(y['max_drawdown'])}|{desc}|")
    lines += ['',
'例如E4在415只上收益+69.29%，共同217只未复权只剩+24.54%，前复权+11.59%；前复权2026年亏损12.46%。其415只相对基线收益区间虽然为正，本轮家族校正p值仍为0.079，共同股票及复权结果更弱，不能据最高收益升级。','',
'相对强弱、指数短期趋势的硬过滤没有普遍改善；叠加多个过滤和风险缩仓的C2前复权回撤虽仅2.42%，胜率降至33.9%、全期收益仅+0.07%，大量留现金不能算信号获得显著优化。','',
'## 4. 逐年选择策略的滚动回放','',
'每年只使用此前3年数据，在完成交易≥20、年化正收益、胜率≥45%的候选中选Calmar最高者；无合格者回退当前基线。旧持仓按自己的退出计划继续。该选择标准写在初始计划里，不使用当年结果选方案。','',
'|股票/价格口径|2022–2026固定当前基线：收益/回撤|相同时段滚动选择：收益/回撤|','|---|---|---|']
    for name,label in names:
        b=a['panels'][name]['walk_forward_baseline'];x=r['panels'][name]['walk_forward']['result'];lines.append(f"|{label}|{f(b['total'])} / {f(b['max_drawdown'])}|{f(x['total'])} / {f(x['max_drawdown'])}|")
    lines += ['',
'415只回放按年选出的策略为E4、B1、E4、B0、X2；2026年依据过去成绩选中40日持有，随后表现不佳。**简单追逐历史最优方案没有带来稳定改善。** 共同217只与前复权结果也不一致，因此不建议上线自动策略选择。','',
'![权益与回撤](equity-drawdown.png)','',
'## 5. 可执行的后续研究方案','',
'- **优先冻结E2作为研究候选。** 保留强档原始事件，单独记录等待确认、失效、确认但无法成交、已入场和未到期；不覆盖原规则和原日志。',
'- **E1作为较保守对照，S2作为仓位风险对照。** 对比同样的实际资金占用，继续检查胜率改善是否足够抵消等待入场和少做交易的机会成本。',
'- 补充此前未使用的数据、包含退市及历史ST状态的时点股票池、复权与公司行为账本、可核验交易日历及更可信的成交约束。采用相同固定规则重跑，避免再用当前历史挑阈值。',
'- 以后用新增数据验证跨市场阶段、成本压力和区间精度；尚无新的独立前瞻样本，不能在本次报告中补造“验证通过”。所有方案均保持研究状态。','',
'## 复现与证据','',
'```sh\n.venv/bin/python research/ma250_optimization.py --plan-only\n.venv/bin/python research/ma250_optimization.py\n.venv/bin/python research/ma250_optimization_audit.py\n.venv/bin/python -m unittest tests.test_ma250_optimization\n```','',
'- `plan.json`：查看新结果前固定的方案、时间切分、选择准则、成本与业务/输入SHA-256。',
'- `results.json`、`robustness.json`：全部21方案、三组样本、分段、滚动选择、区块重采样及所有稳健性诊断；`*-events.json`保留完整实验入场与退出计划。',
'- `validation.json`、`tests-full.log`、`tests-research.log`：研究引擎检查、全部后端检查和生产代码未变化记录。',
'- 方法风险参考：[Bailey等，The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)。该文说明重复选择策略的统计风险；本研究未声称计算其PBO指标，也未把一个时间留出段当成充分证明。','']
    (OUT/'report.md').write_text('\n'.join(lines))
    print(OUT/'report.md')

if __name__=='__main__':main()
