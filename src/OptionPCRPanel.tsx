import React,{useEffect,useRef,useState} from 'react';
import * as echarts from 'echarts';

type Row={date:string;pcr:number;call_volume:number;put_volume:number;band_mid:number|null;band_upper:number|null;band_lower:number|null;gap_before?:boolean;collected_at:string};
type Report={days:Row[];running:boolean;error:string;latest_eligible:string|null;source_url?:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const fmt=(n:number|null|undefined,digits=3)=>n==null||!Number.isFinite(n)?'—':n.toFixed(digits);
const next=(a:string,b:string)=>{const x=new Date(a+'T00:00:00Z'),y=new Date(b+'T00:00:00Z');const d=(y.getTime()-x.getTime())/86400000;return d===1||(d===3&&x.getUTCDay()===5&&y.getUTCDay()===1);};

export default function OptionPCRPanel(props:{request:Request;selectedDate:string;intradayDate:string}){
 const [product,setProduct]=useState('510050');
 const [chosenDate,setChosenDate]=useState(props.selectedDate);
 const [revision,setRevision]=useState(0);
 useEffect(()=>{setChosenDate(props.selectedDate);},[props.selectedDate]);
 return <section className="option-panel" id="breadth-option-pcr" aria-label="期权PCR比较">
  <div className="option-heading"><div><h3>期权 PCR <small>成交量口径</small></h3><p>选择标的，查看收盘曲线</p></div>
   <label>期权标的 <select aria-label="期权标的" value={product} onChange={e=>setProduct(e.target.value)}><option value="510050">上证50ETF（510050）</option><option value="510300">沪深300ETF（510300）</option><option value="etf-exchanges">沪深ETF期权合计</option><option value="cffex-IO">沪深300股指期权（IO）</option><option value="cffex-HO">上证50股指期权（HO）</option><option value="cffex-MO">中证1000股指期权（MO）</option></select></label></div>
  {!product.startsWith('cffex-')&&<PCRComparison request={props.request} chosenDate={chosenDate} revision={revision} intradayDate={props.intradayDate}/>}
  <PCRContent key={product} {...props} product={product} chosenDate={chosenDate} setChosenDate={setChosenDate} onUpdated={()=>setRevision(x=>x+1)}/>
 </section>;
}

function PCRComparison({request,chosenDate,revision,intradayDate}:{request:Request;chosenDate:string;revision:number;intradayDate:string}){
 const [reports,setReports]=useState<(Report|null)[]>([null,null]);
 const [loaded,setLoaded]=useState(false);
 useEffect(()=>{let active=true,reading=false;
  const load=async()=>{if(reading)return;reading=true;const results=await Promise.allSettled(['510050','510300'].map(security_code=>request<Report>('option_pcr',{security_code})));if(active){setReports(results.map(r=>r.status==='fulfilled'?r.value:null));setLoaded(true);}reading=false;};
  void load();const timer=setInterval(load,30000);return()=>{active=false;clearInterval(timer);};
 },[request,revision]);
 const common=reports[0]?.days.filter(r=>reports[1]?.days.some(other=>other.date===r.date)).at(-1)?.date;
 const date=chosenDate||common||'';
 const rows=reports.map(r=>r?.days.find(d=>d.date===date&&(!intradayDate||d.date<intradayDate)));
 const position=(row:Row|undefined,index:number)=>{
  if(!reports[index])return loaded?'获取失败':'加载中';
  if(!row)return intradayDate&&date>=intradayDate?'盘中不显示当日收盘':'无同日数据';
  if(row.band_lower==null||row.band_upper==null||!Number.isFinite(row.band_lower)||!Number.isFinite(row.band_upper)||!Number.isFinite(row.pcr))return '通道样本不足';
  if(row.pcr<row.band_lower)return '低于下轨';
  if(row.pcr>row.band_upper)return '高于上轨';
  return '通道内';
 };
 return <div className="pcr-comparison" role="region" aria-label="同日期权PCR对照">
  <div className="pcr-comparison-title">同日通道对照 <span>{date||'暂无共同日期'} · 各标的收盘统计</span></div>
  <div className="pcr-comparison-grid">{['50ETF（510050）','300ETF（510300）'].map((label,i)=><div key={label}><span>{label}</span><strong>{fmt(rows[i]?.pcr)}</strong><small>{position(rows[i],i)}</small>{reports[i]?.error&&<small>采集异常，保留已有数据</small>}</div>)}</div>
  <p>两种 ETF 期权仅供结构对照，日终统计无法反映盘中是否击穿；通道位置不是见底判断。</p>
 </div>;
}

function PCRContent({request,product,selectedDate,chosenDate,setChosenDate,onUpdated,intradayDate}:{request:Request;selectedDate:string;intradayDate:string;product:string;chosenDate:string;setChosenDate:(date:string)=>void;onUpdated:()=>void}){
 const aggregate=product==='etf-exchanges';
 const index=product.startsWith('cffex-'),indexProduct=product.slice(6);
 const label=index?({'IO':'沪深300股指','HO':'上证50股指','MO':'中证1000股指'} as Record<string,string>)[indexProduct]:aggregate?'沪深ETF合计':product==='510300'?'沪深300ETF':'上证50ETF';
 const [report,setReport]=useState<Report>({days:[],running:false,error:'',latest_eligible:null});
 const [error,setError]=useState(''),[busy,setBusy]=useState(false);
 const ref=useRef<HTMLDivElement>(null),chart=useRef<echarts.ECharts|null>(null),alive=useRef(true),reading=useRef(false);
 const load=async()=>{if(reading.current)return;reading.current=true;try{const r=await request<Report>(index?'index_option_pcr':aggregate?'etf_option_pcr':'option_pcr',index?{product:indexProduct}:aggregate?{}:{security_code:product});if(alive.current){setReport(r);setError('');}}catch(e){if(alive.current)setError(String(e));}finally{reading.current=false;}};
 useEffect(()=>{alive.current=true;void load();const timer=setInterval(load,30000);return()=>{alive.current=false;clearInterval(timer);};},[request]);
 useEffect(()=>{if(!ref.current)return;const c=echarts.init(ref.current,'dark',{renderer:'canvas'});chart.current=c;const observer=new ResizeObserver(()=>c.resize());observer.observe(ref.current);return()=>{observer.disconnect();c.dispose();chart.current=null;};},[]);
 useEffect(()=>{
  if(!chart.current)return;
  const eligible=report.days.filter(r=>(!(aggregate||index)||Date.parse(r.collected_at)<=Date.now()+5000)&&(!chosenDate||r.date<=chosenDate)&&(!intradayDate||r.date<intradayDate));
  const slots:(Row|null)[]=[];eligible.forEach((r,i)=>{if(i&&(r.gap_before??!next(eligible[i-1].date,r.date)))slots.push(null);slots.push(r);});
  const make=(name:string,key:'pcr'|'band_mid'|'band_upper'|'band_lower',color:string,dashed=false)=>({name,type:'line',connectNulls:false,symbol:key==='pcr'?'circle':'none',symbolSize:5,lineStyle:{color,width:key==='pcr'?2:1,type:dashed?'dashed':'solid'},itemStyle:{color},data:slots.map(d=>d?.[key]??null)});
  chart.current.setOption({animation:false,backgroundColor:'transparent',grid:{left:54,right:28,top:30,bottom:38},tooltip:{trigger:'axis',confine:true,formatter:(params:any)=>{const d=slots[params[0]?.dataIndex];return d?`${d.date}<br/>${label} 成交量 PCR：${fmt(d.pcr)}<br/>20日中轨：${fmt(d.band_mid)}<br/>上轨 / 下轨：${fmt(d.band_upper)} / ${fmt(d.band_lower)}`:'数据间隔';}},xAxis:{type:'category',data:slots.map((d,i)=>d?.date||`gap-${i}`),axisLabel:{color:'#9eafc7',hideOverlap:true,formatter:(s:string)=>s.startsWith('gap-')?'…':s.slice(5)},axisLine:{lineStyle:{color:'#69778a'}}},yAxis:{type:'value',scale:true,axisLabel:{color:'#9eafc7'},splitLine:{lineStyle:{color:'#28313d'}}},series:[make('PCR','pcr','#80b8ff'),make('20日中轨','band_mid','#d4ad55',true),make('上轨','band_upper','#879ab8',true),make('下轨','band_lower','#879ab8',true)]},true);
 },[report.days,chosenDate,intradayDate]);
 const refresh=async()=>{setBusy(true);setError('');try{const job=await request<{job:string}>(index?'index_option_pcr_refresh':aggregate?'etf_option_pcr_refresh':'option_pcr_refresh',index?{product:indexProduct}:aggregate?{}:{security_code:product});for(;;){const r=await request<{status:string;error?:string;result?:Report}>('job',{job:job.job});if(!alive.current)return;if(r.status==='failed')throw Error(r.error);if(r.status==='done'){if(r.result){setReport(r.result);onUpdated();}break;}await new Promise(resolve=>setTimeout(resolve,500));}}catch(e){if(alive.current)setError(String(e));}finally{if(alive.current)setBusy(false);}};
 const available=report.days.filter(r=>(!(aggregate||index)||Date.parse(r.collected_at)<=Date.now()+5000)&&(!intradayDate||r.date<intradayDate));
 const chosen=chosenDate?available.find(x=>x.date===chosenDate):available.at(-1);
 const prior=!chosen&&chosenDate?available.filter(r=>r.date<chosenDate).at(-1):undefined;
 return <div aria-label={`${label}期权PCR`} role="region">
  <div className="option-heading"><p>{index?`中金所 ${indexProduct}`:aggregate?'沪深9只ETF期权':`上交所 ${product}`} · 认沽成交张数 ÷ 认购成交张数</p><div><label>日期 <select aria-label="期权统计日期" value={chosenDate||chosen?.date||''} onChange={e=>setChosenDate(e.target.value)}>{chosenDate&&!chosen&&<option value={chosenDate}>{chosenDate}（无数据）</option>}{available.slice().reverse().map(r=><option key={r.date} value={r.date}>{r.date}</option>)}</select></label> <button onClick={refresh} disabled={busy||report.running}>{busy||report.running?'采集中…':'刷新期权统计'}</button></div></div>
  {(error||report.error)&&<div className="breadth-error" role="status">{error||report.error}；已保留上次有效统计。</div>}
  <div className="option-readout"><div><span>{chosenDate||chosen?.date||'暂无统计日期'}</span><strong>{fmt(chosen?.pcr)}</strong></div><div><span>认沽 / 认购成交</span><strong>{chosen?`${chosen.put_volume.toLocaleString('zh-CN')} / ${chosen.call_volume.toLocaleString('zh-CN')} 张`:'—'}</strong></div><div><span>20日通道（上 / 下）</span><strong>{chosen?`${fmt(chosen.band_upper)} / ${fmt(chosen.band_lower)}`:'—'}</strong></div></div>
  {!chosen&&<p className="option-missing">{intradayDate&&chosenDate>=intradayDate?'盘中不显示当日及之后的收盘期权统计。':chosenDate?`所选日期没有可用的${label}期权统计。`:'暂无已核验的期权统计。'}</p>}
  {prior&&<button onClick={()=>setChosenDate(prior.date)}>查看最近有效记录 · {prior.date}</button>}
  {selectedDate&&chosenDate!==selectedDate&&<button onClick={()=>setChosenDate(selectedDate)}>返回大盘所选日期 · {selectedDate}</button>}
  <div className="option-chart" ref={ref} role="img" aria-label={`${label}期权PCR及20日通道曲线`}/>
  <div className="option-note">{index?'中金所单一股指期权，不代表全市场；历史与后续数据按不同来源逐合约核对。':aggregate?'沪深9只ETF期权成交张数合计，不含中金所；深交所数据日期按查询确认。':'上交所单一 ETF 期权，不代表全市场 PCR；'}按收盘后统计，20 个连续交易日不足时通道留空。{chosenDate&&'图表仅显示所选日期及之前的数据。'}{chosen&&<> 本次数据采集于 {chosen.collected_at.slice(0,19).replace('T',' ')} 北京时间；历史补采不代表当时已可获取。</>}{index?<a href="https://www.cfachina.org/servicesupport/sspz/?type=5" target="_blank" rel="noreferrer">期货业协会</a>:<><a href="https://www.sse.com.cn/assortment/options/date/" target="_blank" rel="noreferrer">上交所</a>{aggregate&&<> · <a href="https://www.szse.cn/market/option/day/index.html" target="_blank" rel="noreferrer">深交所</a></>}</>}</div>
 </div>;
}
