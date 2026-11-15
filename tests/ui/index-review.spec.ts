import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {indexSparkline} from '../../src/indexSparkline';
const original=JSON.parse(readFileSync('public/market-overview-preview.json','utf8'));
const code='sh000001';
function prefix(){const x=structuredClone(original);x.quotes=x.quotes.filter((q:any)=>q.code===code);x.minute.code=code;x.minute.cached_at='2026-10-30T10:30:20+08:00';x.collected_at=x.minute.cached_at;x.quotes[0].timestamp=x.minute.cached_at;x.minute.bars=x.minute.bars.filter((b:any)=>b.time<='10:31');return x;}

test('a pending endpoint cannot become confirmed merely because the wall clock advances without a fresh snapshot',()=>{
 const feed=prefix();expect(indexSparkline(feed,code,Date.parse('2026-10-30T10:32:00+08:00'))!.until).toBe('10:30');
});
test('a cache timestamp earlier than the trading day cannot validate that day’s minute prices',()=>{
 const feed=prefix();feed.minute.cached_at='2026-10-29T16:00:00+08:00';expect(indexSparkline(feed,code,Date.parse('2026-10-31T17:00:00+08:00'))).toBeNull();
});
test('a closed quote with an incomplete morning minute cache must remain visibly stale',()=>{
 const feed=prefix();feed.quotes[0].timestamp='2026-10-30T16:14:00+08:00';feed.minute.bars=feed.minute.bars.filter((b:any)=>b.time<='10:30');expect(indexSparkline(feed,code,Date.parse('2026-10-31T17:00:00+08:00'))!.stale).toBe(true);
});
test('malformed cache rows never crash the index card',()=>{
 expect(()=>indexSparkline({...prefix(),quotes:[null]} as any,code,Date.parse('2026-10-31T17:00:00+08:00'))).not.toThrow();
});
