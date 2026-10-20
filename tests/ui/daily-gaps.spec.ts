import {test,expect} from '@playwright/test';
import {dailyGaps} from '../../src/dailyGaps';
import type {Daily} from '../../src/models';
const day=(date:string,low:number,high:number):Daily=>({date,low:String(low),high:String(high),open:String(low),close:String(high),volume:'100'});
test('up gap shrinks on partial fill and is removed exactly on full fill',()=>{
 const bars=[day('2026-10-12',9,10),day('2026-10-13',12,13),day('2026-10-14',11,12)];
 const g=dailyGaps(bars)[0];expect([g.low,g.high]).toEqual([10,11]);expect(g.filledOn).toBeUndefined();
 expect(dailyGaps([...bars,day('2026-10-15',10,12)])[0].filledOn).toBe('2026-10-15');
});
test('down gap shrinks and boundary equality closes it; touching bars create no gap',()=>{
 const bars=[day('2026-10-12',12,13),day('2026-10-13',9,10),day('2026-10-14',9,11)];
 expect(dailyGaps(bars)[0]).toMatchObject({direction:'down',low:11,high:12});
 expect(dailyGaps([...bars,day('2026-10-15',10,12)])[0].filledOn).toBe('2026-10-15');
 expect(dailyGaps([day('2026-10-12',9,10),day('2026-10-13',10,11)])).toEqual([]);
});
test('gap remains provisional for an unfinished daily candle',()=>{
 expect(dailyGaps([day('2026-10-12',9,10),{...day('2026-10-13',12,13),provisional:true}])[0].provisional).toBe(true);
});
