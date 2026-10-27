import type {DailyPattern,PatternLine} from './dailyPatterns';
import {dailyPatternStatus} from './dailyPatterns';
import type {CustomSeriesOption,CustomSeriesRenderItem,ScatterSeriesOption} from 'echarts';

export const dailyPatternColors={'rising-flag':'#ffd166','falling-flag':'#d2a8ff',triangle:'#59e3ff',spring:'#ff8daf'};

/** Price boundaries and actual OHLC anchors only; no target or future extension. */
export function dailyPatternOverlay(patterns:DailyPattern[],width:()=>number):[CustomSeriesOption,ScatterSeriesOption]|[]{
 if(!patterns.length)return [];
 // Keep the structural boundaries. Necklines and rebound zigzags are
 // recognition evidence, not additional overlays on the price chart.
 const segments:{pattern:DailyPattern;line:PatternLine}[]=patterns.flatMap(pattern=>pattern.lines.filter(line=>line.role!=='neckline'&&line.role!=='outline').map(line=>({pattern,line})));
 const markers=patterns.map(p=>{const anchor=p.kind==='spring'&&p.status==='reclaimed'?p.anchors.at(-1)!:p.end;return {value:[anchor.date,anchor.price],patternKey:p.key,itemStyle:{color:dailyPatternColors[p.kind]}};});
 const byKey=new Map(patterns.map(p=>[p.key,p]));
 const renderItem:CustomSeriesRenderItem=(params,api)=>{
  const {pattern:p,line}=segments[params.dataIndex],a=api.coord!([api.value(0),api.value(1)]),b=api.coord!([api.value(2),api.value(3)]);
  const cs=params.coordSys as unknown as {x:number;y:number;width:number;height:number};
  return {type:'group',clipPath:{type:'rect',shape:{x:cs.x,y:cs.y,width:cs.width,height:cs.height}},children:[
   {type:'line',shape:{x1:a[0],y1:a[1],x2:b[0],y2:b[1]},style:{stroke:dailyPatternColors[p.kind],lineWidth:1,opacity:1}},
   ...((line.role==='outline'||line.role==='pole')?[]:[{type:'circle' as const,shape:{cx:a[0],cy:a[1],r:2},style:{fill:dailyPatternColors[p.kind],opacity:1}}])
  ]};
 };
 return [
  {name:'日线形态轮廓',type:'custom',silent:true,z:5,clip:true,tooltip:{show:false},renderItem,
   dimensions:['start','startPrice','end','endPrice'],encode:{x:[0,2],y:[1,3]},
   data:segments.map(({line})=>[line.from.date,line.from.price,line.to.date,line.to.price])},
  {name:'日线形态识别',type:'scatter',z:8,symbol:'circle',symbolSize:5,
   label:{show:true,position:'top',distance:9,fontSize:11,color:'#edf4ff',backgroundColor:'#162238',padding:[3,5],borderRadius:3,
    formatter:params=>{const p=byKey.get((params.data as {patternKey:string}).patternKey);return p?`${p.name} · ${dailyPatternStatus(p)}`:'';}},
   // The price grid starts at y=30. Keep text in its reserved top margin so
   // neither candles nor pattern boundaries can pass through a label.
   labelLayout:params=>({hideOverlap:true,x:Math.max(65,Math.min(params.labelRect.x,width()-35-params.labelRect.width)),y:4,align:'left',verticalAlign:'top'}),
   data:markers}
 ];
}
