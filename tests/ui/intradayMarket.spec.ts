import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {breadthCountsConsistent,closedSnapshotReady,intradayBreadth,intradayIndex,intradayEstimate} from '../../src/intradayMarket';
import {createExchangeCalendar} from '../../src/exchangeCalendar';

test('verified calendars can cross year boundaries without guessing missing years',async()=>{
 // Synthetic 2027 dates verify the mechanism, not the real exchange calendar.
 const one=createExchangeCalendar([{year:2026,closed_ranges:[]}]);
 const both=createExchangeCalendar([{year:2026,closed_ranges:[]},{year:2027,closed_ranges:[['2027-01-01','2027-01-03']]}]);
 expect(one.tradingDay('2027-01-04')).toBeNull();
 expect(one.priorTradingDay('2027-01-04')).toBeNull();
 expect(both.tradingDay('2027-01-01')).toBe(false);
 expect(both.tradingDay('2027-01-04')).toBe(true);
 expect(both.priorTradingDay('2027-01-04')).toBe('2026-12-31');
 expect(both.tradingDay('2027-02-30')).toBe(false);
});

test('closed observations must actually have been collected after their market close',async()=>{
 const day=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8')).days.at(-1);
 const now=Date.parse('2026-10-31T05:00:00+08:00');
 expect(closedSnapshotReady({...day,collected_at:'2026-10-29T17:00:00+08:00'},now)).toBe(false);
 expect(closedSnapshotReady({...day,collected_at:'2026-10-30T14:59:59+08:00'},now)).toBe(false);
 expect(closedSnapshotReady({...day,collected_at:'2026-10-30T15:00:00+08:00'},now)).toBe(true);
 expect(closedSnapshotReady({...day,collected_at:'2026-10-31T04:00:00+08:00'},now)).toBe(true);
 expect(closedSnapshotReady({...day,collected_at:'2026-10-31T06:00:00+08:00'},now)).toBe(false);
});

test('a closed observation cannot claim a weekend or a known exchange holiday',async()=>{
 const day=JSON.parse(await readFile('public/breadth-csi300-preview.json','utf8')).days.at(-1);
 const now=Date.parse('2026-11-02T17:00:00+08:00');
 for(const date of ['2026-10-31','2026-10-05','2026-02-30']){
  expect(closedSnapshotReady({...day,date,collected_at:'2026-11-02T16:00:00+08:00'},now)).toBe(false);
 }
 expect(closedSnapshotReady({...day,date:'2026-10-30',collected_at:'2026-10-30T16:00:00+08:00'},now)).toBe(true);
});

test('market counts must account for every covered stock',async()=>{
 const day=JSON.parse(await readFile('public/breadth-preview.json','utf8')).days.at(-1);
 expect(breadthCountsConsistent(day)).toBe(true);
 expect(breadthCountsConsistent({...day,suspended:day.suspended+1})).toBe(false);
 expect(breadthCountsConsistent({...day,suspended:-1})).toBe(false);
 expect(breadthCountsConsistent({...day,covered:day.covered-1})).toBe(false);
});

test('intraday state is gated by time, data coverage and continuous prior closes',async()=>{
 const breadth=JSON.parse(await readFile('public/breadth-preview.json','utf8')).days.at(-1);
 const report=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 report.daily=report.daily.filter((r:any)=>r.date<'2026-10-29');
 report.latest_eligible='2026-10-28';
 const day={...breadth,status:'provisional',first_quote:'2026-10-29T10:00:00+08:00',last_quote:'2026-10-29T10:00:24+08:00',collected_at:'2026-10-29T10:00:28+08:00'};
 const quote={code:'sh000001',price:'3600',timestamp:'2026-10-29T10:00:24+08:00',source:'tencent'};
 const market={quotes:[quote],minute:null};
 const now=Date.parse('2026-10-29T10:00:30+08:00');
 const result=intradayEstimate(day,report,market,now);
 const last=report.daily.slice(-19);
 expect(result?.ma).toBeCloseTo((last.reduce((s:number,r:any)=>s+r.close,0)+3600)/20,8);
 expect(intradayEstimate({...day,covered:day.expected-1},report,market,now)).toBeNull();
 expect(intradayEstimate({...day,first_quote:'2026-10-29T09:54:00+08:00'},report,market,now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,quotes:[{...quote,timestamp:'2026-10-29T09:57:00+08:00'}]},now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,quotes:[{...quote,source:'other'}]},now)).toBeNull();
 expect(intradayEstimate({...day,first_quote:'2026-10-29T09:29:59+08:00'},report,market,now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,error:'指数报价暂时不可用'},now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,error:'上证分时暂时不可用'},now)?.price).toBe(3600);
 expect(intradayEstimate(day,report,{...market,error:'指数报价暂时不可用；上证分时暂时不可用'},now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,error:'未知错误'},now)).toBeNull();
 expect(intradayEstimate(day,report,{...market,error:'上证分时暂时不可用',quotes:[{...quote,timestamp:'2026-10-29T09:57:00+08:00'}]},now)).toBeNull();
 expect(intradayEstimate(day,{...report,latest_eligible:'2026-10-27'},market,now)).toBeNull();
 const gap=structuredClone(report);gap.daily.at(-4).gap_before=true;
 expect(intradayEstimate(day,gap,market,now)).toBeNull();
 expect(intradayEstimate(day,report,market,Date.parse('2026-10-29T12:00:00+08:00'))).toBeNull();
 expect(intradayEstimate(day,report,market,Date.parse('2026-10-30T10:00:30+08:00'))).toBeNull();
});

test('weekends, exchange holidays and years without a calendar cannot be treated as live sessions',async()=>{
 const base=JSON.parse(await readFile('public/breadth-preview.json','utf8')).days.at(-1);
 const all=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 for(const date of ['2026-10-31','2026-10-05','2027-01-04']){
  const day={...base,date,status:'provisional',first_quote:`${date}T10:00:00+08:00`,last_quote:`${date}T10:00:24+08:00`,collected_at:`${date}T10:00:28+08:00`};
  const daily=all.daily.filter((row:any)=>row.date<date),report={...all,daily,latest_eligible:daily.at(-1)?.date};
  const market={quotes:[{code:'sh000001',price:'3600',timestamp:`${date}T10:00:24+08:00`,source:'tencent'}],minute:null};
  const now=Date.parse(`${date}T10:00:30+08:00`);
  expect(intradayBreadth(day,now)).toBeNull();
  expect(intradayIndex(day,report,market,now)).toBeNull();
  expect(intradayEstimate(day,report,market,now)).toBeNull();
 }
});

test('intraday decisions require the immediately preceding trading day index close',async()=>{
 const base=JSON.parse(await readFile('public/breadth-preview.json','utf8')).days.at(-1);
 const all=JSON.parse(await readFile('public/index-technical-preview.json','utf8'));
 for(const [date,latest,stale] of [
  ['2026-10-26','2026-10-23','2026-10-22'], // weekend
  ['2026-10-08','2026-09-30','2026-09-29'], // exchange holiday
 ]){
  const day={...base,date,status:'provisional',first_quote:`${date}T10:00:00+08:00`,last_quote:`${date}T10:00:24+08:00`,collected_at:`${date}T10:00:28+08:00`};
  const market={quotes:[{code:'sh000001',price:'3600',timestamp:`${date}T10:00:24+08:00`,source:'tencent'}],minute:null};
  const now=Date.parse(`${date}T10:00:30+08:00`);
  const report={...all,daily:all.daily.filter((r:any)=>r.date<=latest),latest_eligible:latest};
  expect(intradayEstimate(day,report,market,now)).not.toBeNull();
  const staleReport={...report,daily:report.daily.filter((r:any)=>r.date<=stale),latest_eligible:stale};
  expect(intradayIndex(day,staleReport,market,now)).toBeNull();
  expect(intradayEstimate(day,staleReport,market,now)).toBeNull();
 }
});
