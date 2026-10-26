#!/usr/bin/env python3
"""把 CLI 中立的 skill 源 `skills/<id>/` 镜像到各 code CLI 的 skill 目录。

**为什么需要**：skill 目录因 CLI 而异——opencode 是 `.opencode/skills/`、Claude Code 是
`.claude/skills/`、还有 `.agents/skills/`。源只放一份（`skills/`），其余目录都是生成物，
免得同一份规程在多处各抄一遍。

用法：

    python3 multiagents/sync_skills.py                    # 写镜像（默认三个目标）
    python3 multiagents/sync_skills.py --check            # 只检查漂移（有漂移 exit 1）
    python3 multiagents/sync_skills.py --dry-run          # 只打印会做什么
    python3 multiagents/sync_skills.py --targets .opencode/skills .claude/skills

约定：镜像里的每个 `SKILL.md` 在 frontmatter 之后插入一行「生成物，勿手改」注释；
镜像目录中不在源里的子目录/文件会被删除（这些目录整体属于生成物）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import i18n                 # 资源字符串（多语言输出；源语言 zh，译文在 multiagents/locales/）

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "skills"
DEFAULT_TARGETS = (".opencode/skills", ".claude/skills", ".agents/skills")
MARK = (i18n.t("<!-- 生成物，勿手改：源 `skills/{sid}/SKILL.md`；改完跑 `python3 multiagents/sync_skills.py` -->"))


def stamp(text: str, sid: str) -> str:
    """在 frontmatter（--- … ---）之后插入生成物注释；没有 frontmatter 就放文件头。"""
    if not text.startswith("---"):
        return MARK.format(sid=sid) + "\n" + text
    lines = text.split("\n")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return MARK.format(sid=sid) + "\n" + text
    return "\n".join(lines[: end + 1] + ["", MARK.format(sid=sid)] + lines[end + 1:])


IGNORE_DIRS = {"__pycache__", ".git"}
IGNORE_EXTS = {".pyc", ".pyo"}


def is_ignored(p: Path) -> bool:
    return any(part in IGNORE_DIRS for part in p.parts) or p.suffix in IGNORE_EXTS


def wanted() -> dict[Path, str]:
    """源 → 相对路径 → 期望内容（文本文件已盖生成物戳）。"""
    out: dict[Path, str] = {}
    if not SRC.is_dir():
        sys.exit(i18n.t("源目录不存在：{SRC}", SRC=SRC))
    for skill in sorted(p for p in SRC.iterdir() if p.is_dir() and not is_ignored(p)):
        for f in sorted(p for p in skill.rglob("*") if p.is_file() and not is_ignored(p)):
            rel = f.relative_to(SRC)
            text = f.read_text(encoding="utf-8", errors="replace")
            out[rel] = stamp(text, skill.name) if f.name == "SKILL.md" else text
    return out


def mirror(target: Path, files: dict[Path, str], check: bool, dry: bool) -> list[str]:
    msgs: list[str] = []
    for rel, text in files.items():
        dst = target / rel
        old = dst.read_text(encoding="utf-8") if dst.exists() else None
        if old == text:
            continue
        msgs.append(f"{'漂移' if check else '写入'} {target.name}/{rel}")
        if not (check or dry):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
    have = (
        {p.relative_to(target) for p in target.rglob("*") if p.is_file() and not is_ignored(p)}
        if target.is_dir()
        else set()
    )
    for stale in sorted(have - set(files)):
        msgs.append(f"{'多余' if check else '删除'} {target.name}/{stale}")
        if not (check or dry):
            (target / stale).unlink()
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(description=i18n.t("skills/ 源 → 各 CLI skill 目录镜像"))
    ap.add_argument("--lang", metavar="CODE",
                    help=i18n.t("本次运行临时改用某语言的输出（zh/ja/en…）"))
    ap.add_argument("--targets", nargs="*", default=list(DEFAULT_TARGETS),
                    help=i18n.t("目标目录（相对仓库根），默认 {p0}", p0=' '.join(DEFAULT_TARGETS)))
    ap.add_argument("--check", action="store_true", help=i18n.t("只检查漂移，有漂移 exit 1"))
    ap.add_argument("--dry-run", action="store_true", help=i18n.t("不写，只打印"))
    args = ap.parse_args()
    if getattr(args, "lang", None):
        i18n.init(args.lang)

    files = wanted()
    skills = sorted({p.parts[0] for p in files})
    print(i18n.t("源 skills/：{p0} 个 skill / {p1} 个文件 → {skills}", p0=len(skills), p1=len(files), skills=skills))
    drift = 0
    for t in args.targets:
        target = (REPO / t).resolve()
        if not str(target).startswith(str(REPO)):
            sys.exit(i18n.t("目标不在仓库内，拒绝：{t}", t=t))
        msgs = mirror(target, files, check=args.check, dry=args.dry_run)
        drift += len(msgs)
        if msgs:
            print(i18n.t("  {t}：{p1} 处", t=t, p1=len(msgs)))
            for m in msgs:
                print(f"    {m}")
        else:
            print(i18n.t("  {t}：已一致", t=t))
    if args.check and drift:
        print(i18n.t("共 {drift} 处漂移：改源后请跑 `python3 multiagents/sync_skills.py`", drift=drift))
        return 1
    if drift and not (args.check or args.dry_run):
        print(i18n.t("已同步 {drift} 处。改 skill 只改 `skills/`，然后跑本脚本。", drift=drift))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
