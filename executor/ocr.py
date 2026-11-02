"""On-device screenshot text recognition. No images or OCR bodies are persisted."""
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from .runtime import bound_timeout

_build_lock=threading.Lock()


class OcrUnavailable(ValueError):pass


def helper_binary():
    if platform.system()!='Darwin':
        raise OcrUnavailable('当前系统没有已验证的本机网页文字识别器，保留待核实状态')
    bundled=Path(getattr(sys,'_MEIPASS',''))/'vision-ocr'
    if getattr(sys,'frozen',False):
        if bundled.is_file():return bundled
        raise OcrUnavailable('安装包缺少本机识别组件，保留待核实状态')
    source=Path(__file__).with_name('vision_ocr.swift')
    key=hashlib.sha256(source.read_bytes()+platform.machine().encode()).hexdigest()[:16]
    folder=source.parent.parent/'.runtime'/'ocr';folder.mkdir(parents=True,exist_ok=True)
    binary=folder/('vision-ocr-'+key)
    with _build_lock:
        if not binary.exists():
            target=('arm64' if platform.machine()=='arm64' else 'x86_64')+'-apple-macos15.0'
            result=subprocess.run(['/usr/bin/xcrun','swiftc','-O','-target',target,str(source),'-o',str(binary)],capture_output=True,timeout=bound_timeout(90))
            if result.returncode:
                binary.unlink(missing_ok=True)
                raise OcrUnavailable('本机识别组件编译失败，保留待核实状态')
    return binary


def recognize(adb):
    binary=helper_binary()
    png=adb.run('exec-out','screencap','-p').stdout
    if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png)>25000000:
        raise OcrUnavailable('没有取得有效的本机截图，保留待核实状态')
    result=subprocess.run([str(binary)],input=png,capture_output=True,timeout=bound_timeout(15))
    if result.returncode:raise OcrUnavailable('本机网页文字识别失败，保留待核实状态')
    try:rows=json.loads(result.stdout)
    except (ValueError,UnicodeDecodeError):raise OcrUnavailable('本机识别结果格式错误') from None
    if not isinstance(rows,list) or len(rows)>1000:raise OcrUnavailable('本机识别结果不完整')
    return rows
