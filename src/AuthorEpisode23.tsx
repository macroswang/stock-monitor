import React from 'react';
import reference from '../fixtures/author-episode23.json';

const signed=(value:number)=>`${value>0?'+':''}${value.toFixed(2)}%`;

export default function AuthorEpisode23(){
 return <details className="breadth-method episode23" aria-label="作者历史分位与七个案例">
  <summary>作者历史分位与七个案例 · 固定截图</summary>
  <p>作者在 2026-10-29 视频约 02:56 表示当时市场尚未见底。这是有日期的个人判断，不代表当前结论；视频未给出可复算的底部或仓位阈值。</p>
  <p>作者 2026-10-29 视频展示的 10-28 指标历史分位；这些百分比是所处分位，并非指标当日的原始数值。历史窗口和排名方法尚未确认。视频为事后展示，不随日期回放，不能用于事前回测。</p>
  <div className="episode23-bars" aria-label="作者截图中的历史分位">
   {reference.percentiles.map(row=><div className="episode23-bar" key={row.label}><span>{row.label}</span><div className="episode23-track"><i style={{width:`${row.value}%`}}/></div><strong>{row.value.toFixed(1)}%</strong></div>)}
  </div>
  <p>视频列出 7 个 2024 年历史样本；下表 20 日数值为作者图中所示，10 日数值由公开上证指数日线独立复算。按共同指数交易日、样本日收盘到第 10 / 20 日收盘计算，两来源日期和收盘价已对照。</p>
  <div className="table-scroll"><table><thead><tr><th>样本日期</th><th>10日 · 独立复算</th><th>20日 · 作者图 / 复算</th></tr></thead><tbody>{reference.samples.map(row=><tr key={row.date}><td>{row.date}</td><td>{signed(row.day10)}</td><td>{signed(row.day20)}</td></tr>)}</tbody></table></div>
  <p>这 7 个日期中，10 日与 20 日上涨均为 1 / 7；平均分别为 {signed(reference.stats['10'].mean)} / {signed(reference.stats['20'].mean)}。视频的 1、3、5 日统计不能由这 7 个日期复现，不能假定使用相同样本。</p>
  <p>视频另将历史形态分为 G1 当前贴合组、A2 评分 20—30、C1 低评分且年线弱，以及 G2 纯普涨脉冲；这些名称不构成完整筛选规则。以下对照视频中 G1 的上涨占比与这七个日期的独立计算：</p>
  <div className="table-scroll"><table><thead><tr><th>持有交易日</th><th>视频 G1 上涨占比</th><th>七个日期复算</th><th>对照</th></tr></thead><tbody>{(['1','3','5','10','20'] as const).map(days=>{const video=reference.video_win_percent[days], verified=reference.stats[days].win_percent;return <tr key={days}><td>{days} 日</td><td>{video.toFixed(1)}%</td><td>{verified.toFixed(1)}%</td><td>{Math.abs(video-verified)<0.05?'显示精度一致':'不一致，原因未知'}</td></tr>;})}</tbody></table></div>
  <p>2024-08-26 的第 10 日收益为 −4.17%，并非 20 日内最大回落；这段时间的最低收盘价相对样本日约为 −5.30%。</p>
  <p>{reference.warning} 七个样本集中在同一年且窗口重叠，比例不能当成已验证的未来概率。 <a href={reference.video_url} target="_blank" rel="noreferrer">查看作者原视频</a></p>
 </details>;
}
