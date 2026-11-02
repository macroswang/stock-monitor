"""Small ADB + uiautomator-dump wrapper used by the local executor.

No network access and no third-party Python dependency.  The login screen of
涨乐通 is marked FLAG_SECURE, so screenshots are intentionally not used here:
all page state comes from the uiautomator XML tree and the current activity.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import time
import uuid
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from .runtime import active_serial, bound_timeout, budget

_DUMP_PATH = "/sdcard/zhangle_window.xml"
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_SAFE_TEXT = re.compile(r"[0-9A-Za-z._@-]+")

# A GUI-launched Tauri app inherits a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
# so `which adb` fails even though the user's terminal finds it. Keep a list of
# the usual install locations instead of relying on PATH alone.
_ADB_CANDIDATES = (
    "/opt/homebrew/bin/adb",
    "/usr/local/bin/adb",
    "~/Library/Android/sdk/platform-tools/adb",
    "~/Android/Sdk/platform-tools/adb",
    "~/Library/Android/sdk/platform-tools/adb.exe",
    "~/AppData/Local/Android/Sdk/platform-tools/adb.exe",
    "C:/Android/platform-tools/adb.exe",
)


def resolve_adb(explicit: str | None = None) -> str:
    """Find adb for both terminal and Finder-launched usage."""
    if explicit:
        return explicit
    env = os.environ.get("ADB_PATH")
    if env:
        return env
    found = shutil.which("adb")
    if found:
        return found
    for candidate in _ADB_CANDIDATES:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return "adb"



class AdbError(RuntimeError):
    """Raised when adb is missing, disconnected, or a shell command fails."""


@dataclass(frozen=True)
class Node:
    text: str
    resource_id: str
    class_name: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    enabled: bool
    password: bool
    checked: bool
    selected: bool = False
    description: str = ""

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)


def _bool(value: str | None) -> bool:
    return value == "true"


def parse_nodes(xml: str) -> list[Node]:
    root = ET.fromstring(xml)
    nodes: list[Node] = []
    for element in root.iter("node"):
        attrs = element.attrib
        match = _BOUNDS.fullmatch(attrs.get("bounds", ""))
        if not match:
            continue
        nodes.append(
            Node(
                text=attrs.get("text", ""),
                resource_id=attrs.get("resource-id", ""),
                class_name=attrs.get("class", ""),
                bounds=tuple(int(part) for part in match.groups()),  # type: ignore[arg-type]
                clickable=_bool(attrs.get("clickable")),
                enabled=_bool(attrs.get("enabled")),
                password=_bool(attrs.get("password")),
                checked=_bool(attrs.get("checked")),
                selected=_bool(attrs.get("selected")),
                description=attrs.get("content-desc", ""),
            )
        )
    return nodes


def find_by_id(nodes: list[Node], resource_id: str) -> Node | None:
    for node in nodes:
        if (
            node.resource_id == resource_id
            or node.resource_id.endswith("/" + resource_id)
            or node.resource_id.endswith(":" + resource_id)
        ):
            return node
    return None


def find_by_text(nodes: list[Node], text: str) -> Node | None:
    for node in nodes:
        if node.text == text:
            return node
    return None


def find_contains(nodes: list[Node], text: str) -> Node | None:
    for node in nodes:
        if text in node.text:
            return node
    return None


def find_all_by_id(nodes: list[Node], resource_id: str) -> list[Node]:
    return [
        node
        for node in nodes
        if node.resource_id == resource_id
        or node.resource_id.endswith("/" + resource_id)
        or node.resource_id.endswith(":" + resource_id)
    ]


def find_selected(nodes: list[Node], texts) -> Node | None:
    """Return the tab that carries ``selected=true`` among ``texts``."""
    for node in nodes:
        if node.selected and node.text in texts:
            return node
    return None


def wait_until(check, timeout: float, interval: float = 0.6):
    """Poll ``check`` until it returns a truthy value or the timeout expires."""
    deadline = time.monotonic() + timeout
    last = None
    with budget(timeout):
        while time.monotonic() < deadline:
            last = check()
            if last:
                return last
            time.sleep(min(interval, max(0, deadline-time.monotonic())))
    return last


class Adb:
    def __init__(self, serial: str | None = None, adb: str | None = None, timeout: float = 20.0):
        self.adb = resolve_adb(adb)
        self.serial = serial or active_serial() or os.environ.get("ANDROID_SERIAL")
        self.timeout = timeout

    def _command(self) -> list[str]:
        command = [self.adb]
        if self.serial:
            command += ["-s", self.serial]
        return command

    def run(self, *args: str, timeout: float | None = None, check: bool = True) -> subprocess.CompletedProcess:
        command = self._command() + list(args)
        sensitive = "input" in args and "text" in args
        description = "shell input text [已隐藏]" if sensitive else " ".join(args)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                # Never let adb (or its shell) inherit our stdin: the desktop
                # client uses stdin as the JSON-RPC pipe, and a child reading
                # from it silently swallows in-flight requests.
                stdin=subprocess.DEVNULL,
                timeout=bound_timeout(timeout if timeout is not None else self.timeout),
            )
        except FileNotFoundError as exc:
            raise AdbError("找不到 adb，请安装 Android Platform Tools 或设置 ADB_PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb 命令超时: {description}") from None
        if check and result.returncode != 0:
            message = "输入失败（详情已隐藏）" if sensitive else result.stderr.decode("utf-8", "replace").strip()
            raise AdbError(f"adb 命令失败: {description}: {message}") from None
        return result

    def shell(self, *args: str, timeout: float | None = None, check: bool = True) -> str:
        result = self.run("shell", *args, timeout=timeout, check=check)
        return result.stdout.decode("utf-8", "replace").strip()

    def devices(self) -> list[str]:
        output = self.run("devices").stdout.decode("utf-8", "replace")
        return [
            line.split()[0]
            for line in output.splitlines()[1:]
            if line.strip() and line.split()[1:2] == ["device"]
        ]

    def is_installed(self, package: str) -> bool:
        output = self.shell("pm", "path", package)
        return "package:" in output

    def current_focus(self) -> str:
        output = self.shell("dumpsys", "window")
        for line in output.splitlines():
            if "mCurrentFocus=" in line:
                return line.split("mCurrentFocus=", 1)[1].strip()
        return ""

    def is_foreground(self, package: str) -> bool:
        return package in self.current_focus()

    def screen_size(self) -> tuple[int, int] | None:
        output = self.shell("wm", "size")
        match = re.search(r"(\d+)x(\d+)", output)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def display_size(self) -> tuple[int, int]:
        """真实画面尺寸（截图像素）。

        ``wm size`` returns the configured size (1920x1080 here) while the
        framebuffer is 1080x1920, so coordinate maths must use the screenshot.
        """
        try:
            width, height, _pixels = self.screencap_raw()
            if width > 0 and height > 0:
                return width, height
        except AdbError:
            pass
        size = self.screen_size() or (1080, 1920)
        return size

    def dump_xml(self, retries: int = 3) -> str:
        last_error = ""
        for _ in range(max(1, retries)):
            # 每次独立文件，dump 失败时不能读到上一次旧页面。一个 adb 往返完成
            # dump/read/delete；不降低 Android 的 idle 校验，也不缓存交易弹窗。
            path = "/sdcard/guanliang_" + uuid.uuid4().hex + ".xml"
            result = self.run(
                "exec-out", "sh", "-c",
                f"uiautomator dump {path} >/dev/null && cat {path}; rm -f {path}",
                timeout=15, check=False
            )
            output = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
            xml = ""
            if "<hierarchy" in output:
                # 兼容部分系统在 XML 之前输出诊断文字。
                start = output.index("<hierarchy")
                end = output.rfind("</hierarchy>")
                if end >= start:
                    xml = output[start:end+len("</hierarchy>")]
                    try:
                        ET.fromstring(xml)
                        return xml
                    except ET.ParseError:
                        pass
                last_error = "XML 内容不完整"
            else:
                last_error = "uiautomator dump 没有返回完整页面"
                if "could not get idle state" in output:
                    last_error = (
                        "页面动画一直没有停止，uiautomator 等不到 idle；"
                        "先运行 python -m executor prepare-device 关闭系统动画"
                    )
            time.sleep(0.4)
        raise AdbError(f"无法读取页面结构: {last_error}")

    def nodes(self, retries: int = 3) -> list[Node]:
        return parse_nodes(self.dump_xml(retries=retries))

    def screencap_raw(self) -> tuple[int, int, bytes]:
        """Return ``(width, height, rgba_bytes)`` without writing a file.

        Used only for pages that ``uiautomator`` cannot read (the WebView 撤单
        page).  The raw format is ``<width><height><format>`` followed by RGBA
        pixels; some builds add trailing header bytes, so the pixel block is
        taken from the end of the buffer.
        """
        result = self.run("exec-out", "screencap", timeout=30)
        data = result.stdout
        if len(data) < 16:
            raise AdbError("截图失败：返回数据为空")
        width, height, _format = struct.unpack("<III", data[:12])
        expected = width * height * 4
        if width <= 0 or height <= 0 or len(data) < expected:
            raise AdbError("截图失败：像素数据不完整")
        return width, height, data[len(data) - expected :]

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(int(x)), str(int(y)))

    def tap_node(self, node: Node) -> None:
        self.tap(*node.center)

    def input_text(self, text: str) -> None:
        if not _SAFE_TEXT.fullmatch(text):
            raise ValueError("输入内容只允许数字、字母和 ._@-，避免 shell 转义问题")
        self.shell("input", "text", text)

    def clear_text(self, length: int = 24) -> None:
        self.shell("input", "keyevent", "123")  # move cursor to end
        self.shell("input", "keyevent", *(["67"] * max(1, length)))

    def keyevent(self, code: int | str) -> None:
        self.shell("input", "keyevent", str(code))

    def start_app(self, activity: str, package: str) -> None:
        """Start an activity and fall back to the launcher when it is wrong.

        ``am start`` exits 0 even for "Error type 3: Activity class does not
        exist", so the exit code alone cannot be trusted.
        """
        result = self.run("shell", "am", "start", "-W", "-n", activity, timeout=30, check=False)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        if result.returncode == 0 and "Error" not in output and "does not exist" not in output:
            return
        self.shell(
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout=30,
        )

    def launch_package(self, package: str) -> None:
        """Launch whichever activity the package declares as its launcher."""
        result = self.run(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-c",
            "android.intent.category.LAUNCHER",
            package,
            check=False,
        )
        text = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
        component = text.splitlines()[-1].strip() if text else ""
        if "/" in component:
            self.start_app(component, package)
            return
        self.shell(
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout=30,
        )

    def force_stop(self, package: str) -> None:
        self.shell("am", "force-stop", package)

    def home(self) -> None:
        self.keyevent(3)

    def set_animations(self, enabled: bool) -> None:
        """Turn system animations off so ``uiautomator dump`` can reach idle.

        同花顺 首页有自动轮播和跑马灯，动画永远不停，uiautomator 会一直等
        ``idle state`` 直到超时。关掉三个动画缩放后 dump 才稳定。
        """
        value = "1" if enabled else "0"
        for key in (
            "window_animation_scale",
            "transition_animation_scale",
            "animator_duration_scale",
        ):
            self.shell("settings", "put", "global", key, value)
