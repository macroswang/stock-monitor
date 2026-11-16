import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import Chart from '../../../src/Chart';
import {previewDrawings} from '../../../src/candleDrawingModel';
import '../../../src/style.css';
const fixture=await fetch('/preview.json').then(response=>response.json());
const w=window as any;
w.__drawingReleases=[];
async function request<T>(method:string,args:Record<string,unknown>={}):Promise<T>{
 const captured=method==='chart_drawings'&&w.__captureDrawingReads?previewDrawings(method,args):null;
 if(w.__holdDrawings?.[method]===args.code)await new Promise<void>(resolve=>w.__drawingReleases.push({method,code:args.code,resolve}));
 if(w.__failDrawingMethod===method)throw Error('模拟断开连接');
 return (captured||previewDrawings(method,args)) as T;
}
function Harness(){
 const [code,setCode]=useState('sh603002'),[frame,setFrame]=useState<'daily'|'weekly'>('daily'),[prepend,setPrepend]=useState(false),[thursday,setThursday]=useState(false),[empty,setEmpty]=useState(false),[shift,setShift]=useState(false),[wide,setWide]=useState(false);
 const original=(fixture.history as any)[code].daily;
 const older=Array.from({length:5},(_,i)=>({...original[0],date:`2025-12-${String(8+i).padStart(2,'0')}`}));
 const window=shift?[...original.slice(1),{...original.at(-1),date:'2026-10-19'}]:original;
 const daily=empty?[]:[...(prepend?older:[]),...window].filter(row=>!thursday||row.date!=='2026-10-16').map((row,i,list)=>wide&&i===list.length-1?{...row,high:'80'}:row);
 return <><button onClick={()=>setCode('sh603002')}>股票A</button><button onClick={()=>setCode('sh688680')}>股票B</button><button onClick={()=>setFrame(frame==='daily'?'weekly':'daily')}>切换周期</button><button onClick={()=>setPrepend(true)}>补充历史</button><button onClick={()=>setThursday(!thursday)}>更新本周</button><button onClick={()=>setEmpty(!empty)}>切换空行情</button><button onClick={()=>setShift(!shift)}>等长更新行情</button><button onClick={()=>setWide(!wide)}>改变价格范围</button><div className="market-grid"><div/><div className="card detail">
  <Chart key={w.__reuseDrawingChart?'shared':code} drawingRequest={request} stockCode={code} daily={daily} selectedDay="2026-10-16" view={frame}/>
 </div></div></>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
