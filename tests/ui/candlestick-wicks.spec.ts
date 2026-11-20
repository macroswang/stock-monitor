import {expect,test,type Locator} from '@playwright/test';

async function inspectCandles(chart:Locator){
 return chart.evaluate(async el=>{
  const source=await fetch('/src/Chart.tsx').then(response=>response.text());
  const echarts=await import(source.match(/from ["']([^"'\n]*echarts\.js[^"'\n]*)["']/)![1]);
  const instance=echarts.getInstanceByDom(el);
  const ratio=window.devicePixelRatio;
  const canvas=instance.renderToCanvas({pixelRatio:ratio});
  const pixels=canvas.getContext('2d')!;
  const boxes=instance.getZr().storage.getDisplayList().filter((item:any)=>
   item.type==='normalCandlestickBox'&&!item.__simpleBox);
  let offset=0,paintedOffset=0,painted=0;
  for(const box of boxes){
   const [left,right,,lower,high,top,low,bottom]=box.shape.points as [number,number][];
   const center=(left[0]+right[0])/2;
   for(const point of [high,top,low,bottom])offset=Math.max(offset,Math.abs(point[0]-center));
   if(painted>=5||right[0]-left[0]<1||lower[1]-left[1]<3||top[1]-high[1]<2||low[1]-bottom[1]<2)continue;
   const from=Math.floor((left[0]-.5)*ratio),through=Math.ceil((right[0]+.5)*ratio);
   if(from<0||through>canvas.width)continue;
   const color=String(box.style.stroke).match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i);
   if(!color)continue;
   const rgb=color.slice(1).map(value=>parseInt(value,16));
   const strokeWidth=Number(box.style.lineWidth);
   const paintedCenter=(at:number,width:number)=>{
    const y=Math.floor(at*ratio);
    if(y<0||y>=canvas.height)return null;
    const row=pixels.getImageData(from,y,through-from,1).data;
    let sum=0,weight=0;
    for(let i=0;i<row.length;i+=4){
     if(rgb.some((value,component)=>Math.abs(value-row[i+component])>4))continue;
     const alpha=row[i+3]/255;
     sum+=(from+i/4+.5)*alpha;weight+=alpha;
    }
    // Exclude sample rows obscured by a moving average, label or gridline.
    return weight>0&&Math.abs(weight-width*ratio)<.15?sum/weight:null;
   };
   const body=paintedCenter((left[1]+lower[1])/2,right[0]-left[0]+strokeWidth);
   const upper=paintedCenter((high[1]+top[1])/2,strokeWidth);
   const lowerWick=paintedCenter((low[1]+bottom[1])/2,strokeWidth);
   if(body===null||upper===null||lowerWick===null)continue;
   painted++;
   paintedOffset=Math.max(paintedOffset,Math.abs(body-upper),Math.abs(body-lowerWick));
  }
  return {boxes:boxes.length,offset,painted,paintedOffset};
 });
}

for(const deviceScaleFactor of [1,2])test.describe(`DPR ${deviceScaleFactor}`,()=>{
 test.use({deviceScaleFactor,viewport:{width:1380,height:980}});
 test('daily and weekly wicks share the painted body center before and after zoom and resize',async({page})=>{
  await page.goto('/');
  for(const [tab,label] of [['日K','日K线及成交量'],['周K','周K线及成交量']]){
   await page.getByRole('button',{name:tab,exact:true}).click();
   const chart=page.getByLabel(label,{exact:true});
   for(const width of [1380,1207]){
    await page.setViewportSize({width,height:980});
    if(width===1207)await page.getByRole('button',{name:'放大K线',exact:true}).click();
    await expect.poll(()=>inspectCandles(chart)).toMatchObject({offset:0});
    const candles=await inspectCandles(chart);
    expect(candles.boxes).toBeGreaterThan(10);
    expect(candles.painted).toBeGreaterThan(0);
    expect(candles.paintedOffset).toBeLessThan(.51);
   }
  }
 });
});
