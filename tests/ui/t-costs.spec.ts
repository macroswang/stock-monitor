import {test,expect} from '@playwright/test';
import {tProfit,defaultTCosts} from '../../src/tCosts';
test('100 shares, commission minimum on both legs, sell-only stamp tax',()=>{
 const r=tProfit(10.21,10.10,{...defaultTCosts,shares:100})!;
 expect(r.gross).toBe(11);expect(r.commission).toBe(10);expect(r.stamp).toBe(.51);expect(r.transfer).toBe(.02);expect(r.net).toBe(.47);
});
test('positive gross spread can still lose money after minimum commissions',()=>{
 const r=tProfit(10.21,10.20,{...defaultTCosts,shares:100})!;
 expect(r.gross).toBe(1);expect(r.net).toBe(-9.53);
});
test('commission grows above minimum; included transfer is not charged twice',()=>{
 const r=tProfit(100,99,{...defaultTCosts,shares:1000})!;
 expect(r.commission).toBe(39.8);expect(r.stamp).toBe(50);expect(r.transfer).toBe(1.99);
 const included=tProfit(100,99,{...defaultTCosts,shares:1000,transferIncluded:true})!;
 expect(included.transfer).toBe(0);expect(included.net-r.net).toBeCloseTo(1.99);
});
test('adverse slippage on both legs and invalid inputs',()=>{
 const r=tProfit(10,10,{...defaultTCosts,shares:100,slippagePerMille:1})!;
 expect(r.slippage).toBe(2);expect(r.net).toBeLessThan(tProfit(10,10,{...defaultTCosts,shares:100})!.net);
 expect(tProfit(0,10,defaultTCosts)).toBeNull();expect(tProfit(10,10,{...defaultTCosts,shares:0})).toBeNull();expect(tProfit(10,10,{...defaultTCosts,minimum:NaN})).toBeNull();
});
test('Shanzi 2000-share trade is profitable; separate 100-share trade is not proportional under minimum fees',()=>{
 const actual=tProfit(2.46,2.41,{...defaultTCosts,shares:2000})!;
 const hundred=tProfit(2.46,2.41,{...defaultTCosts,shares:100})!;
 expect(actual.gross).toBe(100);expect(actual.commission).toBe(10);expect(actual.stamp).toBe(2.46);expect(actual.transfer).toBe(.10);expect(actual.net).toBe(87.44);
 expect(hundred.gross).toBe(5);expect(hundred.net).toBe(-5.12);
 expect(defaultTCosts.shares).toBe(2000);expect(defaultTCosts.commissionWan).toBe(2);
});
