# AGENTS.md

> 遵循 [AGENTS.md 开放标准](https://agents.md/)：置于项目根目录、面向 AI 编码 Agent 的说明文件。
> 本文件仅包含核心约束与索引指针，详细规程按需加载对应技能（见下方技能地图）。

## 初始化引导

当 `multiagents/state/first_run.json` 不存在或 `complete` 不为 true 时，进入初次运行引导流程：

1. 运行 `python3 multiagents/agentctl.py me` 检查初始化进度与状态，按 skill `first-run` 推进引导（步骤 1–8）。初始化全部完成后进入常规工作模式。
2. 交互原则：一次提问一个事项，等待用户答复后再继续下一步。首个问题确立输出语言（中文 / 日本語 / English），后续全流程保持选定语言。

## 项目概览

当前工作区以主题（topic）为核心组织单元：围绕指定研究或工程主题开展数据获取、清洗、分析脚本编写与报告输出，统一归档相关资产，确保分析过程与结论可复现、可追溯。

## 核心原则

按主题归档：同一主题的脚本、产出图片、数据集与研究笔记须存放于对应主题目录，禁止散落在仓库根目录或跨主题混放。

## 身份与多 Agent 协同

会话启动或上下文恢复后，首先确认 Agent 身份：
- 运行 `python3 multiagents/agentctl.py me`。若命中当前会话，脚本自动登记并载入身份卡。
- 若未识别当前会话，脚本退出码为 3 并打印名册与选项（选择已有身份 / `new <角色>` 新建 / 暂不登记）。此时须由用户明确选择，不自行推定认领。
- 运行时临时文件统一存放在 `/tmp/<agent>/`，任务板、记忆单一事实源与档案字段规范见 skill `multiagent-workflow`。名册唯一事实源为 `multiagents/`。

## 目录结构

| 目录 | 用途 | 归档规则 |
| --- | --- | --- |
| `scripts/` | 脚本源码 | `scripts/<主题>/<agent>/`，并在对应目录维护 `SCRIPTS.md` |
| `tools/` | 第三方工具与依赖源码 | `tools/<工具>/`，构建产物保留在工具目录内 |
| `data/` | 清洗后的数据集 | `data/<主题>/` |
| `archive/` | 原始数据与历史归档 | `archive/<主题>/` |
| `memory/` | 沉淀知识与规则视图（.md 为只读导出物） | 详见 skill `multiagent-workflow` |
| `multiagents/` | 名册、运行状态、单一事实源数据与协同脚本 | 机器维护的事实源存储于 `state/` |
| `output/` | 最终交付物（分析报告与图表） | `output/<主题>/{report,img}/` |
| `repos/` | 外部依赖或研究用代码仓库 | `repos/<名字>/`，支持 clone 或 symlink，默认不入版本控制，来源记录于 `memory/` |
| `src/` | 自研复用模块或独立项目工程 | 大型项目置于 `src/<主题>/<项目>/`，复用模块扁平化组织 |
| `web_doc/` | 参考资料与配套站点 | `web_doc/<主题>/` |

## 核心约束

- 脚本模块化：主入口（`main.py` / `run_*.py`）不超过 200 行，独立模块不超过 300 行；保持单一职责，禁止内联长数据。详见 skill `repo-conventions`。
- 路径安全：禁止硬编码绝对机器路径；本地外部路径统一由根目录 `.env` 注入（参考 `.env.example`）。
- 凭证保护：禁止在终端输出、日志或归档文档中打印私密配置的明文值；必要时仅打印键名并使用掩码（如 `API_KEY=****`）。公开仓库提交使用 GitHub noreply 邮箱。
- 单一事实源与导出视图：任务板事实源为 `multiagents/state/todo.json`，记忆事实源为 `multiagents/state/memory/**/*.json`。根目录 `TODO.md` 与 `memory/**/*.md` 均为只读导出视图，禁止手动修改，统一使用 `agentctl.py` 维护。
- 并发文件修改加锁：代码库通用文件、配置、规则、技能与事实源数据的修改，统一调用 `python3 multiagents/agentctl.py file edit|write|append <路径>`。该接口基于跨进程文件锁实现原子写入并留痕于 `multiagents/state/locks/edits.jsonl`，防止并行会话相互覆盖。Agent 独占的私有主题产物可直接编辑。

## 技能地图（按需加载）

| Skill ID | 适用场景 |
| --- | --- |
| `multiagent-workflow` | 会话启动、身份认领、任务板操作、记忆维护、简报生成与档案管理 |
| `repo-conventions` | 目录规划、脚本编写规范、路径配置与外部仓库管理 |
| `plotting-standards` | 数据可视化与图表绘制规范 |
| `quant-analysis-rules` | 数据统计分析、指标校验与结论验证 |
| `report-writing` | 正式交付报告撰写、论据溯源与数据核对 |
| `rigorous-writing` | 正式文档文风规范、去 AI 味约束与自动化文风体检 |
| `first-run` | 工作区初次安装引导与基础环境就绪检查 |

### 技能加载方式

技能完整内容默认不加载至模型上下文中。系统向 Agent 提供可用技能列表，当需要执行对应领域任务时，通过调用 `skill` 工具或显式引用加载对应技能内容。
- 会话启动时，`agentctl.py me` 输出的身份卡包含建议加载的技能列表，按需加载后开展工作。
- 技能单一事实源存储于 `skills/<id>/SKILL.md`，通过 `python3 multiagents/sync_skills.py` 镜像同步至各 CLI 配置目录，`--check` 参数用于检查镜像一致性。

### 默认引导员 00_yuki

仓库预置默认引导员 `00_yuki`（档案位于 `multiagents/00_yuki.json`），用于协助新工作区完成环境初始化。使用者可直接认领该身份或创建专属 Agent。

## 收尾清单

- [ ] 产出文件已按主题归档至 `output/`、`data/` 或 `scripts/`
- [ ] 脚本满足行数与单一职责约束，`SCRIPTS.md` 索引已同步更新
- [ ] 代码与文档中无硬编码本地绝对路径
- [ ] 正式报告通过 `style_lint.py` 规范检查，数字结论均可溯源
- [ ] 关键技术经验与结论已同步至记忆单一事实源，运行 `memory verify --all` 确认无漂移
- [ ] 工作日志已按 `memory/<项目>/diary/<日期>_<agent>.md` 记录
