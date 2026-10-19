#!/bin/bash
# Shipped beside 观量.app in the installation image; no development tools required.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
source_app="$here/观量.app"
target="/Applications/观量.app"
old_entry="$HOME/Applications/观量.app"
data="$HOME/Library/Application Support/com.xreddot.stockmonitor"
backup="$data/upgrade-backups/$(date +%Y%m%d-%H%M%S)-$$"
fail() { echo "安装未完成：$*"; echo "请保留此窗口中的提示。"; exit 1; }
trap 'echo "安装中断。原数据不会被删除；已创建的备份位于：$backup"' ERR
test -d "$source_app" || fail "请从安装镜像内运行本程序。"
/usr/bin/codesign --verify --deep --strict "$source_app" || fail "应用完整性校验失败。"
test -w /Applications || fail "没有应用程序目录写入权限，请联系管理员安装。"
mkdir -p "$backup" "$HOME/Applications"
echo "正在停止旧客户端，然后备份本地数据……"
# Restrict termination to the two supported installed locations, never another monitor.
stop_installed() {
 /bin/ps -axo pid=,comm= | while read -r pid executable; do
  case "$executable" in
   "$target/Contents/MacOS/stock-monitor"|"$target/Contents/MacOS/monitor-core"|"$old_entry/Contents/MacOS/stock-monitor"|"$old_entry/Contents/MacOS/monitor-core")
    /bin/kill -TERM "$pid" 2>/dev/null || true;;
  esac
 done
}
stop_installed
/bin/sleep 1
db="$data/monitor.sqlite3"
counts="SELECT 'watch',count(*) FROM watch UNION ALL SELECT 'cache',count(*) FROM cache UNION ALL SELECT 'events',count(*) FROM events UNION ALL SELECT 'messages',count(*) FROM messages;"
if test -f "$db"; then
 sql_backup="${backup//\'/\'\'}"
 /usr/bin/sqlite3 "$db" ".backup '$sql_backup/monitor.sqlite3'"
 /usr/bin/sqlite3 "$db" "$counts" > "$backup/before-counts.txt"
 /usr/bin/sqlite3 "$backup/monitor.sqlite3" 'PRAGMA integrity_check;' | /usr/bin/grep -qx ok || fail "数据备份校验失败，未替换应用。"
fi
staged="/Applications/.stock-monitor-upgrade-$$.app"
/usr/bin/ditto "$source_app" "$staged"
/usr/bin/codesign --verify --deep --strict "$staged"
if test -e "$target"; then /bin/mv "$target" "$backup/previous-system-app.disabled"; fi
if ! /bin/mv "$staged" "$target"; then
 test ! -d "$backup/previous-system-app.disabled" || /bin/mv "$backup/previous-system-app.disabled" "$target"
 fail "替换应用失败，已尝试恢复旧应用。"
fi
if test -L "$old_entry"; then
 /bin/mv "$old_entry" "$backup/previous-user-entry"
elif test -e "$old_entry"; then
 /bin/mv "$old_entry" "$backup/previous-user-app.disabled"
fi
/bin/ln -s "$target" "$old_entry"
if test -f "$db"; then
 /usr/bin/sqlite3 "$db" "$counts" > "$backup/after-counts.txt"
 /usr/bin/cmp "$backup/before-counts.txt" "$backup/after-counts.txt" || fail "记录数量发生变化，请保留备份并联系维护者。"
fi
echo "安装完成。自选、行情缓存、触发记录和消息数据均保留。"
echo "升级前备份：$backup"
echo "正在启动 /Applications/观量.app；旧的用户目录入口已指向此版本。"
if test "${STOCK_MONITOR_INSTALL_NO_LAUNCH:-0}" != 1; then /usr/bin/open "$target"; fi
