import {useEffect,useState} from 'react';
import './marketOpportunity.css';
import type {BreadthDay} from './MarketBreadth';
import {breadthView,currentStamp} from './marketOverview';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Member={code:string;name:string};
type IndexRow={code:string;name:string;price:number|null;percent:number|null;change:number|null;ma5:number|null;ma10:number|null;ma20:number|null;
  above_ma5:boolean|null;above_ma20:boolean|null;high20:number|null;low20:number|null;volume:number|null;volume_ratio:number|null;
  support:number|null;resistance:number|null;stamp:string|null};
type BreadthPulse={date:string;status:string;advance:number;decline:number;flat:number;advancing_percent:number|null;trin:number|null;
  amount_yuan:number|null;amount_5d_avg:number|null;amount_ratio:number|null;days_used:number|null};
type Market={indices:IndexRow[];breadth:BreadthPulse|null;signals:string[]};
type FlowRow={code:string;name:string;net_yuan:number;change_percent:number};
type FlowBlock={inflow:FlowRow[];outflow:FlowRow[];measure:string|null;date:string|null};
type PersistentRow={code:string;name:string;sector_kind:string;net_yuan:number|null;net_5d:number|null;days:number|null;change_percent:number|null};
type Capital={industry:FlowBlock|null;concept:FlowBlock|null;persistent:PersistentRow[];history_days:number|null};
type LimitStat={today:number|null;yesterday:number|null;attempt:number|null;sealed_rate:number|null;open_num:number|null};
type YesterdayPerformance={count:number|null;advance:number|null;avg_percent:number|null;promote:number|null;promote_rate:number|null};
type HotReason={name:string;count:number;codes?:string[];stocks?:Member[]};
type Sentiment={limit_up:LimitStat|null;limit_down:LimitStat|null;max_board:number|null;max_board_name:string|null;
  ladder:{boards:number;count:number}[];non_consecutive:number|null;yesterday_performance:YesterdayPerformance|null;
  hot_reasons:HotReason[];trend:{date:string;limit_up:number|null;limit_down:number|null;sealed_rate:number|null;max_board:number|null}[];temperature:string|null};
type NewsRow={time:string;title:string;url:string;region:string|null;match:string|null};
type Hotspots={news:NewsRow[];reasons:HotReason[]};
type Pulse={market:Market|null;capital:Capital|null;sentiment:Sentiment|null;hotspots:Hotspots|null};
type Levels={ma5:number|null;ma10:number|null;ma20:number|null;high20:number|null;low20:number|null};
type Entry={buy_low:number;buy_high:number;stop:number;chase:number;note:string;target1?:number|null;target2?:number|null;trail?:number|null;sell_note?:string|null};
type Stock={code:string;name:string;role:string;price:number|null;percent:number|null;amount_yuan:number|null;low:number|null;
  boards:number|null;limit_tag:string|null;reason:string|null;levels:Levels|null;entry:Entry|null};
type Gate={kind:string;value?:number};
type Direction={rank:number;sector:string;sector_code:string;sector_kind:string;change:number|null;net:number|null;
  net_5d:number|null;net_5d_days:number|null;score:number;state:string;why:string;opportunity:string;logic:string[];risk:string;
  candidate:Member|null;peers:{code:string;name:string;stop?:number|null}[];stocks:Stock[];timing:{window:string;triggers:string[];invalidation:string[];gates:Gate[]};news_title?:string|null;
  evidence:{label:string;value:string;source:string}[]};
type Idea={sector:string;sector_code:string;sector_kind?:string;change?:number|null;net?:number|null;reason?:string;risk?:string;
  allow_entry?:boolean;stocks:{code:string;name:string;low:number}[];core_members?:Member[]};
type PoolTheme={code?:string;name:string;matched_count?:number;advance?:number;change?:number;net?:number;
  members?:{code:string;name:string;basis:string}[]};
type Issue={screen_version?:number;horizon?:string;verdict?:string;bias?:string;position?:string;pulse?:Pulse;focus?:Focus|null;top_picks?:TopPick[];radar?:Radar[];radar_summary?:string;
  playbooks?:{name:string;conditions:string[];action:string;position:string;active:boolean}[];
  timetable?:{time:string;focus:string;rule:string}[];risk?:string[];warnings?:string[];directions?:Direction[];
  published_at:string;quote_date:string;native_slot?:string;coverage?:{industry:number;concept:number;disclosed?:number;unavailable?:number};
  discovery?:{days:number;observed:number;failed_days?:number;source_failures?:Record<string,number>;filing_errors?:Record<string,string>};
  exclusions?:Record<string,string>;directory?:Record<string,string>;themes?:PoolTheme[];ideas?:Idea[];news_counts?:Record<string,number>};
type Quote={code:string;price:string;previous_close:string;day_low:string;timestamp:string;amount_yuan?:string;volume?:number;day_high?:string};
type SectorFlow={change:number;net:number;time:string;inferred?:boolean};
type Report={schedule?:string;completed_slot?:string|null;issue:Issue|null;quotes:Quote[];sectors?:Record<string,SectorFlow>;
  day:string|null;batch:string|null;preview_note?:string};
type BreadthReport={days:BreadthDay[];error?:string};
type LiveQuote={price:number;previous:number;low:number;pct:number;time:string;amount:number|null};
type LiveSector={change:number;net:number;time:string};
type LiveCtx={valid:boolean;reason:string;quotes:Map<string,LiveQuote>;sectors:Map<string,LiveSector>};
type LiveKind='可考虑建仓'|'继续等'|'已转弱'|'行情待核对'|'观察'|'回避';
type Check={kind:string;ok:boolean|null;text:string};
type Assessment={kind:LiveKind;why:string;checks:Check[];candidatePct?:number;candidateName?:string;live:boolean;static?:boolean};
type Focus={sector:string;sector_code:string;state:string;why:string;candidate:Member|null;window:string;summary:string};
type RadarStock={code:string;name:string;role:string;price:number|null;percent:number|null;boards:number|null;limit_tag:string|null;
  reason:string|null;levels:Levels|null;entry:Entry|null};
type Radar={theme:string;kind:string;stage:string;stage_note:string|null;signals:string[];limit_up_today:number|null;limit_up_prev:number|null;
  limit_up_5d:number|null;max_board:number|null;news_count:number|null;net_yuan:number|null;change:number|null;verdict:string;risk:string;
  watch:string[];stocks:RadarStock[];evidence:{label:string;value:string;source:string}[]};
type TopPick={code:string;name:string;role:string;sector:string;sector_code:string;sector_kind:string;rank:number;state:string;why:string;
  price:number|null;percent:number|null;boards:number|null;limit_tag:string|null;
  buy_low:number|null;buy_high:number|null;chase:number|null;stop:number|null;target1:number|null;target2:number|null;trail:number|null;
  note?:string|null;sell_note?:string|null;window?:string|null;sizing?:string|null;trigger?:string|null};

const DEFAULT_GATES:Gate[]=[{kind:'market_decline_share_max',value:2/3},{kind:'sector_change_min',value:0},
  {kind:'sector_net_min',value:0},{kind:'candidate_pct_max',value:5},{kind:'candidate_recover'},{kind:'peers_rising_min',value:1}];

const numText=(value:number|null|undefined,digits=2)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(digits):'待取得';
const pctText=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?(value>0?'+':'')+value.toFixed(2)+'%':'待取得';
const rateText=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?(value>1?value.toFixed(1):(value*100).toFixed(1))+'%':'待取得';
const yiText=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?(value/1e8).toFixed(2)+' 亿':'待取得';
const signedYi=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?(value>=0?'+':'')+(value/1e8).toFixed(2)+' 亿':'待取得';
const amountText=(value:number|null|undefined)=>{
  if(typeof value!=='number'||!Number.isFinite(value)||value<=0)return '待取得';
  return value>=1e8?(value/1e8).toFixed(2)+' 亿':(value/1e4).toFixed(0)+' 万';
};
const tone=(value:number|null|undefined)=>typeof value==='number'?(value>0?' positive':value<0?' negative':''):'';
const stampText=(iso:string|null|undefined)=>{
  if(typeof iso!=='string'||iso.length<16)return '待取得';
  return iso.slice(0,10)+' '+iso.slice(11,16);
};
const clockText=(iso:string|null|undefined)=>typeof iso==='string'&&iso.length>=16?iso.slice(11,16):'待取得';
const shortText=(text:string|null|undefined,max=3)=>{
  if(typeof text!=='string'||!text.trim())return '待取得';
  const parts=text.split('；').filter(part=>part.trim());
  if(parts.length<=max)return parts.join('；');
  return parts.slice(0,max).join('；')+'…';
};
const shortWindow=(window:string|null|undefined)=>{
  if(typeof window!=='string'||!window.trim())return '待取得';
  const range=window.match(/\d{1,2}:\d{2}[–-]\d{1,2}:\d{2}/);
  return range?range[0]:window;
};
const radarStageClass=(stage:string|undefined)=>
  stage==='启动初期'?'start':stage==='发酵'?'ferment':stage==='加速/高潮'?'peak':stage==='分歧'?'diverge':stage==='退潮'?'ebb':'';
const radarSignalText=(radar:Radar)=>{
  const parts:string[]=[];
  if(typeof radar.limit_up_today==='number')parts.push('涨停 '+radar.limit_up_today+' 家');
  if(typeof radar.max_board==='number'&&radar.max_board>0)parts.push('最高 '+radar.max_board+' 板');
  if(typeof radar.news_count==='number'&&radar.news_count>0)parts.push('新闻 '+radar.news_count+' 条');
  if(typeof radar.net_yuan==='number'&&Number.isFinite(radar.net_yuan))parts.push('资金 '+signedYi(radar.net_yuan));
  if(typeof radar.change==='number'&&Number.isFinite(radar.change))parts.push('板块 '+pctText(radar.change));
  return parts.length?parts.join(' · '):'待取得';
};
const shortSizing=(sizing:string|null|undefined)=>{
  if(typeof sizing!=='string'||!sizing.trim())return '待取得';
  return sizing.replace(/（[^）]*）/g,'').trim()||sizing;
};
const targetPercent=(price:number|null|undefined,target:number|null|undefined)=>{
  if(typeof price!=='number'||!Number.isFinite(price)||price<=0)return null;
  if(typeof target!=='number'||!Number.isFinite(target))return null;
  return (target/price-1)*100;
};
const stateClass=(kind:LiveKind)=>kind==='可考虑建仓'?'ready':kind==='已转弱'?'weak':kind==='行情待核对'?'unknown':kind==='回避'?'avoid':kind==='观察'?'watch':'wait';

/** Only quotes from the current, verified breadth batch may drive live states. */
function liveContext(report:Report,day:BreadthDay|undefined,now:number):LiveCtx{
  const quotes=new Map<string,LiveQuote>(),sectors=new Map<string,LiveSector>();
  const missing=(reason:string):LiveCtx=>({valid:false,reason,quotes,sectors});
  if(!report.day||!report.batch)return missing('本轮没有可核对的行情批次，等待更新。');
  if(day&&(report.day!==day.date||report.batch!==day.collected_at))return missing('行情批次与全市场广度快照未对齐，等待下一轮核对。');
  const times=report.quotes.map(q=>q.timestamp).filter(t=>typeof t==='string'&&t.length>=16).sort();
  const first=day?.first_quote??times[0]??null,last=day?.last_quote??times[times.length-1]??null;
  const fresh=(time:string|undefined)=>{
    if(typeof time!=='string'||time.slice(0,10)!==report.day)return false;
    if(first&&time<first)return false;
    if(last&&time>last)return false;
    return currentStamp(time,report.day,now);
  };
  for(const quote of report.quotes){
    const price=Number(quote.price),previous=Number(quote.previous_close),low=Number(quote.day_low);
    if(![price,previous,low].every(v=>Number.isFinite(v)&&v>0)||low>price||!fresh(quote.timestamp))continue;
    const amount=Number(quote.amount_yuan);
    quotes.set(quote.code,{price,previous,low,pct:(price/previous-1)*100,time:quote.timestamp,amount:Number.isFinite(amount)?amount:null});
  }
  for(const [code,sector] of Object.entries(report.sectors??{})){
    if(!sector||typeof sector.change!=='number'||typeof sector.net!=='number')continue;
    if(!Number.isFinite(sector.change)||!Number.isFinite(sector.net))continue;
    if(typeof sector.time!=='string'||!currentStamp(sector.time,report.day,now))continue;
    sectors.set(code,{change:sector.change,net:sector.net,time:sector.time});
  }
  return {valid:true,reason:'',quotes,sectors};
}

function checkGate(gate:Gate,cq:LiveQuote,candidate:Stock,sector:LiveSector,peers:{code:string;name:string;quote:LiveQuote}[],
  counts:{advance:number;decline:number;flat:number}|null):Check|null{
  const value=typeof gate.value==='number'&&Number.isFinite(gate.value)?gate.value:undefined;
  if(gate.kind==='market_decline_share_max'){
    const max=value??2/3;
    if(!counts||counts.advance+counts.decline+counts.flat<=0)return {kind:gate.kind,ok:null,text:'全市场广度数据待取得，方向状态降为观察。'};
    const total=counts.advance+counts.decline+counts.flat,share=counts.decline/total;
    return {kind:gate.kind,ok:share<=max+1e-9,text:'当日下跌家数占比 '+(share*100).toFixed(1)+'%，上限 '+(max*100).toFixed(1)+'%。'};
  }
  if(gate.kind==='sector_change_min'){
    const min=value??0;
    return {kind:gate.kind,ok:sector.change>=min,text:'板块当日涨跌幅 '+pctText(sector.change)+'，需不低于 '+min.toFixed(2)+'%。'};
  }
  if(gate.kind==='sector_net_min'){
    const min=value??0;
    return {kind:gate.kind,ok:sector.net>=min,text:'板块当日净额 '+signedYi(sector.net)+'，需不低于 '+min.toFixed(2)+' 亿元。'};
  }
  if(gate.kind==='candidate_pct_max'){
    const max=value??5;
    return {kind:gate.kind,ok:cq.pct<max,text:'候选股'+(candidate.name??'')+'当日涨幅 '+pctText(cq.pct)+'，上限 '+max.toFixed(2)+'%。'};
  }
  if(gate.kind==='candidate_recover'){
    const ok=cq.low<=cq.previous&&cq.price>cq.previous;
    return {kind:gate.kind,ok,text:'候选股回落后重新站上昨收（现价 '+cq.price.toFixed(2)+'，昨收 '+cq.previous.toFixed(2)+'，当日低 '+cq.low.toFixed(2)+'）。'};
  }
  if(gate.kind==='peers_rising_min'){
    const min=value??1,rising=peers.filter(p=>p.quote.pct>0).length;
    return {kind:gate.kind,ok:rising>=min,text:'上涨同行 '+rising+' 只，需至少 '+min+' 只。'};
  }
  return null;
}

function assess(direction:Direction,ctx:LiveCtx,day:BreadthDay|undefined,report:Report):Assessment{
  const pulse=report.issue?.pulse;
  if(direction.state==='回避'){
    return {kind:'回避',why:direction.why||'命中本机回避规则，等待下一轮研判。',checks:[],live:ctx.valid};
  }
  if(!ctx.valid)return {kind:'行情待核对',why:ctx.reason,checks:[],live:false};
  const stocks=direction.stocks??[];
  const candidateMember=direction.candidate??(stocks[0]?{code:stocks[0].code,name:stocks[0].name}:null);
  if(!candidateMember)return {kind:'行情待核对',why:'本期没有候选股行情，等待核对。',checks:[],live:false};
  const candidateStock=stocks.find(stock=>stock.code===candidateMember.code)??stocks.find(stock=>stock.role==='低吸候选')??stocks[0];
  if(!candidateStock)return {kind:'行情待核对',why:'本期没有候选股行情，等待核对。',checks:[],live:false};
  const cq=ctx.quotes.get(candidateMember.code);
  if(!cq)return {kind:'行情待核对',why:'候选股'+(candidateMember.name||'')+'不在本批行情或时间戳已过期。',checks:[],live:false};
  const peerMembers=direction.peers?.length?direction.peers:stocks.filter(stock=>stock.code!==candidateMember.code).slice(0,2).map(stock=>({code:stock.code,name:stock.name,stop:null}));
  const peers:{code:string;name:string;stop:number|null;quote:LiveQuote}[]=[];
  for(const peer of peerMembers){
    const quote=ctx.quotes.get(peer.code);
    if(!quote)return {kind:'行情待核对',why:'同行'+(peer.name||'')+'行情待核对。',checks:[],live:false};
    peers.push({code:peer.code,name:peer.name,stop:typeof peer.stop==='number'&&Number.isFinite(peer.stop)?peer.stop:null,quote});
  }
  const sector=ctx.sectors.get(direction.sector_code);
  if(!sector)return {kind:'行情待核对',why:'板块行情未同步或时间戳已过期，等待核对。',checks:[],live:false};
  const base={candidatePct:cq.pct,candidateName:candidateMember.name,live:true};
  const stop=candidateStock.entry?Number(candidateStock.entry.stop):NaN;
  if(Number.isFinite(stop)&&cq.price<stop){
    return {...base,kind:'已转弱',checks:[],why:(candidateMember.name||'候选股')+'现价 '+cq.price.toFixed(2)+' 元已跌破失效价 '+stop.toFixed(2)+' 元。'};
  }
  const peerStops=peers.filter(peer=>peer.stop!==null);
  if(peerStops.length>0&&peerStops.every(peer=>peer.quote.price<peer.stop!)){
    return {...base,kind:'已转弱',checks:[],why:'两只同行现价都已跌破各自的失效价。'};
  }
  const pulseBreadth=pulse?.market?.breadth??null;
  const counts=day&&day.date===report.day?{advance:day.advance,decline:day.decline,flat:day.flat}
    :pulseBreadth&&pulseBreadth.date===report.day?{advance:pulseBreadth.advance,decline:pulseBreadth.decline,flat:pulseBreadth.flat}:null;
  const gates=direction.timing?.gates?.length?direction.timing.gates:DEFAULT_GATES;
  const checks:Check[]=[];
  let firstFail:Check|undefined;
  for(const gate of gates){
    const check=checkGate(gate,cq,candidateStock,sector,peers,counts);
    if(!check)continue;
    checks.push(check);
    if(check.ok!==true&&!firstFail)firstFail=check;
  }
  if(!checks.length)return {...base,kind:'继续等',checks,why:'本期没有可核对的盘中条件，先观察。'};
  if(firstFail)return {...base,kind:'继续等',checks,why:firstFail.text};
  return {...base,kind:'可考虑建仓',checks,why:checks.length+' 项盘中条件全部满足，板块资金为净流入。'};
}

/** 预览模式没有与 issue 对齐的 breadth 批次，按后端静态状态渲染，并明确标注非实时。 */
function assessStatic(direction:Direction):Assessment{
  const state=direction.state;
  const kind:LiveKind=state==='可考虑建仓'||state==='继续等'||state==='观察'||state==='回避'?state:'继续等';
  return {kind,why:direction.why||'后端静态研判状态。',checks:[],live:false,static:true};
}

type MarketProps={market:Market|null};
function MarketCard({market}:MarketProps){
  const breadth=market?.breadth??null;
  return <section className="card mo-card" aria-label="市场温度">
    <h2>市场温度 <span className="mo-sub">三大指数均线与量能 · 全市场广度</span></h2>
    {!market?<p className="mo-wait">待取得</p>:<>
      <div className="mo-indexes">{market.indices.map(index=><div className="mo-index" key={index.code}>
        <div className="mo-index-line"><b>{index.name||index.code}</b><span className={'mo-num'+tone(index.percent)}>{pctText(index.percent)}</span>
          <span className="mo-num">{numText(index.price)}</span><span className="mo-sub">{clockText(index.stamp)}</span></div>
        <div className="mo-index-meta">
          <span>MA5 {numText(index.ma5)}{index.above_ma5===true?' 上方':index.above_ma5===false?' 下方':''}</span>
          <span>MA20 {numText(index.ma20)}{index.above_ma20===true?' 上方':index.above_ma20===false?' 下方':''}</span>
          <span>20 日 {numText(index.low20)}–{numText(index.high20)}</span>
          <span>量比 {numText(index.volume_ratio)}</span>
          <span>支撑 {numText(index.support)} / 阻力 {numText(index.resistance)}</span>
        </div>
      </div>)}</div>
      {!market.indices.length&&<p className="mo-wait">指数日线待取得（腾讯与新浪日线均未返回），暂不展示均线。</p>}
      <div className="mo-block"><h3>全市场广度</h3>
        {!breadth?<p className="mo-wait">广度数据待取得</p>:<div className="mo-stat-grid">
          <div className="mo-stat"><span>上涨 / 下跌 / 平盘</span><b>{breadth.advance} / {breadth.decline} / {breadth.flat}</b></div>
          <div className="mo-stat"><span>上涨占比</span><b>{pctText(breadth.advancing_percent)}</b></div>
          <div className="mo-stat"><span>两市成交额</span><b>{yiText(breadth.amount_yuan)}</b></div>
          <div className="mo-stat"><span>近 5 日均额</span><b>{yiText(breadth.amount_5d_avg)}</b></div>
          <div className="mo-stat"><span>成交额比</span><b>{numText(breadth.amount_ratio)}</b></div>
          <div className="mo-stat"><span>TRIN</span><b>{numText(breadth.trin)}</b></div>
          <div className="mo-stat"><span>广度日期</span><b>{breadth.date||'待取得'}</b></div>
          <div className="mo-stat"><span>统计天数</span><b>{typeof breadth.days_used==='number'?breadth.days_used+' 天':'待取得'}</b></div>
        </div>}
      </div>
      {market.signals?.length>0&&<div className="mo-block"><h3>本机规则信号</h3>
        <ul className="mo-list">{market.signals.map((signal,index)=><li key={index}>{signal}</li>)}</ul></div>}
    </>}
  </section>;
}

function FlowList({flow,label}:{flow:FlowBlock|null;label:string}){
  if(!flow)return <div className="mo-flow"><span className="mo-sub">{label}</span><p className="mo-wait">{label}资金待取得</p></div>;
  const row=(item:FlowRow)=><div className="mo-flow-row" key={item.code}>
    <span className="mo-flow-name">{item.name}</span>
    <span className={'mo-num'+tone(item.change_percent)}>{pctText(item.change_percent)}</span>
    <span className={'mo-num'+tone(item.net_yuan)}>{signedYi(item.net_yuan)}</span>
  </div>;
  return <div className="mo-flow">
    <div className="mo-flow-head"><b>{label}</b><span className="mo-sub">{flow.measure||'口径待取得'} · {flow.date||'日期待取得'}</span></div>
    <div className="mo-flow-cols">
      <div><span className="mo-sub">净流入</span>{(flow.inflow??[]).slice(0,3).map(row)||null}</div>
      <div><span className="mo-sub">净流出</span>{(flow.outflow??[]).slice(0,3).map(row)||null}</div>
    </div>
  </div>;
}

function CapitalCard({capital}:{capital:Capital|null}){
  return <section className="card mo-card" aria-label="资金流向">
    <h2>资金流向 <span className="mo-sub">行业 / 概念当日资金与近 5 日持续流入</span></h2>
    {!capital?<p className="mo-wait">待取得</p>:<>
      <FlowList flow={capital.industry} label="行业"/>
      <FlowList flow={capital.concept} label="概念"/>
      <div className="mo-block"><h3>近 5 个采集日持续流入</h3>
        {!capital.persistent?.length?<p className="mo-wait">历史采集不足，持久流入待取得</p>:
          <div className="mo-scroll"><table className="mo-table">
            <thead><tr><th>板块</th><th>类型</th><th>当日净额</th><th>近 5 日累计</th><th>天数</th><th>涨幅</th></tr></thead>
            <tbody>{capital.persistent.map(row=><tr key={row.code}>
              <td>{row.name}</td><td>{row.sector_kind||'待取得'}</td>
              <td className={'mo-num'+tone(row.net_yuan)}>{signedYi(row.net_yuan)}</td>
              <td className={'mo-num'+tone(row.net_5d)}>{signedYi(row.net_5d)}</td>
              <td className="mo-num">{typeof row.days==='number'?row.days+' 天':'待取得'}</td>
              <td className={'mo-num'+tone(row.change_percent)}>{pctText(row.change_percent)}</td>
            </tr>)}</tbody></table></div>}
        <span className="mo-sub">可用采集日 {typeof capital.history_days==='number'?capital.history_days+' 天':'待取得'}；不足 3 天时近 5 日累计显示待取得</span>
      </div>
    </>}
  </section>;
}

function LimitBlock({limit,label}:{limit:LimitStat|null;label:string}){
  if(!limit)return <div className="mo-stat"><span>{label}</span><b>待取得</b></div>;
  return <>
    <div className="mo-stat"><span>{label}（今日 / 昨日）</span><b>{limit.today??'待取得'} / {limit.yesterday??'待取得'}</b></div>
    <div className="mo-stat"><span>{label}封板率</span><b>{rateText(limit.sealed_rate)}</b></div>
    <div className="mo-stat"><span>{label}炸板 / 触板</span><b>{limit.open_num??'待取得'} / {limit.attempt??'待取得'}</b></div>
  </>;
}

function SentimentCard({sentiment}:{sentiment:Sentiment|null}){
  return <section className="card mo-card" aria-label="市场人气">
    <h2>市场人气 {sentiment?.temperature&&<span className={'mo-chip mo-temp'}>{sentiment.temperature}</span>}</h2>
    {!sentiment?<p className="mo-wait">待取得</p>:<>
      <div className="mo-stat-grid">
        <LimitBlock limit={sentiment.limit_up} label="涨停"/>
        <LimitBlock limit={sentiment.limit_down} label="跌停"/>
        <div className="mo-stat"><span>最高连板</span><b>{sentiment.max_board??'待取得'} 板{sentiment.max_board_name?' · '+sentiment.max_board_name:''}</b></div>
        <div className="mo-stat"><span>非连续涨停</span><b>{sentiment.non_consecutive??'待取得'} 家</b></div>
      </div>
      <div className="mo-block"><h3>连板梯队</h3>
        {!sentiment.ladder?.length?<p className="mo-wait">连板梯队待取得</p>:
          <div className="mo-chips">{sentiment.ladder.map(item=><span className="mo-chip" key={item.boards}>{item.boards} 板 × {item.count}</span>)}</div>}
      </div>
      <div className="mo-block"><h3>昨日涨停今日表现</h3>
        {!sentiment.yesterday_performance?<p className="mo-wait">—（昨日涨停池与同日报价未对齐，不参与评分）</p>:<div className="mo-stat-grid">
          <div className="mo-stat"><span>样本 / 上涨</span><b>{sentiment.yesterday_performance.count??'待取得'} / {sentiment.yesterday_performance.advance??'待取得'}</b></div>
          <div className="mo-stat"><span>平均涨幅</span><b>{pctText(sentiment.yesterday_performance.avg_percent)}</b></div>
          <div className="mo-stat"><span>晋级 / 晋级率</span><b>{sentiment.yesterday_performance.promote??'待取得'} / {rateText(sentiment.yesterday_performance.promote_rate)}</b></div>
        </div>}
      </div>
      <div className="mo-block"><h3>近 5 个交易日趋势</h3>
        {!sentiment.trend?.length?<p className="mo-wait">趋势待取得</p>:
          <div className="mo-scroll"><table className="mo-table">
            <thead><tr><th>日期</th><th>涨停</th><th>跌停</th><th>封板率</th><th>最高板</th></tr></thead>
            <tbody>{sentiment.trend.map(row=><tr key={row.date}>
              <td>{row.date}</td><td className="mo-num">{row.limit_up??'待取得'}</td><td className="mo-num">{row.limit_down??'待取得'}</td>
              <td className="mo-num">{rateText(row.sealed_rate)}</td><td className="mo-num">{row.max_board??'待取得'}</td>
            </tr>)}</tbody></table></div>}
      </div>
    </>}
  </section>;
}

function HotspotCard({hotspots,fallbackReasons}:{hotspots:Hotspots|null;fallbackReasons:HotReason[]|null}){
  const reasons=hotspots?.reasons?.length?hotspots.reasons:(fallbackReasons??[]);
  return <section className="card mo-card" aria-label="热点题材">
    <h2>热点题材 <span className="mo-sub">涨停原因热度 · 新闻热点</span></h2>
    {!hotspots&&!reasons.length?<p className="mo-wait">待取得</p>:<>
      <div className="mo-block"><h3>涨停原因热度</h3>
        {!reasons.length?<p className="mo-wait">待取得</p>:<div className="mo-reasons">{reasons.slice(0,8).map(reason=><div className="mo-reason" key={reason.name}>
          <b>{reason.name}</b><span className="mo-sub">{reason.count} 家</span>
          {!!reason.stocks?.length&&<span className="mo-sub">{reason.stocks.slice(0,3).map(stock=>stock.name).join('、')}</span>}
        </div>)}</div>}
      </div>
      <div className="mo-block"><h3>新闻热点</h3>
        {!hotspots?.news?.length?<p className="mo-wait">新闻待取得</p>:
          <ul className="mo-news">{hotspots.news.slice(0,12).map(news=><li key={news.url+news.title}>
            <a href={news.url} target="_blank" rel="noreferrer">{news.title}</a>
            <span className="mo-sub">{stampText(news.time)}{news.region?' · '+news.region:''}{news.match?' · 匹配 '+news.match:''}</span>
          </li>)}</ul>}
      </div>
    </>}
  </section>;
}

const staticKind=(state:string|undefined):LiveKind=>
  state==='可考虑建仓'||state==='继续等'||state==='观察'||state==='回避'?state:'继续等';

function pickAssessment(pick:TopPick,assessments:Map<string,Assessment>,preview:boolean){
  const directionAssessment=assessments.get(pick.sector_code);
  if(preview)return {kind:staticKind(pick.state),why:pick.why||'后端静态研判状态。',static:true};
  if(directionAssessment)return {kind:directionAssessment.kind,why:directionAssessment.why,static:false};
  return {kind:'行情待核对' as LiveKind,why:'行情待核对。',static:false};
}

function BuildList({picks,assessments,selected,onSelect,preview,enhanced}:{
  picks:TopPick[];assessments:Map<string,Assessment>;selected:string;onSelect:(code:string)=>void;preview:boolean;enhanced:boolean;
}){
  if(!picks.length){
    return <p className="mo-wait">{enhanced?'本期没有可执行的建仓清单，等待下一轮研判。':'研判增强尚未生成（等待本机每 30 分钟更新）；建仓清单待取得。'}</p>;
  }
  const rows=picks.map(pick=>{
    const status=pickAssessment(pick,assessments,preview);
    return {pick,status,targetPct:targetPercent(pick.price,pick.target1)};
  });
  const readyCount=rows.filter(row=>row.status.kind==='可考虑建仓').length;
  return <>
    <div className="mo-picks-head">
      <h2>建仓清单 <span className="mo-sub">买点区间 · 止损 · 止盈目标 · 仓位 · 观察窗口；点击行查看该方向详情</span></h2>
      <span className="mo-sub">共 {picks.length} 条 · 可考虑建仓 {readyCount} 条 · {preview?'状态为预览静态':'状态由本批行情实时核对'}</span>
    </div>
    <div className="mo-picks-wrap">
      <div className="mo-pick-head" aria-hidden="true">
        <span>股票</span><span>方向 · 角色</span><span>现价 · 涨幅</span><span>状态</span><span>买点区间</span>
        <span>追高上限</span><span>止损</span><span>止盈目标</span><span>仓位</span><span>观察窗口</span>
      </div>
      {rows.map(({pick,status,targetPct})=>{
        const title=[pick.trigger?('触发条件：'+pick.trigger):'触发条件：待取得',pick.sell_note?('卖出：'+pick.sell_note):''].filter(Boolean).join('　');
        return <button type="button" key={pick.code+'|'+pick.sector_code} className="mo-pick-row"
          aria-pressed={pick.sector_code===selected} aria-controls="mo-direction-detail" title={title}
          onClick={()=>onSelect(pick.sector_code)}>
          <span className="mo-p-name"><b>{pick.name||'待取得'}</b> <span className="mo-code">{pick.code||''}</span>
            {pick.limit_tag&&<span className="mo-chip">{pick.limit_tag}</span>}</span>
          <span className="mo-p-sector"><b>{pick.sector||'待取得'}</b><span className="mo-chip mo-kind">{pick.sector_kind||'类型待核实'}</span>
            <span className="mo-role">{pick.role||'角色待取得'}</span></span>
          <span className="mo-p-price"><i className="mo-p-label">现价</i><b>{numText(pick.price)}</b>
            <span className={'mo-num'+tone(pick.percent)}>{pctText(pick.percent)}</span></span>
          <span className="mo-p-state"><i className="mo-p-label">状态</i><span className={'mo-state '+stateClass(status.kind)}>{status.kind}</span></span>
          <span className="mo-p-buy"><i className="mo-p-label">买点</i>
            {typeof pick.buy_low==='number'&&typeof pick.buy_high==='number'?numText(pick.buy_low)+'–'+numText(pick.buy_high):'待取得'}</span>
          <span className="mo-p-chase"><i className="mo-p-label">追高</i>{typeof pick.chase==='number'?'≤ '+numText(pick.chase):'待取得'}</span>
          <span className="mo-p-stop"><i className="mo-p-label">止损</i>{numText(pick.stop)}</span>
          <span className="mo-p-target"><i className="mo-p-label">目标</i>{numText(pick.target1)}
            {targetPct!==null?<span className="positive"> +{targetPct.toFixed(1)}%</span>:null}</span>
          <span className="mo-p-sizing" title={pick.sizing||'待取得'}><i className="mo-p-label">仓位</i>{shortSizing(pick.sizing)}</span>
          <span className="mo-p-window" title={pick.window||'待取得'}><i className="mo-p-label">窗口</i>{shortWindow(pick.window)}</span>
          <span className="mo-p-why">{status.why}
            {pick.trigger?<span className="mo-sub">　方向条件：{shortText(pick.trigger,3)}</span>:<span className="mo-sub">　方向条件：待取得</span>}</span>
        </button>;
      })}
    </div>
  </>;
}

function DirectionTable({directions,assessments,activeCode,onSelect,enhanced}:{
  directions:Direction[];assessments:Map<string,Assessment>;activeCode:string;onSelect:(code:string)=>void;enhanced:boolean;
}){
  if(!directions.length)return <p className="mo-wait">{enhanced?'本期没有满足条件的建仓方向，等待下一轮研判。':'研判增强尚未生成（等待本机每 30 分钟更新）；方向排名待取得。'}</p>;
  return <div className="mo-rank">
    <div className="mo-rank-head" aria-hidden="true">
      <span>#</span><span>方向</span><span>涨幅</span><span>净额</span><span>近 5 日</span><span>综合分</span><span>状态</span>
    </div>
    {directions.map(direction=>{
      const assessment=assessments.get(direction.sector_code)??{kind:'行情待核对' as LiveKind,why:'行情待核对。',checks:[],live:false};
      return <button type="button" key={direction.sector_code} className="mo-rank-row"
        aria-pressed={direction.sector_code===activeCode} aria-controls="mo-direction-detail" onClick={()=>onSelect(direction.sector_code)}>
        <span className="mo-c-num">{direction.rank??'—'}</span>
        <span className="mo-c-sector"><b>{direction.sector}</b><span className="mo-chip mo-kind">{direction.sector_kind||'类型待核实'}</span></span>
        <span className={'mo-c-change'+tone(direction.change)}>{pctText(direction.change)}</span>
        <span className="mo-c-net">{signedYi(direction.net)}</span>
        <span className="mo-c-net5">{typeof direction.net_5d==='number'?signedYi(direction.net_5d)+(direction.net_5d_days?' · '+direction.net_5d_days+' 天':''):'历史采集不足'}</span>
        <span className="mo-c-score">{numText(direction.score)}</span>
        <span className="mo-c-state"><span className={'mo-state '+stateClass(assessment.kind)}>{assessment.kind}</span>
          {assessment.static&&<span className="mo-static">静态</span>}</span>
        <span className="mo-c-why">{assessment.static?'预览：静态状态，非实时核对。':''}{assessment.why}</span>
      </button>;
    })}
  </div>;
}

function RadarCard({radar,summary,preview}:{radar:Radar[];summary:string;preview:boolean}){
  const [open,setOpen]=useState<string|null>(null);
  const rows=radar.slice(0,5);
  const riskNote='名称辈 / 生肖玄学 / 事件题材 · 风险高，只宜小仓或观察';
  return <section className="card mo-radar" aria-label="炒作雷达">
    <div className="mo-radar-head">
      <h2>炒作雷达 <span className="mo-sub">{riskNote}</span></h2>
      <span className="mo-sub">{summary||'识别结果待取得'}{preview?' · 预览静态':''}</span>
    </div>
    {!rows.length?<p className="mo-wait">本期没有识别到新的炒作/概念信号。名称/玄学与事件题材仅小仓或观察，不构成投资建议。</p>:<>
      <div className="mo-radar-list">
        <div className="mo-radar-head-row" aria-hidden="true">
          <span>主题</span><span>阶段</span><span>今日信号</span><span>代表标的</span><span>结论</span>
        </div>
        {rows.map(item=>{
          const expanded=open===item.theme;
          const names=(item.stocks??[]).slice(0,3).map(stock=>stock.name).filter(Boolean);
          return <div className="mo-radar-item" key={item.theme}>
            <button type="button" className="mo-radar-row" aria-expanded={expanded}
              title={(item.stage_note||'')+(item.risk?'　风险：'+item.risk:'')} onClick={()=>setOpen(expanded?null:item.theme)}>
              <span className="mo-r-theme"><i className="mo-r-label">主题</i><b>{item.theme||'待取得'}</b>
                <span className="mo-chip mo-kind">{item.kind||'类型待核实'}</span></span>
              <span className="mo-r-stage"><i className="mo-r-label">阶段</i>
                <span className={'mo-stage '+radarStageClass(item.stage)}>{item.stage||'待取得'}</span></span>
              <span className="mo-r-signal"><i className="mo-r-label">信号</i>{radarSignalText(item)}</span>
              <span className="mo-r-stocks"><i className="mo-r-label">标的</i>{names.length?names.join('、'):'先观察（暂无标的）'}</span>
              <span className="mo-r-verdict"><i className="mo-r-label">结论</i>{item.verdict||'待取得'}</span>
            </button>
            {expanded&&<div className="mo-radar-detail">
              {item.stage_note&&<p className="mo-sub">阶段说明：{item.stage_note}</p>}
              <div className="mo-radar-cols">
                <div>
                  <h3>信号</h3>
                  {item.signals?.length?<ul className="mo-list">{item.signals.map((line,index)=><li key={index}>{line}</li>)}</ul>:<p className="mo-wait">待取得</p>}
                  <h3>风险</h3><p className="mo-radar-risk">{item.risk||'待取得'}</p>
                  <h3>观察条件</h3>
                  {item.watch?.length?<ul className="mo-list">{item.watch.map((line,index)=><li key={index}>{line}</li>)}</ul>:<p className="mo-wait">待取得</p>}
                </div>
                <div>
                  <h3>代表股票 <span className="mo-sub">仓位提示：≤0.5 成或只观察</span></h3>
                  {!item.stocks?.length?<p className="mo-wait">先观察，等首批涨停或资金确认。</p>:
                    <div className="mo-scroll"><table className="mo-table mo-radar-stock-table">
                      <thead><tr><th>角色</th><th>股票</th><th>现价</th><th>涨幅</th><th>连板</th><th>均线 / 20 日高低</th><th>买点</th><th>止损</th><th>止盈</th><th>仓位提示</th></tr></thead>
                      <tbody>{item.stocks.map(stock=>{
                        const entry=stock.entry,levels=stock.levels;
                        const t1Pct=targetPercent(stock.price,entry?.target1);
                        return <tr key={stock.code}>
                          <td><span className="mo-role">{stock.role||'角色待取得'}</span></td>
                          <td><b>{stock.name||'待取得'}</b> <span className="mo-code">{stock.code||''}</span>
                            {stock.limit_tag&&<span className="mo-chip">{stock.limit_tag}</span>}
                            {stock.reason&&<span className="mo-sub">{stock.reason}</span>}</td>
                          <td className="mo-num">{numText(stock.price)}</td>
                          <td className={'mo-num'+tone(stock.percent)}>{pctText(stock.percent)}</td>
                          <td className="mo-num">{typeof stock.boards==='number'&&stock.boards>0?stock.boards+' 板':(stock.limit_tag||'—')}</td>
                          <td className="mo-levels">{levels?'MA5 '+numText(levels.ma5)+' · 20 日 '+numText(levels.low20)+'–'+numText(levels.high20):'—'}</td>
                          <td className="mo-entry">{entry?'低吸 '+numText(entry.buy_low)+'–'+numText(entry.buy_high)+' · 追高 '+numText(entry.chase):'待取得'}</td>
                          <td className="mo-num">{numText(entry?.stop)}</td>
                          <td className="mo-sell">{entry?(numText(entry.target1)+(t1Pct!==null?'（+'+t1Pct.toFixed(1)+'%）':'')):'待取得'}</td>
                          <td className="mo-r-sizing">≤0.5 成或只观察</td>
                        </tr>;
                      })}</tbody></table></div>}
                </div>
              </div>
              {!!item.evidence?.length&&<details className="mo-evidence-box"><summary>证据与来源（{item.evidence.length} 条）</summary>
                <ul className="mo-evidence">{item.evidence.map((line,index)=><li key={index}><b>{line.label}</b> {line.value}
                  <span className="mo-sub">来源 {line.source}</span></li>)}</ul></details>}
            </div>}
          </div>;
        })}
      </div>
    </>}
  </section>;
}

function DirectionTabs({directions,assessments,activeCode,onSelect}:{
  directions:Direction[];assessments:Map<string,Assessment>;activeCode:string;onSelect:(code:string)=>void;
}){
  if(!directions.length)return null;
  return <div className="mo-tabs" role="group" aria-label="切换方向">
    {directions.map(direction=>{
      const assessment=assessments.get(direction.sector_code);
      return <button type="button" key={direction.sector_code} className="mo-tab"
        aria-pressed={direction.sector_code===activeCode} onClick={()=>onSelect(direction.sector_code)}>
        <span className="mo-tab-rank">#{direction.rank??'—'}</span><b>{direction.sector}</b>
        {assessment&&<span className={'mo-state '+stateClass(assessment.kind)}>{assessment.kind}</span>}
      </button>;
    })}
  </div>;
}

function DirectionBody({direction,assessment,ctx,enhanced,preview}:{
  direction:Direction|undefined;assessment:Assessment|undefined;ctx:LiveCtx;enhanced:boolean;preview:boolean;
}){
  if(!direction||!assessment)return <p className="mo-wait">{enhanced?'本期没有可展示的方向。':'研判增强尚未生成（等待本机每 30 分钟更新）；方向详情待取得。'}</p>;
  const timing=direction.timing,stocks=direction.stocks??[];
  const candidate=stocks.find(stock=>stock.role==='低吸候选')??stocks.find(stock=>stock.code===direction.candidate?.code)??stocks[0];
  const counts=assessment.checks.length;
  return <>
    <div className="mo-detail-head">
      <h2>{direction.sector} <span className="mo-chip mo-kind">{direction.sector_kind||'类型待核实'}</span></h2>
      <span className={'mo-state '+stateClass(assessment.kind)}>{assessment.kind}</span>
      {assessment.static&&<span className="mo-sub">预览：静态状态，非实时核对</span>}
      <span className="mo-sub">排名 #{direction.rank??'—'} · 综合分 {numText(direction.score)} · 涨幅 {pctText(direction.change)} · 净额 {signedYi(direction.net)}</span>
    </div>
    <p className="mo-why"><b>{assessment.kind}</b> · {assessment.why}{direction.why&&direction.why!==assessment.why?<span className="mo-sub">　研判说明：{direction.why}</span>:null}</p>
    <h3>机会</h3>
    <p>{direction.opportunity||'待取得'}</p>
    {direction.news_title&&<p className="mo-news-title">相关消息：{direction.news_title}</p>}
    <div className="mo-timing">
      <h3>买入时机 <span className="mo-sub">观察窗口 {timing?.window||'待取得'}</span></h3>
      <div className="mo-timing-cols">
        <div><span className="mo-sub">满足什么才买</span>
          {timing?.triggers?.length?<ul className="mo-list">{timing.triggers.map((line,index)=><li key={index}>{line}</li>)}</ul>:<p className="mo-wait">待取得</p>}</div>
        <div><span className="mo-sub">出现什么放弃 / 离场</span>
          {timing?.invalidation?.length?<ul className="mo-list">{timing.invalidation.map((line,index)=><li key={index}>{line}</li>)}</ul>:<p className="mo-wait">待取得</p>}</div>
      </div>
      <div className="mo-gates">
        <span className="mo-sub">{assessment.static?'盘中条件（预览静态，未核对）':'盘中条件（实时核对，共 '+(counts||timing?.gates?.length||0)+' 项）'}</span>
        {assessment.static?<p className="mo-wait">预览模式按后端静态状态展示，未做实时行情核对。</p>:
          assessment.kind==='回避'?<p className="mo-wait">该方向命中回避规则，不评估盘中条件。</p>:
          counts?<ul>{assessment.checks.map(check=><li key={check.kind} className={check.ok===true?'ok':check.ok===false?'bad':'unknown'}>
            <span className="mo-gate-mark">{check.ok===true?'已满足':check.ok===false?'未满足':'待核对'}</span>{check.text}</li>)}</ul>
            :<p className="mo-wait">行情待核对，暂不评估盘中条件。</p>}
      </div>
    </div>
    <h3>重点股票</h3>
    {!stocks.length?<p className="mo-wait">重点股票待取得</p>:<div className="mo-scroll"><table className="mo-table mo-stock-table">
      <thead><tr><th>角色</th><th>股票</th><th>现价</th><th>涨幅</th><th>成交额</th><th>连板</th><th>均线 / 20 日高低</th><th>买点</th><th>卖点</th></tr></thead>
      <tbody>{stocks.map(stock=>{
        const live=preview?undefined:ctx.quotes.get(stock.code);
        const price=live?live.price:stock.price,percent=live?live.pct:stock.percent,amount=live?.amount??stock.amount_yuan;
        const levels=stock.levels,entry=stock.entry;
        const t1Pct=targetPercent(price,entry?.target1);
        return <tr key={stock.code}>
          <td><span className="mo-role">{stock.role||'角色待取得'}</span></td>
          <td><b>{stock.name||'待取得'}</b> <span className="mo-code">{stock.code||''}</span>
            {stock.limit_tag&&<span className="mo-chip">{stock.limit_tag}</span>}
            {stock.reason&&<span className="mo-sub">{stock.reason}</span>}</td>
          <td className="mo-num">{numText(price)}{live?<span className="mo-sub"> 实时</span>:null}</td>
          <td className={'mo-num'+tone(percent)}>{pctText(percent)}</td>
          <td className="mo-num">{amountText(amount)}</td>
          <td className="mo-num">{typeof stock.boards==='number'&&stock.boards>0?stock.boards+' 板':(stock.limit_tag||'—')}</td>
          <td className="mo-levels">{levels?'MA5 '+numText(levels.ma5)+' · MA10 '+numText(levels.ma10)+' · MA20 '+numText(levels.ma20)+' · 20 日 '+numText(levels.low20)+'–'+numText(levels.high20):'日线待取得'}</td>
          <td className="mo-entry">{entry?'低吸 '+numText(entry.buy_low)+'–'+numText(entry.buy_high)+' · 追高 '+numText(entry.chase)+' · 止损 '+numText(entry.stop):'待取得'}</td>
          <td className="mo-sell" title={entry?.sell_note||''}>{entry?('目标 '+numText(entry.target1)+(t1Pct!==null?'（+'+t1Pct.toFixed(1)+'%）':'')+' / '+numText(entry.target2)+' · 移动止损 '+numText(entry.trail)):'待取得'}</td>
        </tr>;
      })}</tbody></table></div>}
    {candidate?.entry?.note&&<p className="mo-entry-note">买入提示：{candidate.entry.note}</p>}
    {candidate?.entry?.sell_note&&<p className="mo-entry-note mo-sell-note">卖出提示：{candidate.entry.sell_note}</p>}
    <h3>逻辑</h3>
    {direction.logic?.length?<ul className="mo-list">{direction.logic.map((line,index)=><li key={index}>{line}</li>)}</ul>:<p className="mo-wait">待取得</p>}
    <h3>风险</h3><p>{direction.risk||'待取得'}</p>
    {!!direction.evidence?.length&&<details className="mo-evidence-box"><summary>证据与来源（{direction.evidence.length} 条）</summary>
      <ul className="mo-evidence">{direction.evidence.map((item,index)=><li key={index}><b>{item.label}</b> {item.value}
        <span className="mo-sub">来源 {item.source}</span></li>)}</ul></details>}
  </>;
}



function ActionPlan({issue}:{issue:Issue}){
  const playbooks=issue.playbooks??[],timetable=issue.timetable??[],risk=issue.risk??[];
  return <section className="card mo-action" aria-label="行动计划">
    <h2>行动计划</h2>
    <h3>剧本</h3>
    {!playbooks.length?<p className="mo-wait">待取得</p>:<div className="mo-playbooks">{playbooks.map((playbook,index)=><div key={playbook.name+index} className={'mo-playbook'+(playbook.active?' active':'')}>
      <div className="mo-playbook-head"><b>{playbook.name}</b>{playbook.active&&<span className="mo-chip mo-active">当前适用</span>}
        <span className="mo-sub">{playbook.position||'仓位待取得'}</span></div>
      {!!playbook.conditions?.length&&<ul className="mo-list">{playbook.conditions.map((line,position)=><li key={position}>{line}</li>)}</ul>}
      <p>{playbook.action||'操作待取得'}</p>
    </div>)}</div>}
    <h3>时间表</h3>
    {!timetable.length?<p className="mo-wait">待取得</p>:<div className="mo-scroll"><table className="mo-table mo-timetable">
      <thead><tr><th>时间</th><th>看点</th><th>规则</th></tr></thead>
      <tbody>{timetable.map((row,index)=><tr key={row.time+index}><td>{row.time}</td><td>{row.focus}</td><td>{row.rule}</td></tr>)}</tbody>
    </table></div>}
    <h3>风险</h3>
    {!risk.length?<p className="mo-wait">待取得</p>:<ul className="mo-list mo-risk">{risk.map((line,index)=><li key={index}>{line}</li>)}</ul>}
  </section>;
}

function Coverage({issue,report,preview,failed,ctx,directions,assessments}:{
  issue:Issue;report:Report;preview:boolean;failed:boolean;ctx:LiveCtx;
  directions:Direction[];assessments:Map<string,Assessment>;
}){
  const [query,setQuery]=useState('');
  const themes:PoolTheme[]=[...(issue.themes??[]),...Object.entries(issue.directory??{}).map(([code,name]):PoolTheme=>({code,name}))];
  const seen=new Set<string>();
  const pool=themes.filter(theme=>{
    const key=theme.code??theme.name;
    if(seen.has(key))return false;
    seen.add(key);return true;
  });
  const trimmed=query.trim().toLowerCase();
  const searched=trimmed?pool.filter(theme=>theme.name.toLowerCase().includes(trimmed)):[];
  const status=preview?'浏览器只读预览样本（静态状态）':failed?'读取失败 · 15 秒后自动重试':ctx.valid?'行情已核对':'行情待核对';
  return <section className="card mo-coverage" aria-label="数据覆盖">
    <h2>数据覆盖 <span className="mo-sub">数据缺口与未核实项逐条列出</span></h2>
    {!issue.warnings?.length?<p className="mo-wait">本期没有记录数据缺口。</p>:
      <ul className="mo-list mo-warnings">{issue.warnings.map((line,index)=><li key={index}>{line}</li>)}</ul>}
    <div className="mo-stat-grid">
      <div className="mo-stat"><span>行业覆盖</span><b>{issue.coverage?.industry??'待取得'} 个</b></div>
      <div className="mo-stat"><span>概念覆盖</span><b>{issue.coverage?.concept??'待取得'} 个</b></div>
      <div className="mo-stat"><span>补充题材</span><b>{issue.coverage?.disclosed??'待取得'} 个</b></div>
      <div className="mo-stat"><span>未取齐方向</span><b>{issue.coverage?.unavailable??0} 个</b></div>
      <div className="mo-stat"><span>行情日期</span><b>{report.day??issue.quote_date??'待取得'}</b></div>
      <div className="mo-stat"><span>研判生成</span><b>{stampText(issue.published_at)}</b></div>
      <div className="mo-stat"><span>筛前版本</span><b>screen_version {issue.screen_version??'待取得'}</b></div>
      <div className="mo-stat"><span>数据更新状态</span><b>{status}</b></div>
    </div>
    {issue.discovery&&<p className="mo-sub">近 {issue.discovery.days} 个交易日识别 {issue.discovery.observed} 个热点{issue.discovery.failed_days?'，其中 '+issue.discovery.failed_days+' 天异动未取齐':''}。</p>}
    {report.preview_note&&<p className="mo-sub">{report.preview_note}</p>}
    <details className="mo-search">
      <summary>查某个方向为什么没入选</summary>
      <label>行业、概念或题材名称<input value={query} onChange={event=>setQuery(event.target.value)} placeholder="输入名称查询本期结果"/></label>
      {trimmed&&!searched.length?<p className="mo-wait">本期数据中没有识别到这个名称，无法判断。</p>:null}
      {searched.slice(0,10).map(theme=>{
        const code=theme.code??'';
        const direction=directions.find(row=>row.sector_code===code);
        const assessment=direction?assessments.get(code):undefined;
        const why=direction?('本期入选：排名第 '+(direction.rank??'—')+'，状态 '+(assessment?.kind??'待核对')+'。'):
          (issue.exclusions?.[code]||'本期未入选，数据覆盖中没有记录具体原因。');
        return <div className="mo-search-result" key={code+theme.name}>
          <p><b>{theme.name}</b> <span className="mo-sub">{why}</span></p>
          {theme.members&&theme.members.length>0&&<p className="mo-sub">已核对 {theme.members.length} 家公司{typeof theme.advance==='number'?'，'+theme.advance+' 家上涨':''}{typeof theme.net==='number'?'，净额 '+signedYi(theme.net):''}。</p>}
        </div>;
      })}
    </details>
  </section>;
}

export default function MarketOpportunity({request,preview}:{request:Request;preview:boolean}){
  const [data,setData]=useState<{report:Report;day?:BreadthDay}>();
  const [failed,setFailed]=useState(false);
  const [now,setNow]=useState(()=>Date.now());
  const [selected,setSelected]=useState('');
  useEffect(()=>{
    let alive=true,pending=false;
    async function read(){
      if(pending)return;
      pending=true;
      try{
        let report:Report,day:BreadthDay|undefined;
        if(preview){
          const response=await fetch('/opportunity-preview.json');
          report=response.ok?await response.json() as Report:{issue:null,quotes:[],sectors:{},day:null,batch:null,schedule:'预览'};
        }else{
          const breadth=await requestWithTimeout(request<BreadthReport>('breadth'));
          const view=breadthView(breadth.days?.at(-1),breadth.error,Date.now());
          day=view?.day;
          report=await requestWithTimeout(request<Report>('daily_outlook',{day:day?.date,batch:day?.collected_at}));
        }
        if(alive){setData({report,day});setFailed(false);setNow(Date.now());}
      }catch{
        if(alive){setFailed(true);setNow(Date.now());}
      }finally{pending=false;}
    }
    void read();
    const timer=setInterval(read,15000);
    return ()=>{alive=false;clearInterval(timer);};
  },[request,preview]);
  const report=data?.report;
  const issue=report?.issue??null;
  if(!report||!issue)return <section className="card market-opportunity mo-empty" aria-label="市场机会研判">
      <h2>市场机会</h2>
      <p className="mo-empty-title">今日研判尚未生成</p>
      <p className="mo-sub">每 15 秒自动检查；生成后会显示定调、仓位与未来 1–3 个交易日的建仓方向。{preview?'当前为浏览器只读预览。':''}{failed?'最近一次读取失败，正在自动重试。':''}</p>
    </section>;
  const ctx=liveContext(report,data?.day,now);
  const pulse=issue.pulse??null;
  const picks=issue.top_picks??[];
  const radar=issue.radar??[];
  const enhanced=!!(pulse||issue.directions?.length||issue.focus||picks.length);
  const directions=[...(issue.directions??[])].sort((left,right)=>Number(left.rank)-Number(right.rank));
  const assessments=new Map<string,Assessment>(directions.map(direction=>[direction.sector_code,preview?assessStatic(direction):assess(direction,ctx,data?.day,report)]));
  const focus=issue.focus??null;
  const activeDirection=directions.find(direction=>direction.sector_code===selected)??directions.find(direction=>direction.sector_code===focus?.sector_code)??directions[0];
  const activeAssessment=activeDirection?assessments.get(activeDirection.sector_code):undefined;
  const kindCount=(kind:LiveKind)=>[...assessments.values()].filter(assessment=>assessment.kind===kind).length;
  const readyCount=kindCount('可考虑建仓'),waitCount=kindCount('继续等'),staleCount=kindCount('行情待核对'),weakCount=kindCount('已转弱');
  const otherCount=directions.length-readyCount-waitCount-staleCount-weakCount;
  const directionSummary='共 '+directions.length+' 个方向 · 可考虑建仓 '+readyCount+' 条 · 继续等 '+waitCount+' 条'+
    (weakCount?' · 已转弱 '+weakCount+' 条':'')+(staleCount?' · 行情待核对 '+staleCount+' 条':'')+(otherCount?' · 观察/回避 '+otherCount+' 条':'');
  const biasClass=issue.bias==='进攻'?'attack':issue.bias==='防守'?'defend':issue.bias==='试错'?'probe':'';
  const status=preview?'浏览器只读预览样本（静态状态）':failed?'读取失败 · 15 秒后自动重试':ctx.valid?'行情已核对':'行情待核对';
  const market=pulse?.market??null,sentiment=pulse?.sentiment??null;
  const focusLine=focus?(focus.summary||('首选 '+focus.sector+' · '+(focus.candidate?.name||'待取得')+'：'+(focus.why||'待取得'))):
    (directions.length?'首选 '+directions[0].sector+' · '+(directions[0].candidate?.name||'待取得')+'：'+(directions[0].why||'待取得'):'');
  const marketSummary=market?('上证 '+pctText(market.indices?.[0]?.percent)+' · 上涨占比 '+pctText(market.breadth?.advancing_percent)+
    ' · 涨停 '+(sentiment?.limit_up?.today??'待取得')+'/'+(sentiment?.limit_up?.yesterday??'待取得')+' · 成交额比 '+numText(market.breadth?.amount_ratio)):'待取得';
  const activePlaybook=(issue.playbooks??[]).find(playbook=>playbook.active);
  const actionSummary=activePlaybook?('当前剧本 '+activePlaybook.name+' · '+(activePlaybook.position||'仓位待取得')):'待取得';
  const rankSummary=enhanced?directionSummary+' · 数据缺口 '+(issue.warnings?.length??0)+' 条':'待取得';
  return <section className="market-opportunity" aria-label="市场机会研判">
    <section className="card mo-verdict" aria-label="研判定调">
      <div className="mo-verdict-main">
        <h2>{issue.verdict||'定调待取得'}</h2>
        {issue.bias&&<span className={'mo-badge mo-bias '+(biasClass||'')}>{issue.bias}</span>}
        <span className="mo-position">{issue.position||'仓位建议待取得'}</span>
      </div>
      <div className="mo-meta">
        <span>研判窗口 {issue.horizon||'待取得'}</span>
        <span>行情日期 {report.day??issue.quote_date??'待取得'}</span>
        <span>定调生成 {stampText(issue.published_at)}</span>
        <span className="mo-data-state">数据更新状态 <b>{status}</b></span>
        {preview&&<span className="mo-chip mo-preview">浏览器只读预览</span>}
      </div>
      <p className="mo-focus-line">{enhanced?(focusLine||'本期没有首选方向，等待下一轮研判。'):'研判增强尚未生成（等待本机每 30 分钟更新）；首选方向与建仓清单待取得。'}</p>
      {!enhanced&&<p className="mo-wait mo-compat">旧格式研判：观测卡与方向排名收在下方折叠区，展开后显示待取得。</p>}
    </section>
    <section className="card mo-picks" aria-label="建仓清单">
      <BuildList picks={picks} assessments={assessments} selected={activeDirection?.sector_code??''} onSelect={setSelected}
        preview={preview} enhanced={enhanced}/>
    </section>
    <RadarCard radar={radar} summary={issue.radar_summary||''} preview={preview}/>
    <section className="card mo-detail" id="mo-direction-detail" aria-label="方向详情">
      <DirectionTabs directions={directions} assessments={assessments} activeCode={activeDirection?.sector_code??''} onSelect={setSelected}/>
      <DirectionBody direction={activeDirection} assessment={activeAssessment} ctx={ctx} enhanced={enhanced} preview={preview}/>
    </section>
    <details className="mo-fold mo-fold-market">
      <summary>市场背景 <span className="mo-sub">{enhanced?marketSummary:'待取得'}</span></summary>
      <section className="mo-fold-body" aria-label="市场背景">
        <div className="mo-cards">
          <MarketCard market={market}/>
          <CapitalCard capital={pulse?.capital??null}/>
          <SentimentCard sentiment={sentiment}/>
          <HotspotCard hotspots={pulse?.hotspots??null} fallbackReasons={sentiment?.hot_reasons??null}/>
        </div>
      </section>
    </details>
    <details className="mo-fold mo-fold-action">
      <summary>行动计划 <span className="mo-sub">{enhanced?actionSummary:'待取得'}</span></summary>
      <ActionPlan issue={issue}/>
    </details>
    <details className="mo-fold mo-fold-rank">
      <summary>方向排名与数据覆盖 <span className="mo-sub">{enhanced?rankSummary:'待取得'}</span></summary>
      <section className="card mo-directions" aria-label="方向排名">
        <h2>方向排名 <span className="mo-sub">按综合分排序；{preview?'预览模式展示后端静态状态，未做实时行情核对':'盘中状态由本批行情实时核对'}</span></h2>
        <DirectionTable directions={directions} assessments={assessments} activeCode={activeDirection?.sector_code??''} onSelect={setSelected} enhanced={enhanced}/>
      </section>
      <Coverage issue={issue} report={report} preview={preview} failed={failed} ctx={ctx}
        directions={directions} assessments={assessments}/>
    </details>
  </section>;
}

