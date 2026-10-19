# 本机架构与迁移边界

React/TypeScript → Tauri受限invoke → Rust管理的Python子进程（stdio JSONL）→ SQLite / 腾讯公开行情 / Bark固定HTTPS。

没有HTTP监听端口，不需要自建业务服务。Rust持有子进程，关闭窗口隐藏至托盘，退出时停止子进程；单实例避免同一电脑重复监控。监控和通知重试在Python后台线程，历史下载任务异步运行，不阻塞UI和本机通知轮询。

SQLite使用WAL，事件唯一键由日期/股票/候选分钟构成；通知状态与事件分离。系统凭据库单独保存Bark密钥，备份不包含密钥。初次运行导入已验证缓存；本机数据与现有正式监控目录隔离。

后续买点：增加规则实现与独立版本，复用行情/事件/通知层；本期无买点算法。
后续服务器：将核心迁移为常驻服务，新增认证API、订阅流、用户/设备标识和同步冲突策略。当前数据格式保留时间、来源、稳定事件键，但没有承诺已实现同步。

外部服务参考：
- https://v2.tauri.app/develop/calling-rust/
- https://v2.tauri.app/develop/sidecar/
- https://v2.tauri.app/plugin/notification/
- https://v2.tauri.app/plugin/autostart/
- https://github.com/Finb/Bark/blob/master/docs/en-us/tutorial.md

已知工程限制：同步添加股票时首次请求可能耗时；长期运行日志导出和自动故障重启尚未实现。核心退出会在界面报错，不能继续显示为已取得新行情。数据来源接口无稳定性保证，本地采样不构成逐笔行情。
