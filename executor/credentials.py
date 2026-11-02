"""Credential storage for the 涨乐通 login.

Passwords are stored in the operating system keychain through ``keyring`` and
are never written to SQLite, JSON, logs or the repository.  Environment
variables are supported for non-interactive runs, but the keychain is preferred.
"""
from __future__ import annotations

import os
import re

SERVICE = "com.xreddot.stockmonitor.zhangle"
ACCOUNT_KEY = "account"
PASSWORD_KEY = "trading-password"

ENV_ACCOUNT = "ZHANGLE_ACCOUNT"
ENV_PASSWORD = "ZHANGLE_PASSWORD"

_PASSWORD = re.compile(r"[0-9]{6,20}")
_ACCOUNT = re.compile(r"[0-9]{6,20}")


class CredentialError(RuntimeError):
    """Raised when the keychain or a credential value is unavailable."""


def _keyring():
    try:
        import keyring
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise CredentialError("缺少 keyring，请先安装 requirements.txt") from exc
    return keyring


def _read(service_key: str) -> str | None:
    try:
        return _keyring().get_password(SERVICE, service_key)
    except Exception as exc:
        raise CredentialError(f"读取系统钥匙串失败: {exc}") from exc


def _write(service_key: str, value: str) -> None:
    try:
        _keyring().set_password(SERVICE, service_key, value)
    except Exception as exc:
        raise CredentialError(f"写入系统钥匙串失败: {exc}") from exc


def get_account() -> str | None:
    value = os.environ.get(ENV_ACCOUNT) or _read(ACCOUNT_KEY)
    return value.strip() if value else None


def set_account(value: str) -> None:
    value = value.strip()
    if not _ACCOUNT.fullmatch(value):
        raise ValueError("账号必须是 6—20 位数字")
    _write(ACCOUNT_KEY, value)


def get_password() -> str | None:
    value = os.environ.get(ENV_PASSWORD) or _read(PASSWORD_KEY)
    return value.strip() if value else None


def set_password(value: str) -> None:
    if not _PASSWORD.fullmatch(value):
        raise ValueError("涨乐通交易密码必须是 6—20 位数字")
    _write(PASSWORD_KEY, value)


def clear_password() -> None:
    try:
        _keyring().delete_password(SERVICE, PASSWORD_KEY)
    except Exception as exc:
        raise CredentialError(f"删除系统钥匙串密码失败: {exc}") from exc
