# multi_agents_templates（多 agent 研究工作区模板）

> 🌐 简体中文 · [English](README.en.md) · [日本語](README.ja.md)

把「多个 agent 会话在同一个工作区里并行干活」需要的那套骨架打包成一个可直接开箱的目录：身份认领、可认领的
项目任务板、JSON 源 + Markdown 视图的记忆、CLI 中立的 skill（含镜像）、以及跨进程加锁的文件编辑接口。

## 开箱：写给人类 / 写给 AI

**写给人类**：`git clone <repo-url> 你起的工作区名` → `cd` → 打开 opencode 输入 `/boot`（任何输入也会触发引导）。
引导员 `00_yuki` 三语提示你输入 `init`，随后带你走完 8 步初始化
（选语言、认领身份、配路径、建主题）；你只需要回答问题。

**写给 AI（agent）**：`git clone <repo-url> 你起的工作区名` → `cd` → continue——会话第一步
`python3 multiagents/agentctl.py me`（命中即自动登记；认不出时列名册让用户选，**不得自行认领**），
按身份卡「先加载」清单用 `skill` 工具逐个加载该档 `skills[]`；首装未完成时一次只问一个问题
（第一问只问输出语言），照 skill `first-run` 步骤 1–8 推进。目标目录没有本框架时：clone 到子目录，
再用 Code Mode 的 `session_move` 把会话移进去，无需用户手动 `cd`。
干活写入走锁（`file` / `todo` / `memory`），收尾跑 `init` / `verify` / `.tests`。

## 官网与文档

- 官网单页（中/英/日三语）：`web_doc/multiagents-site/`（`index.html` 中文、`en.html` English、
  `ja.html` 日本語，右上角切换器互链；附 `robots.txt`、`agents.txt`（给 AI agent 的站点说明）、`sitemap.xml`）。
- 本地预览：`python3 -m http.server 8000 -d web_doc/multiagents-site`，访问 `http://127.0.0.1:8000/`。
- 部署：单独仓库（如 `opencode-multiagents-project-site`）推 GitHub 后，Settings → Pages → 从分支 `master` 根目录部署，
  访问 `https://<user>.github.io/opencode-multiagents-project-site/`。免费账户私有仓库不支持 Pages，公开后再开。

框架自检：`python3 multiagents/.tests/test_framework.py`（只读，不写任何源；覆盖不变量 / 只读面 / 字段引用完整性，见 `multiagents/.tests/README.md`）。

框架本体只用 Python 标准库：`multiagents/agentctl.py` 与 `multiagents/sync_skills.py` 无需任何第三方依赖。
`requirements.txt` 列的是各 skill 工作流可能用到的可选依赖。

## 创建原因

opencode v2 已经支持多窗口 TUI。
你可以同时开多个会话窗口、并行处理多个任务——单看每个窗口，体验都很好。

但窗口之间是互相不知道对方存在的。对同一个项目开多窗口让多个 agent 协作时，问题立刻出现：
两个会话抢同一个身份、都改同一个文件丢更新、各自记的笔记互相覆盖、不知道对方认领了什么任务、
skill 在每个 CLI 里各一份很快改漂移。窗口多了，协同本身成了最难的活。

本项目就是给这个场景补的骨架——刚好够用，不多不少：
一个 `agentctl.py`（纯标准库）管身份、任务板、记忆、加锁文件编辑；
会话第一步认领身份，写入走锁，记忆各写各的节，skill 单一源镜像分发。
复杂项目里「多个 agent 并行干活」需要的最小公约数，都在这了。

## 它解决什么

| 问题 | 做法 |
| --- | --- |
| 两个会话撞同一个身份 | 会话第一步 `agentctl.py me` 按客户端与会话自动登记；认不出来时列出名册让用户选，脚本绝不自行认领 |
| 不知道谁在干什么 | 项目任务板 `todo`（源 JSON、视图 `TODO.md`）可认领、可留备注、可交接；每个 agent 另有私人清单 `task` |
| 长记忆互相覆盖 | 记忆正文源是 JSON，`.md` 由脚本导出；一档按 `## 标题` 切节，两个 agent 同写一篇各写各的节 |
| skill 各 CLI 一份、改起来漂移 | 源 `skills/<id>/SKILL.md` CLI 中立，`sync_skills.py` 镜像到各 CLI 目录，`--check` 查漂移 |
| 并发改同一文件丢更新 | 项目通用文件走 `agentctl.py file`：跨进程 flock + 原子替换 + 编辑留痕 |

## 目录导航

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

## 用它做你自己的项目

模板不含任何项目专属内容。落地顺序：建主题（`todo topic add`）→ 建目录（`scripts/<主题>/`、`data/<主题>/`、
`output/<主题>/{report,img}/`）→ 按需加项目专属 skill（`skills/<id>/SKILL.md` 并在 `AGENTS.md` 的 skill 地图补一行）
→ 把机器相关路径放进 `.env`（`cp .env.example .env`，真实 `.env` 不进版本库）。

要研究或依赖别人的代码时，先问清代码在哪，再决定 `git clone` 到 `repos/<名字>/`（自包含、可复现）还是
`ln -s` 链到本机已有的克隆（省磁盘、两边同步），两种都把 URL + commit 记进 `memory/<项目>/`；
要跑/构建的第三方工具放 `tools/<名字>/`，自己写的模块放 `src/`。细则见 skill `repo-conventions`。

## 多语言输出

框架的 CLI 输出走资源字符串：源码里是 `i18n.t("中文原文", **占位)`，译文在 `multiagents/locales/<lang>.json`，**键就是中文原文**。中文是源语言、不需要目录，查不到译文就回落中文（漏译因此是静默的，用 `--check` 查）。随模板附 `ja` 一份完整目录，可照着加别的语言。

```bash
python3 multiagents/agentctl.py lang            # 看当前语言与可选语言
python3 multiagents/agentctl.py lang ja         # 持久切换（写 multiagents/state/settings.json）
python3 multiagents/agentctl.py --lang ja todo list   # 只影响本次运行
AGENTCTL_LANG=zh python3 multiagents/agentctl.py roster   # 环境变量
```

维护目录：`python3 multiagents/i18n_extract.py`（补新 msgid、删失效键）｜`--new <lang>`（建骨架）｜`--check`（查漏译与占位符不一致）。

## 许可

MIT——保留署名的最宽松许可：任意使用、修改、分发（含商用），唯需在副本中保留版权与许可声明。
详见 [LICENSE](LICENSE)。skill 真源随本仓库同许可；从上游原样引入的第三方 skill（如 `rigorous-writing`）以其上游许可为准。
