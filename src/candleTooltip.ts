import type {Daily} from './models';

/** Display only. Read the hovered candle and its immediate predecessor, never a live quote or later candle. */
export function candleChangeText(rows:ReadonlyArray<Daily>,index:number):string{
 const current=rows[index],prior=rows[index-1];
 const close=Number(current?.close),base=Number(prior?.close);
 if(!current||!Number.isFinite(close)||close<=0)return '—（当前收盘价无效）';
 if(!prior||prior.date>=current.date||!Number.isFinite(base)||base<=0)return '—（缺少前收盘）';
 if(prior.provisional)return '—（前收盘未确认）';
 const percent=(close/base-1)*100;
 if(!Number.isFinite(percent))return '—（涨跌幅无效）';
 const rounded=Number(percent.toFixed(2));
 return `${rounded>0?'+':''}${rounded.toFixed(2)}%`;
}
