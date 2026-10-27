import {test,expect} from '@playwright/test';
import {paperChartMarks} from '../../src/paperMarks';
const fills=[{stamp:'2026-10-19 10:00',side:'buy' as const,shares:100,amount:100000,fills:1},{stamp:'2026-10-19 10:00',side:'buy' as const,shares:200,amount:220000,fills:2},{stamp:'2026-10-19 11:00',side:'sell' as const,shares:100,amount:120000,fills:1},{stamp:'2026-10-20 09:31',side:'sell' as const,shares:100,amount:110000,fills:1}];
test('minute partial fills aggregate by side and actual time with weighted execution price',()=>{
 const m=paperChartMarks(fills.slice(0,3));expect(m.map(p=>p.value)).toEqual(['B','S']);expect(m[0].buyShares).toBe(300);expect(m[0].price).toBeCloseTo(10.6666667);expect(m[0].fills).toBe(3);expect(m[1].time).toBe('11:00');
});
test('daily same-stock buy plus sell becomes T, single-side days remain B or S',()=>{
 const m=paperChartMarks(fills,true);expect(m.map(p=>[p.time,p.value])).toEqual([['2026-10-19','T'],['2026-10-20','S']]);expect(m[0].buyShares).toBe(300);expect(m[0].sellShares).toBe(100);
 expect(paperChartMarks(fills.slice(0,2),true)[0].value).toBe('B');
});
test('same-minute two sides stay separate and large execution counts stay bounded',()=>{
 const m=paperChartMarks([...Array.from({length:10000},()=>fills[0]),{...fills[2],stamp:fills[0].stamp}]);expect(m).toHaveLength(2);expect(m.map(x=>x.value)).toEqual(['B','S']);
});
test('order markers retain their first execution minute with cumulative shares and fill interval',()=>{
 const points=[{order_id:'buy-1',stamp:'2026-10-27 10:53',last_stamp:'2026-10-27 10:55',side:'buy' as const,shares:2000,amount:470000,fills:2},
 {order_id:'buy-2',stamp:'2026-10-27 11:01',last_stamp:'2026-10-27 11:01',side:'buy' as const,shares:100,amount:23400,fills:1}];
 const marks=paperChartMarks(points);expect(marks).toHaveLength(2);
 expect(marks.map(m=>m.time)).toEqual(['10:53','11:01']);expect(marks[0].buyShares).toBe(2000);expect(marks[0].price).toBe(2.35);expect(marks[0].lastTime).toBe('10:55');expect(marks[0].orderCount).toBe(1);expect(marks[0].fills).toBe(2);
});
test('different orders sharing an anchor minute expose the order count without losing totals',()=>{
 const points=['a','b'].map(order_id=>({order_id,stamp:'2026-10-27 10:53',last_stamp:'2026-10-27 10:53',side:'buy' as const,shares:100,amount:23500,fills:1}));
 const marks=paperChartMarks(points);expect(marks).toHaveLength(1);expect(marks[0].orderCount).toBe(2);expect(marks[0].buyShares).toBe(200);
});
