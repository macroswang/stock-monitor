import {useEffect,useState} from 'react';
import type {BreadthDay} from './MarketBreadth';
import {breadthView,currentStamp} from './marketOverview';
import ForwardOutlook, {useForwardOutlook, type OutlookDecision} from './ForwardOutlook';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Breadth={days:BreadthDay[];error?:string};
type Representative={name:string;code:string;change_percent:number;time:string};
type Sector={name:string;code:string;change_percent:number;net_yuan:number;representative?:Representative};
type Snapshot={date:string;source:string;sectors?:Sector[];anchor_time?:string;quote_time?:string;date_inferred?:boolean;measure:string};
type Flow={snapshot:Snapshot|null;error?:string;running:boolean};
const signed=(n:number)=>(n>0?'+':'')+n.toFixed(2)+'%';

export default function OpportunityBoard({request,preview}:{request:Request;preview:boolean}){
  const [report,setReport]=useState<Breadth>(),[flow,setFlow]=useState<Flow>();
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{
    let alive=true,pending=false;
    async function read(){
      if(pending)return;
      pending=true;
      const [b,f]=await Promise.allSettled([
        requestWithTimeout(request<Breadth>('breadth')),
        requestWithTimeout(request<Flow>('sector_flow',{kind:'industry'})),
      ]);
      if(alive){
        setReport(b.status==='fulfilled'?b.value:undefined);
        setFlow(f.status==='fulfilled'?f.value:{snapshot:null,running:false,error:'连接失败'});
        setNow(Date.now());
      }
      pending=false;
    }
    void read();
    const timer=setInterval(read,15000);
    return ()=>{alive=false;clearInterval(timer);};
  },[request]);
  const breadth=breadthView(report?.days.at(-1),report?.error,now);
  const day=breadth?.day;
  const outlook=useForwardOutlook(request,day,now,preview);
  const snapshot=flow?.snapshot;
  const stamp=snapshot?.quote_time||snapshot?.anchor_time;
  const valid=snapshot&&currentStamp(stamp,snapshot.date,now)&&Array.isArray(snapshot.sectors)&&snapshot.sectors.length>0&&(!day||snapshot.date===day.date);
  const picks=valid?snapshot.sectors!.filter(r=>r.name&&Number.isFinite(r.change_percent)&&r.change_percent>0&&Number.isFinite(r.net_yuan)&&r.net_yuan>0)
    .sort((a,b)=>b.net_yuan-a.net_yuan||b.change_percent-a.change_percent).slice(0,3):[];
  const stockFor=(row:Sector)=>{
    const stock=row.representative;
    return stock?.name&&Number.isFinite(stock.change_percent)&&stock.change_percent>row.change_percent&&currentStamp(stock.time,snapshot!.date,now)?stock:null;
  };
  const representatives=new Map<string,Representative>();
  for(const row of picks){
    const stock=stockFor(row);
    if(stock)representatives.set(row.code,stock);
  }
  const focus=picks.filter(row=>stockFor(row)).sort((a,b)=>b.change_percent-a.change_percent)[0];
  return <div className="decision-board">
    <section className="card market-brief" aria-label="当天走强的行业和代表股">
      <h2>当天走强的行业和代表股</h2>
      {valid&&<small>{snapshot.date} · {snapshot.source} · {snapshot.date_inferred?'日期由代表股报价推定':stamp?.slice(11,19)}{flow?.error?' · 更新失败，沿用已核对的快照':''}</small>}
      {picks.length>0&&<>{focus&&<p><b>本期已走强的代表股是{focus.name}的{stockFor(focus)!.name}。</b> 在有代表股跑赢行业的入选方向中，{focus.name}涨幅最大。</p>}
        <div className="decision-picks">{picks.map(row=>{
          const stock=representatives.get(row.code);
          const candidate=outlook.ordered.find(item=>item.idea.sector_code===row.code);
          return <div className="decision-pick" key={row.code}>
            <h3>{row.name}<small className="opportunity-kind">行业</small> <span>{signed(row.change_percent)}</span></h3>
            <small>{snapshot?.measure==='大单及超大单净额'?'大单净流入':'方向净流入'} {(row.net_yuan/1e8).toFixed(2)} 亿元</small>
            {stock?<div className="decision-stock"><b>{stock.name}</b><em>{signed(stock.change_percent)}</em><small>{stock.code.slice(2)} · 当天代表股</small></div>:<p>暂无已核对且跑赢行业的代表股。</p>}
            {!preview&&<SectorDecision sector={row.name} representative={stock} candidate={candidate}
              reason={outlook.issue?.exclusions?.[row.code]} rank={outlook.ranked.findIndex(r=>r.idea.sector_code===row.code)+1}
              limit={outlook.ordered.length} current={outlook.updated&&!outlook.pending}/>}
          </div>;
        })}</div>
        <small>行业上涨且资金净流入，按净流入金额取前三。个股须跑赢所属行业。</small></>}
      {valid&&!picks.length&&<p>已核对的行业里，还没有同时上涨且资金净流入的方向。</p>}
      {!valid&&<p>{flow?.running||!flow?'正在获取行业行情。':'本期行业数据不足，暂不能列出可靠的股票名单。'}</p>}
    </section>
    <ForwardOutlook outlook={outlook} representatives={representatives} preview={preview}/>
  </div>;
}


function SectorDecision({sector,representative,candidate,current,reason,rank,limit}:{
  sector:string;representative?:Representative;candidate?:OutlookDecision;current:boolean;reason?:string;rank:number;limit:number;
}){
  if(!current)return <p>继续等。本期建仓名单正在更新。</p>;
  if(!candidate){
    const detail=reason||(rank>0?`本期排第 ${rank}，面板展示前 ${limit} 个方向。`:'这期没有记录更具体的筛选原因。');
    return <p><b>继续等。</b>{sector}未列入本期重点建仓候选。{detail}</p>;
  }

  const stock=candidate.idea.stocks[0];
  const different=representative&&representative.code!==stock.code;
  const action=candidate.status==='ready'?'可考虑建仓':'继续等';
  return <div>
    <p><b>建仓候选 · {stock.name} · {action}</b></p>
    {different&&<p>{representative.name}因当天涨幅超过行业而列为代表股。</p>}
  </div>;
}
