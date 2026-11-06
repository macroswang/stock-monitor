import {test,expect} from '@playwright/test';
import {autoTradeMarks,autoTradeRecords,autoTradeDetails,type AutoTradePoint,type AutoTradeChart} from '../../src/autoTradeMarks';
const day='2026-11-03';
const point:AutoTradePoint={id:'one',account_id:'a',broker_name:'银河',account_masked:'400***162',code:'sh603938',day,side:'buy',status:'accepted',mode:'live',signal_key:'signal',signal_time:'14:03',reference_price:27.89,created_at:day+'T14:03:05+08:00',ordered_at:day+'T14:04:01+08:00',order_price:'27.90',quantity:200,message:'',attempted:true};
const view=(points:AutoTradePoint[]):AutoTradeChart=>({code:point.code,day,accounts:[],points});
test('successful automatic orders show only B/S at their order minute; details retain price and status',()=>{
 for(const side of ['buy','sell'] as const){const p={...point,side},[m]=autoTradeMarks(view([p]),[],day);expect(m.time).toBe('14:04');expect(m.price).toBe(27.90);expect(m.label).toBe(side==='buy'?'B':'S');expect(autoTradeDetails(p).join(' ')).toContain('委托限价：27.90');expect(autoTradeDetails(p).join(' ')).not.toContain('已核实成交：');}
});
test('every live automatic submission has B/S while pre-submit and trial records do not',()=>{
 for(const status of ['sending','unknown','rejected']){const p={...point,status};expect(autoTradeMarks(view([p]),[],day)).toHaveLength(1);expect(autoTradeMarks(view([p]),[],day)[0].opacity).toBe(.55);}
 for(const status of ['pending','processing','skipped','not_sent','trial']){const p={...point,status,mode:status==='trial'?'trial':'live'};expect(autoTradeMarks(view([p]),[],day)).toEqual([]);expect(autoTradeRecords(view([p]),[],day)[0].point.status).toBe(status);}
});
test('verified fill and limit stay separate without adding prices to the reminder letter',()=>{
 const p={...point,status:'filled',fill_price:'27.88',filled:200};expect(autoTradeMarks(view([p]),[],day)[0]).toMatchObject({label:'B',price:27.88});expect(autoTradeDetails(p).join(' ')).toContain('委托限价：27.90');expect(autoTradeDetails(p).join(' ')).toContain('均价 27.88');
 expect(autoTradeMarks(view([{...p,fill_price:undefined}]),[],day)[0]).toMatchObject({label:'B',price:27.90});
});
test('legacy missing records remain account-scoped in details and never create B/S',()=>{
 const data={...view([point]),accounts:[{id:'a',broker_name:'银河',account_masked:'400***162',buy_enabled:true,sell_enabled:true},{id:'b',broker_name:'华泰',account_masked:'666***623',buy_enabled:true,sell_enabled:true}]};
 const shapes=[{key:'signal',kind:'bottom',time:'14:03',price:27.89}],records=autoTradeRecords(data,shapes,day);expect(records).toHaveLength(2);expect(records[1].point.status).toBe('unrecorded');expect(records[1].point.account_id).toBe('b');expect(autoTradeMarks(data,shapes,day)).toHaveLength(1);expect(data.points).toHaveLength(1);
 expect(autoTradeMarks(data,[], '2026-11-02')).toEqual([]);expect(autoTradeMarks(view([{...point,code:'sz000981'}]),[],day)).toEqual([]);
});
test('automatic attempts from multiple accounts keep separate lanes',()=>{
 const m=autoTradeMarks(view([{...point,id:'unknown',status:'unknown'},point,{...point,id:'two',account_id:'b'}]),[],day);expect(m.map(p=>p.offset)).toEqual([-26,-46,-66]);expect(m.map(p=>p.point.account_id)).toEqual(['a','a','b']);
});
test('success without a captured order attempt or valid limit cannot create a reminder',()=>{
 for(const p of [{...point,attempted:false},{...point,order_price:undefined},{...point,order_price:'NaN'},{...point,mode:'trial'}])expect(autoTradeMarks(view([p]),[],day)).toEqual([]);
});
test('legacy receipt and unknown automatic attempts both show B while settlement state stays distinct',()=>{
 const legacy={...point,status:'unknown',receipt_accepted:true,order_id:'142783',receipt_message:'委托提交成功,合同号:142783'};
 expect(autoTradeMarks(view([legacy]),[],day)[0]).toMatchObject({label:'B',price:27.90,time:'14:04'});
 expect(autoTradeDetails(legacy).join(' ')).toContain('券商回执已受理，成交尚未回报');expect(autoTradeDetails(legacy).join(' ')).not.toContain('已核实成交：');
 for(const p of [{...legacy,receipt_accepted:false},{...legacy,order_id:undefined}]){expect(autoTradeMarks(view([p]),[],day)).toHaveLength(1);expect(autoTradeDetails(p).join(' ')).toContain('未收到明确回执');}
 for(const p of [{...legacy,status:'skipped'},{...legacy,attempted:false},{...legacy,mode:'trial'}])expect(autoTradeMarks(view([p]),[],day)).toEqual([]);
 expect(legacy.status).toBe('unknown');
});
test('verified broker cache records render B/S at fill price and expose cache evidence',()=>{
 const cached={...point,id:'broker-fill',source:'broker_cache' as const,mode:'broker',status:'filled',order_price:undefined,fill_price:'27.88',filled:200,cache_observed_at:'2026-11-03T15:05:00+08:00'};
 const [mark]=autoTradeMarks(view([cached]),[],day);expect(mark).toMatchObject({label:'B',price:27.88,time:'14:04',opacity:1});
 expect(autoTradeDetails(cached).join(' ')).toContain('券商成交买入');expect(autoTradeDetails(cached).join(' ')).toContain('成交时间：14:04:01');expect(autoTradeDetails(cached).join(' ')).toContain('缓存更新：15:05:00');
});
test('auction and afternoon-open orders anchor to visible chart minutes without changing exact details',()=>{
 for(const [clock,anchor] of [['09:25:00','09:30'],['13:00:00','13:01']]){
  const cached={...point,source:'broker_cache' as const,mode:'broker',status:'filled',ordered_at:day+'T'+clock+'+08:00',fill_price:'27.88',filled:200};
  expect(autoTradeMarks(view([cached]),[],day)[0].time).toBe(anchor);expect(autoTradeDetails(cached).join(' ')).toContain('成交时间：'+clock);
 }
});
