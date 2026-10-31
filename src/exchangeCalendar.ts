/// <reference types="vite/client" />
import calendar2026 from '../fixtures/exchange-calendar-2026.json' with { type: 'json' };

type Calendar={year:number;closed_ranges:string[][]};

// Vite bundles every checked-in, verified calendar. Direct Node-based tests
// have no Vite glob implementation and use the checked-in 2026 fallback.
const files:Record<string,Calendar>=(()=>{
 try{return import.meta.glob<Calendar>('../fixtures/exchange-calendar-*.json',{eager:true,import:'default'});}
 catch{return {'../fixtures/exchange-calendar-2026.json':calendar2026};}
})();
const bundled=Object.values(files);

export function createExchangeCalendar(calendars:Calendar[]){
 const byYear=new Map(calendars.map(c=>[c.year,c]));
 const hasYear=(year:number)=>byYear.has(year);
 const tradingDay=(day:string):boolean|null=>{
  const date=new Date(day+'T00:00:00Z');
  if(!Number.isFinite(date.getTime())||date.toISOString().slice(0,10)!==day)return false;
  const calendar=byYear.get(date.getUTCFullYear());
  if(!calendar)return null;
  return date.getUTCDay()!==0&&date.getUTCDay()!==6&&!calendar.closed_ranges.some(([a,b])=>a<=day&&day<=b);
 };
 const priorTradingDay=(day:string):string|null=>{
  if(tradingDay(day)!==true)return null;
  const date=new Date(day+'T00:00:00Z');
  for(let i=0;i<16;i++){
   date.setUTCDate(date.getUTCDate()-1);
   const label=date.toISOString().slice(0,10),valid=tradingDay(label);
   if(valid===null)return null;
   if(valid)return label;
  }
  return null;
 };
 return {hasYear,tradingDay,priorTradingDay};
}

export const exchangeCalendar=createExchangeCalendar(bundled);
