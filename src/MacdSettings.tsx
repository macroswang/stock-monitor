import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {defaultMacdParameters,parseMacdParameters,type MacdParameters} from './minuteMacd';
import './macdSettings.css';

export default function MacdSettings({value,onChange,onClose}:{value:MacdParameters;onChange:(v:MacdParameters)=>void;onClose:()=>void}){
 const [draft,setDraft]=useState(value),[error,setError]=useState('');
 const title=useId(),form=useRef<HTMLFormElement>(null);
 useEffect(()=>{
  const previous=document.activeElement as HTMLElement|null;
  form.current?.querySelector('input')?.focus();
  return()=>previous?.focus({preventScroll:true});
 },[]);
 return createPortal(<div className="modal-overlay macd-settings-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
  <form ref={form} className="card macd-settings-dialog" role="dialog" aria-modal="true" aria-labelledby={title} onKeyDown={e=>{
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onClose();}
   if(e.key==='Tab'){
    const controls=form.current?.querySelectorAll<HTMLElement>('input,button');if(!controls?.length)return;
    const first=controls[0],last=controls[controls.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
   }
  }} onSubmit={e=>{e.preventDefault();const next=parseMacdParameters(draft);if(!next){setError('请输入1–250的整数，短周期须小于长周期。');return;}onChange(next);onClose();}}>
   <h2 id={title}>MACD周期设置</h2><p>个股与大盘使用相同参数</p>
   <div className="macd-period-fields">{([['fast','短周期'],['slow','长周期'],['signal','信号周期']] as const).map(([key,label])=><label key={key}>{label}<input aria-label={label} type="number" min="1" max="250" step="1" required value={Number.isNaN(draft[key])?'':draft[key]} onChange={e=>{setError('');setDraft({...draft,[key]:e.target.value===''?NaN:Number(e.target.value)});}}/></label>)}</div>
   {error&&<p className="macd-settings-error" role="alert">{error}</p>}
   <div className="macd-settings-actions"><button type="button" className="macd-reset" onClick={()=>{setDraft({...defaultMacdParameters});setError('');}}>恢复默认</button><button type="button" onClick={onClose}>取消</button><button className="primary" type="submit">保存</button></div>
  </form>
 </div>,document.body);
}
