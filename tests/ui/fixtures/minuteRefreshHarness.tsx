import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import Chart from '../../../src/Chart';
import type {Bar,IndexMinute} from '../../../src/models';
import '../../../src/style.css';

const day='2026-11-16';
const bars:Bar[]=Array.from({length:60},(_,i)=>({
 time:`${String(Math.floor((570+i)/60)).padStart(2,'0')}:${String((570+i)%60).padStart(2,'0')}`,
 close:(10+Math.sin(i/6)*.1+i*.003).toFixed(3),average:(10+i*.002).toFixed(3),volume:1000+i*100,complete:true,
}));
function Harness(){
 const [metadata,setMetadata]=useState(0),[updates,setUpdates]=useState(0),[code,setCode]=useState('sz000981');
 const [trade,setTrade]=useState(false),[future,setFuture]=useState(false),[priceTicks,setPriceTicks]=useState(0);
 const [flat,setFlat]=useState(false);
 const [cacheClock,setCacheClock]=useState('12:00'),[indexClock,setIndexClock]=useState('12:00');
 const feed=bars.map((bar,i)=>flat&&i>=48?{...bar,close:'10.15'}:bar);
 const data=feed.map((bar,i)=>({...bar,...(i===bars.length-1?{close:(Number(bar.close)+(updates+priceTicks)*.01).toFixed(3),volume:bar.volume+updates*100}:{})}));
 const index:IndexMinute={code:'sz399001',name:'深证成指',date:day,previous_close:'10000',source:'refresh-fixture',
  cached_at:`${day}T${indexClock}:${String(metadata%60).padStart(2,'0')}+08:00`,
  bars:bars.map((bar,i)=>({time:bar.time,close:String(10000+(Number(bar.close)+(i===bars.length-1?updates*.01:0))*10),volume_lots:1000+i*100}))};
 return <><div className="refresh-actions">
  <button onClick={()=>setMetadata(n=>n+1)}>只更新缓存时间</button>
  <button onClick={()=>setUpdates(n=>n+1)}>更新实际行情</button>
  <button onClick={()=>setPriceTicks(n=>n+1)}>只更新末端价格</button>
  <button onClick={()=>setFlat(true)}>平稳坐标行情</button>
  <button onClick={()=>setCode(c=>c==='sz000981'?'sz000001':'sz000981')}>切换股票</button>
  <button onClick={()=>setCacheClock('10:28')}>收紧缓存截止</button>
  <button onClick={()=>setCacheClock('10:29')}>推进缓存截止</button>
  <button onClick={()=>setIndexClock('10:28')}>收紧指数截止</button>
  <button onClick={()=>setIndexClock('10:29')}>推进指数截止</button>
  <button onClick={()=>setTrade(value=>!value)}>切换成交标记</button>
  <button onClick={()=>setFuture(value=>!value)}>切换未来缓存</button>
  <output aria-label="刷新批次">{metadata}|{updates}</output>
 </div><div className="market-grid"><div/><div className="card detail minute-detail">
  <Chart stockCode={code} stockName="刷新测试" view="minute" selectedDay={day} minute={data} previousClose={10}
   minuteCachedAt={`${future?'2099-01-01':day}T${cacheClock}:${String(metadata%60).padStart(2,'0')}+08:00`} macdBenchmark={index} fixedTurningMode="zhangle"
   autoTrading={{code,day,accounts:[],points:trade?[{id:'refresh-order',account_id:'a',broker_name:'测试',account_masked:'***',code,day,side:'buy',status:'accepted',mode:'live',created_at:day+'T09:32:00+08:00',ordered_at:day+'T09:32:00+08:00',order_price:'10.01',quantity:100,attempted:true,message:''}]:[]}}/>
 </div></div></>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
