# multi_agents_templates（多 Agent 研究工作区模板）

> 简体中文 · [English](README.en.md) · [日本語](README.ja.md)

本仓库提供支持多个 AI Agent 会话在同一工作区协同工作的基础骨架：涵盖会话身份认领、团队任务板、JSON 单一事实源与 Markdown 视图解耦的共享记忆、CLI 中立的技能分发机制，以及跨进程加锁的文件编辑接口。

## 快速上手

使用者操作流程：
1. 克隆并进入目录：`git clone <repo-url> <workspace_name> && cd <workspace_name>`。
2. 启动终端环境并输入 `/boot`（或任意初次指令触发初始化引导）。
3. 引导员 `00_yuki` 将依次协助确认交互语言、规划研究主题、配置环境变量与认领工作身份。

AI Agent 操作流程：
1. 会话启动第一步：执行 `python3 multiagents/agentctl.py me` 确认当前会话绑定的 Agent 身份。
2. 身份命中后，根据身份卡提示加载对应技能（`skills[]`）；若未命中名册，则展示选项由使用者确认，不自行假定身份。
3. 工作区通用文件编辑调用加锁接口（`python3 multiagents/agentctl.py file`），任务状态流转通过 `agentctl.py todo` 维护，分析结论沉淀至共享记忆（`agentctl.py memory`）。

## 架构背景

在现代 AI 辅助研发流程中，开发者常通过多会话、多窗口或跨客户端（如 Antigravity、OpenCode、Claude Code、Codex）并行处理复杂任务。在缺乏协同约定时，容易产生多重冲突：不同会话争抢同一身份、并发编辑相同文件导致改动覆盖、上下文遗忘导致重复排查、以及各环境提示词与规则配置漂移。

本项目抽象出多 Agent 协同所需的最小基础机制：
- 统一控制层：通过标准库脚本 `agentctl.py` 统一管理身份分配、任务板、共享记忆与加锁编辑。
- 单一事实源架构：任务板与记忆数据以 JSON 作为单一事实源，Markdown 视图由脚本自动导出，避免解析漂移。
- 技能中立化：技能单一事实源统一存放在 `skills/`，通过脚本自动镜像分发至各客户端配置目录。

## 兼容的 Agent 与客户端环境

框架通过环境标识自动识别会话，无缝支持主流 Agent CLI 与开发环境：
- Antigravity：自动识别 `ANTIGRAVITY_AGENT` 与 `ANTIGRAVITY_CONVERSATION_ID` 会话标识，技能镜像分发至 `.agents/skills/`。
- OpenCode：支持多窗口 TUI 会话探测，内置 `/boot` 快捷插件（位于 `.opencode/plugins/multiagents/`），技能镜像分发至 `.opencode/skills/`。
- Claude Code：支持独立终端会话检测，技能镜像分发至 `.claude/skills/`。
- Codex / CodeBuddy 等通用环境：支持环境标识探测与 `.agents/` 开放技能目录规范。

## 核心机制对照

| 痛点场景 | 框架解决方案 |
| --- | --- |
| 多会话身份冲突 | 会话启动运行 `agentctl.py me` 自动基于会话标识匹配档案；未匹配时由用户选定 |
| 任务分工与进展脱节 | 项目任务板 `todo`（单一事实源 JSON、视图 `TODO.md`）支持认领、交接与完成状态追踪；个人待办走 `task` |
| 协作知识覆盖遗失 | 记忆事实源按小节组织并加锁写入，多 Agent 并行记录时追加各自独立小节 |
| 跨客户端技能规则漂移 | 统一维护 `skills/<id>/SKILL.md`，通过 `sync_skills.py` 镜像同步至各 CLI 配置目录 |
| 并发修改文件冲突丢失 | 项目通用文件编辑通过 `agentctl.py file` 加锁执行，基于文件锁保证原子写入并审计留痕 |

## 目录结构一览

| 目录/文件 | 职能说明 |
| --- | --- |
| `AGENTS.md` | 面向 AI Agent 的核心规约与索引入口 |
| `multiagents/` | 框架控制工具、名册档案、单一事实源数据（`state/`）与协议说明 |
| `skills/` | 技能单一事实源（CLI 中立），一技能一目录 |
| `memory/` | 共享知识与研究日志视图（.md 为只读导出物，事实源在 `multiagents/state/memory/`） |
| `scripts/` | 按主题组织的分析脚本，内部通过 `SCRIPTS.md` 索引 |
| `repos/` | 外部依赖或参考代码仓库，默认不纳入版本控制 |
| `data/` | 清洗后的结构化中间数据 |
| `output/` | 最终交付成果（分析报告与图表） |
| `TODO.md` | 团队任务板导出视图（事实源为 `multiagents/state/todo.json`） |
| `tools/` | 第三方依赖工具源码与编译目录 |

## 面向 Vibe Coding 的主题目录哲学（`<asset>/<theme>/<product>`）

在借助大模型进行直觉驱动与高频迭代（**Vibe Coding**）时，开发者最常遭遇的工程瓶颈是：上下文被无关代码撑爆、临时探索脚本堆满根目录、生成的数据与图表散落无法复现、以及多窗口并发时代码相互踩踏。

本框架推行 **`<asset>/<theme>/<product>`（资产 / 主题 / 专属工件三级隔离）** 与 **`scripts/<theme>/<agent>/`（专属试验场）** 设计，旨在让 Vibe Coding 从"一次性狂欢"转变为"可持续的高能产出"：

1. **上下文精准投喂（Context Boundary）**：当 Agent 聚焦于某个特定任务（如 `ai_tts`）时，只需局部扫描 `scripts/ai_tts/`、`data/ai_tts/` 与 `memory/ai_tts/`。无关模块（如模拟器操作、底层驱动逆向）不进入上下文，信噪比最大化，彻底杜绝模型因信息过载而产生的注意力漂移与幻觉。
2. **极低爆炸半径（Low Blast Radius Playground）**：Vibe Coding 鼓励大胆尝试与快速生成探索脚本。每个 Agent 拥有独立的脚本子目录 `scripts/<theme>/<agent>/`，无论写多少验证性 demo 或临时探针，都绝不会破坏主干流程或干扰并行的其他 Agent；成熟模块沉淀进 `SCRIPTS.md`，废弃版本归档至 `archive/`。
3. **全链路可复现闭环（Reproducible Pipeline）**：从 `archive/<theme>/`（原始资产）➔ `data/<theme>/`（清洗数据）➔ `scripts/<theme>/`（计算逻辑）➔ `output/<theme>/`（报告与图表）➔ `memory/<theme>/`（结论与日记），每一次 Vibe 探索产出的图表与结论都能追溯来源脚本与数据版本，告别"只跑了一次就再也复现不了"的玄学窘境。
4. **多会话并发不撞车（Parallel Vibes without Clashes）**：支持开发者同时开启多个窗口（如 Antigravity、Claude Code、OpenCode）让不同的 Agent 分头探索。各自在专属主题与小节内运作，配合项目跨进程文件锁，保障所有人全速 Vibe、永不冲突。
5. **人类升级为"总导演"（From Coder to Director）**：产出物统一落盘在 `output/<theme>/{report,img}/`，人类开发者从繁重的低层代码细节中抽身，通过审阅直观的可视化图表与精炼报告进行决策与调优，以纯粹的直觉驱动下一轮迭代。

## 自定义工程适配

本模板不包含任何业务私有内容。适配新工程的典型流程：
1. 添加研究主题：执行 `python3 multiagents/agentctl.py todo topic add "主题名"`。
2. 建立目录骨架：创建 `scripts/<主题>/`、`data/<主题>/` 与 `output/<主题>/{report,img}/`。
3. 拓展专有技能：在 `skills/<id>/SKILL.md` 编写特定业务操作规范，并登记至 `AGENTS.md` 技能地图。
4. 本地路径配置：复制 `.env.example` 为 `.env` 并填写本地实际路径（`.env` 默认不提交版本库）。

## 多语言支持

框架命令行输出基于资源字典组织，源码中通过 `i18n.t("中文原文", **kwargs)` 调用，键名以中文原文为准，翻译维护于 `multiagents/locales/<lang>.json`。
- 查看或切换输出语言：`python3 multiagents/agentctl.py lang [code]`
- 提取与校验翻译字典：`python3 multiagents/i18n_extract.py --check`

## 许可证

本项目基于 MIT 许可证开源，具体条款见 [LICENSE](LICENSE)。第三方技能模块遵循其上游原始许可。
