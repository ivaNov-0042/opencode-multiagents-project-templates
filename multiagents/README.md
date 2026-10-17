# 多 Agent 并行工作流（协议 + 名册）

> 设计原型与决策记录（为什么这么设计）：见 [DESIGN.md](DESIGN.md)。

> 本目录是**多 agent 并行工作**的唯一权威：名册、各 agent 的工作状态、占用的资源都在这里。
> 操作脚本见 `multiagents/`。

同一工作区可能同时有多个 agent 会话（**且可能来自不同客户端**：opencode / CodeBuddy / Codex …）。
本协议解决四件事：**我是谁**、**我在做什么**、**我占了什么**、**别人怎么不撞我**。

## 1. 身份协议（会话启动 / 上下文压缩后，第一步）

**这一步由脚本一步做完**（别再手工拆分执行）：

```bash
python3 multiagents/agentctl.py me                     # 首选：获取当前 agent
python3 multiagents/agentctl.py me --name 02_reviewer  # 用户点名时（点名优先于会话匹配）
python3 multiagents/agentctl.py new reviewer --display "复核"   # 「新增一个 agent」分支
python3 multiagents/agentctl.py spawn helper --skill multiagent-workflow  # 生成**另一个** agent（不登记当前会话）
```

`me` 按客户端与会话匹配档案：**命中就自动登记**（等价 `attach`）并打印身份卡——含可直接复述的
「我是 `X`」声明句、任务板分组、个人清单、`claims`、交接；**未命中则打印名册 + 三个选项与对应命令**，
退出码 3，**不自行认领**（退出码 3 是正常分支：等用户选，此时不要写任何源）。
`new` = 建档 + 登记 + 建 `/tmp/<agent>/` + 身份卡，一命令完成（`--no-attach` 则不登记当前会话）。
`spawn <role>` = 生成**另一个** agent（建档 + 注入 `skills` + 建 `/tmp/<名>/` + 摘要），**不**登记当前会话——
它的客户端与会话等它自己跑 `me` 时登记，所以一个 agent 造分身时不会把自己的会话绑上去；
`spawn --handoff '给 X：…'` 顺手把交接写进我的 `handoff` 字段（它会读到）。

身份**只有两个来源**，优先级从高到低：

1. **上下文里有显式声明** → 照用。包括：用户开场说了「你是 `02_reviewer`」、会话标题写明、或本会话此前已声明过。
2. **没有显式声明** → **必须读本名册（`README.md` 下面的表，或本目录的 `*.json`），让用户从名册里选**。
   不得自行认领。给用户的选项固定三类：**名册某项** / **新增一个 agent** / **暂不登记**。

拆开的原始动作（`me`/`new` 内部的步骤，仍可用）：

查看名册与匹配建议：

```bash
python3 multiagents/agentctl.py roster        # 打印客户端探测结果 + 名册 + 建议
python3 multiagents/agentctl.py roster --markdown   # 输出下面的表
python3 multiagents/agentctl.py card <agent>        # 只读看某 agent 的状态（不登记会话、不改档）
```

`roster` 只给**建议**（session_id 完全匹配优先、其次最近更新），**不替用户决定**。
用户口头点名时不盲目采用：模糊比对名册后列出匹配项，或提示新建。

读别人的进度不需要特殊权限，也不会改别人的档：`card <agent>` 给整档摘要，`todo list --owner <agent>` 按人过滤板子，
`task list --name <agent>` 读私人清单，`json get <字段> --name <agent>` 读任一字段，`memory show <档>` 读记忆正文（记忆是共享的）。
`me --name X` **不是**读命令——它会把当前会话登记到 X。

选定后登记并声明：

```bash
python3 multiagents/agentctl.py attach --name 02_reviewer
```

然后**显式声明一句**「我是 `02_reviewer`（角色 reviewer）」，读回该档的 `focus` / `board` / `todo` / `claims`，再动手。

**压缩后**同样先查上下文有没有声明；没有就重走上面第 2 步。压缩不会清 shell 环境，
客户端与会话 ID 仍可探测，但**探测结果只是线索，不能替代用户的选择**。

## 2. 名册

| agent | 角色 | 状态 | 更新 | 在做 | 占用资源 |
| --- | --- | --- | --- | --- | --- |
| `01_analyst` | analyst | active | 2026-10-17T15:50 | <一句话：当前在做什么> | <占用资源> |
| `02_reviewer` | reviewer | active | 2026-10-17T15:49 | <一句话：当前在做什么> | <占用资源> |

> 本表由 `agentctl.py roster --markdown` 生成后人工贴入；细节以各 `*.json` 为准。

## 3. 命名与档案

**命名规则**：`<两位自增序号>_<role>`，如 `01_analyst`、`02_reviewer`、`03_report`。
序号按首次登记顺序递增，**不复用、不回收**；`role` 变更需同步文件名与 json 内 `name`。

**必填字段**：`name` `role` `client` `status` `updated` `focus`。其余可选，宁可缺、不要编。

```jsonc
{
  "name": "02_reviewer", "role": "reviewer", "client": "opencode",    // client 默认 opencode
  "status": "active",                                                  // active|paused|blocked|done
  "updated": "2026-10-17T15:33:38+08:00",
  "focus": "复核数据与结论",
  "sessions": [ { "client": "opencode", "session_id": "ses_…", "state": "active" } ],
  "board": ["1.3"],                                                    // 认领的项目级 todo
  "todo": [],                                                          // 可选：自己的细项（用 task add/done/… 操作）
  "claims": { "files": [], "tmp": "/tmp/02_reviewer", "resources": ["gpu"] },
  "memory": [ { "path": "memory/<项目>/<主题>.md", "role": "maintainer" } ],
  "skills": ["multiagent-workflow"],                                   // 该 agent 该用的 skill ID（me 会打印）
  "created_by": "",                                                    // 由哪个 agent 生成（spawn 时写）
  "jobs": [], "artifacts": [], "handoff": "", "history": []
}
```

新建档案：

```bash
python3 multiagents/agentctl.py register --role report --focus "写报告"
# → 自动生成 03_report.json（序号自增）
```

## 4. 项目任务板（源 `multiagents/state/todo.json`，视图 根 `TODO.md`）

编号 `主题号.子号`（如 `1.3`）；主题号登记在 `todo.json` 的 `topics[]`（`todo topic add`，不复用、不回收）。
认领是唯一的协调动作：写操作对 JSON 加 `flock` 原子改写，已被他人认领则拒绝。

```bash
agentctl.py todo list
agentctl.py todo add "整理原始数据" --topic 1
agentctl.py todo claim 1.3 --owner 02_reviewer
agentctl.py todo note  1.3 "补充：…"
agentctl.py todo done  1.3
agentctl.py todo release 1.3
agentctl.py todo topic add "新主题名" --owner 01_analyst
agentctl.py todo export --write     # 由源重新渲染 TODO.md
agentctl.py todo verify            # 检查 TODO.md 是否与源漂移（exit 1 = 漂移）
```

- 根 `TODO.md` 是**生成物**：手改会在下次导出时被覆盖（`verify` 能查出）。改任务一律走上面的命令。
- 每次写操作后脚本**自动重导** `TODO.md`，故两处一般不会不一致。
- 板尾的手写散文（归档说明）放 `multiagents/state/todo.footer.md`，导出时原样附末尾；章节级说明放 `topics[].prose`。
- 项目级 TODO = **任务池**；agent json 的 `board[]` / `todo[]` = **我的视图**（可细可粗）。
- **禁止双写**：同一任务的不同粒度只在一处展开，另一处放 id / 指针。

## 5. 记忆（`memory/`，共有）

**存储模型：正文的源是 JSON，`.md` 是导出视图。** 源随其它机器写的状态一起收在 `multiagents/` 下：

```
multiagents/state/memory/<项目>/<主题>.json          # 源（一档一文件 ⇒ 锁的粒度就是一档）
multiagents/state/memory/<项目>/diary/<日期>_<agent>.json
memory/<项目>/<主题>.md                              # 导出视图（生成物，勿手改）
memory/<项目>/diary/<日期>_<agent>.md
memory/MEMORY.md                                    # 索引（视图）
```

一档按 `## 标题` 切成**节（section）**；写操作以节为单位、全部走脚本并对源加 `flock`：

```bash
agentctl.py memory list [--sections]                                  # 有哪些档、各有哪些节
agentctl.py memory show <档> [--section 03]
agentctl.py memory new  <档> --title "…"
agentctl.py memory append <档> --section "<标题>" --file <临时文件>    # 节存在则追加，不存在则新建
agentctl.py memory set    <档> --section <编号|标题> --file <临时文件>
agentctl.py memory set    <档> --title "<新标题>"
agentctl.py memory drop   <档> --section <编号|标题>                   # 下架到源 archived[]（可找回）
agentctl.py memory import <md 路径> [--owner X]                        # 收编手写 md（一次性）
agentctl.py memory export <档> --write | verify [--all]                # 导出 / 漂移检测
```

- 正文传参仿 `git commit`：`--text` ≈ `-m`（短），`--file` ≈ `-F`（长，`--file -` 读 stdin）。
  **长文首选 `--file`**：heredoc 里的反引号会被 bash 当命令替换**执行**（已踩过）。
- 传进去的正文按 **Markdown** 解析：含 `## 标题` 时以文内标题为准（`append` 可一次传多节），
  首个 `##` 之前的文字并入档的 `preamble`，代码围栏内的 `##` 不算标题；`set` 只接受单节。
- `<项目>`：领域名（如 `research`）；与具体主题无关的杂项用 `others`。
- 日记文件名带 agent，**同一天两个 agent 各写各的档**；即便写同一档，也是各写各的节、互不覆盖
  （曾因两个 agent 共用 `memory/others/<日期>.md`、各自整文件重写而互相覆盖过；现在靠「一档一锁 + 分节追加」消掉）。
- **禁止**再写回 `<项目>/<日期>.md` 这种不带 `diary/` 与 agent 名的旧形式。
- 归属不明的内容先记占位名 `00_unnamed`（查清归属后再改名），例如
  `memory/others/diary/<日期>_00_unnamed.md`。
- **归属的权威记录在各 agent json 的 `memory[]`**（`maintainer` / `contributor`），路径指向源 `.json`。
- 索引 **`memory/MEMORY.md`** 由 `agentctl.py memory-index --write` 从源渲染（「主题 / diary」类型 + 规模列）。

## 6. 冲突与资源规约

1. **临时目录隔离**：一律 `/tmp/<agent>/…`（曾因多个 agent 共用同一个临时目录撞车）。
2. **长任务登记**：编译 / rsync / 长时间分析写进 `jobs[]`（pid、日志、起止），免得别人重复起或误杀。
3. **破坏性操作**：删/覆盖他人产出前，先在对方 json 的 `handoff` 留言 + 项目板登记。
4. **让路顺序**：先声明者优先；抢占要有理由并写进 `history`。
5. **改项目通用文件走 `agentctl.py file`**：CLI 原生 edit / write 没有跨进程互斥，两个 agent 同改一个文件会丢更新
   （实测 12 个进程并发追加：加锁 12 行全在，不加锁只剩 4 行）。代码库、脚本、配置、源、规则、skill 一律加锁改
   （`file edit|write|append`），留痕在 `multiagents/state/locks/edits.jsonl`；agent 档案 / 任务板 / 记忆源由
   `json` / `todo` / `memory` 子命令写，用的是**同一把锁**；自己独占的产物可用原生 edit。

## 7. 落地清单

- 协议：本文件
- 工具：`multiagents/agentctl.py`（**唯一**的 py 工具，`json` 子命令覆盖所有档案字段操作；
  有意豁免 AGENTS.md 的长度规约）+ `multiagents/clients.json` + 用法速查 `multiagents/SCRIPTS.md`
- 规则条文：`AGENTS.md` 的「身份与多 agent」小节与它的 skill 地图（**只写规则，不写名册**）
- 记忆索引：`memory/MEMORY.md`

## 8. skill 与框架初始化

- **skill 源是 CLI 中立的 `skills/<id>/SKILL.md`**：各家 code CLI 的 skill 目录不同（`.opencode/skills/`、
  `.claude/skills/`、`.agents/skills/` 等），所以源只放一份，其余由 `python3 multiagents/sync_skills.py`
  生成镜像（`--check` 查漂移、`--dry-run` 预览）。**改 skill 只改 `skills/`**，别直接改镜像。
- **每个 agent 该用哪些 skill 记在档案的 `skills[]`**：`me` 的身份卡会打印，模型据 `description` 自行按需加载。
- **`00_yuki` 是随框架发布的默认引导员**：新克隆的仓库里先认领它（或用 `new` 建自己的 agent），
  它负责介绍这套框架并照 skill `first-run` 引导初始化；它不做具体研究任务。人设是長門有希，
  开场白与「目录 + 能力」自我介绍也在那个 skill 里，可按需换掉。
- **`python3 multiagents/agentctl.py init`** = 初始化自检：逐档核对字段引用的实例是否都在
  （`claims` / `memory[]` / `skills[]` / `artifacts[]` / `jobs[].log` / `todo[]` / `board[]` / `sessions[]`），
  `--fix` 只自动建 `/tmp/<agent>/`。克隆后跑一次就知道还缺什么。
- 框架开源前的私有内容清理清单：记忆档 `memory/others/first_run.md` 的「私有内容与开源边界」节。
- 落地清单（续）：`skills/`（源）+ `multiagents/sync_skills.py` + `multiagents/00_yuki.json` + 根 `README.md`。
