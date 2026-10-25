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
