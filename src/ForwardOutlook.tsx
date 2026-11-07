import {useEffect,useState} from 'react';
import type {BreadthDay} from './MarketBreadth';
import {currentStamp} from './marketOverview';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Idea={sector_kind?:string;sector:string;sector_code:string;reason:string;risk:string;news_title?:string;allow_entry:boolean;stocks:{code:string;name:string;low:number}[]};
type ThemeCoverage={matched_count?:number;unquoted?:number;name:string;code?:string;members?:{code:string;name:string;basis:string}[];change?:number;net?:number;advance?:number};
type Issue={directory?:Record<string,string>;discovery?:{source_failures?:Record<string,number>;observed:number;days:number;failed_days:number;filing_errors:Record<string,string>};themes?:ThemeCoverage[];exclusions?:Record<string,string>;native_slot?:string;published_at:string;quote_date:string;coverage:{industry:number;concept:number;disclosed?:number;unavailable?:number};ideas:Idea[]};
type Quote={code:string;price:string;previous_close:string;timestamp:string;day_low:string};
type Sector={change:number;net:number;time:string;inferred:boolean};
type Report={schedule?:string;completed_slot?:string|null;issue:Issue|null;quotes:Quote[];sectors?:Record<string,Sector>;day:string|null;batch:string|null};
export type OutlookDecision={idea:Idea;status:'ready'|'watch'|'weak'|'missing';why:string;percent?:number};
const chinaDay=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'});

function assess(idea:Idea,report:Report,day:BreadthDay|undefined,now:number):OutlookDecision{
  const missing:OutlookDecision={idea,status:'missing',why:'本期行情正在核对。'};
  if(!day||report.day!==day.date||report.batch!==day.collected_at||idea.stocks.length!==3)return missing;
  const group=idea.stocks.map(stock=>{
    const q=report.quotes.find(row=>row.code===stock.code);
    if(!q||!day.first_quote||!day.last_quote||q.timestamp<day.first_quote||q.timestamp>day.last_quote||!currentStamp(q.timestamp,day.date,now))return null;
    const price=Number(q.price),previous=Number(q.previous_close),low=Number(q.day_low);
    if(![price,previous,low].every(v=>Number.isFinite(v)&&v>0)||low>price)return null;
    return {pct:(price/previous-1)*100,broken:price<stock.low,recovered:low<=previous&&price>previous};
  });
  const [stock,...peers]=group;
  if(!stock||peers.some(q=>!q))return missing;
  const base={idea,percent:stock.pct};
  if(stock.broken||peers.every(q=>q?.broken))return {...base,status:'weak',why:'候选股或两只同行已跌破研判时的参考低点。'};
  const sector=report.sectors?.[idea.sector_code];
  if(!sector||!currentStamp(sector.time,day.date,now))return {...base,status:'missing',why:'板块行情未同步，等待核对。'};
  if(day.decline*3>=(day.advance+day.decline+day.flat)*2)return {...base,status:'watch',why:'市场中至少三分之二的股票在跌，暂缓建仓。'};
  if(!idea.allow_entry)return {...base,status:'watch',why:idea.risk};
  if(sector.change<=0||sector.net<=0)return {...base,status:'watch',why:'板块上涨和资金净流入尚未同时出现。'};
  if(stock.pct>=5)return {...base,status:'watch',why:'候选股当日已涨至少 5%，继续等回落机会。'};
  if(!stock.recovered||!peers.some(q=>q&&q.pct>0))return {...base,status:'watch',why:'候选股回落后重新超过昨收、同行同步上涨的条件尚未齐备。'};
  if(day.status==='closed')return {...base,status:'watch',why:'收盘时已走强，下一交易日开盘后再确认。'};
  return {...base,status:'ready',why:'候选股回落后已重新超过昨收，有同行上涨，板块也上涨且资金净流入。'};
}

export function useForwardOutlook(request:Request,day:BreadthDay|undefined,now:number,preview:boolean){
  const [report,setReport]=useState<Report|null>(null);
  const date=day?.date,batch=day?.collected_at;
  useEffect(()=>{
    let alive=true,pending=false;
    async function read(){
      if(preview||pending)return;
      pending=true;
      try{const next=await requestWithTimeout(request<Report>('daily_outlook',{day:date,batch}));if(alive)setReport(next);}
      catch{if(alive)setReport(null);}
      finally{pending=false;}
    }
    void read();const timer=setInterval(read,15000);
    return ()=>{alive=false;clearInterval(timer);};
  },[request,preview,date,batch]);
  const issue=report?.issue,updated=issue?.published_at.slice(0,10)===chinaDay.format(now);
  const rows=issue&&report&&updated?issue.ideas.map(idea=>assess(idea,report,day,now)):[];
  const localTime=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
  const [hour, minute]=localTime.split(':');
  const due=hour+':'+(Number(minute)<30?'00':'30');
  const pending=Boolean(report?.schedule&&issue?.native_slot!==chinaDay.format(now)+' '+due);
  const priority={ready:0,watch:1,missing:2,weak:3};
  const ranked=rows.map(r=>pending&&r.status==='ready'?{...r,status:'watch' as const,why:'等本期更新完成后再确认。'}:r)
    .sort((a,b)=>priority[a.status]-priority[b.status] || Number(b.idea.allow_entry)-Number(a.idea.allow_entry));
  // Keep screening the full pool: a later candidate can move up on new quotes.
  const ordered=ranked.slice(0,5);
  return {issue, updated, pending, ordered, ranked, schedule:report?.schedule};
}

type DailyRepresentative={code:string;name:string;change_percent:number};
export default function ForwardOutlook({outlook,representatives,preview}:{
  outlook:ReturnType<typeof useForwardOutlook>;
  representatives:Map<string,DailyRepresentative>;
  preview:boolean;
}){
  const {issue,updated,ordered,schedule}=outlook;
  const [query,setQuery]=useState('');
  const themes:ThemeCoverage[]=[...(issue?.themes??[]),...Object.entries(issue?.directory??{}).map(([code,name])=>({code,name}))];
  const searched=themes.filter(t=>query.trim()&&t.name.toLowerCase().includes(query.trim().toLowerCase()));
  function sectorKind(code:string, declared?:string){
    if(declared==='补充题材'||declared==='题材')return '题材';
    if(declared==='行业'||declared==='概念')return declared;
    if(code.startsWith('gn_'))return '概念';
    if(code.startsWith('new_')||/^BK\d+$/.test(code))return '行业';
    if(issue?.themes?.some(t=>t.code===code))return '题材';
    return '类别待核实';
  }
  const extraThemes=issue?.themes??[];
  const insufficient=extraThemes.filter(t=>t.members&&t.members.length<3).length;
  const compared=extraThemes.filter(t=>t.change!==undefined&&t.net!==undefined&&t.code&&!(t.code in (issue?.discovery?.filing_errors??{}))).length;
  const categories=ordered.map(r=>sectorKind(r.idea.sector_code,r.idea.sector_kind));
  const extraPicks=categories.filter(kind=>kind==='题材').length;
  const breakdown=['行业','概念','题材'].map(kind=>kind+' '+categories.filter(k=>k===kind).length).join(' · ');
  const lead=ordered.find(r=>r.status==='ready'||r.status==='watch');
  const stock=lead?.idea.stocks[0];
  const count=ordered.filter(r=>r.status==='ready').length;
  const reasons=new Map<string,string[]>();
  for(const row of ordered){
    const sectors=reasons.get(row.why)??[];
    sectors.push(row.idea.sector);
    reasons.set(row.why,sectors);
  }
  const sharedReasons=[...reasons].filter(([,sectors])=>sectors.length>1);
  return <section className="card market-brief" aria-label="未来几天的建仓候选">
    <h2>未来几天的建仓候选</h2>
    <strong>{count?'可考虑建仓 · 首选 '+stock?.name:'继续等 · '+(ordered.length?'当前没有确认的建仓机会':'暂无建仓候选')}</strong>
    <p>{preview?'每日研判显示在本机观量中。':!updated?'今日研判尚未更新。':count
      ?'以下优先展示的方向中，有 '+count+' 个可考虑建仓。'
      :lead?'优先观察 '+lead.idea.sector+'的'+stock?.name+'。'
      :ordered.length?'候选已转弱或最新报价暂未核对。':'本轮没有筛出符合条件的股票。'}</p>
    {sharedReasons.map(([reason,sectors])=><p key={reason}>{sectors.length<ordered.length&&sectors.join('、')+'：'}{reason}</p>)}
    {!!ordered.length&&<><h3>本期前 {ordered.length} 名 <small>{breakdown}</small></h3>
      <div className="outlook-candidates">{ordered.map((r,index)=>{
        const representative=representatives.get(r.idea.sector_code);
        const candidate=r.idea.stocks[0];
        return <article key={r.idea.sector_code}>
        <div className="outlook-row"><b>{index+1}. {r.idea.sector}<small className="opportunity-kind">{categories[index]}</small></b><span className={r.status==='ready'?'outlook-ready':''}>{r.status==='ready'?'可考虑建仓':r.status==='weak'?'继续等 · 已转弱':'继续等'}</span></div>
        <strong>{r.idea.stocks[0].name} <small>{r.idea.stocks[0].code.slice(2)}</small></strong>
        {reasons.get(r.why)?.length===1&&<p>{r.why}</p>}
        {representative&&representative.code!==candidate.code&&<small>{representative.name}当天涨 {representative.change_percent.toFixed(2)}%，是同行代表。{candidate.name}入选的依据如下。</small>}
        <small>{r.idea.reason}</small>
        {r.idea.news_title&&<small>相关消息：{r.idea.news_title}</small>}
      </article>})}</div></>}
    {updated&&!outlook.pending&&issue?.discovery&&extraThemes.length>0&&<p>补充题材中，{compared} 个有足够的公司和行情可比较，{extraPicks} 个进入本期重点。{insufficient>0&&<>另有 {insufficient} 个在本轮来源中未找到三家可对照的公司。</>}</p>}
    {updated&&!outlook.pending&&issue&&themes.length>0&&<details className="theme-results">
      <summary>查某个方向为什么没入选</summary>
      <label>行业或题材名称　<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="输入名称查询本期结果"/></label>
      {query.trim()&&!searched.length&&<p>本期数据中没有识别到这个名称，无法判断。</p>}
      {searched.slice(0,10).map(theme=>{
        if(!theme.code)return null;
        const pos=outlook.ranked.findIndex(r=>r.idea.sector_code===theme.code);
        const pick=ordered.find(r=>r.idea.sector_code===theme.code);
        const headline=pick?pick.idea.stocks[0].name+' · '+(pick.status==='ready'?'可考虑建仓':'继续等'):'未入选';
        const why=pick?pick.why:issue.exclusions?.[theme.code]||
          (pos>=0?'候选排第 '+(pos+1)+'，本期只展示前 '+ordered.length+'。'+outlook.ranked[pos].why:'本轮数据不足。');
        return <div key={theme.code}><p><b>{theme.name} · {headline}</b> <small className="opportunity-kind">{sectorKind(theme.code)}</small>　{why}
          {theme.members&&theme.advance!==undefined&&theme.net!==undefined&&<>　{theme.members.length} 家中 {theme.advance} 家上涨，主力资金净{theme.net>=0?'流入':'流出'} {(Math.abs(theme.net)/1e8).toFixed(2)} 亿元。</>}</p>
          {!!theme.members?.length&&<details><summary>查看 {theme.members.length} 家公司及入选依据</summary>
            {theme.matched_count!==undefined&&theme.matched_count>theme.members.length&&<p>共找到 {theme.matched_count} 家相关公司，按成交额取最多 40 家活跃公司。{theme.unquoted?'其中 '+theme.unquoted+' 家行情未核齐。':''}</p>}
            {theme.change!==undefined&&<p>按各公司等权计算，筛选时平均涨跌 {theme.change.toFixed(2)}%。</p>}
            {theme.members.map(m=><p key={m.code}>{m.name}（{m.code.slice(2)}） · {m.basis}</p>)}
          </details>}</div>;
      })}
    </details>}
    {issue?.discovery?.source_failures&&Object.entries(issue.discovery.source_failures).some(([,n])=>n>0)&&<small>本轮部分数据未取全：{Object.entries(issue.discovery.source_failures).filter(([,n])=>n>0).map(([label])=>label).join('、')}。</small>}
    {issue?.discovery&&<small>近 {issue.discovery.days} 个交易日的市场异动及近期新闻共识别 {issue.discovery.observed} 个热点方向。{issue.discovery.failed_days>0?'其中 '+issue.discovery.failed_days+' 天异动数据未取齐。':''}{Object.keys(issue.discovery.filing_errors).length>0?'部分题材的公司公告暂未核实。':''}</small>}
    {issue&&<small>研判 {issue.published_at.slice(0,16).replace('T',' ')} · 行情 {issue.quote_date} · 已筛查 {issue.coverage.industry} 个行业、{issue.coverage.concept} 个概念{issue.coverage.disclosed?'、'+issue.coverage.disclosed+' 个补充题材':''}{issue.coverage.unavailable?' · '+issue.coverage.unavailable+' 个方向成分未取齐，未参与选股':''}</small>}
    {!preview&&<small className="outlook-schedule">观量自动更新 · 每 30 分钟重筛（北京时间整点和半点）{schedule?' · '+schedule:''}</small>}
  </section>;
}
