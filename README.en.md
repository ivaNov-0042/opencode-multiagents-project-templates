# opencode-multiagents-project-templates (Multi-Agent Research Workspace Template)

> 🌐 [简体中文](README.md) · English · [日本語](README.ja.md)

Bundles the skeleton that "multiple agent sessions working in parallel in one workspace" needs into an out-of-the-box directory: identity claiming, a claimable project task board, JSON-truth memory with Markdown views, CLI-neutral skills (with mirrors), and cross-process lock-protected file editing.

## 开箱：写给人类 / 写给 AI

**For humans**: `git clone <repo-url> your-workspace` → `cd` → open opencode and type `/boot` (any input also triggers onboarding).
The guide `00_yuki` asks you (in three languages) to type `init`, then walks you through the 8-step setup
(language, identity, paths, first topic); you just answer questions.

**For AI (agents)**: `git clone <repo-url> your-workspace` → `cd` → continue — first step of every session:
`python3 multiagents/agentctl.py me` (auto-registers on match; otherwise it lists the roster for the user to pick — **never self-claim**).
Load every skill in the profile's `skills[]` via the `skill` tool per the "load first" checklist; if onboarding is incomplete, ask one question at a time
(first one: output language), following skill `first-run` steps 1–8. If this directory has no framework: clone into a subdirectory,
then move the session with Code Mode `session_move` — no manual `cd` needed.
Write through locks (`file` / `todo` / `memory`); finish with `init` / `verify` / `.tests`.

## Website & docs

- Official single-page site (zh/en/ja): `web_doc/multiagents-site/` (`index.html` Chinese, `en.html` English,
  `ja.html` 日本語, switcher top-right; plus `robots.txt`, `agents.txt` (AI-agent guidance), `sitemap.xml`).
- Local preview: `python3 -m http.server 8000 -d web_doc/multiagents-site`, then open `http://127.0.0.1:8000/`.
- Deploy: push a separate repo (e.g. `opencode-multiagents-project-site`), then Settings → Pages → deploy from branch `master` root;
  visit `https://<user>.github.io/opencode-multiagents-project-site/`. Free accounts cannot use Pages on private repos — make it public first.

Framework self-check: `python3 multiagents/.tests/test_framework.py` (read-only; covers invariants / read-only surface / field-reference integrity, see `multiagents/.tests/README.md`).

The framework core uses only the Python standard library: `multiagents/agentctl.py` and `multiagents/sync_skills.py` need no third-party packages.
`requirements.txt` lists optional dependencies used by skill workflows.

## Why this exists

opencode v2 already supports multi-window TUI.
You can open several session windows at once and run tasks in parallel — each window on its own works great.

But the windows know nothing about each other. Point multiple agents at one project and problems appear immediately:
two sessions grabbing the same identity, lost updates on the same file, notes overwriting each other, no idea what tasks others claimed,
and a per-CLI copy of every skill drifting apart. With more windows, coordination itself becomes the hardest job.

This project is the skeleton for exactly that scenario — just enough, no more:
one `agentctl.py` (pure stdlib) handling identity, task board, memory, and locked file editing;
claim identity at session start, write through locks, each agent writes its own memory sections, skills live in one source mirrored everywhere.
The minimal common denominator for "multiple agents working in parallel" on complex projects, all of it here.

## What it solves

| Problem | Approach |
| --- | --- |
| Two sessions clash on identity | First step `agentctl.py me` registers by client & session; when unsure it lists the roster for the user — the script never self-claims |
| Unknown who does what | Task board `todo` (JSON truth, `TODO.md` view) supports claiming, notes, handoff; each agent also has a private checklist `task` |
| Long memory overwriting | Memory truth is JSON, `.md` exported by script; docs split into sections by `## title` — two agents write different sections |
| Skills drifting per CLI | One CLI-neutral source `skills/<id>/SKILL.md`; `sync_skills.py` mirrors into CLI dirs, `--check` detects drift |
| Concurrent edits lose updates | Project-common files go through `agentctl.py file`: cross-process flock + atomic replace + audit trail |

## Layout

| 路径 | 是什么 |
| --- | --- |
| `AGENTS.md` | 面向 agent 的硬约束与指针，开工前读 |
| `multiagents/` | 框架本体：名册与档案、任务板与记忆源（`state/`）、`agentctl.py`、`sync_skills.py`、协议 `README.md` |
| `skills/` | skill 源（CLI 中立），一 skill 一目录 |
| `memory/` | 记忆视图（`.md` 为生成物）；源在 `multiagents/state/memory/` |
| `scripts/` | 脚本，按主题分目录，各配 `SCRIPTS.md` |
| `repos/` | 外部代码仓库（研究或依赖对象）：clone 或 symlink 进来，默认不入版本库；复现信息记 `memory/` |
| `data/` | 清洗后的中间数据 |
| `output/` | 报告与图片：`output/<主题>/{report,img}/` |
| `TODO.md` | 任务板视图（生成物），源 `multiagents/state/todo.json` |
| `tools/` | 第三方工具与源码 |

## Build your own project on it

模板不含任何项目专属内容。落地顺序：建主题（`todo topic add`）→ 建目录（`scripts/<主题>/`、`data/<主题>/`、
`output/<主题>/{report,img}/`）→ 按需加项目专属 skill（`skills/<id>/SKILL.md` 并在 `AGENTS.md` 的 skill 地图补一行）
→ 把机器相关路径放进 `.env`（`cp .env.example .env`，真实 `.env` 不进版本库）。

要研究或依赖别人的代码时，先问清代码在哪，再决定 `git clone` 到 `repos/<名字>/`（自包含、可复现）还是
`ln -s` 链到本机已有的克隆（省磁盘、两边同步），两种都把 URL + commit 记进 `memory/<项目>/`；
要跑/构建的第三方工具放 `tools/<名字>/`，自己写的模块放 `src/`。细则见 skill `repo-conventions`。

## Multilingual output

框架的 CLI 输出走资源字符串：源码里是 `i18n.t("中文原文", **占位)`，译文在 `multiagents/locales/<lang>.json`，**键就是中文原文**。中文是源语言、不需要目录，查不到译文就回落中文（漏译因此是静默的，用 `--check` 查）。随模板附 `ja` 一份完整目录，可照着加别的语言。

```bash
python3 multiagents/agentctl.py lang            # 看当前语言与可选语言
python3 multiagents/agentctl.py lang ja         # 持久切换（写 multiagents/state/settings.json）
python3 multiagents/agentctl.py --lang ja todo list   # 只影响本次运行
AGENTCTL_LANG=zh python3 multiagents/agentctl.py roster   # 环境变量
```

维护目录：`python3 multiagents/i18n_extract.py`（补新 msgid、删失效键）｜`--new <lang>`（建骨架）｜`--check`（查漏译与占位符不一致）。

## License

MIT — the most permissive license that keeps attribution: use, modify, distribute (commercially included), just keep the copyright & license notice in copies.
See [LICENSE](LICENSE). Skill sources share this license; third-party skills imported verbatim (e.g. `rigorous-writing`) follow their upstream license.
