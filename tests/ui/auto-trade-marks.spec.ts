import {test,expect} from '@playwright/test';
import {autoTradeMarks,autoTradeDetails,type AutoTradePoint,type AutoTradeChart} from '../../src/autoTradeMarks';
const day='2026-11-03';
const point:AutoTradePoint={id:'one',account_id:'a',broker_name:'银河',account_masked:'400***162',code:'sh603938',day,side:'buy',status:'accepted',mode:'live',signal_key:'signal',signal_time:'14:03',reference_price:27.89,created_at:day+'T14:03:05+08:00',ordered_at:day+'T14:04:01+08:00',order_price:'27.90',quantity:200,message:'',attempted:true};
const view=(points:AutoTradePoint[]):AutoTradeChart=>({code:point.code,day,accounts:[],points});
test('accepted order uses its submission minute and limit, not signal time or an invented fill',()=>{
 const [m]=autoTradeMarks(view([point]),[],day);expect(m.time).toBe('14:04');expect(m.price).toBe(27.90);expect(m.label).toBe('买单 27.90');expect(m.fillPrice).toBeNull();
 expect(autoTradeDetails(point).join(' ')).toContain('委托限价：27.90');expect(autoTradeDetails(point).join(' ')).not.toContain('已核实成交：');
});
test('unknown result remains explicitly uncertain even with a quoted fill field',()=>{
 const p={...point,status:'unknown',fill_price:'27.80',filled:200};const [m]=autoTradeMarks(view([p]),[],day);expect(m.label).toBe('买? 27.90');expect(m.fillPrice).toBeNull();expect(autoTradeDetails(p).join(' ')).not.toContain('已核实成交：');
});
test('verified fill price and original limit remain separate; legacy fills without average say limit',()=>{
 const p={...point,status:'filled',fill_price:'27.88',filled:200};const [m]=autoTradeMarks(view([p]),[],day);expect(m.label).toBe('买成 27.88');expect(autoTradeDetails(p).join(' ')).toContain('委托限价：27.90');expect(autoTradeDetails(p).join(' ')).toContain('均价 27.88');
 expect(autoTradeMarks(view([{...p,fill_price:undefined}]),[],day)[0].label).toBe('买成 27.90限');
});
test('missing executions are marked per account without manufacturing a receipt or altering source records',()=>{
 const data={...view([point]),accounts:[{id:'a',broker_name:'银河',account_masked:'400***162',buy_enabled:true,sell_enabled:true},{id:'b',broker_name:'华泰',account_masked:'666***623',buy_enabled:true,sell_enabled:true}]};
 const m=autoTradeMarks(data,[{key:'signal',kind:'bottom',time:'14:03',price:27.89}],day);expect(m).toHaveLength(2);expect(m[1].point.status).toBe('unrecorded');expect(m[1].point.account_id).toBe('b');expect(m[1].point.attempted).toBe(false);expect(data.points).toHaveLength(1);
 expect(autoTradeMarks(data,[], '2026-11-02')).toEqual([]);expect(autoTradeMarks(view([{...point,code:'sz000981'}]),[],day)).toEqual([]);
});
test('trial and skipped records never look like live orders',()=>{
 for(const p of [{...point,status:'trial',mode:'trial'},{...point,status:'skipped',attempted:false,message:'资金不足'}]){const m=autoTradeMarks(view([p]),[],day)[0];expect(m.time).toBe('14:03');expect(m.price).toBe(27.89);expect(m.label).not.toContain('买单');}
});
