import type {Daily} from '../../../src/models';
export function candles(points:[number,number][],start='2026-07-01'):Daily[]{
 const rows:Daily[]=[];let segment=0,day=new Date(start+'T00:00:00Z');
 for(let i=0;i<=points.at(-1)![0];i++){
  while(day.getUTCDay()===0||day.getUTCDay()===6)day.setUTCDate(day.getUTCDate()+1);
  while(segment+1<points.length-1&&i>points[segment+1][0])segment++;
  const [a,v]=points[segment],[z,w]=points[segment+1],close=v+(w-v)*(i-a)/(z-a);
  rows.push({date:day.toISOString().slice(0,10),open:(close-.02).toFixed(4),close:close.toFixed(4),high:(close+.04).toFixed(4),low:(close-.04).toFixed(4),volume:String(1000000-i*10000)});
  day.setUTCDate(day.getUTCDate()+1);
 }
 return rows;
}
export const flag=candles([[0,8],[2,8.1],[7,12.2],[10,11.2],[13,11.9],[16,10.9],[18,11.3],[19,12],[20,12.1]]);
export const bear=flag.map(b=>({...b,open:String(22-+b.open),close:String(22-+b.close),high:String(22-+b.low),low:String(22-+b.high)}));
export const triangle=candles([[0,10],[3,12],[8,8.8],[13,11.5],[18,9.4],[23,11],[28,10],[30,10.4],[31,11.5]]);
export const spring=candles([[0,11],[2,10],[5,12],[8,10.2],[9,9.6],[10,10.4],[11,10.9],[12,12.4]]);
