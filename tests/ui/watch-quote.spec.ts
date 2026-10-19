import {test,expect} from '@playwright/test';
import {quoteStats} from '../../src/watchQuote';
test('change is yuan not vendor percent; amplitude uses previous close',()=>{
 const q={price:'10.5',previous_close:'10',high:'10.8',low:'9.8',change:'5',timestamp:''};
 expect(quoteStats(q).change).toBeCloseTo(.5);expect(quoteStats(q).percent).toBeCloseTo(5);expect(quoteStats(q).amplitude).toBeCloseTo(10);
 expect(quoteStats({...q,price:'9.5'}).percent).toBeCloseTo(-5);
});
test('missing or invalid reference/range remains unknown rather than zero',()=>{
 expect(quoteStats()).toEqual({change:null,percent:null,amplitude:null});
 expect(quoteStats({price:'10',previous_close:'0',timestamp:''}).percent).toBeNull();
 expect(quoteStats({price:'10',previous_close:'10',high:'9',low:'11',timestamp:''}).amplitude).toBeNull();
});
