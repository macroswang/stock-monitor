"""执行器共享约束：总耗时预算，以及同一设备的线程/进程互斥。"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time

_deadline = ContextVar("executor_deadline", default=None)
_device = ContextVar("executor_device", default=None)
_locks = {}
_guard = threading.Lock()


def bound_timeout(seconds):
    deadline = _deadline.get()
    if deadline is None:
        return seconds
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("本次设备操作已超时，已停止后续动作")
    return min(seconds, remaining)


@contextmanager
def budget(seconds):
    outer = _deadline.get()
    deadline = time.monotonic() + seconds
    token = _deadline.set(min(deadline, outer) if outer is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def active_serial():
    return _device.get()


@contextmanager
def device_operation(adb, seconds=120):
    """占用整段操作；忙时拒绝，不排队执行可能已经过时的委托。"""
    nested = _device.get()
    if nested:
        if adb.serial and adb.serial != nested:
            raise RuntimeError("嵌套操作不能切换设备")
        adb.serial = nested
        yield
        return
    with budget(seconds):
        devices = adb.devices()
        serial = adb.serial
        if not serial:
            if len(devices) != 1:
                raise RuntimeError("请连接唯一模拟器，或用 ANDROID_SERIAL 指定设备")
            serial = devices[0]
        if serial not in devices:
            raise RuntimeError("指定模拟器未连接")
        with _guard:
            lock = _locks.setdefault(serial, threading.Lock())
        if not lock.acquire(blocking=False):
            raise RuntimeError("模拟器正在执行其他操作，请等待当前操作完成")
        handle = None
        token = None
        try:
            # CLI 和桌面核心共用锁；进程异常退出后由 OS 自动释放。
            folder = Path(tempfile.gettempdir()) / "guanliang-device-locks"
            folder.mkdir(mode=0o700, exist_ok=True)
            path = folder / (hashlib.sha256(serial.encode()).hexdigest() + ".lock")
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            handle = os.fdopen(fd, "r+b")
            if os.name == "nt":
                import msvcrt
                if not path.stat().st_size:
                    handle.write(b"0"); handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            adb.serial = serial
            token = _device.set(serial)
            yield
        except (BlockingIOError, PermissionError):
            raise RuntimeError("模拟器已被另一个执行器占用") from None
        finally:
            if token is not None:
                _device.reset(token)
            if handle is not None:
                handle.close()
            lock.release()
