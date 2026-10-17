#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""style_lint.py —— Markdown 研究报告「去 AI 味 + 严谨性」纯文本体检器

零依赖：只用 Python 标准库；不解析 Markdown 语义，只做逐行/整篇的正则与计数分析。
用途：扫出报告里「AI 味重」与「不够严谨」的可疑点，给出「文件:行号 + 命中片段 + 提示」，
      便于人工复核后再改写。它只报警、不自动改稿。

检测项
  1. 加粗密度过高      正文每 100 行 `**` 出现次数超过阈值（默认 30）
  2. emoji / 装饰符号   ✅ ⚠️ 🔥 ✨ 📌 💡 🚀 🎯 等，及变体选择符 U+FE0F
  3. 破折号滥用        中文破折号 `——`
  4. 套话/口号式小标题  「一句话结论」「兜底证据」「隐藏冠军」「常青」等
  5. 修辞反转句式       「不是…而是…」「与其说…不如说…」
  6. 比喻化营销措辞     专利 / 重灾区 / 之谜 / 体温计 / 水位计 / 烧起来 等
  7. 空话连接词         综上所述 / 总而言之 / 值得注意的是 / 需要注意的是（同篇 >=2 次）
  8. 无法回溯的断言     显然 / 众所周知 / 无疑 / 必然是 / 毋庸置疑
  9. 机械枚举           在同篇出现 首先/其次/再次/最后 中的 >=2 个（疑似并列套路）

用法示例
  # 体检单份报告
  python3 style_lint.py output/<主题>/report/<报告>.md

  # 批量体检（shell 展开）
  python3 style_lint.py output/*/report/*.md

  # 收紧加粗阈值、只报「错误」级（退出码 1）
  python3 style_lint.py --bold-per-100 10 --dash-per-100 2 output/<主题>/report/*.md

  # 查看全部参数
  python3 style_lint.py --help

退出码
  0 = 未命中任何可疑点；1 = 至少命中一处；2 = 用法错误（无输入文件等）。
"""

import argparse
import os
import re
import sys

from style_rules import (  # noqa: F401
    _ANALOGY_SOFT_RE, _ANALOGY_STRONG_RE, _DECOR_RE, _EMPTY_CONNECT_RE,
    _ENUM_TOKENS, _INVERSION_RE, _METAPHOR_RE, _OPENING_NEG_RE,
    _PATENT_METAPHOR_RE, _RULES, _SLOGAN_RE, _SOURCE_HEADING_RE,
    _UNTESTABLE_RE)



def _clip(text, start, end, width=26):
    """截取命中片段及其上下文，压成单行。"""
    a = max(0, start - width)
    b = min(len(text), end + width)
    frag = text[a:b].replace("\n", " ").strip()
    return ("…" if a > 0 else "") + frag + ("…" if b < len(text) else "")


def lint_text(text, path, bold_per_100=30, dash_per_100=0):
    """对单份文本做全部规则检测，返回命中列表与整篇指标。

    每个命中为 dict(file, lineno, rule, level, snippet, hint)。
    """
    hits = []
    lines = text.splitlines()
    n_lines = max(1, len(lines))

    # --- 整篇级指标：加粗密度 / 破折号密度 -------------------------------
    bold_marks = text.count("**")
    bold_density = round(bold_marks / n_lines * 100, 1)
    if bold_density > bold_per_100:
        hits.append(dict(
            file=path, lineno=0, rule="bold_density", level="error",
            snippet="%d 处 `**` / %d 行 = %.1f 处每百行"
                    % (bold_marks, n_lines, bold_density),
            hint="加粗密度超阈值 %d，仅保留术语首次定义与关键数值" % bold_per_100,
        ))

    dash_marks = text.count("——")
    dash_density = round(dash_marks / n_lines * 100, 1)
    if dash_per_100 and dash_density > dash_per_100:
        hits.append(dict(
            file=path, lineno=0, rule="dash_density", level="warn",
            snippet="%d 处 `——` / %d 行 = %.1f 处每百行"
                    % (dash_marks, n_lines, dash_density),
            hint="破折号过密，多用逗号/冒号或拆句替代",
        ))

    # --- 逐行级规则 ------------------------------------------------------
    in_sources = False  # 进入「9. 信息来源」后，跳过类比/比喻等措辞检查
    first_body_of_section = True  # 小节内是否还没出现过正文句
    for i, line in enumerate(lines, 1):
        if _SOURCE_HEADING_RE.match(line):
            in_sources = True
        is_heading = line.lstrip().startswith("#")
        if is_heading:
            first_body_of_section = True   # 新小节，重置
        if line.lstrip().startswith("```"):
            continue  # 跳过代码围栏行
        # 标题行也要查措辞：标题里的对比句式/比喻与正文同等有害（此前误跳过标题，已修）
        for rule, rx, level, hint in _RULES:
            if in_sources and rule == "analogy_verb":
                continue  # 来源清单是引用他人标题，非本文措辞
            for m in rx.finditer(line):
                hits.append(dict(
                    file=path, lineno=i, rule=rule, level=level,
                    snippet=_clip(line, m.start(), m.end()),
                    hint=hint,
                ))
        if in_sources:
            continue  # 来源清单只跳过措辞类检查，仍统计破折号
        # 位置错配：只在小节「首个正文句」判定——读者此时尚不知道该概念，否定没有着落点
        stripped = line.strip()
        if stripped and not stripped.startswith(("|", ">", "!", "#")):
            if first_body_of_section and _OPENING_NEG_RE.match(stripped):
                hits.append(dict(
                    file=path, lineno=i, rule="opening_negation", level="error",
                    snippet=_clip(stripped, 0, len(stripped)),
                    hint="小节开场/概念首次出现处用否定句式，读者尚无该念头；"
                         "先用陈述句交代是什么，再展开"))
            first_body_of_section = False  # 本小节的正文句已出现
        # 「专利」仅在其作比喻（「是…的专利」）时才报，避免与专利库语境混淆
        for m in _PATENT_METAPHOR_RE.finditer(line):
            hits.append(dict(
                file=path, lineno=i, rule="metaphor", level="error",
                snippet=_clip(line, m.start(), m.end()),
                hint="比喻化营销措辞，改为中性技术表述",
            ))
        # 破折号逐处命中（正文字数控制项，单列）
        for m in re.finditer("——", line):
            hits.append(dict(
                file=path, lineno=i, rule="emdash", level="warn",
                snippet=_clip(line, m.start(), m.end()),
                hint="中文破折号，建议改为逗号/冒号或拆句",
            ))

    # --- 机械枚举：同篇出现 >=2 个并列标记 ------------------------------
    present = {}
    for i, line in enumerate(lines, 1):
        for tok in _ENUM_TOKENS:
            if tok in line:
                present.setdefault(tok, i)
    if len(present) >= 2:
        for tok, i in sorted(present.items(), key=lambda kv: kv[1]):
            hits.append(dict(
                file=path, lineno=i, rule="enumeration", level="warn",
                snippet=tok + " …",
                hint="出现多种并列标记（首先/其次/…），非流程语境建议改连贯段落",
            ))

    metrics = dict(lines=n_lines, bold_marks=bold_marks,
                   bold_density=bold_density, dash_marks=dash_marks,
                   dash_density=dash_density)
    return hits, metrics


def _fmt(hit):
    loc = "%s:%d" % (hit["file"], hit["lineno"]) if hit["lineno"] else hit["file"]
    return "  [%-8s] %-18s %s\n             ↳ %s  ｜ %s" % (
        hit["level"], loc, hit["rule"], hit["snippet"], hit["hint"])


# 每条规则的「正例」：自检时逐条确认它能被报出来。
# 动机：检查器若漏检，会给出虚假的通过信号（2026-10-01 曾漏检全部标题行）。
_SELFTEST_CASES = [
    ("emoji", "这是重点 ✅ 完成\n"),
    ("slogan", "## 0. 一句话结论\n"),
    ("inversion", "这种做法是辅助，而非替代。\n"),
    ("inversion", "这不是渐进下滑，而是断裂。\n"),
    ("metaphor", "溢价是通道收紧的体温计。\n"),
    ("untestable", "显然，数据说明一切。\n"),
    ("analogy_verb", "申购通道被掐断后，场内长出高溢价。\n"),
    ("empty_conn", "综上所述，结论成立。\n"),
    ("bare_negation", "规模大不是原因，规模是结果。\n"),
    ("bold_density", "**a** **b** **c** **d** **e** **f** **g** **h**\n"),
    ("emdash", "数据很重要——这一点必须强调。\n"),
]


def _selftest() -> int:
    """用内置正例逐条验证规则覆盖，返回 0 表示全部报得出来。"""
    bad = 0
    for rule, text in _SELFTEST_CASES:
        hits, _ = lint_text(text, "<selftest>", bold_per_100=1, dash_per_100=0)
        got = {h["rule"] for h in hits}
        if rule not in got:
            print("✗ 规则 %-14s 未能报出正例：%r" % (rule, text.strip()))
            bad += 1
    print("=" * 62)
    if bad:
        print("自检失败：%d / %d 条规则漏检" % (bad, len(_SELFTEST_CASES)))
    else:
        print("自检通过：%d 条正例全部报出" % len(_SELFTEST_CASES))
    print("=" * 62)
    return 1 if bad else 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="style_lint.py",
        description="Markdown 研究报告「去 AI 味 + 严谨性」纯文本体检器（零依赖）",
        epilog="示例：python3 style_lint.py output/<主题>/report/*.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", help="待体检的 Markdown 文件")
    p.add_argument("--bold-per-100", type=float, default=30,
                   help="加粗密度阈值（每百行 `**` 次数），默认 30")
    p.add_argument("--dash-per-100", type=float, default=0,
                   help="破折号密度阈值（每百行 `——` 次数），默认 0=不按密度报")
    p.add_argument("--quiet", action="store_true", help="只输出汇总，不逐条列出")
    p.add_argument("--selftest", action="store_true",
                   help="自检：用内置正例验证每条规则都报得出来（检查器自身的覆盖率）")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.files:
        p.print_help()
        return 2

    all_hits = []
    total_lines = 0
    for path in args.files:
        if not os.path.isfile(path):
            sys.stderr.write("跳过（不是文件）：%s\n" % path)
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        hits, m = lint_text(text, path,
                            bold_per_100=args.bold_per_100,
                            dash_per_100=args.dash_per_100)
        total_lines += m["lines"]
        all_hits.extend(hits)

        if hits and not args.quiet:
            print("── %s（%d 行，%d 处命中）" % (path, m["lines"], len(hits)))
            for h in hits:
                print(_fmt(h))
            print()

    # 汇总统计
    by_rule = {}
    by_level = {}
    for h in all_hits:
        by_rule[h["rule"]] = by_rule.get(h["rule"], 0) + 1
        by_level[h["level"]] = by_level.get(h["level"], 0) + 1

    print("=" * 62)
    print("汇总：%d 个文件 / %d 行，命中 %d 处（error %d，warn %d）"
          % (len([f for f in args.files if os.path.isfile(f)]), total_lines,
             len(all_hits), by_level.get("error", 0), by_level.get("warn", 0)))
    if by_rule:
        print("按规则：" + "，".join(
            "%s=%d" % (k, v) for k, v in sorted(by_rule.items(),
                                                key=lambda kv: -kv[1])))
    else:
        print("按规则：（无命中）")
    print("=" * 62)

    return 1 if all_hits else 0


if __name__ == "__main__":
    sys.exit(main())
