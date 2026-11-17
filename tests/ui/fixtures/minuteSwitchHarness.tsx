import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import Chart from '../../../src/Chart';
import '../../../src/style.css';
const day='2026-11-17';
function Harness(){
 const [code,setCode]=useState('sz000981');
 const base=code==='sz000981'?2.1:28;
 const minute=Array.from({length:60},(_,i)=>({time:`${String(Math.floor((570+i)/60)).padStart(2,'0')}:${String((570+i)%60).padStart(2,'0')}`,close:String(base+Math.sin(i/6)*base*.01),average:String(base),volume:1000+i*100,complete:true}));
 return <div className="workspace market-workspace"><header style={{height:80}}><button onClick={()=>setCode('sz000981')}>山子高科</button><button onClick={()=>setCode('sh603938')}>三孚股份</button></header><section className="market-grid"><div/><div className="card detail minute-detail" data-stock={code}>
 <div className="detail-top"><h2>{code}</h2></div><div className="chart-toolbar"><span>分时</span></div>
 <Chart key={code} stockCode={code} stockName={code} view="minute" selectedDay={day} minute={minute} previousClose={base} fixedTurningMode="zhangle" minuteCachedAt={day+'T16:00:00+08:00'}/>
 </div></section></div>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
