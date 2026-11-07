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
  return <div className="decision-board">
    <section className="card market-brief" aria-label="当天走强的行业和代表股">
      <div className="brief-heading"><h2>当天走强的行业和代表股</h2>
        {valid&&<small>{snapshot.date} {snapshot.date_inferred?'（报价推定）':stamp?.slice(11,16)}{flow?.error?' · 快照未更新':''}</small>}
      </div>
      {picks.length>0&&<div className="decision-picks">{picks.map(row=>{
        const stock=representatives.get(row.code);
        const candidate=outlook.ordered.find(item=>item.idea.sector_code===row.code);
        return <div className="decision-pick" key={row.code}>
          <div><b>{row.name}</b> <small className="opportunity-kind">行业</small> <span className="positive">{signed(row.change_percent)}</span></div>
          <div>{stock?<><b>{stock.name}</b> <span className="positive">{signed(stock.change_percent)}</span></>:'暂无跑赢行业的代表股'}</div>
          <small>{snapshot?.measure==='大单及超大单净额'?'大单净流入':'净流入'} {(row.net_yuan/1e8).toFixed(2)} 亿</small>
          {!preview&&<SectorDecision representative={stock} candidate={candidate}
            reason={outlook.issue?.exclusions?.[row.code]} rank={outlook.ranked.findIndex(r=>r.idea.sector_code===row.code)+1}
            limit={outlook.ordered.length} current={outlook.updated&&!outlook.pending}/>}
        </div>;
      })}</div>}
      {valid&&!picks.length&&<p>已核对的行业里，还没有同时上涨且资金净流入的方向。</p>}
      {!valid&&<p>{flow?.running||!flow?'正在获取行业行情。':'本期行业数据不足，暂不能列出可靠的股票名单。'}</p>}
    </section>
    <ForwardOutlook outlook={outlook} preview={preview}/>
  </div>;
}


function SectorDecision({representative,candidate,current,reason,rank,limit}:{
  representative?:Representative;candidate?:OutlookDecision;current:boolean;reason?:string;rank:number;limit:number;
}){
  if(!current)return <small>继续等 · 研判待更新</small>;
  if(!candidate){
    const detail=reason||(rank>0?`本期排第 ${rank}，仅列前 ${limit} 名。`:'本期未提供具体原因。');
    return <div className="decision-note"><b>继续等 · 未入选</b>　{detail}</div>;
  }
  const stock=candidate.idea.stocks[0];
  const different=representative&&representative.code!==stock.code;
  const action=candidate.status==='ready'?'可考虑建仓':'继续等';
  return <div className="decision-note"><b>{action}</b> · {different
    ?<>{representative.name}当天跑赢行业；建仓候选为{stock.name}。{candidate.idea.reason}</>
    :<>建仓候选 {stock.name}</>}</div>;
}
