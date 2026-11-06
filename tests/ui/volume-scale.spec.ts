import {test,expect} from '@playwright/test';
import {volumeDisplayMaximum} from '../../src/volumeScale';

test('isolated opening spikes no longer flatten regular volume and original inputs stay intact',()=>{
 const values=[5294,2459,3155,...Array(225).fill(211),...Array(12).fill(1323)],before=[...values];
 expect(volumeDisplayMaximum(values)).toBe(2000);expect(values).toEqual(before);
 expect(volumeDisplayMaximum([500,...Array(240).fill(10)])).toBe(20);
});
test('sparse, missing, zero and ordinary volumes keep their automatic linear scale',()=>{
 for(const values of [[],[null,undefined,NaN,Infinity,-1,0],Array(241).fill(0),Array(19).fill(100),[5000,...Array(18).fill(100)],Array(241).fill(100)])expect(volumeDisplayMaximum(values)).toBeUndefined();
});
