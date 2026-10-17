---
name: 报告撰写与文风
description: 本仓库长篇报告的撰写流程与数字核验：交 subagent 写、主会话抽查、verify_claims 核验、收尾过文风门禁；文风规则本身见 skill `rigorous-writing`。凡是要写/改报告或核验报告数字时加载。
---

# 报告撰写与文风

## 撰写流程

- **长篇报告必须交由专门的 subagent 撰写**（`subagent` 工具），不要在主导航会话里直接长篇写作。
- 主会话只负责：跑数据/分析 → 产出 `data/` 下的表与 `output/` 下的图 → 给 subagent 一份**自包含**素材清单（结论要点、表路径、图路径、来源链接、口径说明）。子会话没有主会话上下文，输入必须自包含。
- 写完后主会话**抽查数据引用是否与产出表一致**。

## 数字核验

- 推荐写 `verify_claims.py`，把报告里每个可核验数字与「产出表口径值（**现算，不写死**）」逐条比对，落表 `data/<主题>/**/report_claims_check.csv`。
- 外部来源标为「参考」，不作断言。
- **同一指标若存在多个口径，必须指定唯一口径并写清定义**，否则核验无从进行。

## 文风与体检（规则见 skill `rigorous-writing`）

- 成文或改写前加载 skill `rigorous-writing`：写作方法与结构、去 AI 味 11 条禁令、交付前清单都在那个 skill 里（含 `references/`）。本 skill 不重抄这些规则，免得两处漂移。
- 否定/对比句式（`不是 X，而是 Y`、`并非…而是…`、`而非…`、`而不是…`、`与其说…不如说…`）的判据与禁用场景见 `rigorous-writing` §三 第 5 条：开场与新概念引入处一律不用；`style_lint.py` 会以 `inversion` / `opening_negation` 报出。
- **收尾必须过门禁**（退出码 0 方可交付）：

  ```bash
  python3 skills/rigorous-writing/scripts/style_lint.py --selftest
  python3 skills/rigorous-writing/scripts/style_lint.py \
      --bold-per-100 10 --dash-per-100 2 output/<主题>/report/*.md
  ```

  `--selftest` 先确认检查器自身没漏检；体检返回 0 命中才算过。
- **改文风不得改动数字**：改完必须重跑核验仍全 OK。

## 收尾

- [ ] 长篇报告由 subagent 撰写，素材清单自包含（结论/表路径/图路径/来源/口径）
- [ ] 报告数字引用已与产出表比对；有 `verify_claims.py` 时改文风后重跑仍全 OK
- [ ] `style_lint.py --selftest` 通过，且对报告返回 0（`--bold-per-100 10 --dash-per-100 2`）；同一指标已指定唯一口径
