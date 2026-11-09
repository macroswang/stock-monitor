import {test,expect} from '@playwright/test';
import {volumeDisplayMaximum} from '../../src/volumeScale';

test('large stock and index peaks fit in full with headroom and original inputs stay intact',()=>{
 const values=[5294,2459,3155,...Array(225).fill(211),...Array(12).fill(1323)],before=[...values];
 expect(volumeDisplayMaximum(values)).toBe(6000);expect(values).toEqual(before);
 expect(volumeDisplayMaximum([500,...Array(240).fill(10)])).toBe(600);
 // 康泰医学 2026-11-09：原 500 手上限截掉的盘中峰值和尾盘最高量均须完整显示。
 expect(volumeDisplayMaximum([1143,578,821,558,742,568,929,1271,...Array(230).fill(100)])).toBe(1500);
});
test('sparse and small-unit volumes fit their peaks; missing and zero data retain automatic fallback',()=>{
 for(const values of [[],[null,undefined,NaN,Infinity,-1,0],Array(241).fill(0)])expect(volumeDisplayMaximum(values)).toBeUndefined();
 expect(volumeDisplayMaximum([5000,...Array(18).fill(100)])).toBe(6000);
 expect(volumeDisplayMaximum(Array(241).fill(100))).toBe(120);
 expect(volumeDisplayMaximum([.0211,null,.0002])).toBeCloseTo(.025,8);
});
