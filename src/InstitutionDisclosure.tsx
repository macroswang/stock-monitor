import React from 'react';

export default function InstitutionDisclosure(){
 return <details className="breadth-method" id="breadth-institution" aria-label="公开持仓观察">
  <summary>公开持仓观察 · 披露范围与核对案例</summary>
  <p>上市公司定期报告主要展示报告期末前十大股东等信息，只能观察到被披露的账户和持仓，不能代表相关资金全部持仓或实时交易。</p>
  <p>不同主体不能简单合并为同一账户；未出现在前十大名单，也不能直接认定已清仓。比较时应核对主体全称、股票、股份类型、报告期末及公告日期。</p>
  <div className="table-scroll"><table><thead><tr><th>固定核对案例</th><th>2026-03-31</th><th>2026-06-30</th><th>公开资料</th></tr></thead><tbody><tr><td>建设银行 A 股<br/>中央汇金资产管理有限责任公司</td><td>496,639,800 股</td><td>496,639,800 股</td><td><a href="https://www2.ccb.com/chn/attachDir/2026/04/2026042919084537315.pdf" target="_blank" rel="noreferrer">一季报</a> · <a href="https://static.cninfo.com.cn/finalpage/2026-08-29/1225531678.PDF" target="_blank" rel="noreferrer">半年报</a></td></tr></tbody></table></div>
  <p>一季报披露于 2026-04-29，半年报披露于 2026-08-28；回看历史时，数据只能在报告披露后使用。此案例只核对两个报告期末的这一笔披露持股数量相同，无法推断期间买卖。报告有披露时滞，不能作为实时资金流向。</p>
 </details>;
}
