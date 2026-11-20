import type {CustomSeriesRenderItem} from 'echarts';

/** Data zoom filters the series before rendering, so the label follows the visible range. */
export const renderChartLowPoint:CustomSeriesRenderItem=(params,api)=>{
 if(params.dataIndexInside!==0)return;
 let lowest=Infinity,selected=-1;
 for(let i=0;i<params.dataInsideLength;i++){
  const value=Number(api.value('price',i));
  if(Number.isFinite(value)&&value>0&&value<lowest){lowest=value;selected=i;}
 }
 if(selected<0)return;
 const [x,y]=api.coord([api.value('time',selected),lowest]);
 const grid=params.coordSys as {type:string;x:number;y:number;width:number;height:number};
 if(!Number.isFinite(x)||!Number.isFinite(y))return;
 const onRight=x<grid.x+grid.width/2;
 const value=lowest.toFixed(2);
 return {type:'text',style:{
  x:x+(onRight?3:-3),y:Math.min(grid.y+grid.height-7,Math.max(grid.y+7,y)),
  text:onRight?`←${value}`:`${value}→`,align:onRight?'left':'right',verticalAlign:'middle',
  font:'12px sans-serif',fill:'#e5edf8',stroke:'#162031',lineWidth:2
 }};
};
