import {useEffect,useRef,useState} from 'react';
import type {Request} from './Panels';
import {today,shiftDay} from './Panels';
export type BuySignal={key:string;code:string;name:string;date:string;time:string;price:number;split:string;coverage:string;relative_strength_5m:number|null;outcome:any};
export type BuyReport={version:string;created_at:string;coverage:any[];candidates:any[];baseline:BuySignal[];signals:BuySignal[];failures:BuySignal[];groups:Record<string,any>;index_missing:number;index_comparable:any;warnings:string[];export_path?:string;codes:string[];start:string;end:string;roundtrip_cost_bps:number|null;split:{development:string[];validation:string[]}};
const percent=(n:number|null|undefined)=>n==null?'—':n.toFixed(2)+'%';
const groupNames:Record<string,string>={strength_only:'只出现强势上涨',v1:'完整V1',v1_index:'V1＋指数相对强度≥0'};
export default function BuyResearch({request,watch,onResult,onOpen,initialReport}:{initialReport?:BuyReport;request:Request;watch:{code:string;name:string}[];onResult:(r:BuyReport)=>void;onOpen:(e:BuySignal)=>void}){
 const [codes,setCodes]=useState<string[]>(initialReport?.codes||[]),[start,setStart]=useState(initialReport?.start||shiftDay(today(),-90)),[end,setEnd]=useState(initialReport?.end||today()),[cost,setCost]=useState(initialReport?.roundtrip_cost_bps==null?'':String(initialReport.roundtrip_cost_bps));
 const [report,setReport]=useState<BuyReport|undefined>(initialReport),[busy,setBusy]=useState(false),[error,setError]=useState(''),[group,setGroup]=useState('v1');
 const initialized=useRef(!!initialReport),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{if(!initialized.current&&watch.length){setCodes(watch.map(w=>w.code));initialized.current=true;}},[watch.map(w=>w.code).join(',')]);
 async function run(exportFiles:boolean){
  setBusy(true);setError('');
  try{
   const task=await request<{job:string}>('buy_research',{codes,start,end,roundtrip_cost_bps:cost,export:exportFiles});
   while(alive.current){
    const job=await request<{status:string;error?:string;result:BuyReport}>('job',{job:task.job});
    if(job.status==='failed')throw Error(job.error||'回放失败');
    if(job.status==='done'){setReport(job.result);onResult(job.result);break;}
    await new Promise(resolve=>setTimeout(resolve,300));
   }
  }catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}
 }
 const items=report?(group==='strength_only'?report.baseline:group==='v1_index'?report.signals.filter(e=>e.relative_strength_5m!=null&&e.relative_strength_5m>=0):report.signals):[];
 return <section className="card form-card buy-research"><h2>强势回踩后再次转强 · V1历史研究</h2><p>仅使用本地缓存逐分钟回放。买点结果独立保存为研究报告，不进入卖点记录或任何通知队列。</p>
 <div className="coverage">{watch.map(w=><label className="switch" key={w.code}><input type="checkbox" checked={codes.includes(w.code)} disabled={busy} onChange={e=>setCodes(c=>e.target.checked?[...c,w.code]:c.filter(x=>x!==w.code))}/>{w.name} {w.code}</label>)}</div>
 <div className="form-row"><label>回放开始日期<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>回放结束日期<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><label>往返总费用（基点，选填）<input type="number" min="0" max="1000" value={cost} placeholder="留空不计算净收益" onChange={e=>setCost(e.target.value)}/></label><button disabled={busy||!codes.length} onClick={()=>run(false)}>{busy?'回放中…':'生成买点回放'}</button><button disabled={busy||!codes.length} onClick={()=>run(true)}>回放并导出报告</button></div>
 <details><summary>查看固定V1参数和判断顺序</summary><p>5分钟上涨≥0.8%，至少4根收在均价线上方，均量≥此前10分钟的1.2倍；当前收盘为最近5根最高。回踩2—8根，深度0.3%—1.2%，均量≤上涨段65%；至少一次距均价线±0.4%，全部收盘不低于当时均价线99.7%。</p><p>确认收盘≥此前两根最高收盘＋0.01元，并高于均价线；均价线不低于3分钟前，确认量≥回踩均量1.2倍，价格不高于均价线1.5%。仅09:45—11:20、13:15—14:30确认，不跨午休；同轮一次，确认后至少10交易分钟重新形成结构。</p><p>成交采用下一完整分钟收盘价代理；费用按填写的往返总基点估算，未建模最低佣金及实际成交。指数数据不足不默认通过。当前自选池存在选股偏差。</p></details>
 {error&&<p role="alert">{error}</p>}
 {report&&<><p>规则：{report.version} · 生成于 {report.created_at.slice(0,19).replace('T',' ')} · 买点实时通知：未启用</p><p className="notice">{report.signals.length?`本轮V1确认 ${report.signals.length} 条；仍需结合数据覆盖与保留验证段评估。`:'本轮没有满足全部V1条件的确认信号，不能据此评价买点有效性。'}</p><details><summary>样本与数据说明（{report.warnings.length}项）</summary><ul>{report.warnings.map(x=><li key={x}>{x}</li>)}</ul></details>
 {report.export_path&&<p className="report-path">报告已保存：{report.export_path}（HTML、JSON、五份CSV）</p>}
 <p>按日期分组：前段 {report.split.development.length} 日，保留验证段 {report.split.validation.length} 日。同一日期所有股票位于同一组。</p>
 <h3>三组对照 · 次日收盘（成交代理，未含费用和滑点）</h3><div className="table-scroll"><table><thead><tr><th>规则组</th><th>信号数</th><th>可评估次日样本</th><th>均值</th><th>中位数</th><th>正收益比例</th></tr></thead><tbody>{Object.entries(report.groups).map(([key,value])=><tr key={key}><td>{groupNames[key]}</td><td>{value.all.signals}</td><td>{value.all.next_close_samples}</td><td>{percent(value.all.mean_next_close)}</td><td>{percent(value.all.median_next_close)}</td><td>{value.all.positive_fraction==null?'—':percent(value.all.positive_fraction*100)}</td></tr>)}</tbody></table></div>
 <p>V1中有指数可比数据的信号 {report.index_comparable.signals} 条；指数缺失 {report.index_missing} 条。应先在可比样本内比较，不能将缺指数信号当作被过滤失败。</p>
 <details><summary>开发／验证、完整／部分日期、日线分组与滑点统计</summary><pre className="research-json">{JSON.stringify(report.groups,null,2)}</pre></details>
 <h3>数据覆盖 · {report.coverage.length} 个股票日期</h3><details><summary>完整 {report.coverage.filter(r=>r.status==='complete').length} · 部分 {report.coverage.filter(r=>r.status==='partial').length} · 缺失 {report.coverage.filter(r=>r.status==='missing').length} · 排除 {report.coverage.filter(r=>r.status==='excluded').length}</summary><div className="table-scroll"><table><thead><tr><th>股票</th><th>日期</th><th>状态</th><th>有效／所需分钟</th><th>说明</th></tr></thead><tbody>{report.coverage.slice(0,200).map(r=><tr key={r.code+r.date}><td>{r.name}</td><td>{r.date}</td><td>{({complete:'完整',partial:'部分',missing:'缺失',excluded:'排除'} as Record<string,string>)[r.status]}</td><td>{r.points}/{r.expected}</td><td>{r.reason}{r.benchmark_proxy?'；科创板使用上证代理基准':''}</td></tr>)}</tbody></table></div></details>
 <h3>信号与图表定位</h3><select aria-label="买点研究规则组" value={group} onChange={e=>setGroup(e.target.value)}>{Object.entries(groupNames).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select><p>当前组 {items.length} 条。页面最多展示200条，导出保留全部明细。点击定位查看分时；绿色三角为买点研究标记，原卖点标记保留。</p>
 <div className="table-scroll"><table><thead><tr><th>股票／日期</th><th>确认时间／价</th><th>回放分组</th><th>执行代理</th><th>次日收盘变化</th><th>锁定期／至次日收盘回撤</th><th>查看</th></tr></thead><tbody>{items.slice(0,200).map(e=><tr key={e.key}><td>{e.name}<small className="table-code">{e.code} · {e.date}</small></td><td>{e.time} / {e.price.toFixed(2)}</td><td>{e.split==='validation'?'保留验证':'开发观察'} · {e.coverage==='complete'?'完整日':'部分日'}</td><td>{e.outcome.entry_time||'—'} / {e.outcome.entry_price?.toFixed(2)||'—'}<small className="table-code">{e.outcome.execution==='close_proxy'?'收盘价代理，非真实成交':'成交不确定／数据不足'}</small></td><td>{percent(e.outcome.next_close_gross_pct)}</td><td>{percent(e.outcome.locked_adverse_pct)}{e.outcome.locked_complete?'':'（不完整）'}<small className="table-code">至次日收盘：{percent(e.outcome.observed_adverse_pct)}{e.outcome.adverse_complete?'':'（不完整）'}</small></td><td><button onClick={()=>onOpen(e)}>定位分时</button></td></tr>)}</tbody></table></div>
 <details><summary>候选与失败案例：{report.candidates.length} 个候选，{report.failures.length} 条失败／回撤案例</summary><p>失败样本定义：次日收盘变化为负，或观测收盘价不利波动超过1.2%；不是自动止损规则。</p><pre className="research-json">{JSON.stringify({candidates:report.candidates.slice(0,30),failures:report.failures.slice(0,30)},null,2)}</pre></details>
 </>}
 </section>;
}
