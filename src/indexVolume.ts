import type {IndexMinuteBar} from './models';

export const indexVolumeColors={buy:'#ef6568',sell:'#36b898',unknown:'#000000'};
const lots=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function splitIndexVolume(bar:IndexMinuteBar,code:string,day:string){
 if(!lots(bar.volume_lots))return null;
 const total=bar.volume_lots,raw=bar.volume_direction;
 const fallback={total,buy:0,sell:0,unclassified:total,verified:false};
 if(!raw||raw.code!==code||raw.day!==day||raw.time!==bar.time||raw.unit!=='lots'||raw.scope!=='index_total'||raw.basis!=='trade_initiator'||raw.complete!==true||typeof raw.source!=='string'||!raw.source.trim())return fallback;
 const values=[raw.buy_lots,raw.sell_lots,raw.neutral_lots,raw.unknown_lots];
 if(!values.every(lots)||!lots(raw.total_lots)||raw.total_lots!==total||values.reduce((a,b)=>a+b,0)!==total)return fallback;
 return {total,buy:raw.buy_lots,sell:raw.sell_lots,unclassified:raw.neutral_lots+raw.unknown_lots,verified:true};
}
