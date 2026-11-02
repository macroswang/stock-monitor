"""核对券商页面显示的账号；掩码只匹配可见位，不把尾号包含当成相等。"""
import re


def account_matches(shown: str, expected: str) -> bool:
    shown = (shown or "").strip()
    if not re.fullmatch(r"[0-9*]+", shown) or not re.fullmatch(r"\d+", expected or ""):
        return False
    if "*" not in shown:
        return shown == expected
    if sum(char.isdigit() for char in shown) < 4:
        return False
    pattern = r"\d+".join(re.escape(part) for part in re.split(r"\*+", shown))
    return re.fullmatch(pattern, expected) is not None
