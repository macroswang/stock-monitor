import {test,expect} from '@playwright/test';
import {DAILY_WINDOW,WEEKLY_WINDOW,dailyViewport,zoomCandleWindow} from '../../src/dailyWindow';
const dates=Array.from({length:300},(_,i)=>new Date(Date.UTC(2025,0,i+1)).toISOString().slice(0,10));
test('daily view starts two up-arrow steps closer than 250 candles and grows a short cache',()=>{
 let zoom={lo:50,hi:299};for(let i=0;i<2;i++)zoom=zoomCandleWindow(dates.length,zoom.lo,zoom.hi,-1,299);
 expect(DAILY_WINDOW).toBe(120);
 expect(zoom.hi-zoom.lo+1).toBe(DAILY_WINDOW);
 expect(WEEKLY_WINDOW).toBe(250);
 expect(dailyViewport(dates,[],dates.at(-1),'')).toEqual({lo:180,hi:299});
 const first=dates.slice(-59);expect(dailyViewport(first,[],first.at(-1),'')).toEqual({lo:0,hi:58});
 const v=dailyViewport(dates,[first[0],first.at(-1)!],dates.at(-1),first.at(-1)!);expect(v.hi-v.lo+1).toBe(120);expect(v.hi).toBe(299);
});
test('prepending history keeps the same visible dates; moving one day shifts only as needed',()=>{
 const old=dates.slice(100),prior=[old[0],old[89]];const kept=dailyViewport(dates,prior,old[0],dates.at(-1)!,90);
 expect(dates[kept.lo]).toBe(prior[0]);expect(dates[kept.hi]).toBe(prior[1]);
 const moved=dailyViewport(dates,prior,dates[99],dates.at(-1)!,90);expect(moved).toEqual({lo:99,hi:188});
});
test('new latest candle follows the end only when the user was viewing the end',()=>{
 const old=dates.slice(0,-1);expect(dailyViewport(dates,[old.at(-90)!,old.at(-1)!],undefined,old.at(-1)!,90)).toEqual({lo:210,hi:299});
 expect(dailyViewport(dates,[dates[10],dates[99]],dates[50],old.at(-1)!,90)).toEqual({lo:10,hi:99});
});
