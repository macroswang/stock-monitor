import {test,expect} from '@playwright/test';
import {resolvedPriceLimits,intradayPriceScale,priceLimitState,pricePercent} from '../../src/priceLimits';
test('main board ceiling is the exact market price, not a rounded chart tick',()=>{
 const limits=resolvedPriceLimits(11.55,[11.9,12.71],{up:12.71,down:10.4});const scale=intradayPriceScale(11.55,[11.9,12.71],limits);
 expect(scale.max).toBe(12.71);expect(scale.min).toBeGreaterThanOrEqual(10.4);expect(priceLimitState(12.71,limits)).toBe('涨停');expect(priceLimitState(12.70,limits)).toBeNull();expect(pricePercent(12.71,11.55)).toBe('+10.04%');
});
test('20 percent and lower-limit prices use the same exact market reference',()=>{
 const limits=resolvedPriceLimits(10,[8,10,12],{up:12,down:8});const scale=intradayPriceScale(10,[8,10,12],limits);
 expect(scale.min).toBe(8);expect(scale.max).toBe(12);expect(priceLimitState(8,limits)).toBe('跌停');expect(pricePercent(12,10)).toBe('+20.00%');
});
test('unknown or inconsistent limits do not manufacture a 10 percent ceiling',()=>{
 expect(resolvedPriceLimits(undefined,[12],{up:12})).toEqual({});expect(resolvedPriceLimits(10,[13],{up:11}).up).toBeUndefined();
 const limits=resolvedPriceLimits(10,[13],{});expect(intradayPriceScale(10,[13],limits).max).toBeGreaterThanOrEqual(13);
});
