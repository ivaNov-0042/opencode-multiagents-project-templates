#!/usr/bin/env python3
"""框架输出的多语言资源（资源字符串 / i18n）。纯标准库。

- 源码里以**中文原文为 msgid**：`t("名册（{n}）:", n=3)`。译文放在
  `multiagents/locales/<lang>.json`（键 = 中文原文，值 = 译文）。
- 语言来源（优先级从高到低）：`--lang <code>` → 环境变量 `AGENTCTL_LANG` →
  `multiagents/state/settings.json` 的 `lang` → 默认 `zh`。
- **zh 不建目录**：查不到译文就回落 msgid（原文），所以漏译不会报错，只是显示中文。
- 维护：`python3 multiagents/i18n_extract.py` 更新目录骨架、`--check` 查漏译与占位符不一致。
- 开发者面向的文本（docstring、注释、开发脚本的内部断言）不翻译，保持中文。
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "multiagents" / "locales"
SETTINGS = ROOT / "multiagents" / "state" / "settings.json"
DEFAULT = "zh"

_LANG = None
_CATALOG = {}


def available() -> list:
    """有哪些语言：默认 zh + `locales/` 里已有的目录文件。"""
    out = [DEFAULT]
    if LOCALES.is_dir():
        out += [f.stem for f in sorted(LOCALES.glob("*.json")) if f.stem not in out]
    return out


def detect(argv=None) -> str:
    """按优先级定语言。argv 为 None 时看本进程的 sys.argv（模块导入时的 t() 也能拿到 --lang）。"""
    argv = sys.argv[1:] if argv is None else list(argv)
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    env = os.environ.get("AGENTCTL_LANG", "").strip()
    if env:
        return env
    try:
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
        if cfg.get("lang"):
            return str(cfg["lang"]).strip()
    except (OSError, ValueError):
        pass
    return DEFAULT


def init(lang=None, argv=None) -> str:
    """选定语言并加载目录（幂等）。"""
    global _LANG, _CATALOG
    _LANG = (lang or detect(argv) or DEFAULT).strip()
    _CATALOG = {}
    path = LOCALES / f"{_LANG}.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"[i18n] {path} 解析失败（{e}）；本次按原文输出", file=sys.stderr)
            data = {}
        _CATALOG = {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}
    return _LANG


def lang() -> str:
    return _LANG if _LANG is not None else init()


def catalog(code: str = None) -> dict:
    """读某个语言的目录（不改变当前语言）。"""
    path = LOCALES / f"{code or lang()}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def t(msgid: str, **kw) -> str:
    """取译文；没有译文就用原文。kw 非空时按 `str.format` 填占位符，失败则退回原文（不让程序崩）。"""
    if _LANG is None:
        init()
    text = _CATALOG.get(msgid, msgid)
    if not kw:
        return text
    for candidate in (text, msgid):
        try:
            return candidate.format(**kw)
        except (KeyError, IndexError, ValueError):
            continue
    return text
