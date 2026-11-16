import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {Daily} from './models';
import {stockTraits} from './stockTraits';
import {requestWithTimeout} from './requestTimeout';
import './stockReference.css';

type Tag={name:string;code?:string;kind?:string};
type Profile={code:string;industry:string[];boards:Tag[];concepts:Tag[];attributes:Tag[];collected_at:string;partial?:boolean};
type Report={code:string;data:Profile|null;themes:Tag[];observations?:Tag[];theme_status?:'available'|'unmatched'|'unavailable';theme_published_at?:string|null;scope?:string;running:boolean;error:string};
type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
const list=(rows:Tag[],limit=2)=>rows.slice(0,limit).map(x=>x.name).join('、')+(rows.length>limit?' +'+(rows.length-limit):'');
const signed=(n:number)=>`${n>0?'+':''}${n.toFixed(1)}%`;

export default function StockReference({request,code,name,day,daily,active=true}:{request:Request;code:string;name:string;day:string;daily:Daily[];active?:boolean}){
  const scope=code+'|'+day;
  const [report,setReport]=useState<Report>();const [open,setOpen]=useState(false);
  const root=useRef<HTMLDetailsElement>(null);
  const popup=useRef<HTMLElement>(null);
  const [position,setPosition]=useState({left:0,top:0,width:510,maxHeight:600});
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{
      const rect=root.current?.getBoundingClientRect();if(!rect)return;
      const width=Math.min(510,window.innerWidth-24);
      const top=rect.bottom+6;
      setPosition({left:Math.max(12,Math.min(window.innerWidth-width-12,rect.right-width)),top,width,maxHeight:Math.max(100,window.innerHeight-top-12)});
    };
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open,code]);
  useEffect(()=>{
    setOpen(false);setReport(undefined);if(!active||!code)return;
    let alive=true,timer:ReturnType<typeof setTimeout>;
    const load=async()=>{
      try{
        const result=await requestWithTimeout(request<Report>('stock_profile',{code,day}));
        if(!alive)return;
        if(result.code!==code||result.data&&result.data.code!==code)throw Error('个股资料不匹配');
        setReport({...result,scope});timer=setTimeout(load,result.running?1500:60000);
      }catch{
        if(alive){setReport(previous=>previous?.scope===scope?{...previous,running:false,error:'资料暂未取得'}:{code,scope,data:null,themes:[],theme_status:'unavailable',running:false,error:'资料暂未取得'});timer=setTimeout(load,10000);}
      }
    };
    void load();return()=>{alive=false;clearTimeout(timer);};
  },[request,code,day,active]);
  useEffect(()=>{
    if(!open)return;
    const close=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node)&&!popup.current?.contains(e.target as Node))setOpen(false);};
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false);};
    document.addEventListener('pointerdown',close);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',escape);};
  },[open]);
  const now=Date.now(),traits=stockTraits(daily,day,now);
  const current=report?.code===code&&report.scope===scope?report:undefined;
  const collected=Date.parse(current?.data?.collected_at||'');
  const profile=Number.isFinite(collected)&&collected<=now&&now-collected<=86400000?current?.data:null;
  const published=current?.theme_published_at?Date.parse(current.theme_published_at):null;
  const themeValid=published===null||Number.isFinite(published)&&published<=now;
  const themes=themeValid?current?.themes??[]:[],observations=themeValid?current?.observations??[]:[],concepts=profile?.concepts??[],attributes=profile?.attributes??[];
  const pending=!current||current.running&&!profile;
  const industry=profile?.industry.at(-1)||list(profile?.boards??[],1);
  const behavior=attributes.find(tag=>/盘股|昨日/.test(tag.name))??attributes.find(tag=>!/^20\d{2}(?:中报|年报|季报)/.test(tag.name));
  const stockStyle=[behavior?.name,traits?`均振幅 ${traits.amplitude.toFixed(1)}%`:null].filter(Boolean).join(' · ');
  const placeholder=pending?'读取中':'待补充';
  const tags=(items:Tag[],empty='暂无匹配')=>items.length?<div className="stock-reference-tags">{items.map((tag,i)=><span key={tag.name+i}>{tag.name}{tag.kind&&<small>{tag.kind}</small>}</span>)}</div>:<span className="stock-reference-muted">{empty}</span>;
  return <details className="stock-reference" ref={root} open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary aria-label={`${name}个股资料`} title="展开行业、概念、题材与股性" onKeyDown={e=>{if(e.key==='Escape')setOpen(false);}}>
      <span className="stock-reference-compact">个股资料 <em aria-hidden="true">▾</em></span>
      <span><i>行业/板块</i><b title={profile?.industry.join(' / ')}>{industry||placeholder}</b></span>
      <span><i>概念</i><b title={concepts.map(x=>x.name).join('、')}>{list(concepts)||placeholder}</b></span>
      <span><i>题材</i><b title={themes.map(x=>x.name).join('、')}>{list(themes)||(!pending&&themeValid&&current?.theme_status!=='unavailable'?'暂无匹配':placeholder)}</b></span>
      <span><i>股性</i><b>{stockStyle||(!pending?'样本不足':placeholder)}</b><em aria-hidden="true">{open?'▴':'▾'}</em></span>
    </summary>
    {open&&createPortal(<section className="stock-reference-popup" ref={popup} style={position} aria-label={`${name}资料详情`}>
      <div className="stock-reference-heading"><strong>{name} · 个股资料</strong><button type="button" aria-label="收起个股资料" onClick={()=>setOpen(false)}>×</button></div>
      <dl>
        <dt>行业/板块</dt><dd>{profile?.industry.length?<p>{profile.industry.join(' / ')}</p>:null}{tags(profile?.boards??[],placeholder)}</dd>
        <dt>概念</dt><dd>{tags(concepts,placeholder)}</dd>
        <dt>题材</dt><dd>{tags(themes,!themeValid||current?.theme_status==='unavailable'?'研判资料待补充':'暂无匹配')}{!!observations.length&&<><small className="stock-reference-method">名称观察</small>{tags(observations)}</>}</dd>
        <dt>股性</dt><dd>{tags(attributes,'')}{traits?<div className="stock-traits">
          <span>平均振幅 <b>{traits.amplitude.toFixed(2)}%</b></span><span>区间涨跌 <b>{signed(traits.change)}</b></span>
          <span>上涨天数 <b>{traits.up}/20</b></span><span>成交量比 <b>{traits.volumeRatio?.toFixed(2)??'—'}</b></span>
        </div>:<span className="stock-reference-muted">日K样本不足或未完整，暂不统计</span>}
        <small className="stock-reference-method">归属标签为当前资料；题材与股性按所选K线范围展示。近20根完整未复权日K统计；成交量比为末根成交量÷此前20根平均量。</small></dd>
      </dl>
      {current?.error&&<p className="stock-reference-muted">{current.error}</p>}
      {profile?.partial&&<p className="stock-reference-muted">部分资料待补充</p>}
    </section>,document.body)}
  </details>;
}
