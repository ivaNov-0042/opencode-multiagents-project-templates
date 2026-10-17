#!/usr/bin/env python3
"""翻译目录维护：从框架源码抽 msgid，生成/更新 `multiagents/locales/<lang>.json`，查漏译。

用法：
  python3 multiagents/i18n_extract.py               # 扫源码 → 更新所有目录（补新 msgid、删已失效的键、保留已有译文）
  python3 multiagents/i18n_extract.py --new ja      # 新建一个语言的骨架（值留空 = 回落中文）
  python3 multiagents/i18n_extract.py --check [en]  # 只查：空译文 / 占位符与原文不一致 → exit 1
  python3 multiagents/i18n_extract.py --list        # 打印全部 msgid

扫描范围：`multiagents/*.py`（框架本体）。docstring 与开发脚本不算——那些保持中文。
目录文件里的**键**是中文原文（msgid），**值**是译文；译文里 `{...}` 占位符必须与原文完全一致。
"""
from __future__ import annotations

import argparse
import ast
import json
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MICRO = ROOT / "multiagents"
LOCALES = MICRO / "locales"
SKIP = {"i18n.py", "i18n_extract.py"}          # 自身与「翻译工具」的输出不入目录


def placeholders(text: str) -> list:
    """`{…}` token 清单（名字 + 格式说明符 + 转换符）：译文必须与原文逐字一致，含 `{p0:<16}` 这类对齐。"""
    out = []
    for _, name, spec, conv in string.Formatter().parse(text):
        if name:
            out.append((name, spec or "", conv or ""))
    return sorted(set(out))


def msgids() -> dict:
    """扫源码里 `i18n.t("…")` 的第一个位置参数 → {msgid: [文件:行]}。"""
    found = {}
    for path in sorted(MICRO.glob("*.py")):
        if path.name in SKIP:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            print(f"  [skip] {path.name}: 语法错误 {e}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            hit = (isinstance(f, ast.Name) and f.id == "t") or \
                  (isinstance(f, ast.Attribute) and f.attr == "t" and
                   isinstance(f.value, ast.Name) and f.value.id == "i18n")
            if not hit:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.setdefault(first.value, []).append(f"{path.name}:{node.lineno}")
    return found


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"  ✗ {path} 解析失败：{e}", file=sys.stderr)
        return {}


def dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "{\n" + ",\n".join(
        f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
        for k, v in sorted(data.items())) + "\n}\n"
    path.write_text(body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="框架翻译目录维护（msgid 见源码里的 i18n.t(…)）")
    ap.add_argument("--new", metavar="LANG", help="新建某语言的骨架")
    ap.add_argument("--check", nargs="?", const="", metavar="LANG", help="只查漏译与占位符不一致")
    ap.add_argument("--list", action="store_true", help="打印全部 msgid")
    args = ap.parse_args()

    ids = msgids()
    if args.list:
        for m in sorted(ids):
            ph = placeholders(m)
            print(f"  {'{' + ','.join(ph) + '} ' if ph else ''}{m}")
        print(f"  共 {len(ids)} 条 msgid")
        return 0

    if args.check is not None:
        langs = [args.check] if args.check else [p.stem for p in sorted(LOCALES.glob("*.json"))]
        bad = 0
        for lang in langs:
            cat = load(LOCALES / f"{lang}.json")
            missing = [m for m in ids if not str(cat.get(m, "")).strip()]
            mismatch = [m for m in ids if cat.get(m) and placeholders(m) != placeholders(cat[m])]
            print(f"  {lang}: 共 {len(ids)} 条｜未译 {len(missing)}｜占位符不一致 {len(mismatch)}")
            for m in missing[:8]:
                print(f"    · 未译: {m[:70]}")
            for m in mismatch[:8]:
                print(f"    · 占位符: {m[:60]} → {cat[m][:60]}")
            bad += len(missing) + len(mismatch)
        return 1 if bad else 0

    if args.new:
        path = LOCALES / f"{args.new}.json"
        if path.exists():
            print(f"  {path} 已存在；直接跑不带参数的命令即可更新")
        dump(path, {m: "" for m in ids})
        print(f"  已建骨架 {path}（{len(ids)} 条，值留空 = 回落中文）")
        return 0

    for path in sorted(LOCALES.glob("*.json")):
        old = load(path)
        new = {m: (old.get(m) or "") for m in ids}
        added = [m for m in ids if m not in old]
        dropped = [k for k in old if k not in ids]
        dump(path, new)
        print(f"  {path.name}: {len(new)} 条（新增 {len(added)}、删失效 {len(dropped)}、"
              f"已译 {sum(1 for v in new.values() if v.strip())}）")
    if not list(LOCALES.glob("*.json")):
        print("  还没有任何目录。用 `--new <lang>` 建一个（zh 不需要：原文即中文）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
