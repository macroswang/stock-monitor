import {useEffect,useState} from 'react';
import {researchScenarios,validateResearchBundle} from './dResearchModel';
import type {ResearchBundle,ResearchScenario,ResearchSlot} from './dResearchModel';
const labels:Record<string,string>={D:'D原交易',S:'补漏影子',S_L1:'补漏：指数晚1分钟',S_LQ:'补漏：确认量能1%'};
const pct=(n:number|null|undefined)=>n===null||n===undefined?'—':`${n>0?'+':''}${n.toFixed(4)}%`;
export default function DHistorySummary(){
 const [data,setData]=useState<ResearchBundle|null>(null),[error,setError]=useState('');
 const [scenario,setScenario]=useState<ResearchScenario>('primary'),[slot,setSlot]=useState<ResearchSlot>('D');
 useEffect(()=>{let active=true;import('./researchSnapshot').then(m=>{const b:unknown=JSON.parse(m.default);validateResearchBundle(b);if(active)setData(b);}).catch(()=>{if(active)setError('历史快照暂不可用，请重新打开页面。不会改用实时行情替代。');});return()=>{active=false;};},[]);
 if(error)return <p role="alert">{error}<button onClick={()=>window.location.reload()}>重新读取</button></p>;
 if(!data)return <p role="status">正在读取历史回测…</p>;
 return <div className="d-history-summary"><p>全样本为{data.meta.dates}个旧交易日期、{data.meta.stockdays}个股票日，不是新日期盲测。D原有35笔常规净收益≥2%的交易在预留库存对照中未被替代；补漏21笔仍未达盈利门槛。以下是独立历史总体结果，不是当前这只股票的收益预测。</p>
  <label>历史成本情景<select aria-label="历史D成本情景" value={scenario} onChange={e=>setScenario(e.target.value as ResearchScenario)}>{Object.entries(researchScenarios).map(([s,label])=><option key={s} value={s}>{label}</option>)}</select></label>
  <div className="table-scroll"><table aria-label="D历史全样本成本对照"><thead><tr><th>研究组</th><th>完成笔数</th><th>胜率</th><th>逐笔平均收益</th><th>固定1000股现金合计</th></tr></thead><tbody>{(['D','S','S_L1','S_LQ'] as ResearchSlot[]).map(s=>{const m=data.metrics[s][scenario];return <tr key={s}><th scope="row">{labels[s]}</th><td>{m.n}</td><td>{m.win_rate===null?'—':(m.win_rate*100).toFixed(2)+'%'}</td><td>{pct(m.mean_net_pct)}</td><td>{m.net_cny.toFixed(2)}元</td></tr>;})}</tbody></table></div>
  <p>固定1000股使高价股投入金额更大，补漏现金合计为正不等于逐笔等权盈利。补漏不占用D预留库存；共享1000股会提前替代9笔D，额外库存隔离则需要另1000股已有可卖持仓。本图不采用补漏交易。</p>
  <label>逐日研究组<select aria-label="D历史逐日研究组" value={slot} onChange={e=>setSlot(e.target.value as ResearchSlot)}>{Object.entries(labels).map(([s,label])=><option key={s} value={s}>{label}</option>)}</select></label>
  <div className="table-scroll"><table aria-label="D历史逐日期结果"><thead><tr><th>交易日期</th><th>完成笔数</th><th>胜率</th><th>平均收益</th><th>现金差</th></tr></thead><tbody>{data.daily.filter(r=>r.slot===slot&&r.scenario===scenario).map(r=><tr key={r.day}><th scope="row">{r.day}</th><td>{r.n}</td><td>{r.win_rate===null?'无交易':(r.win_rate*100).toFixed(2)+'%'}</td><td>{pct(r.mean_net_pct)}</td><td>{r.net_cny.toFixed(2)}元</td></tr>)}</tbody></table></div>
  <details><summary>14笔误伤的历史复核</summary><div className="table-scroll"><table aria-label="D历史14笔误伤"><thead><tr><th>股票 / 日期</th><th>D原确认</th><th>D常规净收益</th><th>旧J结果</th><th>原因</th></tr></thead><tbody>{data.cases.filter(c=>c.tags.includes('harm')).map(c=><tr key={c.id}><th scope="row">{c.name} · {c.day}</th><td>{c.trades.D.primary?.signal_time}</td><td>{pct(c.trades.D.primary?.net_pct)}</td><td>{c.oldJ?.signal?`${c.oldJ.signal} / ${pct(c.oldJ.net_pct)}`:'未入场'}</td><td>{c.oldJ?.signal?'提前补漏挤占D':'大盘硬筛误删D'}</td></tr>)}</tbody></table></div></details>
 </div>;
}
