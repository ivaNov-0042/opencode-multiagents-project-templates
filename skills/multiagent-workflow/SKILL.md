---
name: Multi-agent workflow 与仓库规程
description: 多 Agent 并行协同的身份流转、任务分配、共享记忆维护与加锁编辑规范。在会话启动、上下文压缩恢复、认领任务或读写记忆时加载本技能。
---

# 多 Agent 协同规程

## 身份确认流程

会话启动或上下文恢复后，首先确认身份：
- 运行 `python3 multiagents/agentctl.py me` 获取身份。退出码含义：
  - `0`：成功匹配名册，自动登记本次会话并输出身份卡（包含身份声明句、焦点任务、关注任务板、claims 与挂载技能）。
  - `2`：参数 `--name` 指定的身份不存在于名册中；需核对名称或使用 `new <角色>` 新建。
  - `3`：当前会话未匹配到已登记档案。脚本打印名册与选项供用户选择，不自行推定认领。
- 未识别（退出码 3）时的处理分支：
  1. 认领名册既有身份：`python3 multiagents/agentctl.py me --name <name>`
  2. 新增独立身份：`python3 multiagents/agentctl.py new <角色>`
  3. 暂不登记：仅做临时排查，不修改事实源数据。
- 确认身份后显式声明当前角色，并核对该档的 focus、board 与 claims 再开展工作。
- 客户端信息记录于 `client` 字段，规程兼容各主流 CLI，不依赖单一客户端专有机制。名册事实源维护于 `multiagents/` 目录。

## 创建与生成 Agent

| 命令 | 适用场景 | 是否登记当前会话 |
| --- | --- | --- |
| `new <角色>` | 为当前会话创建并绑定全新档案（当前会话即该 Agent） | 是 |
| `spawn <角色>` | 生成另一个独立 Agent（建档并配置技能与临时目录，供其他会话后续认领） | 否 |
| `me --name <档>` | 将当前会话关联至已有档案 | 是 |

- `spawn` 用于创建协作子 Agent；其客户端与会话信息待对应会话启动后执行 `me` 自动登记。`new --no-attach` 与 `spawn` 等价。
- 常用参数包括：`--display` 说明中文职责、`--focus` 设定初始任务目标、`--skill <id>` 注入关联技能、`--handoff` 指定交接说明、`--no-tmp` 跳过创建临时目录。

## 统一工具：agentctl.py

| 子命令 | 主要用途 |
| --- | --- |
| `me` / `new` / `spawn` | 身份查询（自动匹配与登记）/ 新建身份 / 生成协作 Agent |
| `roster` / `register` / `attach` | 查看名册 / 基础建档 / 手动绑定会话 |
| `rename` | 变更 Agent 名称并同步更新关联事实源 |
| `card` | 查看指定 Agent 的状态摘要（只读，不修改会话绑定） |
| `todo` | 项目任务板（支持任务增删、认领、完成与视图导出） |
| `task` | Agent 个人待办清单（管理档案内部 `todo[]`，不公开认领） |
| `json` | 读写 Agent 档案的基础字段与属性 |
| `memory` / `memory-index` | 共享记忆读写与全局记忆索引刷新 |
| `quick-report`（别名 `report`） | 生成即时进展简报 |

名册、任务板、记忆正文与档案属性统一通过 `agentctl.py` 读写，底层基于 flock 文件锁确保并发安全，禁止手动修改 `multiagents/*.json`。

## 任务板管理与个人清单

- 项目任务板 `todo`：单一事实源为 `multiagents/state/todo.json`，导出视图为根目录 `TODO.md`，面向团队公开认领。
  - 支持操作：`list`、`add`、`claim <编号>`、`done`、`release`、`note`、`export`、`verify`、`topic add`。
  - 任务状态变更后脚本自动重新导出视图。
- 个人待办清单 `task`：记录于各 Agent 档案内部的 `todo[]` 列表中，用于拆解个人即时步骤，不支持跨 Agent 认领。
  - 支持操作：`list`、`add`、`doing`、`done`、`drop`、`set`、`rm`；支持 `--board <编号>` 关联项目板任务号。
- 认领任务执行 `todo claim <主题号.子号>`。独占文件、目录或设备资源须登记至档案的 `claims` 字段，操作前核对他人 claims 避免冲突。运行时临时文件统一置于 `/tmp/<agent>/`。
- 任务拆解粒度以可独立验证为准（如独立脚本、图表或报告段落）。

## 共享知识沉淀与记忆维护

- 正文单一事实源为 JSON 结构，存储于 `multiagents/state/memory/<项目>/<档>.json`；对应 `.md` 为脚本生成的只读视图，手改内容会被下次导出覆盖。
- 读写统一调用 `python3 multiagents/agentctl.py memory append|set|drop|new …`。
- 参数传递规则：短文本使用 `--text`，多行长正文使用 `--file <文件>`（或 `--file -` 读取标准输入）。
- 记忆按 `## 标题` 组织为节，追加操作以节为单位（`--section "<标题>"`）；不同 Agent 协同记录时追加各自独立小节，互不影响。
- 主题知识文档：`memory/<项目>/<主题>.md` 存放提炼后的分析方法、经验总结与业务规则。
- 工作日志：记录于 `memory/<项目>/diary/<日期>_<agent>.md`，命名包含日期与 Agent 标识，避免同日并行写入冲突。
- `memory/MEMORY.md` 为全局记忆索引，可通过 `agentctl.py memory-index --write` 重新生成。
- 开展新主题操作前，阅读 `memory/<主题>/` 目录下的既有说明，避免重复排查已知问题。

## 上下文压缩恢复后的状态同步

客户端进行上下文压缩时会将历史会话折叠为摘要，可能遗失局部细节。在检测到上下文压缩发生后，优先完成状态同步：
1. 运行 `agentctl.py me` 确认当前身份绑定与会话状态。
2. 核对任务板：将压缩前已完成的步骤或最新进展补齐至任务板（`todo done` / `todo note`）。
3. 补齐记忆：将排查所得结论与关键参数通过 `memory append` 写入对应记忆档。
4. 检查是否有未落盘的草稿，及时保存至对应主题目录。
完成同步确认后再继续推进后续业务逻辑。

## 进展简报与正式报告划分

- 进展简报（quick report）：针对当前工作状态的即时快照，调用 `python3 multiagents/agentctl.py quick-report` 生成，文件存储于 `output/quick-report/<日期时间>_<agent>.md`。
- 正式研究报告：属于完整任务交付成果，完成全部分析与验证后输出至 `output/<主题>/report/`。
当使用者询问当前进展时，根据需求提供口头说明、生成简报快照或汇报正式报告预计完成节点。

## 档案属性管理（json 子命令）

- 支持指令：`get`、`set`、`add`、`remove`、`history`、`touch`、`memory`、`job`、`handoff`、`artifact`。
- `claims` 记录当前持有的资源；`skills[]` 声明当前 Agent 建议加载的技能集合。
