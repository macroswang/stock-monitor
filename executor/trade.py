"""涨乐通普通交易页（买入/卖出表单）的页面对象。

预览只预填；提交必须逐项核对确认框。结果区分受理、拒绝和未知，未知不能重发。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .adb import Adb, AdbError, Node, find_by_id, find_by_text, wait_until
from .runtime import budget, OperationInterrupted

TRADE_ACTIVITY = "com.lphtsccft.zhangle.trading.normaltrade.HtscNormalTradeActivity"

CODE_ID = "trade_editText"
SEARCH_CODE_ID = "search_edit_text"
FIELD_ID = "et_content"
SUBMIT_ID = "tv_trade"
MAX_VOLUME_ID = "tv_max_volume"
MAX_LABEL_ID = "tv_max_volume_label"
BACK_ID = "title_bar_left"

TABS = ("买入", "卖出", "撤单", "委托", "持仓")

DIALOG_TITLE_ID = "tv_title_text"
DIALOG_MESSAGE_ID = "tv_message_text"
DIALOG_OK_ID = "tv_positive"
DIALOG_CANCEL_ID = "tv_negative"

_SIDE_LABEL = {"buy": "买入", "sell": "卖出"}

_CODE = re.compile(r"证券代码:\s*(\d{6})")
_NAME = re.compile(r"证券名称:\s*(\S+)")
_PRICE = re.compile(r"委托价格:\s*([0-9.]+)")
_QUANTITY = re.compile(r"委托数量:\s*(\d+)")

_ERROR_NEEDLES = (
    "不允许",
    "失败",
    "不足",
    "超过",
    "停牌",
    "未开通",
    "已过期",
    "拒绝",
    "错误",
    "无效",
)
_SUCCESS_NEEDLES = ("已提交", "委托成功", "委托提交成功", "已受理", "受理成功", "已报", "已成交")


class TradeError(RuntimeError):
    """Raised when the trade form is not in the expected state."""


class TradePreparationError(TradeError):
    """A pre-submit failure with an allowlisted, credential-free page trace."""
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


class _InputNotReady(TradeError):
    pass


@dataclass(frozen=True)
class TradeForm:
    side: str | None
    code: str
    price: str
    quantity: str
    max_label: str
    max_volume: str
    submit_text: str | None

    def as_dict(self) -> dict:
        return {
            "side": self.side,
            "code": self.code,
            "price": self.price,
            "quantity": self.quantity,
            "max_label": self.max_label,
            "max_volume": self.max_volume,
            "submit_text": self.submit_text,
        }


def is_trade_form(nodes: list[Node], focus: str) -> bool:
    if TRADE_ACTIVITY in focus:
        return True
    return find_by_id(nodes, SUBMIT_ID) is not None and find_by_id(nodes, CODE_ID) is not None


def _norm(text: str) -> str:
    return text.replace("\xa0", " ").replace("\r", " ").replace("\n", " ")


@dataclass(frozen=True)
class OrderConfirm:
    """The 委托确认 dialog shown after tapping 买入/卖出."""

    title: str
    code: str
    name: str
    price: str
    quantity: str
    raw: str

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "quantity": self.quantity,
            "message": self.raw,
        }


@dataclass(frozen=True)
class OrderResult:
    """The dialog shown after confirming; may be a success or a rejection."""

    kind: str
    title: str
    message: str

    def as_dict(self) -> dict:
        result={"kind": self.kind, "title": self.title, "message": self.message}
        # Only an explicitly named unique contract number is an order identity.
        ids=set(re.findall(r'(?:合同编号|合同号|委托编号|委托号)\s*[:：]\s*([0-9]{1,20})(?![0-9])',self.message))
        if self.kind=='success' and len(ids)==1:result['order_id']=ids.pop()
        return result


def parse_confirm(nodes: list[Node]) -> OrderConfirm | None:
    message = find_by_id(nodes, DIALOG_MESSAGE_ID)
    if message is None:
        return None
    raw = _norm(message.text)
    code = _CODE.search(raw)
    if not code:
        return None
    price = _PRICE.search(raw)
    quantity = _QUANTITY.search(raw)
    name = _NAME.search(raw)
    title = find_by_id(nodes, DIALOG_TITLE_ID)
    return OrderConfirm(
        title=title.text.strip() if title else "",
        code=code.group(1),
        name=name.group(1) if name else "",
        price=price.group(1) if price else "",
        quantity=quantity.group(1) if quantity else "",
        raw=raw.strip(),
    )


def parse_result(nodes: list[Node]) -> OrderResult | None:
    message = find_by_id(nodes, DIALOG_MESSAGE_ID)
    if message is None:
        return None
    title = find_by_id(nodes, DIALOG_TITLE_ID)
    return parse_result_message(message.text, title.text.strip() if title else "")


def parse_result_message(message: str, title: str = "") -> OrderResult | None:
    """Classify a captured native receipt without accessing the device."""
    raw = _norm(message).strip()
    if "证券代码" in raw:
        return None
    success = any(needle in raw for needle in _SUCCESS_NEEDLES)
    error = any(needle in raw for needle in _ERROR_NEEDLES)
    # 网络错误或混合消息不能证明未受理，必须保留未知状态。
    if (success and error) or any(needle in raw for needle in ("网络", "超时", "断开", "连接异常")):
        kind = "unknown"
    elif error:
        kind = "error"
    elif success:
        kind = "success"
    else:
        kind = "unknown"
    return OrderResult(kind=kind, title=title, message=raw)


def _fields(nodes: list[Node]) -> list[Node]:
    """Price and quantity inputs share one resource-id; order them by y."""
    fields = [node for node in nodes if node.resource_id.endswith(FIELD_ID)]
    return sorted(fields, key=lambda node: node.bounds[1])


def _value(node: Node | None) -> str:
    """Ignore placeholder text such as '卖出数量' and keep only real input."""
    if node is None:
        return ""
    text = node.text.strip()
    if not text or any("\u4e00" <= char <= "\u9fff" for char in text):
        return ""
    return text


def read_form(nodes: list[Node]) -> TradeForm:
    submit = find_by_id(nodes, SUBMIT_ID)
    code_node = find_by_id(nodes, CODE_ID)
    fields = _fields(nodes)
    price = _value(fields[0]) if len(fields) > 0 else ""
    quantity = _value(fields[1]) if len(fields) > 1 else ""
    max_volume = find_by_id(nodes, MAX_VOLUME_ID)
    max_label = find_by_id(nodes, MAX_LABEL_ID)
    submit_text = submit.text.strip() if submit else None

    side = None
    for key, label in _SIDE_LABEL.items():
        if submit_text == label:
            side = key
            break

    code_text = _norm(code_node.text).strip() if code_node else ""
    match = re.fullmatch(r"([0-9]{6})(?:\s*[^0-9].*)?", code_text)
    code = match.group(1) if match else ""
    return TradeForm(
        side=side,
        code=code,
        price=price,
        quantity=quantity,
        max_label=max_label.text.strip() if max_label else "",
        max_volume=max_volume.text.strip() if max_volume else "",
        submit_text=submit_text,
    )


class TradePage:
    def __init__(self, adb: Adb | None = None):
        self.adb = adb or Adb()
        self.preparation = []
        self.preparation_started = time.monotonic()

    def snapshot(self) -> tuple[str, list[Node]]:
        focus = self.adb.current_focus()
        return focus, self.adb.nodes()

    # ----- navigation ------------------------------------------------------
    def open(self, timeout: float = 20.0,side='buy') -> tuple[str, list[Node]]:
        """Return the trade form, opening it from the trade tab if needed."""
        if side not in _SIDE_LABEL:raise ValueError('side 只能是 buy 或 sell')
        focus, nodes = self.snapshot()
        if is_trade_form(nodes, focus):
            return focus, nodes

        entry = find_by_text(nodes, _SIDE_LABEL[side])
        if entry is None:
            from .zhangle import is_trade_page
            # Holdings traversal can scroll the entire trade page, hiding its
            # buy/sell shortcuts. Restore the header before opening the form.
            account=find_by_id(nodes,'title_bar_right')
            shown=account.text if account else None
            if is_trade_page(nodes) and shown:
                width,height=self.adb.display_size()
                for _ in range(3):
                    self.adb.shell('input','swipe',str(width//2),str(int(height*.3)),str(width//2),str(int(height*.85)),'450')
                    focus,nodes=self.snapshot()
                    current=find_by_id(nodes,'title_bar_right')
                    if not is_trade_page(nodes) or current is None or current.text!=shown:
                        raise TradeError('恢复交易入口时账户或页面变化，已停止')
                    entry=find_by_text(nodes,_SIDE_LABEL[side])
                    if entry is not None:break
        if entry is None:
            raise TradeError("当前页面不是交易页，也找不到“买入”入口")
        self.adb.tap_node(entry)
        page = wait_until(
            lambda: (lambda pair: pair if is_trade_form(pair[1], pair[0]) else None)(
                self.snapshot()
            ),
            timeout=timeout,
            interval=0.8,
        )
        if not page:
            raise TradeError("没有进入普通交易页")
        return page

    def switch(self, side: str, timeout: float = 15.0, nodes=None) -> list[Node]:
        if side not in _SIDE_LABEL:
            raise ValueError("side 只能是 buy 或 sell")
        label = _SIDE_LABEL[side]
        if nodes is None:
            _, nodes = self.snapshot()
        current = read_form(nodes)
        if current.side == side:
            return nodes
        tab = find_by_text(nodes, label)
        if tab is None:
            raise TradeError(f"交易页找不到顶部“{label}”标签")
        self.adb.tap_node(tab)

        def switched():
            _, current_nodes = self.snapshot()
            return current_nodes if read_form(current_nodes).side == side else None

        result = wait_until(switched, timeout=timeout, interval=0.6)
        if not result:
            raise TradeError(f"切换到“{label}”失败")
        return result

    def close(self) -> None:
        """Leave the form without submitting anything."""
        _, nodes = self.snapshot()
        back = find_by_id(nodes, BACK_ID)
        if back is not None:
            self.adb.tap_node(back)

    # ----- form editing ----------------------------------------------------
    def _record_preparation(self, stage, attempt, focus, nodes, issue=""):
        form = read_form([n for n in nodes if not n.password])
        editor = next((n for n in nodes if n.focused and "EditText" in n.class_name), None)
        numeric = lambda value: value if re.fullmatch(r"[0-9.,]{1,20}", value or "") else ""
        activity=re.search(r"([A-Za-z_][\w.]+/[A-Za-z_][\w.$]+)",focus)
        self.preparation.append(dict(stage=stage,attempt=attempt,side=form.side,code=form.code,
            elapsed_ms=max(0,round((time.monotonic()-self.preparation_started)*1000)),
            price=numeric(form.price),quantity=numeric(form.quantity),max_volume=numeric(form.max_volume),
            activity=activity.group(1) if activity else "",
            search_open=find_by_id(nodes, SEARCH_CODE_ID) is not None,
            focused_id=editor.resource_id.rsplit('/',1)[-1] if editor else "",
            editor_value=numeric(editor.text) if editor and not editor.password and editor.resource_id.rsplit('/',1)[-1] in (SEARCH_CODE_ID,CODE_ID,FIELD_ID) else "",
            issue=issue))
        self.preparation = self.preparation[-24:]

    def _preparation_guard(self, focus, nodes, side, code=None):
        form = read_form(nodes)
        if (side not in _SIDE_LABEL or TRADE_ACTIVITY not in focus or form.side != side
                or find_by_id(nodes, CODE_ID) is None or len(_fields(nodes)) != 2
                or find_by_id(nodes, DIALOG_MESSAGE_ID) is not None
                or any(n.password for n in nodes)):
            raise TradeError("预填时交易页面或买卖方向发生变化，已停止")
        if code is not None and form.code != code:
            raise TradeError("预填时股票代码发生变化，已停止")

    @staticmethod
    def _empty_editor(node):
        text = _norm(node.text).strip()
        return not text or text.startswith("请输入") or text in ("买入价格","卖出价格","买入数量","卖出数量")

    @staticmethod
    def _quote_ready(nodes, side, code):
        form = read_form(nodes)
        try:
            value = Decimal(form.price)
            valid_price = value.is_finite() and value > 0
        except InvalidOperation:
            valid_price = False
        return (form.code == code and form.side == side and valid_price
                and form.max_label == ("可买" if side == "buy" else "可卖")
                and re.fullmatch(r"[0-9]+", form.max_volume.replace(',','')) is not None)

    def _prepare_input(self, kind, value, side, code, timeout, nodes=None):
        """Recover edits only before the submit boundary, under one total deadline.

        涨乐通点击表面代码框后，会弹出独立 search_edit_text；必须等该输入框
        获得焦点才清空、输入。只重新编辑同一交易页，绝不重新点击委托按钮。
        """
        label = {"code":"股票代码","price":"委托价格","quantity":"委托数量"}[kind]
        started = time.monotonic()
        latest = [self.adb.current_focus(), nodes] if nodes is not None else list(self.snapshot())
        attempt = 0
        edited = False
        def read(stage):
            latest[:] = self.snapshot()
            self._record_preparation(stage,attempt,*latest)
            self._preparation_guard(*latest,side,None if kind == "code" else code)
            return latest[1]
        def target(ns):
            if kind == "code":
                return find_by_id(ns, SEARCH_CODE_ID) or find_by_id(ns, CODE_ID)
            fields = _fields(ns)
            return fields[0 if kind == "price" else 1] if len(fields) == 2 else None
        def matches(ns):
            form = read_form(ns)
            if kind == "code":return self._quote_ready(ns,side,code) and find_by_id(ns,SEARCH_CODE_ID) is None
            current = form.price if kind == "price" else form.quantity
            try:return Decimal(current) == Decimal(value) if kind == "price" else current == value
            except InvalidOperation:return False
        try:
            with budget(timeout):
                for attempt in (1,2):
                    try:
                        if attempt > 1:read(kind+"_recover")
                        self._preparation_guard(*latest,side,None if kind == "code" else code)
                        if matches(latest[1]):
                            self._record_preparation(kind+"_ready",attempt,*latest)
                            return latest[1], edited
                        field = target(latest[1])
                        if field is None or not field.enabled or field.password or "EditText" not in field.class_name:
                            raise TradeError("交易页缺少可编辑的"+label)
                        self.adb.tap_node(field)
                        edited = True
                        def focused():
                            ns=read(kind+"_focus");editor=target(ns)
                            return ns if editor is not None and editor.focused and editor.enabled and not editor.password else None
                        focused_nodes=wait_until(focused,timeout=5,interval=.25)
                        if not focused_nodes:raise _InputNotReady(label+"输入框未就绪")
                        editor=target(focused_nodes)
                        if not self._empty_editor(editor):
                            self.adb.clear_text(min(64,len(editor.text)+8))
                            cleared=read(kind+"_clear");editor=target(cleared)
                            if editor is None or not editor.focused or not self._empty_editor(editor):
                                raise _InputNotReady(label+"没有清空，未追加输入")
                        self.adb.input_text(value)
                        def entered():
                            ns=read(kind+"_readback")
                            return ns if matches(ns) else None
                        ready=wait_until(entered,timeout=6,interval=.3)
                        if ready:return ready, True
                        raise _InputNotReady(label+"输入或行情加载未完成")
                    except (_InputNotReady,AdbError,TimeoutError) as exc:
                        self._record_preparation(kind+"_retry",attempt,*latest,issue=type(exc).__name__)
                        if attempt == 2 or time.monotonic()-started >= timeout-2:raise
        except OperationInterrupted:
            raise
        except (TradeError,AdbError,TimeoutError) as exc:
            self._record_preparation(kind+"_failed",attempt,*latest,issue=type(exc).__name__)
            reason=str(exc) if isinstance(exc,TradeError) else "设备读取超时或连接中断"
            raise TradePreparationError(label+"预填失败："+reason,
                dict(stage=kind,attempts=attempt,elapsed_ms=round((time.monotonic()-started)*1000),steps=list(self.preparation))) from None

    def set_code(self, code: str, timeout: float = 24.0, nodes=None) -> list[Node]:
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("股票代码必须是 6 位数字")
        if nodes is None:
            _, nodes = self.snapshot()
        side=read_form(nodes).side
        return self._prepare_input("code",code,side,code,timeout,nodes)[0]

    def _fill(self, index: int, value: str, nodes=None) -> bool:
        if nodes is None:
            _, nodes = self.snapshot()
        form=read_form(nodes)
        if index not in (0,1) or not form.code or form.side not in _SIDE_LABEL:
            raise TradeError("交易表单缺少代码、价格或数量输入框")
        return self._prepare_input("price" if index == 0 else "quantity",value,form.side,form.code,18,nodes)[1]

    def set_price(self, price: str) -> None:
        self._fill(0, price)

    def set_quantity(self, quantity: int | str) -> None:
        self._fill(1, str(quantity))

    def use_max_volume(self) -> None:
        """Tap the 可买/可卖 number to fill the maximum allowed quantity."""
        _, nodes = self.snapshot()
        node = find_by_id(nodes, MAX_VOLUME_ID)
        if node is None:
            raise TradeError("找不到可买/可卖数量")
        self.adb.tap_node(node)

    def preview(
        self,
        side: str,
        code: str,
        quantity: int | None = None,
        price: str | None = None,
    ) -> TradeForm:
        """Fill the form and stop before the submit button.

        Nothing is submitted: the caller gets the parsed form for review.
        """
        self.preparation=[]
        self.preparation_started=time.monotonic()
        _, nodes = self.open(side=side)
        nodes = self.switch(side, nodes=nodes)
        nodes = self.set_code(code, nodes=nodes)
        if price:
            if self._fill(0, price, nodes=nodes):
                nodes = None  # 输入可能弹出键盘，下一字段必须重新定位。
        if quantity:
            self._fill(1, str(quantity), nodes=nodes)
        _, nodes = self.snapshot()
        return read_form(nodes)

    # ----- submit ----------------------------------------------------------
    def _dialog_button(self, primary: str) -> Node | None:
        _, nodes = self.snapshot()
        return find_by_id(nodes, primary)

    def _wait_confirm(self, timeout: float) -> OrderConfirm | None:
        return wait_until(
            lambda: parse_confirm(self.snapshot()[1]), timeout=timeout, interval=0.8
        )

    def _wait_result(self, timeout: float) -> OrderResult | None:
        return wait_until(
            lambda: parse_result(self.snapshot()[1]), timeout=timeout, interval=0.8
        )

    def submit(
        self,
        side: str,
        code: str,
        quantity: int,
        price: str | None = None,
        max_value: float | None = 1000.0,
        dry_run: bool = False,
        timeout: float = 20.0,
        before_confirm=None,
        wait_for_receipt: bool = True,
    ) -> dict:
        """Fill, submit, verify the confirmation dialog and confirm it.

        Safety: the confirmation dialog must match the requested code/price/
        quantity, otherwise it is cancelled and ``TradeError`` is raised.
        ``dry_run`` opens the dialog and cancels it, so no order is sent.
        """
        if side not in _SIDE_LABEL or not re.fullmatch(r"\d{6}", code):
            raise TradeError("委托方向或股票代码无效")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise TradeError("委托数量必须为正整数")
        try:
            cap = Decimal(str(max_value)) if max_value is not None else None
            limit = Decimal(str(price)) if price is not None else None
            if cap is not None and (not cap.is_finite() or cap <= 0):
                raise ValueError()
            if cap is None and limit is None:
                raise ValueError()
            if limit is not None and (not limit.is_finite() or limit <= 0):
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise TradeError("价格及可选金额上限必须为有效正数") from None
        form = self.preview(side=side, code=code, quantity=quantity, price=price)
        if form.side != side or form.code != code:
            raise TradeError(
                f"表单与预期不一致：side={form.side} code={form.code}，已放弃提交"
            )

        _, nodes = self.snapshot()
        current = read_form(nodes)
        # 预填后仍要重新核对，防止用户手工切换方向或更改输入。
        if current.side != side or current.code != code or current.quantity != str(quantity):
            raise TradeError("提交前表单发生变化，已停止")
        try:
            form_price = Decimal(current.price)
            if not form_price.is_finite() or form_price <= 0 or (cap is not None and form_price * quantity > cap):
                raise ValueError()
            if limit is not None and form_price != limit:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise TradeError("提交前价格或金额上限校验未通过") from None
        button = find_by_id(nodes, SUBMIT_ID)
        if button is None or not button.enabled:
            raise TradeError("提交按钮不可用")
        if not dry_run:
            if before_confirm is None:
                raise TradeError("真实委托必须通过观量持久化请求入口提交")
            # 即使预期会出现确认框，初次点击后的失联也必须按可能提交处理。
            before_confirm()
        self.adb.tap_node(button)

        confirm = self._wait_confirm(timeout)
        if confirm is None:
            raise TradeError("点击提交后没有出现委托确认弹窗")

        problems: list[str] = []
        if confirm.title != "委托" + _SIDE_LABEL[side]:
            problems.append("买卖方向不一致或无法识别")
        if confirm.code != code:
            problems.append(f"代码 {confirm.code} != {code}")
        if confirm.quantity != str(int(quantity)):
            problems.append(f"数量 {confirm.quantity} != {quantity}")
        value = None
        try:
            confirmed_price = Decimal(confirm.price)
            if not confirmed_price.is_finite() or confirmed_price <= 0 or confirmed_price != form_price:
                problems.append("确认价格与预填价格不一致")
            value = confirmed_price * int(confirm.quantity)
        except (InvalidOperation, TypeError, ValueError):
            problems.append("无法计算委托金额")
        if cap is not None and value is not None and value.is_finite() and value > cap:
            problems.append(f"金额 {value:.2f} 超过上限 {cap:.2f}")

        if problems:
            self._cancel_dialog()
            raise TradeError("委托确认弹窗与预期不一致：" + "；".join(problems))

        if dry_run:
            self._cancel_dialog()
            return {"submitted": False, "status": "preview", "confirm": confirm.as_dict(),"preparation":list(self.preparation)}

        # 确认内容和按钮取自同一份新快照，不能校验一份弹窗后盲点下一份。
        _, final_nodes = self.snapshot()
        latest = parse_confirm(final_nodes)
        if latest != confirm:
            raise TradeError("确认弹窗发生变化，已停止")
        ok = find_by_id(final_nodes, DIALOG_OK_ID)
        if ok is None or not ok.enabled or ok.text != "确定":
            raise TradeError("委托确认弹窗缺少“确定”按钮")
        if before_confirm is None:
            raise TradeError("真实委托必须通过观量持久化请求入口提交")
        try:
            before_confirm()
        except Exception:
            self._cancel_dialog()
            raise
        try:
            self.adb.tap_node(ok)
            if not wait_for_receipt:
                return {"submitted": True, "status": "unknown", "receipt_pending": True,
                        "message": "委托确认已发送，待手动同步成交", "confirm": confirm.as_dict()}
            result = self._wait_result(timeout)
        except Exception:
            result = None  # 点击可能已经生效；不能把读回失败当成未提交。
        status = "accepted" if result and result.kind == "success" else "rejected" if result and result.kind == "error" else "unknown"
        return {
            "submitted": status == "accepted",
            "status": status,
            "confirm": confirm.as_dict(),
            "result": result.as_dict() if result else None,
            "preparation": list(self.preparation),
        }

    def _cancel_dialog(self) -> None:
        _, nodes = self.snapshot()
        button = find_by_id(nodes, DIALOG_CANCEL_ID)
        if button is None or not button.enabled or button.text != "取消":
            raise TradeError("找不到可确认的取消按钮；未点击确定，请手动关闭弹窗")
        self.adb.tap_node(button)
        if not wait_until(lambda: parse_confirm(self.snapshot()[1]) is None, timeout=5, interval=.2):
            raise TradeError("未确认弹窗已关闭，请手动检查")
