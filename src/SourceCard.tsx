import type {SourceInfo} from './models';
import {sourceName} from './format';
export default function SourceCard({info,actual}:{info?:SourceInfo;actual?:unknown}){
 if(!info)return null;
 return <details className="source-details"><summary>数据来源：{sourceName(actual||info.selected)} · 查看地址、口径与覆盖范围</summary><div className="source-grid"><div><strong>当前接入</strong><p>{sourceName(info.selected)} · 价格：元 · 日线：未复权<br/>分钟量保存为股，日线显示为万股。</p><p>日线缓存：{info.daily_coverage.join(' 至 ')||'无'}<br/>分钟缓存：{info.minute_coverage.join(' 至 ')||'无'}</p></div><div><strong>数据接口地址</strong><p>报价：<code>{info.quote_url}</code><br/>分时：<code>{info.minute_url}</code><br/>{sourceName(actual)==='新浪行情'&&<>当前历史分时（新浪）：<code>{info.history_minute_url}</code><br/></>}日线：<code>{info.daily_url}</code></p><small>报价时间：{info.quote_time||'尚未读取'}<br/>本机缓存更新时间：{info.cache_time||'旧版验证缓存，未记录'}</small></div></div><p>实时监控使用腾讯；新浪仅按整日补充缺失历史，不拼接分钟量。新浪首分钟含集合竞价，规则回放暂未认证。</p></details>;
}
