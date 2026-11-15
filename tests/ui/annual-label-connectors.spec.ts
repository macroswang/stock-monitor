import {test,expect,Page} from '@playwright/test';
import {readFileSync,writeFileSync} from 'node:fs';

function fixture(){
 const f=JSON.parse(readFileSync('public/preview.json','utf8')),h=f.history.sh603002;
 const candle=(offset:number)=>h.daily.at(offset);
 const reclaim=candle(-50);
 h.ma250={signals:[{date:reclaim.date,key:'reclaim',close:+reclaim.close,ma250:+reclaim.close*.98,ma5:+reclaim.close*.99,distance_pct:2,touch_date:candle(-55).date,touch_low:+reclaim.close*.97,touch_depth_pct:1,pullback_pct:5,stop:+reclaim.close*.95,strong:false,strong_reasons:['market']}],
  breakouts:[-90,-18].map((offset,i)=>{const b=candle(offset);return {date:b.date,close:+b.close,ma250:+b.close*.98,margin_pct:2,slope60_pct:1,volume_ratio:1.5,days_below:30,quality:i===1};})};
 return f;
}
async function inspect(page:Page){
 return page.getByLabel('日K线及成交量',{exact:true}).evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]),c=e.getInstanceByDom(el),option=c.getOption();
  const rect=(element:any)=>{const r=element.getBoundingRect().clone();r.applyTransform(element.getComputedTransform());return {x:r.x,y:r.y,width:r.width,height:r.height};};
  return c.getModel().getSeries().filter((s:any)=>['年线回踩信号','年线突破信号'].includes(s.name)).flatMap((s:any)=>{
   const d=s.getData();return Array.from({length:d.count()},(_,i)=>{
    const group=d.getItemGraphicEl(i),marker=group?.getSymbolPath(),label=marker?.getTextContent(),line=marker?.getTextGuideLine();
    const shape=marker?.shape,matrix=marker?.getComputedTransform();
    const global=(x:number,y:number)=>matrix?[matrix[0]*x+matrix[2]*y+matrix[4],matrix[1]*x+matrix[3]*y+matrix[5]]:[x,y];
    const arrow=shape?.symbolType==='triangle'?{tip:global(shape.x+shape.width/2,shape.y),base:global(shape.x+shape.width/2,shape.y+shape.height)}:null;
    const value=d.getRawDataItem(i).value,candle=option.series[0].data[option.xAxis[0].data.indexOf(value[0])];
    const highY=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[value[0],candle[3]])[1],lowY=c.convertToPixel({xAxisIndex:0,yAxisIndex:0},[value[0],candle[2]])[1],reclaim=s.name==='年线回踩信号';
    const candleData=c.getModel().getSeriesByIndex(0).getData(),candleIndex=candleData.indexOfName(value[0]),candleShape=candleData.getItemGraphicEl(candleIndex)?.shape;
    // Read actual painted pixels as well as geometry: native Retina canvases
    // have twice as many pixels as the CSS coordinates used by convertToPixel.
    let paintedGap:number|null=null;
    if(arrow){
     for(const canvas of el.querySelectorAll('canvas')){
      const ctx=canvas.getContext('2d');if(!ctx)continue;
      const scale=canvas.width/c.getWidth(),x=Math.round(arrow.tip[0]*scale),tip=arrow.tip[1]*scale,edge=(reclaim?lowY:highY)*scale;
      const y0=Math.max(0,Math.floor(Math.min(tip,edge))-3),y1=Math.min(canvas.height-1,Math.ceil(Math.max(tip,edge))+3);
      if(x<2||x>=canvas.width-2||y1<=y0)continue;
      // Candlestick wick x is snapped to half pixels by ECharts; do not
      // accidentally sample a neighboring candle at a narrow zoom level.
      const wickX=Math.floor((candleShape?.points?.[reclaim?6:4]?.[0]??arrow.tip[0])*scale);
      const pixels=ctx.getImageData(x-1,y0,3,y1-y0+1).data,wickPixels=ctx.getImageData(wickX,y0,1,y1-y0+1).data,markerPixels:number[]=[],candles:number[]=[];
      for(let y=y0;y<=y1;y++)for(let dx=0;dx<3;dx++){
       const k=((y-y0)*3+dx)*4,[r,g,b,a]=pixels.slice(k,k+4);
       if(a>80&&(reclaim?r>g+20&&g>b+40&&y>=tip-2:b>r+30&&b>g+25&&y<=tip+2))markerPixels.push(y);
      }
      for(let y=y0;y<=y1;y++){
       const k=(y-y0)*4,[r,g,b,a]=wickPixels.slice(k,k+4);
       if(a>80&&((r>g+50&&r>b+50&&Math.abs(g-b)<35)||(g>r+60&&g>b+15&&b>r+40))&&Math.abs(y-edge)<=3)candles.push(y);
      }
      if(markerPixels.length&&candles.length)paintedGap=reclaim?Math.min(...markerPixels)-Math.max(...candles)-1:Math.min(...candles)-Math.max(...markerPixels)-1;
     }
    }
    return {value,text:d.getRawDataItem(i).label.formatter,anchor:c.convertToPixel({xAxisIndex:0,yAxisIndex:0},value),candleLowY:lowY,candleHighY:highY,paintedGap,arrow,marker:marker?rect(marker):null,label:label?rect(label):null,hidden:!label||label.ignore,lineHidden:!line||line.ignore,line:line?.shape.points,dash:line?.style.lineDash};
   });
  });
 });
}
test('three annual labels have attached dashed guides that follow resize and keyboard zoom without changing signal anchors',async({page})=>{
 const f=fixture(),h=f.history.sh603002,expected=[...h.ma250.signals,...h.ma250.breakouts].map((s:any)=>[s.date,s.close]);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 const verify=async()=>{
  await expect(async()=>{
   const rows=await inspect(page);expect(rows.map((r:any)=>r.value)).toEqual(expected);expect(rows.map((r:any)=>r.text)).toEqual(['年线回踩','突破年线','突破·确认']);
   for(const row of rows){
    expect(row.hidden).toBe(false);expect(row.lineHidden).toBe(false);expect(row.dash).toEqual([2,2]);
    const start=row.line[0],end=row.line.at(-1),reclaim=row.text==='年线回踩';
    // Inspect the transformed triangle geometry: every arrow points toward its
    // candle, with breakouts above and reclaims below the signal price.
    expect(row.arrow).not.toBeNull();
    expect(Math.abs(row.arrow.tip[1]-row.anchor[1])).toBeLessThan(Math.abs(row.arrow.base[1]-row.anchor[1]));
    expect(reclaim?row.arrow.tip[1]<row.arrow.base[1]:row.arrow.tip[1]>row.arrow.base[1]).toBe(true);
    expect(reclaim?row.marker.y>row.anchor[1]:row.marker.y+row.marker.height<row.anchor[1]).toBe(true);
    const gap=reclaim?row.marker.y-row.candleLowY:row.candleHighY-row.marker.y-row.marker.height;
    expect(gap).toBeGreaterThanOrEqual(.9);expect(gap).toBeLessThanOrEqual(1.6);
    expect(Math.abs(start[0]-end[0])).toBeLessThan(1);
    expect(Math.abs(end[0]-(row.label.x+row.label.width/2))).toBeLessThan(1);
    expect(Math.abs(end[1]-(reclaim?row.label.y:row.label.y+row.label.height))).toBeLessThan(1);
    expect(reclaim?end[1]-start[1]:start[1]-end[1]).toBeGreaterThan(15);
   }
  }).toPass({timeout:5000});
 };
 await verify();await page.setViewportSize({width:1000,height:900});await verify();
 const chart=page.getByLabel('日K线及成交量',{exact:true});await chart.focus();await chart.press('ArrowUp');await verify();await chart.press('ArrowDown');await verify();
 await page.mouse.move(0,0);await chart.screenshot({path:test.info().outputPath('annual-label-guides.png')});
 await page.getByRole('button',{name:'周K',exact:true}).click();
 const series=await page.getByLabel('周K线及成交量',{exact:true}).evaluate(async el=>{const source=await fetch('/src/Chart.tsx').then(r=>r.text()),e=await import(source.match(/from "([^"\n]*echarts\.js[^"\n]*)"/)![1]);return e.getInstanceByDom(el).getOption().series.map((s:any)=>s.name);});
 expect(series).not.toContain('年线回踩信号');expect(series).not.toContain('年线突破信号');expect(errors).toEqual([]);
});

test('a hidden overlapping annual label does not leave an orphan guide',async({page})=>{
 const f=fixture(),b=f.history.sh603002.ma250.breakouts; b.push({...b.at(-1),quality:false});
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 await expect(async()=>{
  const rows=await inspect(page),overlap=rows.filter((r:any)=>r.value[0]===b.at(-1).date);expect(overlap).toHaveLength(2);
  expect(overlap.filter((r:any)=>r.hidden)).toHaveLength(1);
  for(const row of overlap)expect(row.lineHidden).toBe(row.hidden);
 }).toPass({timeout:5000});
});

for(const strong of [false,true])for(const body of ['bull','bear'] as const){
 test(`reclaim marker and label clear the candle low for ${strong?'strong':'normal'} long ${body} bodies through zoom and resize`,async({page})=>{
  const f=fixture(),h=f.history.sh603002,bar=h.daily.at(-50),signal=h.ma250.signals[0],close=+bar.close;
  Object.assign(bar,body==='bull'?{open:String(close*.55),low:String(close*.5),high:String(close*1.1)}:{open:String(close*1.5),low:String(close*.8),high:String(close*1.6)});
  signal.strong=strong;const expected=[signal.date,signal.close];
  await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
  const chart=page.getByLabel('日K线及成交量',{exact:true});
  const verify=async()=>{
   await expect(async()=>{
    const row=(await inspect(page)).find((r:any)=>r.text.startsWith('年线回踩'))!;
    expect(row.value).toEqual(expected);expect(row.hidden).toBe(false);expect(row.lineHidden).toBe(false);
    expect(row.marker.y-row.candleLowY).toBeGreaterThanOrEqual(.9);
    expect(row.marker.y-row.candleLowY).toBeLessThanOrEqual(1.6);
    expect(row.label.y-row.marker.y-row.marker.height).toBeGreaterThan(12);
    expect(row.dash).toEqual([2,2]);
   }).toPass({timeout:5000});
  };
  await verify();await page.setViewportSize({width:1000,height:1100});await verify();
  await chart.focus();await chart.press('ArrowUp');await verify();await chart.press('ArrowDown');await verify();
  await page.mouse.move(0,0);await chart.screenshot({path:test.info().outputPath('reclaim-candle-clearance.png')});
 });
}

test('both breakout arrows stay close above long upper wicks on resize and zoom',async({page})=>{
 const f=fixture(),h=f.history.sh603002,expected=h.ma250.breakouts.map((s:any)=>[s.date,s.close]);
 for(const signal of h.ma250.breakouts){const b=h.daily.find((row:any)=>row.date===signal.date);b.high=String(signal.close*1.15);}
 await page.route('**/preview.json',r=>r.fulfill({json:f}));await page.goto('/');await page.getByRole('button',{name:'日K',exact:true}).click();
 const chart=page.getByLabel('日K线及成交量',{exact:true});
 const verify=async()=>{
  await expect(async()=>{
   const rows=(await inspect(page)).filter((r:any)=>r.text.startsWith('突破'));expect(rows.map((r:any)=>r.value)).toEqual(expected);
   for(const row of rows){
    const gap=row.candleHighY-row.marker.y-row.marker.height;
    expect(row.hidden).toBe(false);expect(row.lineHidden).toBe(false);expect(gap).toBeGreaterThanOrEqual(.9);expect(gap).toBeLessThanOrEqual(1.6);
    expect(row.arrow.tip[1]).toBeGreaterThan(row.arrow.base[1]);
   }
  }).toPass({timeout:5000});
 };
 await verify();await page.setViewportSize({width:1000,height:1100});await verify();await chart.focus();await chart.press('ArrowUp');await verify();
});

for(const deviceScaleFactor of [1,2])test(`painted arrow tips stay within five physical pixels at DPR ${deviceScaleFactor}`,async({browser},info)=>{
 const context=await browser.newContext({viewport:{width:1380,height:980},deviceScaleFactor}),page=await context.newPage();
 try{
  await page.route('**/preview.json',r=>r.fulfill({json:fixture()}));await page.goto(info.project.use.baseURL as string);
  await page.getByRole('button',{name:'日K',exact:true}).click();
  const chart=page.getByLabel('日K线及成交量',{exact:true});
  writeFileSync(info.outputPath('painted-tip-measurements.json'),JSON.stringify(await inspect(page),null,2));
  const verify=async()=>{
   await expect(async()=>{
    const rows=await inspect(page);
    writeFileSync(info.outputPath('painted-tip-last.json'),JSON.stringify(rows,null,2));
    for(const row of rows){expect(row.paintedGap).not.toBeNull();expect(row.paintedGap).toBeGreaterThanOrEqual(1);expect(row.paintedGap).toBeLessThanOrEqual(5);}
    for(const row of rows){
     const reclaim=row.text.startsWith('年线回踩'),gap=reclaim?row.arrow.tip[1]-row.candleLowY:row.candleHighY-row.arrow.tip[1];
     expect(gap*deviceScaleFactor).toBeGreaterThanOrEqual(1);
     expect(gap*deviceScaleFactor).toBeLessThanOrEqual(5);
    }
   }).toPass({timeout:3000}).catch(async error=>{await chart.screenshot({path:info.outputPath('painted-tip-failure.png')});throw error;});
  };
  await verify();await page.setViewportSize({width:1000,height:1100});await verify();await chart.focus();await chart.press('ArrowUp');await verify();await chart.press('ArrowDown');await verify();
  await page.mouse.move(0,0);await chart.screenshot({path:info.outputPath('painted-tip-final.png')});
 }finally{await context.close();}
});
