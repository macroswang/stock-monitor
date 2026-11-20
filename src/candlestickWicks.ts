import {PRIORITY,registerLayout} from 'echarts';

// ECharts snaps the body edges and the wick separately. Use the midpoint of
// the snapped body so both wicks stay centered at every zoom and display scale.
registerLayout(PRIORITY.VISUAL.LAYOUT+1,{
 seriesType:'candlestick',
 reset(){
  return {
   progress(params,data){
    if(!params.next||data.getLayout('isSimpleBox'))return;
    let index:number|null;
    while((index=params.next())!=null){
     const ends=data.getItemLayout(index)?.ends as [number,number][]|undefined;
     if(ends?.length!==8)continue; // Large mode has no separate body and wicks.
     const center=(ends[0][0]+ends[1][0])/2;
     if(!Number.isFinite(center))continue;
     // The last four points are the upper and lower wick segments.
     for(let end=4;end<8;end++)ends[end][0]=center;
    }
   },
  };
 },
});
