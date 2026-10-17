---
name: Multi-agent workflow 与仓库规程
description: 本仓库多 agent 并行的身份、任务板、记忆、档案、简报规程。会话启动或上下文压缩后、以及要跑 multiagents/agentctl.py、认领任务、写 memory、出简报时先加载；仓库目录/脚本/绘图/报告规范见同目录其它 skill。
---

# 多 agent 流程与档案

## 身份（会话启动 / 上下文压缩后第一步）

- 跑 `python3 multiagents/agentctl.py me` 获取身份。退出码语义：
  - `0` 命中名册，**已自动登记**本次会话，打印身份卡（可复述的「我是 `X`」声明句、focus、任务板、claims、skills）。
  - `2` `--name` 指定的档不在名册；用 `me --name <正确名>`，或 `new <角色>` 新建。
  - `3` 无法从当前会话识别身份；脚本打印名册与三个选项，**不得自行认领**，须由用户从名册选。
- 未识别（退出码 3）时的三个选项：① 名册里就是某一个 → `me --name <name>`；② 新增 → `new <角色>`；③ 暂不登记（本次会话不写任何真源）。
- 用户口头点名时不盲目采用：模糊比对名册后列出匹配项或提示新建，由用户确认。
- 登记后**显式声明**一句「我是 `<name>`（角色 X）」，读回该档的 focus/board/todo/claims 再动手。
- `client` 字段记录当前客户端（默认 opencode）；不得依赖任何单一客户端的私有能力。
- 名册不写进 AGENTS.md（会漂移），唯一权威是 `multiagents/`。

## 生成 agent：`new` / `spawn` / `me --name`

| 命令 | 含义 | 登记当前会话 |
| --- | --- | --- |
| `new <角色>` | 新建档案并把**当前会话**登记到它（我=这个新档） | 是 |
| `spawn <角色>` | 生成**另一个** agent：建档 + 注入 skills + 建 `/tmp/<名>/` | 否 |
| `me --name <档>` | 把当前会话登记到某个**已存在**的档 | 是 |

- `spawn` 用于造出子 agent / 分身；它的客户端与会话由它启动后跑 `me` 时自行登记。`new --no-attach` 与 `spawn` 等价。
- 常用参数：`--display` 中文职责、`--focus` 初始焦点、`--skill <id>` 注入 skill（可重复）、`--handoff`（spawn 时把当前 handoff 写成交给它的说明）、`--no-tmp` 不建临时目录。

## 唯一工具：`multiagents/agentctl.py`

| 子命令 | 用途 |
| --- | --- |
| `me` / `new` / `spawn` | 当前身份（自动登记 + 身份卡）／新档并登记／生成另一个 agent |
| `roster` / `register` / `attach` | 名册／建档／登记（拆开动作） |
| `rename` | 改 agent 名字（真源引用一并改，叙述文字只列位置） |
| `card` | 只读看某 agent 的状态（整档摘要；不登记会话、不改档） |
| `todo` | 项目任务板（真源、视图导出、认领、完成） |
| `task` | 我自己的待办清单（写档案 `todo[]`，不共享不认领） |
| `json` | 读写 agent 档案的**所有**字段 |
| `memory` / `memory-index` | 记忆正文读写／刷新索引 |
| `quick-report`（别名 `report`） | 进展简报 |

- 名册、任务板、记忆、档案字段一律走这个脚本；**不要手写 `multiagents/*.json`**（脚本用 `flock` 原子改写）。
- 速查见 `multiagents/SCRIPTS.md`，协议见 `multiagents/README.md`。
- 该脚本**有意豁免**脚本长度规约（见 `repo-conventions`）；改它之前先读 `multiagents/README.md`。

## 任务板 `todo` 与个人清单 `task`（分家）

- `todo` = **项目任务板**：真源 `multiagents/state/todo.json`，人类可读视图根 `TODO.md`（由脚本导出、勿手改）。**可被多 agent 认领**。
  - 动作：`list` / `add` / `claim <号>` / `done` / `release` / `note` / `export` / `verify` / `topic add`。
  - `done` 后脚本自动重导视图。主题内部细粒度清单可仍是手写 Markdown（如 `output/<主题>/TODO_<主题>.md`），由该主题主责 agent 自持。
- `task` = **我这个 agent 的私人清单**：写进自己档案 `todo[]`，**不共享、不可认领**。
  - 动作：`list` / `add` / `doing` / `done` / `drop` / `set` / `rm`；`add --board <号>` 关联项目板号。
- 认可任务用 `todo claim <主题号.子号>`；占用文件/目录/资源写进自己 json 的 `claims`，动手前先扫别人的 `claims`；临时目录一律 `/tmp/<agent>/`。
- 清单拆到「可独立验证」的粒度（一个脚本、一张图、一份报告各占一项）；收尾时全部完成或显式标注「遗留」。
- OpenCode V2 已移除内置 `todowrite`，任务清单走本脚本。

## 记忆

- **正文真源是 JSON，`.md` 是导出视图。** 真源 `multiagents/state/memory/<项目>/<档>.json`（一档一文件，写操作加 `flock`）；`memory/<项目>/<档>.md` 由脚本渲染，开头带「生成物，勿手改」，手改会被下次导出覆盖。
- 写入一律走 `python3 multiagents/agentctl.py memory append|set|drop|new …`（用法见 `multiagents/SCRIPTS.md`）。
- 正文传参仿 `git commit`：`--text`（≈ `-m`）写短文本、`--file <文件>`（≈ `-F`）写长正文、`--file -` 读 stdin。长正文用 `--file`，因为 heredoc 里的反引号会被 bash 执行。临时文件一律放 `/tmp/<agent>/`。
- 一档按 `## 标题` 切成**节**，追加以节为单位（`--section "<标题>"` 存在则追加、不存在则新建）；两个 agent 同时补写同一篇文档时各写各的节、互不覆盖。
- **常青主题文档** `memory/<项目>/<主题>.md`（游戏相关用游戏名，杂项用 `others`）承载提炼后的方法、规则、经验，可从日记总结，也可直接落盘。
- **日记** `memory/<项目>/diary/<日期>_<agent>.md`（`memory append <项目>/diary/<日期>_<agent> --section "<标题>"`，无此档时首条 append 自动建档）。一 agent 一天一文件、名字带 agent，正是为了两个 agent 同一天写记忆时不撞同一路径。**禁止**写回 `<项目>/<日期>.md` 这种不带 `diary/` 与 agent 名的旧形式。
- 归属不明的内容先记**占位名 `un_emanon`**（`emanon` 即 `no name` 倒写，`un_` 前缀标示"未归属"，与 `00_`–`99_` 编号的 agent 区分开），如 `memory/others/diary/2026-10-16_un_emanon.md`，查清归属后再改名；名册不为 `un_emanon` 建档案。
- `memory/MEMORY.md` 是记忆总览（索引），由 `memory-index --write` 刷新。
- **开始一个主题的具体操作前，必须先读 `memory/<主题>/` 下对应说明文件**（如 `touch_coords_<游戏>.md`、`<游戏>_headless.md`），其中沉淀了已验证的坐标、流程链、踩坑与"勿盲试"警告。
- 重要规约/坐标不要复制进 AGENTS.md（双份维护、很快过期）；AGENTS.md 只写**每次都要遵守**的硬约束与指针；过程细节进 skill 真源，项目细节进 `SCRIPTS.md` / `memory/`。
- `json memory <路径>` 的参数是 `memory/…md` 视图路径，不是子命令名——传错（如传了字面量 `get`）会把坏条目
  upsert 进档案 `memory[]`，`init` 会报「真源不存在」。写完用 `init` 或 `memory verify --all` 兜底。
- 收尾跑 `python3 multiagents/agentctl.py memory verify --all`，查视图与真源有无漂移。
- 改了框架（`agentctl.py` / skill 真源 / 真源 json）后收尾跑 `python3 multiagents/.tests/test_framework.py`：只读自检（不变量 + 只读面 + 字段引用完整性，见 `multiagents/.tests/README.md`）。

## 上下文压缩后（compact）立即同步真源

- opencode 的 compact 会把旧对话折叠成摘要——**摘要不保证保真**：任务状态、刚做完的步骤、认领/释放、
  踩坑结论都可能丢。所以压缩发生后（用户提「压缩了 / compact」、或你发现上下文只剩摘要 + 本 skill 被重新加载），
  在继续任何任务动作之前，**先做一轮真源同步**：
  1. `me` → 重新拿身份卡（登记可能仍在，确认 session 没换档）。
  2. **todo**：把压缩前已做但未记的任务状态补上——`todo done <号>` / `todo note <号> "<进展>"` /
     `todo claim <号>`；`task add/doing/done` 同理。宁可重复 `note`，不可丢状态。
  3. **memory**：压缩期间到手的结论、坐标、坑，立刻 `memory append`（日记节 + 常青文档各归各处）。
     压缩前说过「等会儿写进 memory」的，现在就写——「等会儿」在压缩后可能就是「永远」。
  4. 有半成品正式报告承诺的，检查 `output/<主题>/report/` 是否已落盘；没有就趁记得先落草稿。
- 同步完再回到手头任务；仍缺的上下文主动问用户一次要全，不要靠摘要猜。

## 进展简报与正式报告（先问清，别默认）

- 用户问「在做什么 / 进展如何」时，**先用一个问题问清要哪种**（选项框或普通提问，一次一问）：
  1. **简报**（quick report）：当前状态的即时快照 → `python3 multiagents/agentctl.py quick-report`，
     正文由 agent 写，脚本落盘到 `output/quick-report/<日期时间>_<agent>.md`（分钟精度，同分钟加 `-2`、
     `-3`，不覆盖旧简报）；落盘时脚本追加一节生成附录（个人待办 / 名下板项 / 占用，读真源现算、
     盖「生成物，勿手改」戳），不想要就 `--no-appendix`；`quick-report --list` 浏览已有简报。
  2. **正式报告**：任务做完后的研究产出 → **现在不落盘**，先答一句「任务完成后会写正式报告到
     `output/<主题>/report/`」，把要点记下（可 `memory append` 备忘），任务收尾时再落盘。
     不要把半成品研究报告当简报写进 quick-report。
- 两种都不是「默认走简报」：问过再动手；用户就是随口一问、不想要任何落盘，口头回答即可。

## 档案字段（`json` 子命令）

- 动作：`get / set / add / remove / history / touch / memory / job / handoff / artifact`。
- `claims`（`files` / `tmp` / `resources`）记录占用，动手前先扫别人的。
- `skills[]`：该 agent 该用的 skill ID 列表（本项目名册用）。`me` 的身份卡会列出它们并给出可照抄的加载清单（`skill(id=…)`）——**动手前先加载**。skill 正文不会自动进上下文，注入的是**镜像**，所以改真源后必须跑 `sync_skills.py`。它与 opencode 自身的 skill 权限（`agents.<id>.permissions` 里的 `action: skill`，作用在 opencode agent 档案上）是两套独立机制——前者是仓库内约定，后者是 opencode 客户端权限。

## opencode 插件（`.opencode/plugins/multiagents/`）

- 本项目自带 opencode 插件：注册 `/boot` 命令、首装未完成时向 system prompt 注入引导规则、固定首装会话标题。
- 插件**随仓库分发**（clone 即用，Discover 机制自动加载每个 `.opencode/plugins/` 目录）；不要把它的职责
  （boot 触发、一次一问）重复写进 AGENTS.md 之外的文件。改动插件文件会自动热重载，改本地依赖才要
  `opencode service restart`。

## 收尾（本 skill 相关）

- [ ] 方法/规则已记到 `memory/`
- [ ] 操作前已读 `memory/<主题>/` 说明文件，坐标/流程先查表
- [ ] 工作日志已按 `memory/<项目>/diary/<日期>_<agent>.md` 写入（用 `memory append --file`，不手改视图）
- [ ] 记忆改动收尾跑过 `memory verify --all`
- [ ] 上下文压缩（compact）后做过一轮「todo + memory」真源同步
