import {test,expect} from '@playwright/test';
import {weeklyBars,candleDate,movingAverage,parsePeriods,candleHistoryNeed} from '../../src/candleData';
import {dailyViewport,zoomCandleWindow} from '../../src/dailyWindow';
import type {Daily} from '../../src/models';
const b=(date:string,open=10,close=11,volume=100):Daily=>({date,open:String(open),close:String(close),high:String(Math.max(open,close)+1),low:String(Math.min(open,close)-1),volume:String(volume),volume_unit:'shares'});
test('weekly OHLC and volume aggregate observed days across holidays and year boundaries',()=>{
 const rows=[b('2026-01-05',20,22,700),b('2025-12-31',12,14,300),b('2025-12-29',10,13,100),b('2025-12-30',13,12,200)];
 const w=weeklyBars(rows);expect(w).toHaveLength(2);expect(w[0]).toMatchObject({date:'2025-12-31',startDate:'2025-12-29',weekStart:'2025-12-29',open:'10',close:'14',high:'15',low:'9',volume:'600'});expect(w[1].volume).toBe('700');
 expect(candleDate(w,'2026-01-02',true)).toBe('2025-12-31');expect(rows[0].volume).toBe('700');
});
test('weekly updates replace duplicate daily candles instead of double counting them',()=>{
 const first=b('2026-11-02',10,11,100),live={...b('2026-11-03',11,12,200),provisional:true};
 expect(weeklyBars([first,b('2026-11-03',11,11,120),live])[0]).toMatchObject({volume:'300',close:'12',provisional:true});
});
test('SMA warms up on full history, never substitutes short averages for missing periods',()=>{
 const rows=Array.from({length:10},(_,i)=>b(`2026-11-${String(i+1).padStart(2,'0')}`,i+1,i+1));
 expect(movingAverage(rows,5)).toEqual([null,null,null,null,3,4,5,6,7,8]);expect(movingAverage(rows,20).every(v=>v===null)).toBe(true);
 expect(movingAverage(rows,5).slice(-3)).toEqual([6,7,8]);
});
test('daily and weekly history demand includes the visible window plus MA warm-up',()=>{
 expect(candleHistoryNeed(90,{periods:[5,10,20,250],enabled:[250],visible:true})).toBe(339);
 expect(candleHistoryNeed(120,{periods:[5,10,20,250],enabled:[20,250],visible:true})).toBe(369);
 expect(candleHistoryNeed(90,{periods:[250],enabled:[250],visible:false})).toBe(90);
 expect(candleHistoryNeed(90,{periods:[250],enabled:[],visible:true})).toBe(90);
});
test('manual periods accept Chinese separators and reject fractional, excessive or invalid values',()=>{
 expect(parsePeriods('5，10、20 30')).toEqual([5,10,20,30]);expect(parsePeriods('5,5,10')).toEqual([5,10]);
 for(const input of ['', '0,5','5.5,10','5,251','NaN','1,2,3,4,5,6,7,8,9'])expect(parsePeriods(input)).toBeNull();
});
test('keyboard zoom preserves anchor position and keeps user zoom after prepending history',()=>{
 expect(zoomCandleWindow(300,210,299,-1,299)).toMatchObject({lo:240,hi:299,desired:60});
 const zoom=zoomCandleWindow(300,210,299,1,299);expect(zoom).toMatchObject({lo:180,hi:299,desired:120});
 const dates=Array.from({length:400},(_,i)=>String(i));expect(dailyViewport(dates,['340','399'],'399','399',60)).toEqual({lo:340,hi:399});
 expect(zoomCandleWindow(30,0,29,1,29)).toEqual({lo:0,hi:29,desired:45});
});
