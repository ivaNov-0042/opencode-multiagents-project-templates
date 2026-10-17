# agentctl.py 设计原型

> 示例中的 agent 名（00_guide / 01_worker / 02_worker）与路径均为占位，实际以各项目名册为准。

> 从正本仓库的 DESIGN.md 提炼的通用设计文档：为什么这么设计、协议怎么定、锁与数据流怎么做。

> 项目专属细节（具体研究内容）不在此；变更史见正本仓库。

## 0. 为什么需要（实测事故，不是假想）

当前工作区**已经**有两个 agent 并行，且已经互相干扰：

| 事故 | 证据 |
| --- | --- |
| 重复劳动：两边都在拆 `0x006bccd4` | 02_worker 把它标为「优先」；01_worker 也去拆了同一个函数 |
| 共用临时目录 | `/tmp/r2nlp/`（02 在 14:34 建的 r2 项目 `nlpcode`），01 在 15:01 又往同一目录写文件 |
| 压缩后失忆 | 上下文压缩后 agent 不知道自己是谁、做到哪、占用了什么 |


| 代号 | 会话 ID | 标题 | 线 |
| --- | --- | --- | --- |
| `02_worker` | `ses_eb7ac4333ffehinPc10g5X0tpr` | OpenAI API 与 Anthropic API 区别 | 静态逆向（<音频格式>） |

**且客户端可能不止一个**：本机实测已装 `~/.codebuddy`（CodeBuddy CN）、`~/.codex`（Codex）、opencode。
规约因此必须是 **客户端无关**的——不能把任何单一客户端的私有变量或接口当作唯一依据。

## 1. 设计原则

1. **客户端无关**：客户端只作元数据（`client` 字段，默认 `opencode`）；协议靠「仓库内文件 + 通用脚本 + 用户确认」成立。
2. **一 agent 一文件，只写自己的**：并发写冲突从结构上消除；全局状态 = 读全部文件。
3. **单一权威**：项目任务在一处（根 `TODO.md`），agent 细节在一处（自己的 json），记忆在一处（`memory/`）。
4. **身份必须经名册确认**：上下文有显式声明就照用；否则**必须读 `multiagents/` 名册让用户选**，
   且选项里**永远含「新增一个 agent」**。脚本只提供匹配建议，不替用户决定。
5. **最小依赖**：只用 `python3` 标准库 + 仓库内脚本，不引入守护进程/外部服务。

## 2. 目录布局

```
multiagents/
├── README.md            # 协议 + **名册索引**（谁是谁、状态、占用了什么）——判定身份先读它
├── DESIGN.md            # 本草案（批准后并入 README.md）
├── 01_worker.json      # 命名规则：自增序号_role；一 agent 一档
└── 02_worker.json
multiagents/
├── SCRIPTS.md           # 脚本索引（AGENTS.md 硬性要求）
├── clients.json         # 客户端探测规则表（env 标记 → client 名，可扩展）
└── agentctl.py          # roster / attach / register / todo / memory-index
TODO.md                  # 项目级任务板（可认领）
```

**命名规则**：`<两位自增序号>_<role>`，如 `01_worker`、`02_worker`、`03_report`。
序号按**首次登记顺序**递增，不复用、不回收；`role` 变更需同步文件名与 json 内 `name`。

## 3. 客户端探测（`client` 字段怎么来的）

`agentctl.py` 按序探测环境标记；**未命中记为 `unknown`，协议仍可用**（靠用户确认）。

| 序 | client | 探测依据 | 能否拿到会话 ID |
| --- | --- | --- | --- |
| 1 | `opencode` | `OPENCODE=1` 或 `OPENCODE_SESSION_ID` | ✅ `OPENCODE_SESSION_ID`（**已实测**：与我的会话一一对应） |
| 2 | `claude-code` | `CLAUDECODE=1`、`CLAUDE_CODE_ENTRYPOINT` | ⏳ 待核 |
| 3 | `codex` | `CODEX_HOME` 等 | ⏳ 可读 `~/.codex/sessions/YYYY/MM/*.jsonl`（待核） |
| 4 | `codebuddy` | `CODEBUDDY_*` | ⏳ 可读 `~/.codebuddy/logs/<date>/<proj>__<hash>.log`（待核） |
| 5 | 其它/未知 | — | ❌ 由用户确认 |

规则表放 `multiagents/clients.json`，不写死在代码里；探测结果**只作匹配建议**。

## 4. 身份协议（会话启动 / 上下文压缩后，第一步必做）

**只有两条来源，优先级从高到低**：

1. **上下文里有显式声明 → 照用。** 包括：用户开场说了「你是 02_worker」、会话标题写明、或本会话此前已声明过。
2. **没有显式声明 → 必须读 `multiagents/README.md` 名册（或该目录下的 `*.json`），让用户从名册里选。**
   不得自行认领。**选项里永远包含「新增一个 agent」**。

脚本 `agentctl.py` 是助手而非决策者：探测客户端、打印名册、给**匹配建议**与排序，供用户参考。

```
$ agentctl.py roster                 # 也可直接读 multiagents/README.md
client : opencode                   (env:OPENCODE=1, session=ses_ebc583d2cffe…)
名册（2）:
  01_worker    active [15:14] 模拟器/GUI 线       claims: -
  02_worker  active [15:09] 静态逆向(<音频格式>)   claims: /tmp/02_worker, data/…/r2/**
建议  : 01_worker（本会话 session_id 与该档一致）── 仅建议，等用户拍板
```

**给用户的选项固定三类**：

- 名册里的某个 agent；
- **新增一个 agent**（名字按 `<序号>_<role>` 规则生成，role 可自取或采纳脚本推荐）；
- **暂不登记**（仅限看代码/问问题这类无副作用的工作）。

**用户直接点名时**（如「你是 static」）不做盲匹配：脚本模糊比对名册，**列出匹配项或提示新建**，
由用户确认——因为名字可能只是近似，也可能根本不存在。

选定后登记并声明：

```
$ agentctl.py attach --name 02_worker    # 幂等：登记当前 client + 会话，刷新 updated
```

然后**显式声明一句**「我是 `02_worker`（角色 static-re）」，读回该档的 `focus` / `board` / `todo` / `claims`，再动手。

**压缩后**：同样先查上下文有没有声明；没有就重走第 2 步（读名册 → 用户选）。压缩不会清 shell 环境，
客户端与会话 ID 仍可探测，但**探测结果只是线索，不能替代用户的选择**。

## 5. agent 档案（`multiagents/<name>.json`）

```jsonc
{
  "name": "02_worker",
  "display": "静态逆向（<音频格式> 解码链）",
  "role": "static-re",
  "client": "opencode",                 // 当前客户端，默认 opencode
  "status": "active",                   // active | paused | blocked | done
  "updated": "2026-10-17T15:20:00+08:00",

  "focus": "定位并还原 <音频格式> 解码函数",
  "sessions": [                          // 同角色可挂多会话
    { "client": "opencode", "session_id": "ses_eb7ac4333ffe…",
      "title": "OpenAI API 与 Anthropic API 区别",
      "attached_at": "…", "last_seen": "…", "state": "active" }
  ],

  "board": ["1.3", "1.7"],               // 认领的项目级 todo（§6）
  "todo": [                              // 可选：仅本 agent 的细项；也可不含大 todo
    { "id": "b1", "task": "读 0x006bccd4 的位分配表引用", "state": "doing", "updated": "…" }
  ],

  "claims": {                            // 动手前先声明；别人先扫这里
    "tmp": "/tmp/02_worker",
    "resources": ["r2"]
  },
  "memory": [                            // 记忆归属的**权威记录**就在这里
  ],
  "jobs": [ { "name": "r2ghidra 编译", "pid": 790886,
              "log": "/tmp/02_worker/r2ghidra_build.log", "started": "…" } ],
  "artifacts": ["/tmp/02_worker/", "output/<主题>/report/<报告>.md"],
  "history": [ { "t": "2026-10-17T15:00", "e": "开始拆 0x006bccd4" } ]
}
```

- **必填**：`name` `role` `client` `status` `updated` `focus`
- **其余可选**：宁可缺，不要编——json 只记**能被验证**的东西。

## 6. 项目级任务板与认领

**编号规则**：`<主题号>.<子号>`。主题号在 `TODO.md` 顶部登记（1=<音频格式>、2=模拟器/GUI、3=本机环境与构建、4=多 agent 规约…）；
子号在每个主题内自增。例：

```markdown
# 项目任务板

主题编号：1=<音频格式> 解码 ｜ 2=模拟器/GUI ｜ 3=本机环境与构建 ｜ 4=多 agent 规约

## 7. 记忆（共享 + 索引）

- `memory/` 是**共有**的：任何 agent 可读、可写。
- **归属的权威记录在各 agent json 的 `memory[]` 里**（`maintainer` / `contributor`），不在 memory 文件本身。
- memory 文件头那行是**给人看的**，非强制、可省略；写法示例：

  ```markdown
  > 读改过: 01_worker, 02_worker（维护） ｜ 更新: 2026-10-17 15:20 ｜ 状态: canonical
  ```

  - 由 `agentctl.py memory-index` 汇总各 json 的 `memory[]` + 扫文件头生成；人工可再编辑。
  - 目前 `memory/MEMORY.md` **不存在**，而 AGENTS.md 已在引用它——本次一并补上。

## 8. 冲突与资源规约

1. **临时目录隔离**：一律 `/tmp/<agent>/…`（今天是 `/tmp/r2nlp/` 被双方共用，才有事故）。
2. **长任务登记**：编译 / rsync / 长时间 r2 分析写进 `jobs[]`（pid、日志、预计时长），避免别人重复起或误杀。
3. **破坏性操作**（删/覆盖他人产出）：必须先在对方 json 的 `handoff` 留言 + 项目板登记，再做。
4. **让路顺序**：先声明者优先；抢占要有理由并写进 `history`。

## 9. 加锁的文件编辑（`file` 子命令）

先按用户当时的要求做了独立工具 `editfile.py` + `filelock.py`（加锁、原子写、编辑留痕、`who` 查 claims），
用户随即要求**合并进 `agentctl.py`**。合并顺带处理了两个隐患：

1. **单一入口**：`agentctl.py file edit|write|append|read|locks|who` 取代 `editfile.py`，`multiagents/` 回到
   「一个 py 工具 + 一个镜像脚本」的形态，与文件头「唯一工具」的自我描述一致。
2. **同一把锁**：原先 `mutate_agent` / `mutate_board` / `mutate_memory` 各自 flock 在**目标文件自身**上，
   而文件编辑锁在**旁挂锁文件**上——同一文件两把锁等于没有锁（`file edit` 改 agent 档案与 `json set`
   可以同时进）。现在三条真源写入改用同一套 `locked()`（锁键 = 仓库内相对路径），实测 holder 持锁时
   `json set` 等了 1.94s 才落盘。
3. 附带好处：全部写入改成「临时文件 + `os.replace`」，读方看不到写了一半的内容；`multiagents/filelock.py`
   这个名字原先与 `requirements.txt` 里钉的 PyPI 包 `filelock==4.2.0` **撞名**，合并后消失。
