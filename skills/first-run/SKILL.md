---
name: 框架初次安装与使用
description: 新工作区初始化与使用指引。向使用者介绍多 Agent 协同工作区结构、明确研究或工程目标、认领 Agent 身份并将工作区初始化至可用状态。
---

# 初次安装引导

## 语言设定

- 首问交互：使用客户端交互工具（如 OpenCode 的 question、Claude Code 的 AskUserQuestion 或常规提问）询问输出语言，提供 中文 / 日本語 / English 选项，并支持自由输入。后续全流程遵循该语言。
- 语言持久化：选定后执行 `python3 multiagents/agentctl.py lang <code>`（`zh` / `ja` / `en`）保存设置。临时切换可使用 `--lang <code>` 参数。
- 专业术语保持原样（agent、skill、todo、memory、claims、handoff、topic），命令与路径严格照抄。

## 框架架构说明

向使用者简要说明工作区核心机制：

1. 多 Agent 并行协同：通过 `python3 multiagents/agentctl.py me` 获取身份。会话匹配则自动登记并展示身份卡；未匹配时列出名册供使用者选择，退出码 3 为等待选择分支。
2. 单一事实源与导出视图：任务板事实源为 `multiagents/state/todo.json`，视图为根目录 `TODO.md`；记忆事实源为 `multiagents/state/memory/**/*.json`，视图为 `memory/**/*.md`。读写统一通过 `agentctl.py` 接口（加锁原子操作）。
3. 技能按需加载：技能单一事实源位于 `skills/<id>/SKILL.md`，使用 `python3 multiagents/sync_skills.py` 镜像分发至各客户端目录。
4. 协同三要素：任务板负责任务认领与流转，共享记忆沉淀可复用经验，进展简报通过 `agentctl.py report` 输出至 `output/quick-report/`。
5. 按主题归档：脚本置于 `scripts/<主题>/`，数据置于 `data/<主题>/`，交付成果置于 `output/<主题>/{report,img}/`。

## 引导风格与自报家门

保持专业、简洁与客观，说明工作区各目录功能与引导员具备的能力：

> 工作区目录规划如下：
> `AGENTS.md` 包含核心约束与规范，`multiagents/` 维护名册、任务板与记忆事实源；
> `skills/` 存放通用操作规约，`memory/` 存放沉淀的技术文档与工作日志；
> `scripts/`、`data/`、`output/` 分别存放分析脚本、清洗数据与交付报告；
> `archive/` 存放原始件，`tools/` 存放第三方工具源码，`repos/` 管理外部代码仓库，`src/` 存放自研通用代码。
> 引导员支持的操作包括：身份认领与建档（`me`/`new`/`spawn`）、任务分配（`todo`/`task`）、记忆读写（`memory`）、简报生成（`report`）、加锁编辑通用文件（`file`）以及完整性自检（`init`）。

## 初始化推进清单

按以下 8 项步骤推进：

- [ ] 1. 自报家门：说明框架结构与当前引导员身份（默认 `00_yuki`，用户自建 Agent 则使用新名称）。
- [ ] 2. 问清这次要研究什么，据此定目录：明确本次任务目标（代码分析、数据挖掘或自定义工程），据此规划目录。
- [ ] 3. 配路径：复制 `.env.example` 为 `.env`，按需填入本地外部路径。
- [ ] 4. 建虚拟环境装依赖：创建虚拟环境并按需安装 `requirements.txt`。
- [ ] 5. 同步 skill 镜像：执行 `python3 multiagents/sync_skills.py`，保证当前 CLI 能正常识别技能。
- [ ] 6. 认领身份：执行 `python3 multiagents/agentctl.py me`。若未识别则根据需求认领或新建 Agent。
- [ ] 7. 建研究主题：执行 `python3 multiagents/agentctl.py todo topic add "主题名" --owner <agent>`。
- [ ] 8. 报告初始化结果与下一步建议：汇总初始化各环节状态并给出后续工作建议。

初始化状态记录于 `multiagents/state/first_run.json`。支持环境判定的步骤可通过 `agentctl.py onboard status` 自动检验。全流程完成后执行 `agentctl.py onboard finish`。

### 目录规划指引

针对使用者的任务类型，采用对应的存放规则：

| 任务对象 | 存放路径 | 关键要素 |
| --- | --- | --- |
| 文本、数据与网页资料 | 原始件置于 `archive/<主题>/`，清洗数据置于 `data/<主题>/` | 明确数据来源与采集方式 |
| 外部代码仓库（分析/依赖） | `repos/<名字>/` | 区分上游 clone 与本地 symlink |
| 第三方工具源码与编译 | `tools/<名字>/` | 构建产物保留在工具目录内 |
| 自研复用模块与独立工程 | 通用模块放 `src/`，大型项目放 `src/<主题>/<项目>/`，脚本放 `scripts/<主题>/<agent>/` | 单模块保持单一职责 |

针对外部代码仓库，在初始化时确认引用形态：
- 上游 clone：`git clone <url> repos/<名字>`（推荐，自包含且版本独立）。
- 本地 symlink：`ln -s <本地路径> repos/<名字>`（复用本地既有克隆），并将真实路径登记至 `.env`。
无论采用何种形式，均须在 `memory/` 中记录来源 URL、commit hash 及 patch 说明。

## 常见问题排查

- 技能未被客户端识别：运行 `python3 multiagents/sync_skills.py` 刷新镜像，重连客户端。
- `me` 退出码 3：属于未识别当前会话的正常交互分支，等待用户明确选择身份，不直接写入数据。
- 环境变量缺失：未创建 `.env` 时，脚本支持相对仓库根目录推导基础路径；纯分析任务可暂留空。
