import {test,expect} from '@playwright/test';
import type {DailyPattern,PatternPoint,PatternLine} from '../../src/dailyPatterns';
import {selectDailyPatterns} from '../../src/dailyPatternSelection';

const point=(index:number,price:number):PatternPoint=>({index,price,date:new Date(Date.UTC(2026,5,index+1)).toISOString().slice(0,10)});
const edge=(role:PatternLine['role'],from:PatternPoint,to:PatternPoint):PatternLine=>({role,from,to});
function triangle(key:string,shift=0,offset=0,status:DailyPattern['status']='up',six=false):DailyPattern{
 const p=(i:number,price:number)=>point(i+shift,price+offset);
 return {key,kind:'triangle',name:'收敛三角形',start:p(0,14),end:p(20,status==='forming'?11.5:14),detectedIndex:shift+18,detectedOn:p(18,0).date,status,volumeNote:'',
  anchors:[p(0,14),p(5,10.25),p(10,13),p(15,10.75),...(six?[p(16,12.4),p(18,10.9)]:[])],
  lines:[edge('upper',p(0,14),p(20,12)),edge('lower',p(0,10),p(20,11))]};
}
function spring(key:string):DailyPattern{
 const support=point(0,11),neck=point(10,13),breach=point(15,10),reclaim=point(18,11.2),end=point(20,14);
 return {key,kind:'spring',name:'破底翻',start:support,end,detectedOn:reclaim.date,detectedIndex:18,status:'neckline',necklineOn:end.date,volumeNote:'',anchors:[support,neck,breach,reclaim],
  lines:[edge('support',support,point(20,11)),edge('neckline',neck,point(20,13)),edge('outline',support,neck),edge('outline',neck,breach),edge('outline',breach,reclaim)]};
}

test('different locations are drawn automatically without a global quota',()=>{
 const a=triangle('early'),b=triangle('later',40),c=triangle('higher',0,100);
 expect(new Set(selectDailyPatterns([a,b,c]).map(p=>p.key))).toEqual(new Set(['early','later','higher']));
});

test('same-location competing kinds retain the more independently supported confirmed structure',()=>{
 const channel=triangle('channel'),reversal=spring('reversal');
 expect(selectDailyPatterns([reversal,channel]).map(p=>p.key)).toEqual(['channel']);
 channel.status='forming';
 expect(selectDailyPatterns([channel,reversal]).map(p=>p.key)).toEqual(['reversal']);
});

test('a newer failed candidate cannot displace a confirmed overlapping structure',()=>{
 const confirmed=triangle('confirmed'),failed=triangle('newer',0,0,'failed');failed.detectedIndex=20;
 expect(selectDailyPatterns([failed,confirmed]).map(p=>p.key)).toEqual(['confirmed']);
});

test('more swing support wins, then tighter boundary fit, then recency breaks an exact tie',()=>{
 const four=triangle('four'),six=triangle('six',0,0,'up',true);
 expect(selectDailyPatterns([four,six]).map(p=>p.key)).toEqual(['six']);
 const loose=triangle('loose');loose.anchors[2].price+=.2;loose.detectedIndex=20;
 expect(selectDailyPatterns([loose,four]).map(p=>p.key)).toEqual(['four']);
 const recent=triangle('recent');recent.detectedIndex=19;
 expect(selectDailyPatterns([four,recent]).map(p=>p.key)).toEqual(['recent']);
});

test('an overlapping weak bridge does not hide two separate stronger locations',()=>{
 const a=triangle('left'),bridge=triangle('bridge',10,0,'forming'),c=triangle('right',24);
 expect(new Set(selectDailyPatterns([a,bridge,c]).map(p=>p.key))).toEqual(new Set(['left','right']));
});

test('incomplete structures and duplicates do not create extra overlays',()=>{
 const missing=triangle('missing');missing.lines.pop();
 const noReclaim=spring('no-reclaim');noReclaim.anchors[3].price=10.8;
 const good=triangle('good');
 expect(selectDailyPatterns([missing,noReclaim,good,good]).map(p=>p.key)).toEqual(['good']);
 expect(selectDailyPatterns([])).toEqual([]);
});

test('selection is deterministic and leaves original identification data untouched',()=>{
 const input=[triangle('older'),triangle('latest',40),spring('competing')],before=JSON.stringify(input);
 expect(selectDailyPatterns(input).map(p=>p.key)).toEqual(selectDailyPatterns([...input].reverse()).map(p=>p.key));
 expect(JSON.stringify(input)).toBe(before);
});
