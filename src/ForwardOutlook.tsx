import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {BreadthDay} from './MarketBreadth';
import {currentStamp} from './marketOverview';
import {requestWithTimeout} from './requestTimeout';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Member={code:string;name:string};
type Idea={core_members?:Member[];change?:number;net?:number;sector_kind?:string;sector:string;sector_code:string;reason:string;risk:string;news_title?:string;allow_entry:boolean;stocks:{code:string;name:string;low:number}[]};
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
  const [snapshot,setSnapshot]=useState<{report:Report;day?:BreadthDay}>();
  const [failed,setFailed]=useState(false);
  const report=snapshot?.report;
  const date=day?.date,batch=day?.collected_at;
  useEffect(()=>{
    let alive=true,pending=false;
    async function read(){
      if(preview||pending)return;
      pending=true;
      try{const next=await requestWithTimeout(request<Report>('daily_outlook',{day:date,batch}));if(alive){setFailed(false);setSnapshot({report:next,day});}}
      catch{if(alive)setFailed(true);}
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
  const pending=failed||Boolean(report?.schedule&&issue?.native_slot!==chinaDay.format(now)+' '+due);
  const priority={ready:0,watch:1,missing:2,weak:3};
  const ranked=rows.map(r=>pending&&r.status==='ready'?{...r,status:'watch' as const,why:'等本期更新完成后再确认。'}:r)
    .sort((a,b)=>priority[a.status]-priority[b.status] || Number(b.idea.allow_entry)-Number(a.idea.allow_entry));
  // Keep screening the full pool: a later candidate can move up on new quotes.
  const ordered=ranked.slice(0,5);
  // Keep the last matched quote/breadth pair on screen while the next batch arrives.
  // Entry decisions above always use the current batch, never this display fallback.
  const quoteDay=snapshot?.day;
  const checkedBatch=!!(quoteDay&&report&&report.day===quoteDay.date&&report.batch===quoteDay.collected_at);
  const refreshing=failed||!day||report?.day!==day.date||report?.batch!==day.collected_at;
  const batchQuotes=new Map((checkedBatch?report!.quotes:[]).map(q=>[q.code,q]));
  function risingMembers(idea:Idea){
    const members=idea.core_members??[], rising=[];
    let checked=0;
    for(const member of members){
      const q=batchQuotes.get(member.code);
      if(!q||!quoteDay?.first_quote||!quoteDay.last_quote||q.timestamp<quoteDay.first_quote||q.timestamp>quoteDay.last_quote||!currentStamp(q.timestamp,quoteDay.date,now))continue;
      const price=Number(q.price),prev=Number(q.previous_close);
      if(![price,prev].every(n=>Number.isFinite(n)&&n>0))continue;
      checked++;
      if(price>prev)rising.push({...member,price,pct:(price/prev-1)*100});
    }
    rising.sort((a,b)=>b.pct-a.pct||a.code.localeCompare(b.code));
    return {rising,checked,total:members.length,stamp:checkedBatch?quoteDay?.last_quote:null};
  }
  return {issue, updated, pending, ordered, ranked, risingMembers, refreshing, schedule:report?.schedule};
}

export default function ForwardOutlook({outlook,preview}:{
  outlook:ReturnType<typeof useForwardOutlook>;
  preview:boolean;
}){
  const {issue,updated,ordered}=outlook;
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
  const [kind,setKind]=useState('全部'),[selected,setSelected]=useState('');
  const visible=ordered.map((row,i)=>({row,rank:i+1,category:categories[i]})).filter(v=>kind==='全部'||v.category===kind);
  const active=visible.find(v=>v.row.idea.sector_code===selected)??visible[0];
  const board=active?.row.idea;
  const leaders=board?outlook.risingMembers(board):null;
  const signed=(n:number)=>(n>0?'+':'')+n.toFixed(2)+'%';
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
    <div className="brief-heading"><h2>未来几天的建仓候选</h2>
      {issue&&<small>研判 {issue.published_at.slice(5,16).replace('T',' ')} · 行情 {issue.quote_date.slice(5)}</small>}
    </div>
    <div className="outlook-verdict"><b>{preview?'仅本机显示研判':!updated?'今日研判尚未更新':outlook.pending?'继续等 · 本轮待更新':count?'可考虑建仓 · 首选 '+stock?.name:lead?'继续等 · 优先观察 '+stock?.name:ordered.length?'继续等 · 尚无确认机会':'本轮暂无候选'}</b>
      {!!ordered.length&&<small>前 {ordered.length} 名 · {breakdown}</small>}
    </div>
    {sharedReasons.map(([reason,sectors])=><p className="decision-note" key={reason}>{sectors.length<ordered.length&&sectors.join('、')+'：'}{reason}</p>)}
    {!!ordered.length&&<div className="opportunity-quotes">
      <div className="direction-pane">
        <div className="kind-switch" role="group" aria-label="筛选前五名分类">{['全部','行业','概念','题材'].map(k=>
          <button type="button" key={k} aria-pressed={kind===k} onClick={()=>setKind(k)}>{k}</button>)}</div>
        <div className="direction-grid grid-heading" aria-hidden="true"><span>#</span><span>方向</span><span>涨幅</span><span>净流入</span><span>建仓候选</span><span>判断</span></div>
        {visible.map(({row:r,rank,category})=><button type="button" className="direction-grid outlook-item" aria-controls="opportunity-risers" key={r.idea.sector_code}
          aria-pressed={r.idea.sector_code===board?.sector_code} onClick={()=>setSelected(r.idea.sector_code)}>
          <small>{rank}</small><span><b>{r.idea.sector}</b> <small className="opportunity-kind">{category}</small></span>
          <span className={Number(r.idea.change)>0?'positive':''}>{r.idea.change!=null?signed(r.idea.change):'—'}</span>
          <span>{r.idea.net!=null?(r.idea.net/1e8).toFixed(2)+'亿':'—'}</span><span>{r.idea.stocks[0].name}</span>
          <b className={r.status==='ready'?'outlook-ready':''}>{r.status==='ready'?'可考虑建仓':r.status==='weak'?'等 · 已转弱':'继续等'}</b>
        </button>)}
        {!active&&<p>本期前五名没有{kind}。</p>}
        {active&&board&&<details className="outlook-evidence" key={board.sector_code}><summary>{board.sector} · 入选依据</summary>
          {reasons.get(active.row.why)?.length===1&&<p>{active.row.why}</p>}<p>{board.reason}</p>{board.news_title&&<p>相关消息：{board.news_title}</p>}</details>}
      </div>
      <RiserPane row={active?.row} members={leaders} refreshing={outlook.refreshing}/>

    </div>}
    {updated&&!outlook.pending&&issue&&themes.length>0&&<details className="theme-results">
      <summary>查某个方向为什么没入选</summary>
      <label>行业、概念或题材名称　<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="输入名称查询本期结果"/></label>
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
    {issue&&<details className="screen-coverage"><summary>筛查范围与更新</summary>
      <p>每 30 分钟重筛 · 行业 {issue.coverage.industry}、概念 {issue.coverage.concept}、补充题材 {issue.coverage.disclosed??0}。</p>
      {updated&&!outlook.pending&&issue.discovery&&extraThemes.length>0&&<p>补充题材：{compared} 个可比较，{extraPicks} 个入选{insufficient>0?'，'+insufficient+' 个不足三家公司':''}。</p>}
      {issue.discovery&&<p>近 {issue.discovery.days} 个交易日识别 {issue.discovery.observed} 个热点{issue.discovery.failed_days?'，其中 '+issue.discovery.failed_days+' 天异动未取齐':''}。</p>}
      {!!issue.coverage.unavailable&&<p>{issue.coverage.unavailable} 个方向成分未取齐。</p>}
    </details>}
    {issue?.discovery?.source_failures&&Object.entries(issue.discovery.source_failures).some(([,n])=>n>0)&&<small>数据未取全：{Object.entries(issue.discovery.source_failures).filter(([,n])=>n>0).map(([label])=>label).join('、')}</small>}
  </section>;
}

type MemberBatch=ReturnType<ReturnType<typeof useForwardOutlook>['risingMembers']>;
function RiserPane({row,members,refreshing}:{row?:OutlookDecision;members:MemberBatch|null;refreshing:boolean}){
  const scroll=useRef<HTMLDivElement>(null);
  const idea=row?.idea, candidate=idea?.stocks[0];
  useLayoutEffect(()=>{if(scroll.current)scroll.current.scrollTop=0;},[idea?.sector_code]);
  const rows=members?.rising??[], top=rows[0];
  // The table shows two decimals; avoid inventing a distinction it cannot show.
  const firsts=top?rows.filter(m=>m.pct.toFixed(2)===top.pct.toFixed(2)):[];
  const firstCodes=new Set(firsts.map(m=>m.code)), tied=firsts.length>1;
  const same=!!candidate&&firstCodes.has(candidate.code);
  const ready=row?.status==='ready'&&!refreshing;
  const verdict=ready?'可考虑建仓':'继续等';
  const front=same?firsts.find(m=>m.code===candidate!.code):top;
  const frontName=front?front.name+(tied?'等 '+firsts.length+' 只':''):'—';
  const pct=(v:number)=>(v>0?'+':'')+v.toFixed(2)+'%';
  const partial=!!members&&members.checked<members.total;
  let explanation='';
  if(candidate&&top&&same)explanation=candidate.name+'既是本期建仓候选，也'+(tied?'并列领涨':'领涨')+'。';
  else if(candidate&&top){
    explanation=top.name+(tied?'等并列领涨':'领涨')+'（'+pct(top.pct)+'）'+(top.pct>=5
      ?'，策略不追涨幅达 5% 的个股，筛选时选中了涨幅不足 5% 的'+candidate.name+'。'
      :'；'+candidate.name+'入选是因为策略优先看回落后翻红，再比成交额。');
  }else if(candidate&&members?.checked)explanation='已核对的核心股中暂无上涨。';
  else if(candidate)explanation=members?.total?'等待同批行情。':'本期尚无核心股名单。';
  return <section className="riser-pane" id="opportunity-risers" aria-label="上涨核心股">
    <div className="riser-heading"><strong>{idea?.sector??'—'} · 上涨核心股</strong>
      <span className={'entry-status '+(ready?'is-ready':'')}>{row?verdict:'暂无候选'}</span></div>
    <div className="riser-roles">
      <div><small>{partial?'已核领涨':'领涨股'}</small><b>{frontName}</b></div>
      <div><small>建仓候选</small><b>{candidate?.name??'—'}</b></div>
    </div>
    <p className="role-explanation">{explanation||'选择入选方向查看核心股。'}</p>
    <div className="riser-scroll" ref={scroll} tabIndex={0} aria-label="核心股涨幅排名">
      <table><thead><tr><th scope="col">股票</th><th scope="col">现价</th><th scope="col">涨幅 ↓</th></tr></thead>
        <tbody>{rows.map(m=><tr key={m.code}><td><span className="stock-identity">{m.name} <small>{m.code.slice(2)}</small></span>
          {firstCodes.has(m.code)&&<span className="stock-role leader-role">{tied?'并列领涨':'领涨'}</span>}
          {m.code===candidate?.code&&<span className="stock-role candidate-role">建仓候选</span>}</td>
          <td>{m.price.toFixed(2)}</td><td className="positive">{pct(m.pct)}</td></tr>)}</tbody></table>
    </div>
    <small className="riser-caption">{refreshing?'行情待同步 · ':''}{members?.stamp&&members.stamp.slice(5,16).replace('T',' ')+' · '}已核 {members?.checked??0}/{members?.total??0} 只 · 上涨 {rows.length} 只</small>
  </section>;
}
