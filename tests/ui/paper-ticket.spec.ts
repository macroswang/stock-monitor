import {test,expect} from '@playwright/test';
import {maxBuyShares,fractionShares} from '../../src/paperTicket';
test('full-position buy accounts for minimum commission and cent-level transfer fees',()=>{
 expect(maxBuyShares(100000,1000,2,500)).toBe(0);
 expect(maxBuyShares(100500,1000,2,500)).toBe(0);
 expect(maxBuyShares(100501,1000,2,500)).toBe(100);
 expect(maxBuyShares(200501,1000,2,500)).toBe(100);
 expect(maxBuyShares(200502,1000,2,500)).toBe(200);
 expect(maxBuyShares(100021000,1000,2,500)).toBe(100000);
 expect(maxBuyShares(100020999,1000,2,500)).toBe(99900);
 expect(maxBuyShares(50006,500,1.1,0)).toBe(0);expect(maxBuyShares(50007,500,1.1,0)).toBe(100);
 expect(maxBuyShares(100001000,1000,1e-7,0)).toBe(100000);
});
test('fractions preserve whole sellable odd lots only when selecting all',()=>{
 expect(fractionShares(1600,2)).toBe(800);expect(fractionShares(1600,3)).toBe(500);expect(fractionShares(1600,4)).toBe(400);
 expect(fractionShares(155,1)).toBe(155);expect(fractionShares(155,2)).toBe(0);
 expect(maxBuyShares(NaN,1000,2,500)).toBe(0);expect(maxBuyShares(100000,0,2,500)).toBe(0);expect(maxBuyShares(100000,1000,NaN,500)).toBe(0);
});
