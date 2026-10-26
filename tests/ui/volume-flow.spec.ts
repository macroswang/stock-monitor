import {test,expect} from '@playwright/test';
import {splitMinuteVolume} from '../../src/volumeFlow';
import type {VolumeFlow} from '../../src/models';
test('buy sell and gray segments conserve authoritative minute volume; no price-based direction guessing',()=>{
 const bar={time:'09:31',close:'10',volume:1000,complete:true};
 const flow:VolumeFlow={code:'sh603938',day:'2026-10-23',status:'ready',message:'test',minutes:[{time:'09:31',total:1000,buy:600,sell:300,neutral:100,unknown:0,verified:true}]};
 expect(splitMinuteVolume(bar,flow)).toMatchObject({buy:600,sell:300,neutral:100,unknown:0});
 expect(splitMinuteVolume({...bar,volume:1001},flow)).toMatchObject({buy:0,sell:0,unknown:1001,verified:false});
 expect(splitMinuteVolume({...bar,complete:false},flow)).toMatchObject({unknown:1000,verified:false});
 expect(splitMinuteVolume(bar)).toMatchObject({unknown:1000,verified:false});
 const corrupt={...flow,minutes:[{...flow.minutes[0],buy:-100,sell:1000}]};expect(splitMinuteVolume(bar,corrupt).verified).toBe(false);
});

test('one-hand reconciliation changes only visual allocation, raw buy and sell counts remain explicit',()=>{
 const bar={time:'10:36',close:'2.24',volume:6212500,complete:true};
 const flow:VolumeFlow={code:'sz000981',day:'2026-10-23',status:'ready',message:'test',minutes:[{time:'10:36',total:6212500,source_total:6212600,difference:100,approximate:true,buy:6134600,sell:78000,neutral:0,unknown:0,verified:true}]};
 const d=splitMinuteVolume(bar,flow);expect(d.verified).toBe(true);expect(d.approximate).toBe(true);expect(d.rawBuy).toBe(6134600);expect(d.rawSell).toBe(78000);
 expect(d.buy+d.sell+d.neutral+d.unknown).toBe(bar.volume);
 expect(splitMinuteVolume(bar,{...flow,total_only:true}).verified).toBe(false);
 const bad={...flow,minutes:[{...flow.minutes[0],source_total:10000000,buy:9922000}]};expect(splitMinuteVolume(bar,bad).verified).toBe(false);
});
