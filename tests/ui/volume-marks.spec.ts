import {test,expect} from '@playwright/test';
import {topVolumeMarks} from '../../src/volumeMarks';
import type {Bar} from '../../src/models';
const bar=(time:string,volume:number,complete=true):Bar=>({time,volume,complete,close:'10'});
test('top volume appears immediately and is anchored to its own minute',()=>{
 const bars=[bar('09:31',100),bar('09:32',200)];
 expect(topVolumeMarks(bars).map(m=>m.coord[0])).toEqual(['09:31','09:32']);
 expect(topVolumeMarks([...bars,bar('09:33',90),bar('09:34',80)])).toEqual(topVolumeMarks(bars));
});
test('ties mark immediately; unfinished and zero volume do not mark',()=>{
 expect(topVolumeMarks([bar('09:31',0),bar('09:32',100),bar('09:33',100),bar('09:34',200,false)]).map(m=>m.coord[0])).toEqual(['09:32','09:33']);
});
test('later larger volume does not erase earlier marks; missing coverage blocks comparison',()=>{
 const first=topVolumeMarks([bar('09:31',100)]);
 expect(topVolumeMarks([bar('09:31',100),bar('09:32',200)]).slice(0,1)).toEqual(first);
 expect(topVolumeMarks([bar('09:32',200)])).toEqual([]);
});
