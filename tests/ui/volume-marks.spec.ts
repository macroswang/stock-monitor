import {test,expect} from '@playwright/test';
import {topVolumeMarks} from '../../src/volumeMarks';
import type {Bar,Event} from '../../src/models';
const bar=(time:string,volume:number,complete=true):Bar=>({time,volume,complete,close:'10'});
const event=(candidate_time='09:32',confirmation_label='09:34',event_label=confirmation_label):Event=>({key:candidate_time,symbol:'000815',trading_date:'2026-10-19',candidate_time,confirmation_label,event_label,volumes:[200,90,80],mode:'history'});
const bars=[bar('09:31',100),bar('09:32',200),bar('09:33',90),bar('09:34',80)];
test('no marker until both complete confirmation minutes and confirmed event exist',()=>{
 expect(topVolumeMarks(bars)).toEqual([]);
 expect(topVolumeMarks(bars.slice(0,2),[event()])).toEqual([]);
 expect(topVolumeMarks(bars.slice(0,3),[event()])).toEqual([]);
 expect(topVolumeMarks([...bars.slice(0,3),bar('09:34',80,false)],[event()])).toEqual([]);
 expect(topVolumeMarks(bars,[event()])).toEqual([{coord:['09:32',10],value:'触发'}]);
});
test('confirmed marker stays on original top even after later larger volume',()=>{
 const first=topVolumeMarks(bars,[event()]);
 expect(topVolumeMarks([...bars,bar('09:35',300)],[event()])).toEqual(first);
 expect(topVolumeMarks(bars,[event(),{...event(),mode:'live'}])).toEqual(first);
});
test('opening first minute needs its own confirmed event',()=>{
 expect(topVolumeMarks(bars.slice(0,1))).toEqual([]);
 expect(topVolumeMarks([bar('09:31',200),bar('09:32',90),bar('09:33',80)],[event('09:31','09:33')])).toEqual([{coord:['09:31',10],value:'触发'}]);
});
test('limit-up wait keeps marker hidden until reopening event arrives',()=>{
 const reopen=event('09:32','09:34','09:36:05');
 expect(topVolumeMarks(bars,[reopen])).toEqual([]);
 expect(topVolumeMarks([...bars,bar('09:35',60),bar('09:36',30,false)],[reopen])).toEqual([{coord:['09:32',10],value:'触发'}]);
});
test('lunch counts trading minutes and missing confirmation bars do not mark',()=>{
 const lunch=[bar('11:30',200),bar('13:01',90),bar('13:02',80)];
 expect(topVolumeMarks(lunch,[event('11:30','13:02')])).toEqual([{coord:['11:30',10],value:'触发'}]);
 expect(topVolumeMarks([bars[1],bars[3]],[event()])).toEqual([]);
 expect(topVolumeMarks(bars,[{...event(),mode:'test'}])).toEqual([]);
});
