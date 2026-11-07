# 大盘广度图表视觉核验

- 参考：`/var/folders/92/0tpdpsx10wz21wp30mfx6w7c0000gn/T/codex-clipboard-ce891f9f-87d2-4398-aaa2-43c5c686cb4f.png`，508×460，视频截图片段。
- 本地实现：`docs/trin-video-ui-20261028/implementation-final.png`，桌面宽度约 1275×717；图表与参考的组合对照见 `docs/trin-video-ui-20261028/comparison-final.png`。参考截图和本地画面的日期范围、来源及口径不同，不按数值或柱高作逐像素比较。
- 核验范围：默认成交股数口径、10 月 23 日历史数据，桌面布局；分别点击图表和表格切换日期，切换成交额对照并检查结果。桌面应用最小宽度为 1000 像素，326 像素侧栏浏览器预览不属于其原有桌面窗口范围。

## 比较与修正

- 字体：使用应用现有中西文字体，图表数值、坐标轴和图例有独立层次；视频截图字体模糊，无法核实字族。
- 布局：图表采用单一日期轴、左轴百分比、右轴 TRIN；日期缺失处断线。图例、数据来源和表格位于图表下方，可滚动查看。
- 颜色：图表改为深灰底、红柱、蓝线、黄绿虚线，并保留右轴 1 的参考线；与视频可见构图一致。
- 标签：初版柱子缺少数值，补充数值后与曲线标签重叠；最终将柱值放在柱内底部，保留曲线数值在曲线附近。
- 图像：参考只有图表，没有需要重制的品牌图像或照片资产；应用图表使用实时绘图。
- 内容：视频红柱原始含义及股票范围尚未核实；经用户确认，以明确标示的上涨组成交占比展示，不冒称视频原红柱。视频 10 月 23 日的 0.93 与本地收盘重算值不一致，界面说明保留这一限制。
- 后续：实际盘中同步采集与作者原始口径仍需独立核验，不以视觉结果替代数据验收。

final result: passed

---

# Design QA — 分时页顶部与价格主图空间分配

- Source visual truth: `/var/folders/92/0tpdpsx10wz21wp30mfx6w7c0000gn/T/codex-clipboard-d9314550-6337-4919-be86-0b33263015bb.png`
- Implementation screenshot: `/Users/macrwang/Documents/XReddot/Code/stock-monitor/outputs/compact-minute-header/minute-macd-compact-minute-eb466-ight-only-to-the-price-pane/compact-minute-header-price-pane.png`
- Combined comparison: `/tmp/stock-monitor-design-qa/comparison.html`，已在 ChatGPT in-app Browser 中完整查看
- Browser viewport: `2254 × 654` CSS px，device scale factor `1`
- Source pixels: `2254 × 654`
- Implementation capture: `1884 × 1111` pixels，股票详情卡元素截图；对照时顶部对齐，并重点检查与需求截图相同的标题、工具条和价格主图区
- State: 深色主题、侧栏与市场趋势折叠、三孚股份、分时页

## Findings

没有待处理的 P0、P1 或 P2 问题。

- Fonts and typography: 沿用现有系统字体、字重和状态色；股票名称保持 17px 主层级，状态和工具条使用 10–11px 辅助层级，未出现截断或重叠。
- Spacing and layout rhythm: 标题/状态/操作区与视图工具条收紧为 73.5px；按钮、日期和页签对齐在稳定的两行网格中。详情卡宽屏和 1000px 桌面宽度均无横向溢出。
- Colors and visual tokens: 继续使用现有深蓝背景、边框和选中态，没有引入新颜色或不一致的阴影。
- Image quality and assets: 本区域没有图片或自定义图标资产；行情画布保持原始清晰度和完整全天范围。
- Copy and content: 所有原操作名称、状态、日期和提示保持不变；测试数据与需求截图的行情内容不同，但信息结构一致。

## Comparison history

1. 初始需求截图：顶部标题/状态/操作与视图工具条占用明显垂直空间，用户要求压缩并把释放高度交给价格主图。
2. 第一次实现：收紧两行信息密度，并将主图新增空间从辅助窗格计算中扣除。浏览器测量为顶部 73.5px、图表 393px、价格窗格 111px。
3. 验证修正：旧成交量测试仍按新增总高度放大辅助窗格，已将基准改为压缩前高度；最终个股/大盘成交量及两组 MACD 高度保持原值，价格窗格精确增加 30px。
4. Post-fix evidence: `compact minute header gives its saved height only to the price pane`、常用窗口适配及成交量高度测试均通过；日K/分时切换可用，浏览器控制台无错误。

## Implementation checklist

- [x] 标题、代码、状态与操作按钮紧凑对齐
- [x] 分时/日K/周K、日期与历史操作形成统一工具条
- [x] 释放的 30px 仅分配给价格主图
- [x] 成交量、MACD、信号和交易逻辑保持不变
- [x] 宽屏与常用桌面断点通过

## Follow-up polish

没有阻塞性后续项。

final result: passed
