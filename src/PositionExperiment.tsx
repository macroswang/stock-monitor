import React from 'react';
import sample from '../fixtures/market-position-experiment.json';
import entry from '../fixtures/low-trin-entry-experiment.json';
import comparison from '../fixtures/low-trin-baseline-comparison.json';
import broadWeak from '../fixtures/broad-weak-position-experiment.json';
import trendCash from '../fixtures/trend-etf-cash-experiment.json';
import validation from '../fixtures/market-validation-results.json';

export default function PositionExperiment(){
 return <details className="breadth-method" aria-label="仓位动作历史实验">
  <summary>仓位动作历史实验 · 固定案例</summary>
  <h4>规则对照：{validation.windows[0].start} 至 {validation.windows[0].end}</h4>
  <p>上证及全市场收盘数据形成条件，次日按假设开盘价交易沪深300 ETF。初始10万元，计入佣金和假设滑点；每段从相同资金重新开始。</p>
  <div className="table-scroll"><table><thead><tr><th>时间段</th><th>规则</th><th>净收益</th><th>最大回撤</th><th>完成交易</th><th>胜率</th><th>盈亏比</th></tr></thead><tbody>{validation.windows.flatMap(period=>period.strategies.map(strategy=><tr key={period.name+strategy.mode}><td>{period.name}<small className="table-code">{period.start} 至 {period.end}</small></td><td>{strategy.name}</td><td>{strategy.net_return_percent.toFixed(2)}%</td><td>{strategy.max_drawdown_percent.toFixed(2)}%</td><td>{strategy.closed_trades}</td><td>{strategy.win_rate_percent==null?'—':strategy.win_rate_percent.toFixed(2)+'%'}</td><td>{strategy.profit_loss_ratio==null?'—':strategy.profit_loss_ratio.toFixed(2)}</td></tr>))}</tbody></table></div>
  <p>胜率与盈亏比仅统计已完成的买卖；期末持仓未计入这两项。{validation.limitations}</p>
  <p>独立研究条件：收盘时上涨家数占比低于 20%，且上证收盘低于 20 日均线。假设原有 10,000 份 510300，下一交易日开盘卖出 5,000 份，第 6 个交易日开盘买回同等份额，与一直持有比较。</p>
  <p>{sample.start} 至 {sample.end} 的 {sample.n} 个单次对照案例中，卖出再买回优于一直持有 {sample.better} 次、低于一直持有 {sample.worse} 次；每个案例平均差额 {Number(sample.average_difference_yuan).toFixed(2)} 元。差额是相对于一直持有，非账户实际盈亏；案例可能重叠，不能相加。</p>
  <p>按时间先后排除持有期重叠后，剩余 {sample.non_overlapping.n} 个案例：较好 {sample.non_overlapping.better} 次、较差 {sample.non_overlapping.worse} 次，平均差额 {Number(sample.non_overlapping.average_difference_yuan).toFixed(2)} 元。排除重叠不代表样本在统计上独立。</p>
  <p>放宽条件对照：收盘时下跌家数多于上涨家数，且上证收盘低于20日均线，采用同样的卖出与买回假设；{broadWeak.start} 至 {broadWeak.end} 全部可比较日期 {broadWeak.baseline.n} 个，其中满足条件 {broadWeak.condition.n} 个。按时间排除重叠后 {broadWeak.condition_non_overlapping.n} 个案例，较好 {broadWeak.condition_non_overlapping.better} 次、较差 {broadWeak.condition_non_overlapping.worse} 次，平均相对差额 {Number(broadWeak.condition_non_overlapping.mean).toFixed(2)} 元。该条件同样未证明能改善收益。</p>
  <p>假设佣金每笔万 2、最低 5 元，买卖每边各 0.001 元滑点，ETF 免印花税；开盘价不保证成交，买回可能需要额外现金。早期股票数据未完全交叉核验，结果不足以预测未来或直接指导加减仓。</p>
  <p>低 TRIN 买入试算：上述弱势条件同时满足成交额 TRIN 小于 0.7 时，下一交易日假设买入 {entry.units} 份 510300，5 个交易日后卖出；{entry.start} 至 {entry.end} 有 {entry.all.n} 个可比较案例，扣除假设成本后 {entry.all.positive} 次盈利、{entry.all.nonpositive} 次亏损或持平，平均 {Number(entry.all.average_net_yuan).toFixed(2)} 元。另有 {entry.skipped} 个案例因假设成交价超出当日范围排除。</p>
  <p>按时间剔除持有期重叠后剩 {entry.non_overlapping.n} 次，其中 {entry.non_overlapping.positive} 次盈利、{entry.non_overlapping.nonpositive} 次亏损或持平。上述结果为事后探索，事件可能相关，不代表实际成交或可推广的胜率；指数、ETF 和个股走势也会不同。</p>
  <p>同条件执行的同期对照：全部可比较日期 {comparison.all_dates.summary.n} 个，平均 {Number(comparison.all_dates.summary.average_net_yuan).toFixed(2)} 元；弱势但 TRIN 不低于 0.7 的案例仅 {comparison.weak_other_trin.summary.n} 个，无法判断低 TRIN 的独立作用。对照包含低 TRIN 案例，且收益窗口可能重叠。</p>
  <p>顺势代理试算：{trendCash.period[0]} 至 {trendCash.period[1]}，以前一日上证收盘高于20日均线作为次日持有 510300 的条件，否则持现金；假设初始 10 万元、按次日开盘价加滑点成交。扣除假设费用后，期末收益 {trendCash.trend.return_percent}%，最大收盘回撤 {trendCash.trend.max_drawdown_percent}%，交易 {trendCash.trend.trade_count} 笔；同期买入持有分别为 {trendCash.buy_and_hold.return_percent}%、{trendCash.buy_and_hold.max_drawdown_percent}%。</p>
  <p>分段对照（各段重新以 10 万元开始，不可相加）：{trendCash.segments.map(x=>`${x.period[0]} 至 ${x.period[1]}，趋势代理 ${x.trend.return_percent}%／持有 ${x.buy_and_hold.return_percent}%`).join('；')}。这是事后分段，不是样本外验证。</p>
  <p>这是事后设定的单一窗口实验；模拟无法保证开盘成交，未计现金利息、涨跌停和流动性限制。所用 ETF 与上证指数不同，参数未预注册，结果不能证明未来有效。</p>
 </details>;
}
