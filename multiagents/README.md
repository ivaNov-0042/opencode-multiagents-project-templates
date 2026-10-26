# 多 Agent 并行协同协议

> 设计原型与决策背景见 [DESIGN.md](DESIGN.md)。操作工具见 `multiagents/agentctl.py`。

本目录为多 Agent 并行协同的权威数据源：维护团队名册、各 Agent 工作状态、资源占用声明与单一事实源数据。
框架支持不同客户端环境（Antigravity、OpenCode、Claude Code、Codex、CodeBuddy 等）并行协作，协议规范核心解决四个维度的协同问题：身份绑定、任务流转、资源占用与并发防冲。

## 1. 身份协议

会话启动或上下文恢复后，首先执行身份识别：

```bash
python3 multiagents/agentctl.py me                     # 自动匹配并登记当前 Agent
python3 multiagents/agentctl.py me --name 02_reviewer  # 指定认领特定身份
python3 multiagents/agentctl.py new reviewer --display "复核"   # 新增并绑定新 Agent
python3 multiagents/agentctl.py spawn helper --skill multiagent-workflow  # 生成独立 Agent（不绑定当前会话）
```

- `me` 命令根据当前环境标识与会话 ID 自动检索档案：
  - 匹配成功：自动完成会话绑定并输出身份卡（包含角色说明、认领任务、个人清单与依赖技能）。
  - 未匹配：输出当前名册与交互选项，退出码为 3，等待使用者明确选择，不执行自动推定认领。
- `new <角色>`：创建新档案、建立会话绑定并初始化 `/tmp/<agent>/` 临时目录。附加 `--no-attach` 参数则跳过会话绑定。
- `spawn <角色>`：用于生成协作者档案，预先配置技能与运行环境；其会话信息留待对应新终端启动后执行 `me` 自动关联。

### 身份判定规则

1. 显式指定优先：当使用者明确指定身份或上下文包含明确分配时，直接关联对应档案。
2. 无明确分配时：输出名册列表与选项，由使用者在名册已有项、新建身份与暂不登记之间做选择。

相关辅助查询指令：
```bash
python3 multiagents/agentctl.py roster        # 查看名册状态与匹配建议
python3 multiagents/agentctl.py card <agent>  # 只读查看指定 Agent 的状态摘要
```

确认身份后显式声明角色，并核对关联档案的 focus、board 任务号与 claims 资源声明后再执行后续操作。

## 2. 名册定义

| Agent | 角色 | 状态 | 最近更新 | 当前关注任务 | 占用资源 |
| --- | --- | --- | --- | --- | --- |
| `01_analyst` | analyst | active | 2026-10-17T15:50 | 基础数据清洗与特征构建 | 无 |
| `02_reviewer` | reviewer | active | 2026-10-17T15:49 | 统计结论复核与数据回溯 | 无 |

名册状态以各 `multiagents/*.json` 档案为准。

## 3. 命名与档案结构

- 命名规范：采用 `<两位自增序号>_<role>` 格式（如 `01_analyst`、`02_reviewer`）。序号按建档顺序递增，不回收复用。
- 核心字段结构：

```jsonc
{
  "name": "02_reviewer",
  "role": "reviewer",
  "client": "opencode",
  "status": "active",
  "updated": "2026-10-17T15:33:38+08:00",
  "focus": "复核数据与结论",
  "sessions": [ { "client": "opencode", "session_id": "ses_...", "state": "active" } ],
  "board": ["1.3"],
  "todo": [],
  "claims": { "files": [], "tmp": "/tmp/02_reviewer", "resources": [] },
  "memory": [ { "path": "multiagents/state/memory/<项目>/<主题>.json", "role": "maintainer" } ],
  "skills": ["multiagent-workflow"],
  "created_by": "framework",
  "jobs": [], "artifacts": [], "handoff": "", "history": []
}
```

新建档案指令：
```bash
python3 multiagents/agentctl.py register --role report --focus "撰写总结报告"
```

## 4. 项目任务板（单一事实源与视图）

团队级任务板事实源位于 `multiagents/state/todo.json`，只读渲染视图位于根目录 `TODO.md`：

```bash
python3 multiagents/agentctl.py todo list                     # 查看任务列表
python3 multiagents/agentctl.py todo add "任务描述" --topic 1  # 添加新任务
python3 multiagents/agentctl.py todo claim 1.3 --owner 01_analyst # 认领任务
python3 multiagents/agentctl.py todo note 1.3 "进展补充"       # 添加任务备注
python3 multiagents/agentctl.py todo done 1.3                 # 标记完成并重新导出视图
python3 multiagents/agentctl.py todo verify                   # 校验视图与事实源是否一致
```

各 Agent 的细分待办存入个人档案的 `todo[]`，通过 `agentctl.py task` 维护，不与团队公共板混淆。

## 5. 共享记忆维护

记忆单一事实源以 JSON 格式按主题维护于 `multiagents/state/memory/<项目>/<主题>.json`，Markdown 导出视图位于 `memory/<项目>/<主题>.md`：

- 写入操作统一通过脚本接口执行，由文件锁保护原子写入：
```bash
python3 multiagents/agentctl.py memory append <档名> --section "小节标题" --text "记录正文"
python3 multiagents/agentctl.py memory export <档名> --write
python3 multiagents/agentctl.py memory verify --all
```
- 正文按 `## 标题` 划分为小节，支持多 Agent 在不同小节并行追加，互不干扰。

## 6. 并发控制与资源互斥

修改项目通用文件（通用代码、技能、配置与事实源数据）时，调用加锁接口：
```bash
python3 multiagents/agentctl.py file edit <路径> --old-file <旧内容> --new-file <新内容>
python3 multiagents/agentctl.py file write <路径> --content-file <内容文件>
```

接口基于文件锁实现并发保护与原子替换，每次修改自动记录于 `multiagents/state/locks/edits.jsonl`。
