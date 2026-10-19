export const wan=(value:number|string)=>Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
export const wanShares=(value:number|string)=>wan(Number(value)/10000);
export const price=(value:number|string)=>Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
export function sourceName(value:unknown):string{const id=typeof value==='object'&&value!==null?(value as {provider?:string}).provider:value;return id==='tencent'?'腾讯行情':id==='sina'?'新浪行情':String(id||'未知来源');}
export const localStatus=(s?:string|null)=>({pending:'待提交',sending:'提交中',accepted:'系统已接受',failed:'提交失败',unknown:'结果未知',expired:'已过期'} as Record<string,string>)[s||'']||'—';
export const phoneStatus=(s?:string|null)=>({accepted:'服务已接受',pending:'待发送',retry:'重试中',failed:'发送失败',expired:'已过期',skipped:'未启用'} as Record<string,string>)[s||'']||'—';
export const modeName=(s:string)=>({live:'实时',replay:'历史回放',history:'区间回放',recovered:'补取恢复',test:'通道测试'} as Record<string,string>)[s]||s;
