import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import './focusPool.css';
import StockSearch from './StockSearch';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Plan={buy_low:number|null;buy_high:number|null;chase:number|null;stop:number|null;target1:number|null;target2:number|null;trail:number|null;note:string|null;sell_note:string|null};
type Quote={price:number;percent:number;time:string;low?:number|null;high?:number|null;basis?:'live'|'last'|'added';fresh?:boolean};
type HistoryRow={day:string;price:number;percent:number;high:number|null;low:number|null;hit_buy:boolean;hit_stop:boolean;hit_target:boolean};
type EntryWindow={n?:number;date?:string|null;close?:number|null;return_percent?:number|null;benchmark_return?:number|null;excess_percent?:number|null};
type Entry={code:string;name:string;added_day:string;added_at?:string|null;added_price:number;source:string;sector:string;role:string;reason:string;state:string;
  entry_tag:string;category:string;group_name:string;groups?:string[];group_rank?:number|null;group_size?:number|null;updated_at:string;
  plan:Plan|null;quote:Quote|null;today_percent:number|null;since_add_percent:number|null;distance_to_buy_percent:number|null;zone:string;hint:string;
  history:HistoryRow[];max_gain_percent:number|null;max_drawdown_percent:number|null;hold_days:number|null;
  windows?:Record<string,EntryWindow|null>|null;holding_days?:number|null;holding_bucket?:string|null};
type WindowStat={sample:number;win_rate:number|null;avg_return_percent:number|null;beat_rate:number|null;avg_excess_percent:number|null};
type WindowStats=Partial<Record<'T+1'|'T+3'|'T+5',WindowStat>>;
type HoldingStat={bucket:string;label:string;count:number;sample:number;win_rate:number|null;avg_since_percent:number|null};
type Summary={total:number;sample:number;wins:number;losses:number;flat:number;win_rate:number|null;avg_since_percent:number|null;
  median_since_percent:number|null;max_since_percent:number|null;min_since_percent:number|null;avg_today_percent:number|null;
  avg_max_gain_percent:number|null;avg_max_drawdown_percent:number|null;ready:number;limit_up:number;above_chase:number;waiting:number;
  speculative:number;manual:number;bought:number;exited:number;in_zone:number;target_hits?:number;stop_hits?:number;buy_zone_hits?:number};
type Group={category:string;count:number;sample:number;win_rate:number|null;avg_since_percent:number|null};
type Counts={total:number;ready:number;limit_up:number;above_chase:number;waiting:number;speculative:number;manual:number;bought:number;exited:number;ignored:number};
type TagStat={entry_tag:string;count:number;sample:number;win_rate:number|null;avg_since_percent:number|null};
type PoolData={updated_at:string|null;quotes_time:string|null;trading?:boolean;error?:string;summary:Summary|null;counts?:Counts|null;
  tag_stats?:TagStat[]|null;groups:Group[];entries:Entry[];filtered_total?:number;has_more?:boolean;offset?:number;limit?:number;filters?:unknown;
  windows?:WindowStats|null;holding?:HoldingStat[]|null;benchmark?:string|null;daily_ready?:boolean|null;archived_count?:number|null};

type FilterState={period:string;group:string;status:string;sort:string;startDay:string;endDay:string;holding:string;includeArchived:boolean};
const DEFAULT_FILTERS:FilterState={period:'近3日',group:'全部',status:'全部',sort:'自入选涨幅',startDay:'',endDay:'',holding:'全部',includeArchived:false};
const WINDOW_KEYS:['T+1'|'T+3'|'T+5',string][]=[['T+1','T+1'],['T+3','T+3'],['T+5','T+5']];
const STORAGE_KEY='stock-monitor-pool-filters';
function readFilters():FilterState{
  try{
    const raw=localStorage.getItem(STORAGE_KEY);
    if(!raw)return DEFAULT_FILTERS;
    const parsed=JSON.parse(raw) as Partial<FilterState>;
    return {...DEFAULT_FILTERS,...parsed};
  }catch{return DEFAULT_FILTERS;}
}

const CATEGORIES=['行业','概念','题材','事件','名称辈','生肖玄学','手动','其他'];
const STATUS_CHIPS:[string,keyof Counts][]=[['可建仓','ready'],['涨停待回踩','limit_up'],['高于追高上限','above_chase'],['条件未达','waiting'],['题材观察','speculative']];
const PERIODS=[['全部','全部'],['今日','今日'],['近3日','近3交易日'],['近5日','近5交易日'],['近10日','近10交易日'],['自定义','自定义']];
const SORTS=['自入选涨幅','今日涨幅','入选日','状态'];
const TAGS=['可建仓','涨停待回踩','高于追高上限','条件未达','题材观察','观察'];
const numText=(value:number|null|undefined,digits=2)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(digits):'待取得';
const pctText=(value:number|null|undefined,digits=2)=>typeof value==='number'&&Number.isFinite(value)?(value>0?'+':'')+value.toFixed(digits)+'%':'待取得';
const pctOrDash=(value:number|null|undefined,digits=2)=>typeof value==='number'&&Number.isFinite(value)?(value>0?'+':'')+value.toFixed(digits)+'%':'—';
const rateText=(value:number|null|undefined,digits=1)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(digits)+'%':'—';
const sign=(value:number|null|undefined)=>typeof value==='number'?(value>0?' positive':value<0?' negative':''):'';
const timeText=(value:string|null|undefined)=>{if(!value)return '待取得';return value.length>=16?value.slice(11,16):value;};
const shortDay=(value:string|null|undefined)=>{if(!value)return '待取得';return value.length>=10?value.slice(5):value;};
const addedTimeLabel=(entry:Entry)=>{
  if(entry.added_at&&entry.added_at.length>=16)return entry.added_at.slice(5,10)+' '+entry.added_at.slice(11,16);
  return shortDay(entry.added_day);
};
const stampText=(value:string|null|undefined)=>{if(!value)return '待取得';return value.length>=16?value.slice(0,10)+' '+value.slice(11,16):value;};
const tagClass=(tag:string)=>tag==='可建仓'?'ready':tag==='涨停待回踩'?'limit':tag==='高于追高上限'?'chase':tag==='条件未达'?'wait':tag==='题材观察'?'speculative':'watch';
const tagOrder=(tag:string)=>{const index=STATUS_CHIPS.findIndex(([value])=>value===tag);return index<0?STATUS_CHIPS.length:index;};
const entryGroups=(entry:Entry)=>entry.groups?.length?entry.groups:[entry.category||'其他'];
const dateMinus=(day:string,offset:number)=>{const value=new Date(day+'T00:00:00Z');value.setUTCDate(value.getUTCDate()-offset);return value.toISOString().slice(0,10);};
const round=(value:number)=>Math.round(value*100)/100;
const average=(values:number[])=>values.length?round(values.reduce((sum,value)=>sum+value,0)/values.length):null;
const median=(values:number[])=>{if(!values.length)return null;const sorted=[...values].sort((a,b)=>a-b);const middle=Math.floor(sorted.length/2);return round(sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2);};

function previousTradingDay(anchor:string,offset:number){
  const value=new Date(anchor+'T00:00:00Z');
  let remaining=Math.max(0,offset);
  while(remaining>0){
    value.setUTCDate(value.getUTCDate()-1);
    const weekday=value.getUTCDay();
    if(weekday!==0&&weekday!==6)remaining--;
  }
  return value.toISOString().slice(0,10);
}
function filterByTime(rows:Entry[],filters:FilterState,anchor:string){
  if(filters.period==='全部')return rows;
  let start=filters.startDay,end=filters.endDay;
  if(filters.period!=='自定义'){
    const days=filters.period==='今日'?1:filters.period==='近3日'?3:filters.period==='近5日'?5:10;
    // 与后端一致：按“交易日”向前数，跳过周末（近3日=11-05/11-06/11-09）
    start=previousTradingDay(anchor,days-1);end=anchor;
  }
  return rows.filter(row=>(!start||row.added_day>=start)&&(!end||row.added_day<=end));
}
function Info({label,children}:{label:string;children:ReactNode}){
  const [open,setOpen]=useState(false);
  const ref=useRef<HTMLSpanElement>(null);
  useEffect(()=>{
    if(!open)return;
    const closeOutside=(event:PointerEvent)=>{
      if(event.target instanceof Node&&!ref.current?.contains(event.target))setOpen(false);
    };
    document.addEventListener('pointerdown',closeOutside,true);
    return ()=>document.removeEventListener('pointerdown',closeOutside,true);
  },[open]);
  return <span className="fp-info" ref={ref}>
    <button type="button" aria-label={label} aria-expanded={open} title={label} onClick={()=>setOpen(value=>!value)}>i</button>
    {open&&<div className="fp-info-body">{children}</div>}
  </span>;
}
function buildPreviewData(source:PoolData,filters:FilterState):PoolData{
  const all=source.entries??[];
  const anchor=(source.updated_at??source.quotes_time??'')[0]===undefined?'2026-11-09':(source.updated_at??source.quotes_time??'').slice(0,10)||'2026-11-09';
  const timeRows=filterByTime(all,filters,anchor).map(entry=>{
    const same=all.filter(row=>row.category===entry.category);
    const ordered=[...same].sort((left,right)=>(right.since_add_percent??-999)-(left.since_add_percent??-999));
    const rank=ordered.findIndex(row=>row.code===entry.code)+1;
    return {...entry,groups:entryGroups(entry),group_rank:rank,group_size:ordered.length};
  });
  const countTag=(tag:string)=>timeRows.filter(row=>row.entry_tag===tag).length;
  const counts:Counts={total:timeRows.length,ready:countTag('可建仓'),limit_up:countTag('涨停待回踩'),above_chase:countTag('高于追高上限'),
    waiting:countTag('条件未达'),speculative:countTag('题材观察'),manual:timeRows.filter(row=>row.category==='手动').length,
    bought:timeRows.filter(row=>row.state==='已买入').length,exited:timeRows.filter(row=>row.state==='已退出').length,
    ignored:timeRows.filter(row=>row.state==='忽略').length};
  const tag_stats=TAGS.map(tag=>{
    const rows=timeRows.filter(row=>row.entry_tag===tag);
    if(!rows.length)return null;
    const sample=rows.filter(row=>row.quote&&Number.isFinite(row.since_add_percent));
    const wins=sample.filter(row=>row.since_add_percent!>0).length;
    return {entry_tag:tag,count:rows.length,sample:sample.length,win_rate:sample.length?round(100*wins/sample.length):null,
      avg_since_percent:average(sample.map(row=>row.since_add_percent as number))};
  }).filter((item):item is TagStat=>Boolean(item));
  const groups=CATEGORIES.map(category=>{
    const members=timeRows.filter(row=>entryGroups(row).includes(category));
    if(!members.length)return null;
    const sample=members.filter(row=>row.quote&&Number.isFinite(row.since_add_percent));
    const wins=sample.filter(row=>(row.since_add_percent??0)>0).length;
    return {category,count:members.length,sample:sample.length,win_rate:sample.length?round(100*wins/sample.length):null,
      avg_since_percent:average(sample.map(row=>row.since_add_percent as number))};
  }).filter((item):item is Group=>Boolean(item));
  let rows=timeRows;
  if(filters.group!=='全部')rows=rows.filter(row=>entryGroups(row).includes(filters.group));
  if(filters.status!=='全部')rows=rows.filter(row=>row.entry_tag===filters.status);
  if(filters.holding!=='全部')rows=rows.filter(row=>row.holding_bucket===filters.holding);
  const sample=rows.filter(row=>row.quote&&Number.isFinite(row.since_add_percent));
  const wins=sample.filter(row=>(row.since_add_percent??0)>0).length;
  const sinceValues=sample.map(row=>row.since_add_percent as number);
  const todayValues=rows.filter(row=>Number.isFinite(row.today_percent)).map(row=>row.today_percent as number);
  const gainValues=rows.filter(row=>Number.isFinite(row.max_gain_percent)).map(row=>row.max_gain_percent as number);
  const drawValues=rows.filter(row=>Number.isFinite(row.max_drawdown_percent)).map(row=>row.max_drawdown_percent as number);
  const summary:Summary={total:rows.length,sample:sample.length,wins,
    losses:sample.filter(row=>(row.since_add_percent??0)<0).length,
    flat:sample.filter(row=>row.since_add_percent===0).length,
    win_rate:sample.length?round(100*wins/sample.length):null,
    avg_since_percent:average(sinceValues),median_since_percent:median(sinceValues),
    max_since_percent:sinceValues.length?Math.max(...sinceValues):null,
    min_since_percent:sinceValues.length?Math.min(...sinceValues):null,
    avg_today_percent:average(todayValues),avg_max_gain_percent:average(gainValues),avg_max_drawdown_percent:average(drawValues),
    ready:counts.ready,limit_up:counts.limit_up,above_chase:counts.above_chase,waiting:counts.waiting,speculative:counts.speculative,
    manual:counts.manual,bought:counts.bought,exited:counts.exited,
    in_zone:rows.filter(row=>row.zone==='已进入买区').length,
    target_hits:rows.reduce((sum,row)=>sum+(row.history??[]).filter(item=>item.hit_target).length,0),
    stop_hits:rows.reduce((sum,row)=>sum+(row.history??[]).filter(item=>item.hit_stop).length,0),
    buy_zone_hits:rows.reduce((sum,row)=>sum+(row.history??[]).filter(item=>item.hit_buy).length,0)};
  const windowStats=(key:string):WindowStat=>{
    const sampled=timeRows.filter(row=>(row.windows??{})[key]);
    const returns=sampled.map(row=>row.windows?.[key]?.return_percent).filter((value):value is number=>typeof value==='number'&&Number.isFinite(value));
    const excess=sampled.map(row=>row.windows?.[key]?.excess_percent).filter((value):value is number=>typeof value==='number'&&Number.isFinite(value));
    const wins=returns.filter(value=>value>0).length;
    const beats=excess.filter(value=>value>0).length;
    return {sample:returns.length,win_rate:returns.length?round(100*wins/returns.length):null,
      avg_return_percent:average(returns),beat_rate:excess.length?round(100*beats/excess.length):null,avg_excess_percent:average(excess)};
  };
  const holdingLabels:Record<string,string>={'0':'0日','1':'1日','2':'2日','3-5':'3–5日','6-10':'6–10日','10+':'10日以上'};
  const holding=Object.keys(holdingLabels).map(bucket=>{
    const members=timeRows.filter(row=>row.holding_bucket===bucket);
    if(!members.length)return null;
    const sampled=members.filter(row=>row.quote&&Number.isFinite(row.since_add_percent));
    const wins=sampled.filter(row=>(row.since_add_percent??0)>0).length;
    return {bucket,label:holdingLabels[bucket],count:members.length,sample:sampled.length,
      win_rate:sampled.length?round(100*wins/sampled.length):null,
      avg_since_percent:average(sampled.map(row=>row.since_add_percent as number))};
  }).filter((item):item is HoldingStat=>Boolean(item));
  const windows:WindowStats={'T+1':windowStats('T+1'),'T+3':windowStats('T+3'),'T+5':windowStats('T+5')};
  return {...source,summary,counts,tag_stats,groups,windows,holding,entries:rows,filtered_total:rows.length,has_more:false,offset:0,limit:60,filters};
}

export default function FocusPool({request,preview,active,onOpenDaily,onTrade,watch}:{
  request:Request;preview:boolean;active:boolean;onOpenDaily:(code:string,name:string)=>void;
  onTrade:(payload:{code:string;name:string;side:'buy'|'sell'})=>void;watch:string[];
}){
  const [filters,setFilters]=useState<FilterState>(()=>readFilters());
  const {period,group,status,sort,startDay,endDay,holding,includeArchived}=filters;
  const patch=(next:Partial<FilterState>)=>setFilters(previous=>({...previous,...next}));
  useEffect(()=>{try{localStorage.setItem(STORAGE_KEY,JSON.stringify(filters));}catch{}},[filters]);
  const [data,setData]=useState<PoolData>();
  const dataRef=useRef<PoolData|undefined>(undefined);
  dataRef.current=data;
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [input,setInput]=useState('');
  const [busy,setBusy]=useState(false);
  const [loadingMore,setLoadingMore]=useState(false);
  const [exporting,setExporting]=useState(false);
  const [exportInfo,setExportInfo]=useState<{csv?:string;report?:string;count?:number}|null>(null);
  const [openCode,setOpenCode]=useState('');
  const [windowsOpen,setWindowsOpen]=useState(()=>{try{return localStorage.getItem('stock-monitor-pool-windows')!=='0';}catch{return true;}});
  const [holdingOpen,setHoldingOpen]=useState(()=>{try{return localStorage.getItem('stock-monitor-pool-holding')!=='0';}catch{return true;}});
  useEffect(()=>{try{localStorage.setItem('stock-monitor-pool-windows',windowsOpen?'1':'0');}catch{}},[windowsOpen]);
  useEffect(()=>{try{localStorage.setItem('stock-monitor-pool-holding',holdingOpen?'1':'0');}catch{}},[holdingOpen]);
  const sequence=useRef(0);
  const baseParams=useMemo(()=>{
    const params:Record<string,unknown>={};
    if(period!=='全部'&&period!=='自定义'&&period!=='今日'){}
    if(period==='自定义'){
      if(startDay)params.start=startDay;
      if(endDay)params.end=endDay;
    }else if(period==='今日')params.days=1;
    else if(period==='近3日')params.days=3;
    else if(period==='近5日')params.days=5;
    else if(period==='近10日')params.days=10;
    if(group!=='全部')params.group=group;
    if(status!=='全部')params.status=status;
    if(holding!=='全部')params.holding=holding;
    params.include_archived=includeArchived;
    return params;
  },[period,group,status,startDay,endDay,holding,includeArchived]);
  const queryKey=JSON.stringify(baseParams);
  useEffect(()=>{
    if(!active)return;
    let alive=true,pending=false;
    async function read(mode:'reset'|'refresh'){
      if(pending)return;
      pending=true;
      const seq=++sequence.current;
      const loaded=mode==='refresh'?dataRef.current?.entries.length??0:0;
      const limit=Math.max(60,loaded);
      try{
        const next=preview
          ?await fetch('/pool-preview.json').then(response=>response.ok?response.json() as Promise<PoolData>:{updated_at:null,quotes_time:null,summary:null,groups:[],entries:[],error:'股票池暂无预览数据'})
          :await request<PoolData>('pool',{...baseParams,limit,offset:0});
        if(!alive||seq!==sequence.current)return;
        setData(next);setError(next.error||'');
      }catch(cause){
        if(alive&&seq===sequence.current)setError(cause instanceof Error?cause.message:'股票池读取失败');
      }finally{pending=false;}
    }
    setData(previous=>previous?{...previous,entries:[],has_more:false}:undefined);
    void read('reset');
    const timer=preview?undefined:setInterval(()=>void read('refresh'),6000);
    return ()=>{alive=false;if(timer!==undefined)clearInterval(timer);};
  },[active,preview,request,queryKey]);
  const viewData=useMemo(()=>{
    if(!data)return undefined;
    return preview?buildPreviewData(data,filters):data;
  },[data,preview,filters]);
  const summary=viewData?.summary??null;
  const counts=viewData?.counts??(summary?{total:summary.total,ready:summary.ready,limit_up:summary.limit_up,above_chase:summary.above_chase,
    waiting:summary.waiting,speculative:summary.speculative,manual:summary.manual,bought:summary.bought,exited:summary.exited,ignored:0}:undefined);
  const tagStats=viewData?.tag_stats??[];
  const groups=viewData?.groups??[];
  const rawEntries=viewData?.entries??[];
  const readOnly=preview;
  const watched=new Set((watch||[]).map(code=>String(code).toLowerCase()));
  const isWatched=(code:string)=>watched.has(String(code).toLowerCase());
  const refetch=async()=>{
    try{
      const next=preview?await fetch('/pool-preview.json').then(response=>response.json() as Promise<PoolData>):await request<PoolData>('pool',{...baseParams,limit:Math.max(60,data?.entries.length??0),offset:0});
      setData(next);setError(next.error||'');
    }catch(cause){setError(cause instanceof Error?cause.message:'股票池读取失败');}
  };
  async function exportReview(){
    if(readOnly){setMessage('浏览器只读预览不支持导出；请在桌面客户端操作。');return;}
    setExporting(true);setError('');
    try{
      const result=await request<{csv?:string;report?:string;count?:number}>('pool_export',{...baseParams});
      setExportInfo(result??{});
    }catch(cause){setError(cause instanceof Error?cause.message:'导出失败');}
    finally{setExporting(false);}
  }
  function pick(payload:{code:string;name:string;side:'buy'|'sell'}){
    if(readOnly){setMessage('浏览器预览为只读；请在桌面客户端操作。');return;}
    onTrade(payload);
  }
  async function addWatch(entry:Entry){
    if(isWatched(entry.code)){setMessage(entry.name+' 已在自选监控中。');return;}
    if(readOnly){setMessage('浏览器预览为只读；请在桌面客户端操作。');return;}
    setBusy(true);setError('');
    try{await request('add_job',{code:entry.code});setMessage('已请求加入自选：'+entry.name+'。');}
    catch(cause){setError(cause instanceof Error?cause.message:'加入自选失败');}
    finally{setBusy(false);}
  }
  async function remove(entry:Entry){
    if(readOnly){setMessage('浏览器预览为只读；请在桌面客户端操作。');return;}
    setBusy(true);setError('');
    try{await request('pool_remove',{code:entry.code});setMessage('已从股票池删除 '+entry.name);await refetch();}
    catch(cause){setError(cause instanceof Error?cause.message:'删除失败');}
    finally{setBusy(false);}
  }
  async function poolAdd(raw:string){
    const code=raw.trim();
    if(!code)return;
    if(readOnly){setMessage('浏览器预览为只读；请在桌面客户端操作。');return;}
    setBusy(true);setError('');
    try{await request('pool_add',{code});setInput('');setMessage('已添加 '+code+' 到股票池');await refetch();}
    catch(cause){setError(cause instanceof Error?cause.message:'添加失败');}
    finally{setBusy(false);}
  }
  async function loadMore(){
    if(preview||loadingMore||!dataRef.current)return;
    setLoadingMore(true);
    const seq=++sequence.current;
    const offset=dataRef.current.entries.length;
    try{
      const next=await request<PoolData>('pool',{...baseParams,limit:60,offset});
      if(seq!==sequence.current)return;
      setData(previous=>previous?{...next,entries:[...previous.entries,...next.entries]}:next);
    }catch(cause){setError(cause instanceof Error?cause.message:'加载更多失败');}
    finally{setLoadingMore(false);}
  }
  const sortEntries=(left:Entry,right:Entry)=>{
    if(sort==='今日涨幅')return (right.today_percent??-999)-(left.today_percent??-999);
    if(sort==='入选日')return String(right.added_day).localeCompare(String(left.added_day));
    if(sort==='状态')return tagOrder(left.entry_tag)-tagOrder(right.entry_tag);
    return (right.since_add_percent??-999)-(left.since_add_percent??-999);
  };
  const grouped=useMemo(()=>{
    const order=[...CATEGORIES,...groups.map(item=>item.category).filter(category=>!CATEGORIES.includes(category))];
    const buckets=new Map<string,Entry[]>();
    for(const entry of rawEntries){
      const key=entry.category||'其他';
      const list=buckets.get(key)??[];
      list.push(entry);buckets.set(key,list);
    }
    return order.filter(category=>buckets.has(category)).map(category=>({
      category,
      stat:groups.find(item=>item.category===category),
      entries:[...buckets.get(category)!].sort(sortEntries),
    }));
  },[rawEntries,groups,sort]);
  const groupStats=(category:string)=>{
    const stat=groups.find(item=>item.category===category);
    const count=stat?.count??rawEntries.filter(entry=>entry.category===category).length;
    return {count,sample:stat?.sample??null,winRate:stat?.win_rate??null,avg:stat?.avg_since_percent??null};
  };
  const showGroupHeader=group==='全部';
  const filteredTotal=viewData?.filtered_total??rawEntries.length;
  const hasMore=Boolean(viewData?.has_more)&&!preview;
  const extraGroups=(entry:Entry)=>entryGroups(entry).filter(category=>category!==entry.category);
  const tagSample=(tag:string)=>{const stat=tagStats.find(item=>item.entry_tag===tag);return stat?stat.sample:0;};
  const windowEntries=viewData?.entries??[];
  const windowCovered=windowEntries.filter(entry=>entry.windows&&Object.values(entry.windows).some(Boolean)).length;
  const windowTotal=windowEntries.length;
  return <section className="focus-pool" aria-label="股票池">
    <div className="fp-title-row">
      <h2>股票池复盘</h2>
      <Info label="样本说明">
        <p><b>胜率与样本</b>：胜率=最新价高于入选基准价的样本占比；样本=有有效最新价的条目数；样本会随时间积累，少样本时不代表未来收益。</p>
        <p><b>触及口径</b>：触及目标 {summary?.target_hits??'待取得'} · 止损 {summary?.stop_hits??'待取得'} · 买点 {summary?.buy_zone_hits??'待取得'}，按本机已保存日快照累计，可能与详情逐日表不完全一致；快照从应用运行期间开始积累。</p>
        <p><b>按入选状态胜率</b>（按最新可用价 vs 入选基准，n=有有效行情样本数）</p>
        {tagStats.length?<table className="fp-info-table">
          <thead><tr><th>入选状态</th><th>样本</th><th>胜率</th><th>平均自入选</th></tr></thead>
          <tbody>{tagStats.map(item=><tr key={item.entry_tag}>
            <td>{item.entry_tag}</td><td>{item.sample}</td>
            <td>{item.win_rate!==null?item.win_rate.toFixed(1)+'%':'待积累'}{item.sample<5&&item.sample>0?<span className="fp-warn-chip">样本少</span>:null}</td>
            <td className={sign(item.avg_since_percent)}>{pctOrDash(item.avg_since_percent)}</td>
          </tr>)}</tbody>
        </table>:<p className="fp-muted">按入选状态胜率待积累。</p>}
        <p><b>提醒规则</b>：进入买区/跌破防守位会按观量现有通知设置发本机/手机提醒（每只每天一次）；仅提醒，不自动交易。</p>
        <p><b>免责声明</b>：股票池为复盘观察记录，不构成投资建议；胜率基于历史样本，不代表未来收益。买入按钮仅打开观量现有模拟/实盘委托面板，股票池本身不会自动下单。</p>
      </Info>
      {readOnly&&<><span className="fp-muted fp-readonly-chip">只读预览</span><Info label="预览说明"><p>浏览器为只读预览：筛选仅作展示，添加/删除/自选、导出与交易请到桌面客户端操作；浏览器只读预览不支持搜索与导出。</p></Info></>}
    </div>
    <div className="fp-kpis" role="group" aria-label="股票池摘要">
      <div className="fp-kpi"><span>样本</span><b>{summary?summary.sample:'待取得'}{summary&&summary.sample<5?<span className="fp-warn-chip">小样本</span>:null}</b></div>
      <div className="fp-kpi"><span>上涨占比（胜率）</span><b className="positive">{summary?pctOrDash(summary.win_rate,1):'待取得'}</b></div>
      <div className="fp-kpi"><span>平均自入选</span><b className={sign(summary?.avg_since_percent)}>{summary?pctOrDash(summary.avg_since_percent):'待取得'}</b></div>
      <div className="fp-kpi"><span>中位自入选</span><b className={sign(summary?.median_since_percent)}>{summary?pctOrDash(summary.median_since_percent):'待取得'}</b></div>
      <div className="fp-kpi"><span>平均最大回撤</span><b className={sign(summary?.avg_max_drawdown_percent)}>{summary?pctOrDash(summary.avg_max_drawdown_percent):'待取得'}</b></div>
      <div className="fp-kpi"><span>今日平均</span><b className={sign(summary?.avg_today_percent)}>{summary?pctOrDash(summary.avg_today_percent):'待取得'}</b></div>
    </div>
    <div className="fp-windows" role="group" aria-label="跨日窗口表现">
      <div className="fp-section-head">
        <b>跨日窗口</b>
        <Info label="跨日窗口说明">
          <p>基准：{viewData?.benchmark||'上证指数'}；T+N 使用本机已缓存日K，未覆盖样本不参与统计。</p>
          <p>日K覆盖 {windowCovered}/{windowTotal}，未覆盖不计入。</p>
        </Info>
        <button type="button" className="fp-collapse" aria-expanded={windowsOpen} aria-label={windowsOpen?'折叠跨日窗口':'展开跨日窗口'} onClick={()=>setWindowsOpen(value=>!value)}>{windowsOpen?'收起':'展开'}</button>
      </div>
      {windowsOpen&&<div className="fp-window-grid">
        <span className="fp-window-head">窗口</span><span>样本</span><span>上涨占比</span><span>平均收益</span><span>跑赢上证占比</span><span>平均超额</span>
        {WINDOW_KEYS.flatMap(([key])=>{
          const stat=viewData?.windows?.[key];
          const sample=stat?.sample??0;
          return [
            <span key={key+'-name'} className="fp-window-name">{key}</span>,
            <span key={key+'-sample'}>{stat?sample:'待积累'}</span>,
            <span key={key+'-win'}>{stat&&sample?rateText(stat.win_rate):'待积累'}</span>,
            <span key={key+'-ret'} className={sign(stat?.avg_return_percent)}>{stat&&sample?pctOrDash(stat.avg_return_percent):'待积累'}</span>,
            <span key={key+'-beat'}>{stat&&sample?rateText(stat.beat_rate):'待积累'}</span>,
            <span key={key+'-excess'} className={sign(stat?.avg_excess_percent)}>{stat&&sample?pctOrDash(stat.avg_excess_percent):'待积累'}</span>,
          ];
        })}
      </div>}
    </div>
    <div className="fp-holdings" role="group" aria-label="按持有交易日">
      <div className="fp-section-head">
        <b>按持有交易日</b>
        <Info label="持有分组说明"><p>按持有交易日（0/1/2/3–5/6–10/10 以上）分桶统计样本、胜率与平均自入选；点击分桶筛选，可与其他筛选叠加。</p></Info>
        <button type="button" className="fp-collapse" aria-expanded={holdingOpen} aria-label={holdingOpen?'折叠按持有交易日':'展开按持有交易日'} onClick={()=>setHoldingOpen(value=>!value)}>{holdingOpen?'收起':'展开'}</button>
      </div>
      {holdingOpen&&<div className="fp-holding-chips">
        {(viewData?.holding??[]).length?(viewData?.holding??[]).map(item=>
          <button type="button" key={item.bucket} aria-pressed={holding===item.bucket}
            title={(item.label||item.bucket)+'：样本 '+item.sample+'，胜率 '+rateText(item.win_rate)+'，平均自入选 '+pctOrDash(item.avg_since_percent)}
            onClick={()=>patch({holding:holding===item.bucket?'全部':item.bucket})}>
            {item.label||item.bucket} <span className="fp-muted">样本 {item.sample} · 胜率 {rateText(item.win_rate)} · 平均自入选 {pctOrDash(item.avg_since_percent)}</span>
          </button>):<span className="fp-muted">持有分组待积累</span>}
      </div>}
    </div>
    <div className="fp-status-chips" role="group" aria-label="入选状态筛选">
      <button type="button" aria-pressed={status==='全部'} onClick={()=>patch({status:'全部'})}>全部 {counts?counts.total:rawEntries.length}</button>
      {STATUS_CHIPS.map(([tag,key])=><button type="button" key={tag} aria-pressed={status===tag} onClick={()=>patch({status:status===tag?'全部':tag})}>
        {tag} {counts?counts[key]:'—'}</button>)}
    </div>
    <div className="fp-toolbar">
      <form className="fp-add" onSubmit={event=>{event.preventDefault();void poolAdd(input);}}>
        <label className="fp-add-label">手动添加股票</label>
        <StockSearch request={request} preview={preview} value={input} onChange={setInput} onSelect={stock=>{void poolAdd(stock.code);}}/>
        <button className="primary" disabled={busy||!input.trim()} type="submit">添加</button>
      </form>
      <div className="fp-filters" role="group" aria-label="分组筛选">
        <button type="button" aria-pressed={group==='全部'} onClick={()=>patch({group:'全部'})}>全部</button>
        {CATEGORIES.map(category=>{
          const stat=groupStats(category);
          return <button type="button" key={category} aria-pressed={group===category} onClick={()=>patch({group:group===category?'全部':category})}>
            {category} {stat.count}{stat.winRate!==null?' · 胜率 '+stat.winRate.toFixed(0)+'%':''}</button>;
        })}
      </div>
      <span hidden><Info label="分组说明"><p>股票可同时属于多个组（多标签），分组计数可重复，因此各组数量之和可能大于总数。</p></Info></span>
      <label className="fp-sort">时间段<select aria-label="时间段" value={period} onChange={event=>patch({period:event.target.value})}>{PERIODS.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      {period==='自定义'&&<div className="fp-custom-days">
        <label>开始<input aria-label="开始日期" type="date" value={startDay} onChange={event=>patch({startDay:event.target.value})}/></label>
        <label>结束<input aria-label="结束日期" type="date" value={endDay} onChange={event=>patch({endDay:event.target.value})}/></label>
      </div>}
      <label className="fp-sort">排序<select aria-label="排序" value={sort} onChange={event=>patch({sort:event.target.value})}>{SORTS.map(value=><option key={value}>{value}</option>)}</select></label>
      <div hidden>
        <label className="fp-switch"><input type="checkbox" aria-label="包含归档" checked={includeArchived} onChange={event=>patch({includeArchived:event.target.checked})}/>包含归档</label>
        <span className="fp-muted">已归档 {viewData?.archived_count??0}</span>
        <Info label="归档说明"><p>入选超过 30 天自动归档，默认视图隐藏；开启“包含归档”可查看；再次入选会自动解除归档。</p></Info>
        <button type="button" disabled={readOnly||exporting} title={readOnly?'浏览器只读预览不支持导出':'导出当前筛选为 CSV 与 Markdown 复盘报告'} onClick={()=>void exportReview()}>{exporting?'导出中…':'导出复盘'}</button>
        <Info label="自动同步说明"><p>自动同步：每次研判更新与应用启动时；盘中报价每 8 秒批量刷新；时间段按入选日筛选（近 N 个交易日）。</p></Info>
      </div>
    </div>
    {error&&<p className="fp-error" role="alert">{error}</p>}
    {message&&<p className="fp-message" role="status">{message}</p>}
    {exportInfo&&<p className="fp-message" role="status">已导出 {exportInfo.count??0} 条：CSV {exportInfo.csv||'待取得'}；Markdown {exportInfo.report||'待取得'}</p>}
    {!rawEntries.length?<p className="fp-empty">股票池还没有标的。市场机会中可考虑建仓的标的、方向候选与题材启动信号会自动加入，也可手动添加。</p>:
      <div className="fp-groups">
        {grouped.map(section=>{
          const stat=groupStats(section.category);
          return <section className="fp-group" key={section.category} aria-label={'分组 '+section.category}>
            {showGroupHeader&&<div className="fp-group-head">
              <b>{section.category}</b>
              <span className="fp-muted">{stat.count} 条</span>
              <span className={sign(stat.avg)}>平均自入选 {pctOrDash(stat.avg)}</span>
              <span className="fp-muted">胜率 {stat.winRate!==null?stat.winRate.toFixed(1)+'%':'待取得'}</span>
              {stat.sample!==null&&stat.sample<5&&<span className="fp-warn-chip">样本少</span>}
            </div>}
            <div className="fp-head-row" aria-hidden="true">
              <span>股票</span><span>入选时间</span><span>入选价格</span><span>自入选</span>
              <span>现价 · 今日</span><span>期间最高 / 回撤</span><span>入选状态</span><span>分组 · 方向 / 来源</span><span>操作</span>
            </div>
            {section.entries.map(entry=>{
              const expanded=openCode===entry.code;
              const quote=entry.quote;
              const detailId='fp-detail-'+entry.code;
              return <div className="fp-item" key={entry.code}>
                <div className={'fp-row'+(expanded?' is-open':'')} onClick={()=>setOpenCode(expanded?'':entry.code)}>
                  <span className="fp-name"><i className="fp-label">股票</i>
                    <button type="button" className="fp-name-button" aria-expanded={expanded} aria-controls={detailId}
                      onClick={event=>{event.stopPropagation();setOpenCode(expanded?'':entry.code);}}>
                      <b>{entry.name}</b><span className="fp-code">{entry.code}</span></button>
                    <span className="fp-source-mini">{entry.source||'待取得'}</span></span>
                  <span className="fp-cell-base fp-added-time"><i className="fp-label">入选时间</i>{addedTimeLabel(entry)}</span>
                  <span className="fp-cell-base"><i className="fp-label">入选价</i><b>{numText(entry.added_price)}</b></span>
                  <span className={'fp-cell-base fp-since-big'+sign(entry.since_add_percent)}><i className="fp-label">自入选</i>{pctOrDash(entry.since_add_percent)}</span>
                  <span className="fp-price"><i className="fp-label">现价</i>
                    {quote?<><b>{numText(quote.price)}</b><span className={sign(entry.today_percent)}>{pctText(entry.today_percent)}</span>
                      <span className="fp-time">{quote.basis==='added'?'基准价':quote.basis==='last'?'收盘 '+timeText(quote.time):'实时 '+timeText(quote.time)}</span></>
                      :<span className="fp-muted">行情待取得</span>}</span>
                  <span className="fp-range"><i className="fp-label">区间</i><span className={sign(entry.max_gain_percent)}>最高 {pctOrDash(entry.max_gain_percent,1)}</span>
                    <span className="fp-muted"> / 回撤 {pctOrDash(entry.max_drawdown_percent,1)}</span></span>
                  <span className="fp-tag"><i className="fp-label">状态</i><span className={'pool-tag '+tagClass(entry.entry_tag)}>{entry.entry_tag||'待取得'}</span></span>
                  <span className="fp-meta"><i className="fp-label">分组</i>{entry.category||'其他'}{entry.group_name?' · '+entry.group_name:''}
                    {extraGroups(entry).map(category=><span className="fp-tag-extra" key={category}>+{category}</span>)}
                    <span className="fp-muted"> / {entry.sector||'待取得'} · {entry.role||'待取得'}</span>
                    {entry.group_rank&&entry.group_size?<span className="fp-rank">组内 #{entry.group_rank}/{entry.group_size}</span>:null}</span>
                  <span className="fp-actions" onClick={event=>event.stopPropagation()}>
                    <button type="button" className="fp-trade" aria-label={entry.name+' 买入'} onClick={()=>pick({code:entry.code,name:entry.name,side:'buy'})}>买入</button>
                    <button type="button" aria-label={entry.name+' 加入自选'} onClick={()=>void addWatch(entry)}>加自选</button>
                    <button type="button" aria-label={entry.name+' 打开K线'} onClick={()=>onOpenDaily(entry.code,entry.name)}>K线</button>
                    <button type="button" aria-label={entry.name+' 删除'} onClick={()=>void remove(entry)}>删除</button>
                  </span>
                </div>
                {expanded&&<section className="fp-detail" id={detailId} aria-label="股票池详情">
                  <div className="fp-detail-cols">
                    <div>
                      <h3>入选与表现</h3>
                      <p>入选基准 {numText(entry.added_price)} 元（{entry.added_at&&entry.added_at.length>=16?stampText(entry.added_at):entry.added_day||'待取得'} 入选）· 现价 {quote?numText(quote.price):'行情待取得'} · 自入选 {pctOrDash(entry.since_add_percent)}</p>
                      <p>已跟踪交易日 {entry.hold_days??'待取得'} 天 · 最大浮盈 {pctOrDash(entry.max_gain_percent,1)} · 最大回撤 {pctOrDash(entry.max_drawdown_percent,1)}</p>
                      <h3>入选理由</h3><p>{entry.reason||'待取得'}</p>
                      <h3>买卖计划</h3>
                      <p>买点区间 {entry.plan?numText(entry.plan.buy_low)+'–'+numText(entry.plan.buy_high):'待取得'} · 追高上限 {numText(entry.plan?.chase)} · 止损 {numText(entry.plan?.stop)}</p>
                      <p>止盈目标 {numText(entry.plan?.target1)} / {numText(entry.plan?.target2)} · 移动止损 {numText(entry.plan?.trail)}</p>
                      {entry.plan?.note&&<p className="fp-muted">{entry.plan.note}</p>}
                      {entry.plan?.sell_note&&<p className="fp-sell">{entry.plan.sell_note}</p>}
                      <p className="fp-muted">进入状态：{entry.zone||'待取得'} · {entry.hint||''}</p>
                      <h3>区间表现 <span className="fp-muted">基准：{viewData?.benchmark||'上证指数'} · 使用本机已缓存日K</span></h3>
                      <table className="fp-window-table">
                        <thead><tr><th>窗口</th><th>日期</th><th>收益</th><th>相对上证超额</th></tr></thead>
                        <tbody>{WINDOW_KEYS.map(([key])=>{
                          const window=entry.windows?.[key];
                          return <tr key={key}>
                            <td>{key}</td>
                            <td>{window?.date?shortDay(window.date):'待积累'}</td>
                            <td className={sign(window?.return_percent)}>{window?.return_percent==null?'待积累':pctOrDash(window.return_percent)}</td>
                            <td className={sign(window?.excess_percent)}>{window?.excess_percent==null?'待积累':pctOrDash(window.excess_percent)}</td>
                          </tr>;
                        })}</tbody>
                      </table>
                    </div>
                    <div>
                      <h3>近 10 日对比 <span className="fp-muted">触及买点 / 止损 / 目标</span></h3>
                      {!entry.history?.length?<p className="fp-muted">历史对比待取得</p>:
                        <div className="fp-scroll"><table className="fp-history">
                          <thead><tr><th>日期</th><th>收盘</th><th>涨跌</th><th>最高</th><th>最低</th><th>买点</th><th>止损</th><th>目标</th></tr></thead>
                          <tbody>{entry.history.slice(-10).map(row=><tr key={row.day}>
                            <td>{row.day}</td><td>{numText(row.price)}</td><td className={sign(row.percent)}>{pctText(row.percent)}</td>
                            <td>{numText(row.high)}</td><td>{numText(row.low)}</td>
                            <td className={row.hit_buy?'hit':''}>{row.hit_buy?'是':'—'}</td>
                            <td className={row.hit_stop?'hit-warn':''}>{row.hit_stop?'是':'—'}</td>
                            <td className={row.hit_target?'hit':''}>{row.hit_target?'是':'—'}</td>
                          </tr>)}</tbody></table></div>}
                    </div>
                  </div>
                </section>}
              </div>;
            })}
          </section>;
        })}
        {!grouped.length&&<p className="fp-empty">当前筛选条件下没有标的。</p>}
      </div>}
    <div className="fp-more">
      <span className="fp-muted">已显示 {rawEntries.length} / 共 {filteredTotal}</span>
      {hasMore&&<button type="button" disabled={loadingMore} onClick={()=>void loadMore()}>
        {loadingMore?'加载中…':'加载更多（已显示 '+rawEntries.length+' / 共 '+filteredTotal+'）'}</button>}
    </div>
  </section>;
}
