"""Command line entry point for the local 涨乐通 executor."""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import credentials
from .adb import Adb, AdbError
from .runtime import device_operation
from .trade import TradeError, TradePage
from .zhangle import (
    LoginError,
    LoginRejected,
    ManualVerificationRequired,
    StartupConsentRequired,
    Zhangle,
)


def _print(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _client(args) -> Zhangle:
    return Zhangle(Adb(serial=args.serial, adb=args.adb))


def cmd_status(args) -> int:
    client = _client(args)
    result = client.status()
    payload = result.as_dict()
    payload.update(
        {
            "installed": client.is_installed(),
            "screen": client.adb.screen_size(),
        }
    )
    return _print(payload)


def cmd_doctor(args) -> int:
    client = _client(args)
    adb = client.adb
    devices = adb.devices()
    payload = {
        "adb": adb.adb,
        "serial": adb.serial,
        "devices": devices,
        "installed": client.is_installed() if devices else False,
        "account_saved": credentials.get_account() is not None,
        "password_saved": credentials.get_password() is not None,
    }
    if devices:
        payload.update(client.status().as_dict())
    return _print(payload, 0 if devices and payload["installed"] else 5)


def cmd_set_account(args) -> int:
    value = args.account or input("涨乐通客户号: ").strip()
    credentials.set_account(value)
    return _print({"ok": True, "account_saved": True})


def cmd_set_password(args) -> int:
    first = getpass.getpass("涨乐通交易密码: ")
    second = getpass.getpass("再次输入交易密码: ")
    if first != second:
        raise ValueError("两次输入的密码不一致")
    credentials.set_password(first)
    return _print({"ok": True, "password_saved": True})


def cmd_clear_password(args) -> int:
    credentials.clear_password()
    return _print({"ok": True, "password_saved": False})


def cmd_login(args) -> int:
    client = _client(args)
    try:
        result = client.ensure_logged_in(
            password=None,
            account=args.account,
            dry_run=args.dry_run,
            timeout=args.timeout,
            accept_terms=args.accept_terms,
        )
    except StartupConsentRequired as exc:
        return _print({"ok": False, "consent": True, "error": str(exc)}, 2)
    except ManualVerificationRequired as exc:
        return _print({"ok": False, "manual": True, "error": str(exc)}, 2)
    except LoginRejected as exc:
        return _print({"ok": False, "rejected": True, "error": str(exc)}, 3)
    except (LoginError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **result.as_dict()})


def cmd_trade_status(args) -> int:
    client = _client(args)
    try:
        return _print({"ok": True, **client.trade_status()})
    except AdbError as exc:
        return _print({"ok": False, "error": str(exc)}, 4)


def cmd_ensure_trade(args) -> int:
    client = _client(args)
    try:
        payload = client.ensure_trade_ready(
            account=args.account,
            dry_run=args.dry_run,
            timeout=args.timeout,
        )
    except StartupConsentRequired as exc:
        return _print({"ok": False, "consent": True, "error": str(exc)}, 2)
    except ManualVerificationRequired as exc:
        return _print({"ok": False, "manual": True, "error": str(exc)}, 2)
    except LoginRejected as exc:
        return _print({"ok": False, "rejected": True, "error": str(exc)}, 3)
    except (LoginError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **payload})


def cmd_trade_preview(args) -> int:
    page = TradePage(Adb(serial=args.serial, adb=args.adb))
    try:
        form = page.preview(
            side=args.side,
            code=args.code,
            quantity=args.quantity,
            price=args.price,
        )
        payload = {"ok": True, "submitted": False, **form.as_dict()}
    except (TradeError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    finally:
        if not args.keep:
            try:
                page.close()
            except AdbError:
                pass
    return _print(payload)


def cmd_trade_submit(args) -> int:
    if not args.yes and not args.dry_run:
        return _print(
            {
                "ok": False,
                "error": "真实提交需要显式加 --yes；先跑 trade-preview 核对表单",
            },
            4,
        )
    page = TradePage(Adb(serial=args.serial, adb=args.adb))
    try:
        payload = page.submit(
            side=args.side,
            code=args.code,
            quantity=args.quantity,
            price=args.price,
            max_value=args.max_value,
            dry_run=args.dry_run,
        )
    except (TradeError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    result = payload.get("result") or {}
    if result.get("kind") == "error":
        return _print({"ok": False, **payload}, 3)
    return _print({"ok": True, **payload})


def cmd_logout(args) -> int:
    client = _client(args)
    try:
        result = client.logout(timeout=args.timeout)
    except (LoginError, AdbError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **result.as_dict()})


def _book(args):
    from .orderbook import OrderBook

    return OrderBook(Adb(serial=args.serial, adb=args.adb))


def cmd_orders(args) -> int:
    from .orderbook import OrderBookError

    try:
        book = _book(args)
        result = book.history_orders() if args.history else book.today_orders()
    except (OrderBookError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **result.as_dict()})


def cmd_trades(args) -> int:
    from .orderbook import OrderBookError

    try:
        book = _book(args)
        result = book.history_trades() if args.history else book.today_trades()
    except (OrderBookError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **result.as_dict()})


def cmd_account(args) -> int:
    from .orderbook import OrderBookError

    try:
        payload = _book(args).account()
    except (OrderBookError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **payload})


def cmd_cancel(args) -> int:
    from .cancel import CancelError, CancelPage, plan_cancel
    from .orderbook import OrderBookError

    if not args.yes and not args.dry_run:
        return _print(
            {
                "ok": False,
                "error": "真实撤单需要显式加 --yes；先不加参数跑一次看计划",
            },
            4,
        )
    book = _book(args)
    try:
        plan = plan_cancel(
            book.today_orders().rows,
            scope=args.scope,
            code=args.code,
            side=args.side,
        )
        result = CancelPage(book.adb).cancel(plan, dry_run=args.dry_run)
    except (CancelError, OrderBookError, AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **plan.as_dict(), **result})


def cmd_ths_status(args) -> int:
    from .ths import ThsTrade

    try:
        payload = ThsTrade(Adb(serial=args.serial, adb=args.adb)).status()
    except (AdbError, ValueError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)
    return _print({"ok": True, **payload.as_dict()})


def cmd_prepare_device(args) -> int:
    """同花顺 的轮播动画会让 uiautomator 永远等不到 idle。"""
    adb = Adb(serial=args.serial, adb=args.adb)
    adb.set_animations(False)
    return _print({"ok": True, "animations": "off"})


def _broker_store():
    """The same SQLite file the desktop app uses."""
    import os
    from pathlib import Path

    from core.store import Store

    data_dir = os.environ.get("STOCK_MONITOR_DATA", str(Path.home() / ".stock-monitor"))
    return Store(Path(data_dir) / "monitor.sqlite3")


def cmd_broker_accounts(args) -> int:
    from core import brokers

    return _print({"ok": True, "accounts": brokers.list_accounts(_broker_store())})


def cmd_broker_add(args) -> int:
    from core import brokers

    store = _broker_store()
    specs = {item["id"]: item for item in brokers.specs()}
    spec = specs.get(args.broker)
    if spec is None:
        raise ValueError(f"暂不支持该券商: {args.broker}")

    values = {}
    for field in spec["fields"]:
        if not field["secret"]:
            continue
        first = getpass.getpass(f"{field['label']}（直接回车保留已保存的值）: ")
        if not first:
            continue
        if first != getpass.getpass(f"再次输入{field['label']}: "):
            raise ValueError("两次输入的密码不一致")
        values[field["key"]] = first

    item = brokers.save_account(store, args.broker, args.account, values, args.label or "")
    return _print({"ok": True, "account": item})


def cmd_migrate_secrets(args) -> int:
    """One-off: move passwords from the old keychain into the local cache."""
    from core import brokers

    try:
        return _print({"ok": True, **brokers.migrate_keychain(_broker_store())})
    except Exception as exc:
        return _print({"ok": False, "error": str(exc)}, 4)


def cmd_broker_login(args) -> int:
    from core import brokers

    store = _broker_store()
    accounts = [item for item in brokers.list_accounts(store) if item["broker"] == args.broker]
    if not accounts:
        raise ValueError("还没有添加该券商的账号，先用 broker-add")
    if args.account:
        accounts = [item for item in accounts if item["account"] == args.account]
        if not accounts:
            raise ValueError("该券商下没有这个账号")
    if len(accounts) > 1:
        raise ValueError("该券商有多个账号，请用 --account 指定")
    target = accounts[0]
    result = brokers.login(store, target["id"])
    return _print({"ok": True, "account": target["account_masked"], **result})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m executor",
        description="本地涨乐通登录执行器（ADB + uiautomator XML，无网络服务）",
    )
    parser.add_argument("--serial", help="ADB 设备序列号，例如 emulator-5554")
    parser.add_argument("--adb", help="adb 可执行文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看当前页面、登录态和登录按钮状态").set_defaults(func=cmd_status)
    sub.add_parser("doctor", help="检查 adb、设备、App 和凭据").set_defaults(func=cmd_doctor)
    sub.add_parser(
        "trade-status", help="只读查看交易页是否解锁、可用资金和持仓盈亏"
    ).set_defaults(func=cmd_trade_status)

    account = sub.add_parser("set-account", help="把客户号写入系统钥匙串")
    account.add_argument("account", nargs="?")
    account.set_defaults(func=cmd_set_account)

    sub.add_parser("set-password", help="把交易密码写入系统钥匙串（交互输入）").set_defaults(
        func=cmd_set_password
    )
    sub.add_parser("clear-password", help="从系统钥匙串删除交易密码").set_defaults(
        func=cmd_clear_password
    )

    login = sub.add_parser("login", help="确保已登录；未登录时自动输入账号密码")
    login.add_argument("--account", help="临时指定客户号，默认读取钥匙串/环境变量")
    login.add_argument("--dry-run", action="store_true", help="只填写密码，不点击登录")
    login.add_argument(
        "--accept-terms",
        action="store_true",
        help="冷启动遇到隐私协议时自动点“同意”（仅在你已同意协议时使用）",
    )
    login.add_argument("--timeout", type=float, default=25.0)
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="退出当前账号（用于测试自动登录）")
    logout.add_argument("--timeout", type=float, default=20.0)
    logout.set_defaults(func=cmd_logout)

    trade = sub.add_parser(
        "ensure-trade",
        help="确保交易页已解锁；仅在交易模块未登录时才提交一次密码",
    )
    trade.add_argument("--account", help="临时指定客户号，默认读取钥匙串/环境变量")
    trade.add_argument("--dry-run", action="store_true", help="只填密码，不点击登录")
    trade.add_argument("--timeout", type=float, default=25.0)
    trade.set_defaults(func=cmd_ensure_trade)

    preview = sub.add_parser(
        "trade-preview",
        help="只填交易表单、不提交；用于核对价格/数量和可买可卖",
    )
    preview.add_argument("--side", choices=("buy", "sell"), required=True)
    preview.add_argument("--code", required=True, help="6 位股票代码")
    preview.add_argument("--quantity", type=int, help="数量（股）")
    preview.add_argument("--price", help="限价，默认使用页面当前价")
    preview.add_argument("--keep", action="store_true", help="保留表单，不返回上一页")
    preview.set_defaults(func=cmd_trade_preview)

    submit = sub.add_parser(
        "trade-submit",
        help="真实提交委托（需 --yes；确认弹窗与预期不一致会自动取消）",
    )
    submit.add_argument("--side", choices=("buy", "sell"), required=True)
    submit.add_argument("--code", required=True, help="6 位股票代码")
    submit.add_argument("--quantity", type=int, required=True)
    submit.add_argument("--price", help="限价，默认使用页面当前价")
    submit.add_argument(
        "--max-value", type=float, default=1000.0, help="单笔委托金额上限（元），默认 1000"
    )
    submit.add_argument("--dry-run", action="store_true", help="只打开确认弹窗后取消")
    submit.add_argument("--yes", action="store_true", help="确认这是真实委托")
    submit.set_defaults(func=cmd_trade_submit)

    orders = sub.add_parser("orders", help="查询今日/历史委托（原生列表，只读）")
    orders.add_argument("--history", action="store_true", help="查历史委托")
    orders.set_defaults(func=cmd_orders)

    trades = sub.add_parser("trades", help="查询今日/历史成交（原生列表，只读）")
    trades.add_argument("--history", action="store_true", help="查历史成交")
    trades.set_defaults(func=cmd_trades)

    sub.add_parser("account", help="读取可用资金与持仓（用于对账）").set_defaults(
        func=cmd_account
    )

    cancel = sub.add_parser("cancel", help="撤单（默认只打印计划，不加 --yes 不会真撤）")
    cancel.add_argument("--scope", choices=("all", "buy", "sell"), default="all")
    cancel.add_argument("--code", help="只撤这只股票；会同时撤掉其它同方向委托时拒绝执行")
    cancel.add_argument("--side", choices=("buy", "sell"), help="配合 --code 使用")
    cancel.add_argument("--dry-run", action="store_true", help="只打印计划，不点击")
    cancel.add_argument("--yes", action="store_true", help="确认这是真实撤单")
    cancel.set_defaults(func=cmd_cancel)

    ths_status = sub.add_parser("ths-status", help="同花顺交易模块登录态（只读）")
    ths_status.set_defaults(func=cmd_ths_status)

    sub.add_parser(
        "prepare-device", help="关闭系统动画，保证 uiautomator 能读到同花顺页面"
    ).set_defaults(func=cmd_prepare_device)

    broker_accounts = sub.add_parser("broker-accounts", help="列出观量里配置的券商账号")
    broker_accounts.set_defaults(func=cmd_broker_accounts)

    broker_add = sub.add_parser(
        "broker-add", help="添加券商账号，密码交互输入并写入系统钥匙串"
    )
    broker_add.add_argument("--broker", required=True, help="券商 id，例如 ths / zhangle")
    broker_add.add_argument("--account", required=True, help="资金账号/客户号")
    broker_add.add_argument("--label", help="备注")
    broker_add.set_defaults(func=cmd_broker_add)

    sub.add_parser(
        "migrate-secrets",
        help="把旧版存在系统钥匙串里的密码迁移到本机凭据文件（会弹一次钥匙串授权）",
    ).set_defaults(func=cmd_migrate_secrets)

    broker_login = sub.add_parser("broker-login", help="用本机凭据文件里的密码登录已添加的账号")
    broker_login.add_argument("--broker", required=True)
    broker_login.add_argument("--account", help="同一券商有多个账号时指定")
    broker_login.set_defaults(func=cmd_broker_login)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        local_only = {cmd_set_account, cmd_set_password, cmd_clear_password, cmd_broker_accounts, cmd_broker_add, cmd_migrate_secrets}
        if args.func in local_only:
            return args.func(args)
        with device_operation(Adb(serial=args.serial, adb=args.adb)):
            return args.func(args)
    except (RuntimeError, credentials.CredentialError, ValueError, TimeoutError) as exc:
        return _print({"ok": False, "error": str(exc)}, 4)


if __name__ == "__main__":
    sys.exit(main())
