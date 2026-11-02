# 涨乐通登录执行器（P1）

> 2026-11-02 更新：真实委托统一经过观量 `broker_submit` 持久化请求入口，并携带
> `request_id`；底层 CLI 不再直接提交无执行记录的真实委托。自动真实撤单已关闭，
> `cancel` 仅支持预览，撤单须在券商 App 中完成。登录核验不再用 120 秒缓存冒充
> 实时状态。详见 [本轮反证复核与修复](../docs/自动交易反证复核与修复-20261102.md)。

本地 ADB + uiautomator XML 的登录模块，不监听端口、不接券商接口、不修改现有
`core/` 监控逻辑。

## 为什么不用截图

涨乐通登录 Activity（`HtscLoginActivity`）带 `SECURE` 标志，`adb screencap`
输出为空。因此本模块只依赖：

- 当前 Activity（`dumpsys window`）；
- uiautomator XML 节点树（resource-id / text / bounds）；
- `adb shell input text` 输入密码。

## 环境

- Python 3.12（使用项目 `.venv`）；
- Android Platform Tools（`adb`）；
- BlueStacks Air 已启动，`adb devices` 能看到 `emulator-5554`；
- 涨乐通已安装（`com.lphtsccft`，验证版本 8.8.73）；
- 同花顺已安装（`com.hexin.plat.android`，验证版本 11.64.07），并已添加银河证券账户。

`adb` 的查找顺序是：`ADB_PATH` 环境变量 → `PATH` → 常见安装位置
（`/opt/homebrew/bin/adb`、`~/Library/Android/sdk/platform-tools/adb` 等）。
这是因为从 Finder 启动的观量只继承 `/usr/bin:/bin:/usr/sbin:/sbin`，
光靠 `PATH` 找不到 Homebrew 装的 adb。

## 使用

> **日常使用不需要命令行。** 账号、密码、登录、查询、撤单都在「观量 → 设置 → 券商账号」里完成；
> 下面这些命令只是排查问题时的调试入口。

```sh
# 检查环境、App、凭据
.venv/bin/python -m executor doctor

# 查看当前页面和登录态
.venv/bin/python -m executor status

# 首次：把客户号和交易密码写入系统钥匙串（交互输入，不回显）
.venv/bin/python -m executor set-account
.venv/bin/python -m executor set-password

# 确保已登录；已登录则直接返回
.venv/bin/python -m executor login

# 只读：交易页是否解锁、可用资金、持仓盈亏
.venv/bin/python -m executor trade-status

# 确保交易页解锁；已解锁则不发任何请求，仅在交易模块未登录时提交一次密码
.venv/bin/python -m executor ensure-trade

# 只填密码，不点登录（调试用）
.venv/bin/python -m executor login --dry-run

# 退出当前账号（测试自动登录用）
.venv/bin/python -m executor logout

# 只读：今日 / 历史委托（原生列表，节点树解析）
.venv/bin/python -m executor orders
.venv/bin/python -m executor orders --history

# 只读：今日 / 历史成交
.venv/bin/python -m executor trades
.venv/bin/python -m executor trades --history

# 只读：可用资金与持仓（对账用）
.venv/bin/python -m executor account

# 撤单：默认只打印计划，不会点任何按钮
.venv/bin/python -m executor cancel
.venv/bin/python -m executor cancel --code 000981 --dry-run

# 真实撤单暂不开放；--yes 也会拒绝执行，请在券商 App 中处理。
```

也可以设置环境变量，适合临时运行：

```sh
ZHANGLE_ACCOUNT=... ZHANGLE_PASSWORD=... .venv/bin/python -m executor login
```

密码不会写入 SQLite、日志或仓库。新版把券商密码存在数据目录的
`broker-secrets.json`（权限 600），**不再访问系统钥匙串**，所以 macOS 不会
反复弹授权框；旧版留在钥匙串里的密码可以用 `python -m executor migrate-secrets`
一次性迁移（会弹一次授权）。

## 登录状态机

- `is_login_screen`：当前 Activity 是 `HtscLoginActivity`，或页面出现
  `login_password_edit` / “登录后继续操作”；
- `is_logged_in`：当前 Activity 是 `MainActivity`，且没有登录表单、没有
  “登录查看”；
- 未登录时：
  1. 启动 App（`SplashScreenActivity`）；
  2. 如果首页显示“登录查看”，点击进入登录页；
  3. 账号为空时从钥匙串/环境变量读取；
  4. 清空密码框，`adb shell input text` 输入密码；
  5. 确认 `login_btn_login` 已启用后点击；
  6. 等待 `MainActivity` 且登录表单消失。
- 遇到短信、人脸、证书激活、设备验证：抛 `ManualVerificationRequired`，
  不自动绕过；
- 密码错误/锁定：抛 `LoginRejected`，不重试，避免锁号；
- 其他异常：抛 `LoginError`。

## 交易模块是独立登录态（重要）

实测发现：App 主登录成功后，“账户”页显示客户号和资产，但“交易”页仍可能停在
未登录布局（顶部“登录 / 我的交易持仓 登录查看”）。点交易页顶部“登录”后弹出的
还是同一个 `HtscLoginActivity`，再登录一次交易页才解锁。

因此判断登录态以交易页为准：

| 页面 | 判定 |
|---|---|
| `trade_unlogin_main_layout` 存在 | 交易模块未登录 |
| `trade_normal_main_layout` 存在 | 交易模块已登录 |

`is_logged_in()` 也已改为：交易页处于未登录布局时一律视为未登录（首页/账户页
会显示缓存的资产数据，不能作为登录依据）。

`ensure-trade` 的流程：

1. 已登录且交易页已解锁 → 直接返回，**不提交密码**；
2. 交易页未解锁 → 点顶部登录入口，填一次密码，登录后回读交易页；
3. 交易登录后仍未解锁 → 报错，不重试。

## 交易页（P2：只读 + 预填，不提交）

普通交易页 Activity：`...zhangle.trading.normaltrade.HtscNormalTradeActivity`。

已确认的节点（用于自动填单，**尚未实现提交**）：

| 元素 | resource-id |
|---|---|
| 股票代码/名称 | `trade_editText` |
| 价格输入 | `et_content`（第一个，按 y 排序） |
| 数量输入 | `et_content`（第二个） |
| 可买/可卖标签 | `tv_max_volume_label` |
| 可买/可卖数量 | `tv_max_volume` |
| 提交按钮 | `tv_trade`（文本为“买入”或“卖出”） |
| 返回 | `title_bar_left` |

价格/数量两个输入框共用 `et_content`，且输入后占位文字会消失，所以代码按
纵坐标排序取第 1、2 个，而不是靠文字匹配。

只读预填命令：

```sh
# 填入卖出 000981 100 股，读回表单状态，然后退出表单（不提交）
.venv/bin/python -m executor trade-preview --side sell --code 000981 --quantity 100
```

输出示例（实测）：

```json
{"ok": true, "submitted": false, "side": "sell", "code": "000981",
 "price": "2.13", "quantity": "100", "max_label": "可卖",
 "max_volume": "12800", "submit_text": "卖出"}
```

**未实现**：撤单、委托查询。提交已实现，但见下文的安全约束。

## 提交委托（P3）

确认弹窗和结果弹窗的节点（实测取得）：

| 元素 | resource-id | 实测文本 |
|---|---|---|
| 弹窗标题 | `tv_title_text` | `委托卖出` / `系统提示` |
| 弹窗正文 | `tv_message_text` | 含 股东账号/证券代码/证券名称/委托价格/委托数量 |
| 取消 | `tv_negative` | 取消 |
| 确定 | `tv_positive` | 确定 |

```sh
# 只打开确认弹窗然后取消，不发出委托
.venv/bin/python -m executor trade-submit --side sell --code 000981 --quantity 100 --dry-run

# 真实提交
.venv/bin/python -m executor trade-submit --side sell --code 000981 --quantity 100 --yes
```

提交前会做三重校验，任何一项不符就**自动点取消**并报错：

1. 表单方向、代码与请求一致；
2. 确认弹窗里的代码、价格、数量与请求一致；
3. 委托金额（价格 × 数量）不超过 `--max-value`（默认 1000 元）。

结果分类：
- `result.kind=success`：正文含“已提交/委托成功/已受理”等；
- `result.kind=error`：正文含“不允许/失败/不足/超过/停牌”等，退出码 3；
- `kind=unknown`：原样返回正文，需人工确认。

实盘状态：非交易时段（周日下午）实测提交返回
`系统提示 / 当前时间不允许委托`，委托被券商拒绝，未产生任何持仓变化。
**成功回执的文案尚未实测**，需在交易时段再跑一次才能把 success 分支坐实。

## 委托 / 成交 / 持仓（原生）与撤单（H5）

交易主页下半部分（`detail_viewpager`）是**原生**的，分「持仓」和「委托/成交」两个标签；
「委托/成交」里再分 今日委托 / 今日成交 / 历史委托 / 历史成交。这些都能直接读节点树：

| 字段 | resource-id | 说明 |
|---|---|---|
| 行容器 | `stock_main_item` | 一行一个委托或成交 |
| 名称 / 代码 | `stock_name` / `stock_code` | 持仓页的 `stock_code` 其实是市值 |
| 方向 | `item_trade_dir` | 买入 / 卖出 / 撤买 / 撤卖 |
| 日期 / 时间 | `item_trade_trust_date` / `item_trade_trust_time` | |
| 委托价 | `item_trade_trust_num` | 只在委托列表 |
| 成交均价 | `item_trade_trust_price` | 只在成交列表 |
| 委量 \| 成交量 | `item_trade_trust_success` | 委托是 `2,300 \| 0`，成交是数量（卖出为负） |
| 状态 | `item_trade_trust_state` | 已报 / 已成 / 已撤 / 部撤 |
| 空列表 | `sub_tv1` = 没有数据 | |

可撤判定：状态属于 未报/待报/已报/部成/已报待撤/部撤，且方向里没有「撤」，
且成交量小于委托量。

**撤单页是 H5，读不到节点。** 它的结构是固定的三按钮底栏「全撤 / 撤买 / 撤卖」。
因此撤单流程是：

1. 先用原生「今日委托」算出可撤集合；
2. 校验目标（按股票撤单时，若同方向还有别的可撤委托就直接拒绝，并列出会误伤的委托）；
3. 进撤单页，扫截图找底栏分隔线，按比例点按钮；
4. 若出现原生确认弹窗，点「确定」；
5. 再读一次原生「今日委托」复核，状态没变就报错。

第 3 步是唯一不精确的地方：底栏坐标靠截图推断，找不到分隔线时退回 1770/1920 比例。
所以撤单永远是「先 dry-run、再 --yes」，且失败会明确要求人工检查。

## 多券商与观量设置界面

设置页新增「券商账号（模拟器自动交易）」，支持多家券商各自一个账号：

- 元数据（券商、账号、备注）存主库 `broker_accounts` 表；
- 密码存数据目录下的 `broker-secrets.json`（权限 600），不写钥匙串；
- 界面只回 `password_saved`，永远拿不到明文；
- 文件权限 600，仅当前系统用户可读；它加密强度不如钥匙串，属于本机明文缓存；
- 登录/检查交易页/预览/真实提交都走后台任务，界面不会被阻塞；
- 真实提交需要在界面勾选确认，并且 `core` 会再校验一次 `confirm=true`。

代码分层：

```
executor/brokers/base.py      # BrokerSpec + BrokerAdapter 接口
executor/brokers/zhangle.py   # 涨乐通适配器
executor/brokers/registry.py  # 券商注册表
core/brokers.py               # 账号 CRUD + 钥匙串 + 分发
src/BrokerAccounts.tsx        # 设置界面
```

新增一家券商：写 `executor/brokers/<broker>.py` 适配器，在 `registry.py` 登记，
界面下拉框会自动出现。**不需要改 `core/` 和现有监控逻辑。**

## 同花顺（银河证券）

同花顺是聚合平台，`com.hexin.plat.android`（实测 11.64.07）。这里只接**券商交易模块**：
用户在 App 里已经添加并选中了「中国银河证券」，适配器不新增账户，只提交交易密码。

已实测的节点：

| 位置 | resource-id | 说明 |
|---|---|---|
| 底部导航 | `content-desc="交易"` | 用 content-desc 定位，不依赖坐标 |
| 账户卡片 | `txt_qsname` / `txt_account_value` | 中国银河证券 / `4004****0162` |
| 登录面板 | `login_component_base_view` | 底部抽屉 |
| 面板券商 | `qs_name` / `account` | 中国银河证券 / `**0162` |
| 密码框 | `weituo_edit_trade_password` | 唯一的输入框 |
| 登录按钮 | `weituo_btn_login` | 密码为空时不可点击，填完才变可点击 |
| 关闭面板 | `close_button` | 放弃登录时用 |

### 登录前的三道护栏

1. **账户尾号校验**：面板显示的 `**0162` 必须与本地记录的 `4004****0162` 一致，
   否则直接报错，**一个字符都不输入**。避免把 A 券商的密码发到 B 券商的登录框。
2. **按钮就绪等待**：填完密码后等 `weituo_btn_login` 变成 `clickable=true`，最多 8 秒。
3. **字符数校验**：密码框里回的掩码点数必须等于密码长度，防止 `input text` 丢字符。

已登录时 `ensure_logged_in` 直接返回，不会再输一次密码——重复调用不会消耗尝试次数。

### 必须先关系统动画

同花顺首页有自动轮播和跑马灯，`uiautomator` 会一直等 `idle state` 直到超时
（报错 `ERROR: could not get idle state`）。先跑一次：

```sh
.venv/bin/python -m executor prepare-device
```

它会把 `window_animation_scale`、`transition_animation_scale`、
`animator_duration_scale` 三个系统设置设为 0。

### 登录后的交易页（已实测）

登录成功后整页都是原生控件：

| 位置 | resource-id | 实测值 |
|---|---|---|
| 券商 / 账号 | `qs_name_text` / `account_text` | 中国银河证券 / k客户号 4004****0162 |
| 总资产 | `capital_value_text` | 21,695.65 |
| 浮动盈亏 | `yingkui_value_text` | -15,032.42 |
| 总市值 | `shizhi_value_text` | 19,999.00 |
| 当日参考盈亏 | `dryk_value_text` / `drykb_value_text` | -1,112.00 / -4.88% |
| 菜单 | `menu_buy` / `menu_sale` / `menu_withdrawal` / `menu_holdings` / `menu_search` | 买入 / 卖出 / 撤单 / 持仓 / 查询 |

「查询」页：`当日成交 drcj`、`当日委托 drwt`、`历史成交 lscj`、`历史委托 lswt`。
委托行字段固定：`result0` 名称 / `result1` `20261030 13:42:57` / `result2` 委托价 /
`result3` 均价 / `first_tv` 委托量 / `second_tv` 成交量 / `result6` 买卖 / `result7` 状态。
成交和持仓行没有 resource-id，按坐标切行（`cluster_rows`），再按文档顺序取字段。

**已知限制**：委托、成交、持仓三个列表都**不显示 6 位股票代码**，只有名称。

### 现在的边界

| 能力 | 状态 |
|---|---|
| 登录 / 幂等重登 | ✅ 实测 |
| 委托查询（当日/历史） | ✅ 实测，历史 10 条 |
| 成交查询（当日/历史） | ✅ 实测，历史 10 条 |
| 资金 + 持仓 | ✅ 实测 |
| 撤单 | ❌ 撤单页是原生，但当前无挂单，**行内撤单按钮结构未实测** |
| 买入/卖出 | ❌ 下单表单未实测 |

所以 `supports_query = True`、`supports_cancel = False`、`supports_order = False`。
界面会把不支持的操作置灰，不会点了才报错。

## 避免触发风控

涨乐通对短时间内的重复登录敏感，因此：

- `login` / `ensure-trade` 在已登录时是**空操作**，不会重复提交密码；
- `logout` 仅用于测试，不要放进循环；
- 同一凭证失败后不要自动重试（代码本身也不重试）；
- 日常只需要调用 `ensure-trade` 一次，失败就人工介入。

## 已知限制

- 交易密码必须是 6—20 位数字（涨乐通登录页的输入类型）；
- “保持在线时长”当前为 30 分钟，可选最长 8 小时；建议登录前在
  “登录设置”里改为 8 小时，减少重登录；
- 登录页禁止截屏，证据只保留 XML；
- App 升级后 resource-id 可能变化，需要跑 `status` / `login --dry-run` 自检；
- 只验证了登录，不包含下单、撤单、对账。

## 代码入口

```python
from executor.zhangle import Zhangle

client = Zhangle()
client.ensure_logged_in()      # 会话有效时直接返回
client.status()                # 只读状态
client.logout()                # 测试/切换账号
```

后续接入主程序时，建议把执行器作为独立进程，通过本地队列或 sidecar 与
Tauri/Python 核心通信，不要把 ADB 和密码逻辑放进 `core/`。
