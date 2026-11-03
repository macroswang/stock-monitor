import {useState} from 'react';
import {MA_COLORS,parsePeriods,type MovingAverages} from './candleData';
import './candleControls.css';

export default function CandleControls({value,onChange,onZoom}:{value:MovingAverages;onChange:(v:MovingAverages)=>void;onZoom:(direction:number)=>void}){
 const [draft,setDraft]=useState(value.periods.join(', ')),[error,setError]=useState('');
 return <div className="candle-controls" role="group" aria-label="K线显示设置">
  <label><input type="checkbox" checked={value.visible} onChange={e=>onChange({...value,visible:e.target.checked})}/>均线</label>
  {value.periods.map((n,i)=><label key={n} className="ma-toggle" style={{color:MA_COLORS[i]}}><input aria-label={`MA${n}`} type="checkbox" disabled={!value.visible} checked={value.enabled.includes(n)} onChange={e=>onChange({...value,enabled:e.target.checked?[...value.enabled,n]:value.enabled.filter(p=>p!==n)})}/><i style={{backgroundColor:MA_COLORS[i]}}/>MA{n}</label>)}
  <details className="ma-settings"><summary onClick={()=>{setDraft(value.periods.join(', '));setError('');}}>均线设置</summary><form onSubmit={e=>{e.preventDefault();const periods=parsePeriods(draft);if(!periods){setError('请输入 1–250 的整数，最多 8 条，用逗号分隔。');return;}onChange({periods,enabled:periods,visible:true});e.currentTarget.closest('details')?.removeAttribute('open');}}>
   <label>均线周期<input aria-label="均线周期" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="5, 10, 20, 30" autoComplete="off"/></label><small>日 K 按交易日，周 K 按周计算</small>{error&&<span className="ma-error" role="alert">{error}</span>}<button type="submit" className="primary">应用</button>
  </form></details>
  <div className="candle-zoom"><button aria-label="放大K线" title="放大K线（↑）" onClick={()=>onZoom(-1)}>＋</button><button aria-label="缩小K线" title="缩小K线（↓）" onClick={()=>onZoom(1)}>−</button><span>↑ 放大 / ↓ 缩小</span></div>
 </div>;
}
