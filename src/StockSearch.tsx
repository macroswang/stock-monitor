import {useEffect,useId,useRef,useState,type KeyboardEvent} from 'react';
import './stockSearch.css';

type Request=<T>(method:string,args?:Record<string,unknown>)=>Promise<T>;
type Suggestion={code:string;name:string;initials?:string};
type StockSearchProps={request:Request;preview:boolean;value:string;onChange:(value:string)=>void;onSelect:(stock:Suggestion)=>void;
  label?:string;placeholder?:string;disabled?:boolean;autoFocus?:boolean};
const codePattern=/^\d{6}$/;

export default function StockSearch({request,preview,value,onChange,onSelect,label='股票代码/名称/拼音首字母',placeholder='输入代码、名称或拼音首字母',disabled,autoFocus}:StockSearchProps){
  const [open,setOpen]=useState(false);
  const [options,setOptions]=useState<Suggestion[]>([]);
  const [active,setActive]=useState(-1);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const sequence=useRef(0);
  const boxId=useId();
  const wrap=useRef<HTMLDivElement|null>(null);
  const trimmed=value.trim();
  useEffect(()=>{
    if(!trimmed||preview){setOptions([]);setActive(-1);setLoading(false);return;}
    const seq=++sequence.current;
    setLoading(true);setError('');
    const timer=window.setTimeout(async()=>{
      try{
        const result=await request<Suggestion[]>('stock_search',{query:trimmed});
        if(seq!==sequence.current)return;
        setOptions(Array.isArray(result)?result.slice(0,8):[]);
      }catch(cause){
        if(seq!==sequence.current)return;
        setOptions([]);setError(cause instanceof Error?cause.message:'搜索失败');
      }finally{
        if(seq===sequence.current)setLoading(false);
      }
    },200);
    return ()=>window.clearTimeout(timer);
  },[trimmed,request,preview]);
  useEffect(()=>{
    const handler=(event:MouseEvent)=>{
      if(!wrap.current||wrap.current.contains(event.target as Node))return;
      setOpen(false);
    };
    document.addEventListener('mousedown',handler);
    return ()=>document.removeEventListener('mousedown',handler);
  },[]);
  const choose=(stock:Suggestion)=>{
    onChange(stock.name||stock.code);
    setOpen(false);setActive(-1);
    onSelect(stock);
  };
  const onKeyDown=(event:KeyboardEvent<HTMLInputElement>)=>{
    if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);setActive(index=>Math.min(options.length-1,index+1));return;}
    if(event.key==='ArrowUp'){event.preventDefault();setActive(index=>Math.max(-1,index-1));return;}
    if(event.key==='Escape'){setOpen(false);setActive(-1);return;}
    if(event.key==='Enter'){
      if(open&&active>=0&&options[active]){event.preventDefault();choose(options[active]);}
      return;
    }
  };
  const showPanel=open&&(preview||loading||!!error||trimmed.length>0);
  return <div className="stock-search" ref={wrap}>
    <input aria-label={label} role="combobox" aria-expanded={showPanel} aria-controls={boxId} aria-autocomplete="list"
      autoComplete="off" autoFocus={autoFocus} disabled={disabled} placeholder={placeholder} value={value}
      onChange={event=>{onChange(event.target.value);setOpen(true);}}
      onFocus={()=>setOpen(true)}
      onKeyDown={onKeyDown}/>
    {showPanel&&<div className="stock-search-panel" id={boxId} role="listbox" aria-label="股票搜索建议">
      {preview&&<div className="stock-search-note" role="status">浏览器只读预览不支持搜索，请在桌面客户端使用；可直接输入六位代码。</div>}
      {!preview&&loading&&<div className="stock-search-note" role="status">搜索中…</div>}
      {!preview&&!!error&&<div className="stock-search-note error" role="alert">{error}</div>}
      {!preview&&!loading&&!error&&trimmed&&options.length===0&&<div className="stock-search-note" role="status">没有匹配的股票；输入六位代码可直接添加。</div>}
      {!preview&&options.map((option,index)=><button type="button" role="option" aria-selected={index===active} key={option.code}
        className={'stock-search-option'+(index===active?' active':'')}
        onMouseDown={event=>event.preventDefault()} onClick={()=>choose(option)}>
        <b>{option.name}</b><span>{option.code}</span>{option.initials&&<small>{option.initials.toUpperCase()}</small>}
      </button>)}
    </div>}
  </div>;
}
