import {lazy,Suspense,useState} from 'react';
import type {DObservation} from './turningD';
import {D_TIMES} from './turningD';
const History=lazy(()=>import('./DHistorySummary'));
const signed=(n:number)=>`${n>0?'+':''}${n.toFixed(2)}`;
export default function DObservationPanel({observation:d,visible}:{observation:DObservation;visible:boolean}){
 const [history,setHistory]=useState(false);
 const sellFirst=d.direction==='sell-buy';
 const status=d.status==='closed'?`${d.exitReason==='scheduled_close'?'计划恢复持股':'原形态退出'} ${d.exitFill!.time} · ${d.netCny===null?'费用无法核算':'模拟净'+signed(d.netCny)+'元'}`:
  d.status==='data_gap'?`数据不完整，观察停在${d.through<0?'开盘前':D_TIMES[d.through]}`:
  d.status==='entry_pending'?'已确认，等待下一完整分钟':d.status==='exit_pending'?'已出现退出形态，等待下一完整分钟':
  d.status==='open'?(sellFirst?'待原形态底回补':'待原形态顶退出'):d.status==='none'?'本日未出现合格入场':'尚无入场确认';
 return <details className="d-purpose-panel"><summary>D做T观察（固定1000股） · {visible?`${sellFirst?'先卖后买':'先买后卖'} · ${status}`:'勾选“显示形态底/顶”查看图上用途'}</summary>
  <p>{sellFirst?'顶·D：已有可卖持仓的候选卖出；底·回：卖出后的原形态底回补观察。14:56计划回补只标“回补”，不是底点或独立开仓买点。':'底·T：原形态底买入观察；顶·退：买底后的原形态顶退出，未套用C1入场过滤。'}均为研究对照，不代表账户已成交。</p>
  <dl><div><dt>入场确认</dt><dd>{d.entry?`${d.entry.time} · ${d.entry.price.toFixed(2)}元`:'尚无确认'}</dd></div><div><dt>{sellFirst?'卖出':'买入'}价格代理</dt><dd>{d.entryFill?`${d.entryFill.time} · ${((sellFirst?d.sellFill:d.buyFill)??d.entryFill.reference).toFixed(2)}元${d.status==='closed'?'（含滑点）':'（分钟参考，待双边费用结算）'}`:'等待下一完整分钟，缺失时不跳到后点'}</dd></div>
   <div><dt>{sellFirst?'回补':'退出'}依据</dt><dd>{d.exit?`原形态${sellFirst?'底':'顶'} ${d.exit.time}`:d.exitReason==='scheduled_close'?'14:56计划恢复原股数':`等待原形态${sellFirst?'底':'顶'}；最晚14:56按研究计划恢复股数`}</dd></div><div><dt>{sellFirst?'回补':'退出'}价格代理</dt><dd>{d.exitFill?`${d.exitFill.time} · ${((sellFirst?d.buyFill:d.sellFill)??d.exitFill.reference).toFixed(2)}元`:'未到成交观察时刻'}</dd></div>
   <div><dt>已恢复股数后的净价差</dt><dd>{d.netCny===null?'未完成，不显示未来盈亏':`${signed(d.netCny)}元 / ${d.netPct!.toFixed(4)}%`}</dd></div></dl>
  <p>固定研究口径1000股，与上方手动价差试算参数独立：次完整分钟收盘价格代理、每边至少1分钱或5bp不利滑点、佣金万2且每边最低5元、卖出印花万5、双边过户十万1。形态确认价不等于可成交价，历史D及补漏均未证明稳定盈利。未达标补漏不加入当前买卖标记，不发送研究通知。</p>
  <details className="d-history-details" onToggle={e=>{if(e.currentTarget.open)setHistory(true);}}><summary>查看历史扣费回测对照</summary>{history&&<Suspense fallback={<p role="status">正在读取随应用保存的历史结果…</p>}><History/></Suspense>}</details>
 </details>;
}
