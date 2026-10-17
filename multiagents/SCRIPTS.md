# multiagents/ 脚本索引

> 多 agent 并行工作流的工具。协议与名册见 **`multiagents/README.md`**，身份规则见 `AGENTS.md`
> 的「身份与多 agent」小节与 skill `multiagent-workflow`。本目录的工具**只做读写，不替用户决定身份**。

## 文件

| 文件 | 作用 |
| --- | --- |
| `agentctl.py` | **唯一的 py 工具**：客户端探测 / 名册 / 登记 / 任务板 / 记忆索引 + **所有 agent 档案字段读写**（`json`）+ **改项目通用文件的加锁接口**（`file edit|write|append|read|locks|who`，加锁与原子写实现在文件内）。**有意豁免** AGENTS.md 的脚本长度规约，理由写在文件头 |
| `sync_skills.py` | skill 源 → 各 CLI skill 目录的镜像工具（CLI 中立的 `skills/<id>/` → `.opencode/skills` / `.claude/skills` / `.agents/skills`）；`--check` 查漂移、`--dry-run` 预览 |
| `i18n.py` | 资源字符串（多语言输出）：`t(msgid, **kw)`，**msgid = 中文原文**，译文在 `locales/<lang>.json`；语言来源 `--lang` → `AGENTCTL_LANG` → `state/settings.json` → `zh` |
| `i18n_extract.py` | 翻译目录维护：扫源码抽 msgid、`--new <lang>` 建骨架、默认跑更新目录、`--check [lang]` 查漏译与占位符不一致 |
| `locales/*.json` | 各语言的翻译目录（键 = 中文原文；**zh 无目录**，原文即中文）。译文里的 `{…}` 占位符须与原文逐字一致 |
| `clients.json` | 客户端探测规则表（env 标记 → client 名），**可扩展**，不写死在代码里 |
| 其余 `*.json` | agent 档案，一 agent 一档；靠「有没有 `name` 键」与非档案 json 区分 |
| `.tests/` | 框架自检测试（stdlib `unittest`，**只读**）：框架不变量 + 只读面 + 字段引用完整性；跑法与约定见 `.tests/README.md` |

已归档：`archive/loveplus/migrate_memory_layout_2026-10-17.py` —— 一次性记忆布局迁移（**已执行完毕**，
现在跑是空转）。留着它是因为表里的「旧 → 新路径映射」是全仓唯一记录旧日记路径的地方。

## 用法

```bash
CTL="python3 multiagents/agentctl.py"

# —— 获取当前 agent（会话启动 / 上下文压缩后第一步；首选，一步做完）——
$CTL me                                    # 会话匹配→自动登记→身份卡；未匹配→名册+三选项（退出码 3，不认领）
$CTL me --name 02_static-re                # 用户点名时（点名优先于会话匹配）
$CTL new static-re --display "静态逆向"     # 「新增一个 agent」分支：建档+登记+/tmp/<agent>/+身份卡
$CTL new helper --display "跑腿" --no-attach  # 只把档建出来，**不**登记当前会话（等价 spawn）
$CTL spawn helper --skill loveplus-emu-ops   # 生成**另一个** agent：建档+注入 skills+/tmp/<名>/+摘要
$CTL spawn helper --focus "先跑通 2.1" --handoff '给 03_helper：…'   # --handoff 同时写我的交接字段

# —— 拆开的原始动作（roster 只读；attach/register 仍可用）——
$CTL roster                                # 客户端探测 + 名册 + 匹配建议（不写任何档）
$CTL roster --markdown                     # 刷新 README 名册表用
$CTL card <agent>                          # 只读看某 agent 的完整状态（不登记会话；看别人用这个）
$CTL attach --name 02_static-re            # 登记当前客户端与会话（幂等）
$CTL register --role report --focus "写报告"      # 新建档案，名字 = <自增序号>_<role>
$CTL rename 00_guide 00_yuki               # 改名：档名+name+/tmp+板子认领人+记忆归属一并改

# —— 项目任务板（号码 = 主题号.子号；源 multiagents/state/todo.json，视图 根 TODO.md）——
$CTL todo list [--owner <agent>] [--topic N] [--state doing|todo|done|paused]   # list 可按人/主题/状态过滤
$CTL todo add "读 0x006bccd4" --topic 1
$CTL todo claim 1.3 --owner 02_static-re
$CTL todo note 1.3 "补充说明"
$CTL todo done 1.3
$CTL todo topic add "新主题名" --owner 02_static-re
$CTL todo export --write                      # 由源重渲染 TODO.md（写操作后已自动做）
$CTL todo verify                              # 校验 TODO.md 与源是否漂移

# —— 个人待办清单（写**自己档案**的 todo[]；与上面可被认领的项目板分家）——
$CTL task list [--name <agent>]              # --name 读别人的个人清单（只读）
$CTL task add "重启 GUI 后确认 extdata" --board 2.1   # --board 只做关联标注
$CTL task doing a1
$CTL task set a1 "改短一点"
$CTL task done a1
$CTL task drop a1                              # 要直接删用 rm

# —— 记忆正文（源 multiagents/state/memory/**/*.json；视图 memory/**/*.md 是生成物）——
$CTL memory list [--sections]                 # 有哪些档 / 各有哪些节（含写入 agent）
$CTL memory show loveplus/headless_azahar --section 03
$CTL memory new  loveplus/新主题 --title "标题"
$CTL memory append loveplus/headless_azahar --section "新坑" --file /tmp/01_emu-gui/body.md
$CTL memory set    loveplus/headless_azahar --section 03 --text "改短的正文"
$CTL memory set    loveplus/headless_azahar --section 03 --title "新节标题"   # 改**节**标题（给 --section 才是节）
$CTL memory set    loveplus/headless_azahar --title "新标题"
$CTL memory drop   loveplus/headless_azahar --section 07        # 下架（源 archived[] 留底）
$CTL memory import memory/others/some.md --owner 01_emu-gui     # 收编手写 md
$CTL memory export loveplus/headless_azahar --write             # 写操作后已自动导出
$CTL memory verify --all                                       # 校验全部视图 + MEMORY.md
$CTL memory-index --write                                      # 重渲染记忆索引

# —— agent 档案：所有字段操作都在 json 子命令下（--name 缺省 = 当前会话匹配到的档）——
$CTL json get                                  # 读整档
$CTL json get claims.tmp                       # 读某字段（点路径）
$CTL json get focus --name <agent>              # 读别人的字段（只读）；整档 `json get --name <agent>`
$CTL json set focus "在验证 extdata 是否被识别"     # 赋值：按 JSON 解析，失败当字符串
$CTL json set claims.files '["a.py","b.py"]'
$CTL json add board 2.1                        # 列表追加（同值自动跳过）
$CTL json add jobs '{"name":"sync","pid":123}' --key name    # 对象列表按 name upsert
$CTL json remove board 2.1                     # 按键值删
$CTL json remove jobs --where name=sync        # 按字段匹配删
$CTL json remove artifacts --index 3           # 按下标删
$CTL json history "重启 GUI 后 extdata 仍不认"     # 追加 history（带时间戳）+ 刷新 updated
$CTL json touch                                # 只刷新 updated / sessions[].last_seen
$CTL json memory memory/loveplus/diary/2026-10-17_01_emu-gui.md --role maintainer
$CTL json job "r2ghidra 编译" --pid 456 --log /tmp/02_static-re/build.log --note "等结果"
$CTL json handoff '给 02_static-re：…'            # 写交接（不带参数则读）
$CTL json artifact scripts/loveplus/run_gui.sh   # 追加产物路径（去重）
$CTL json add skills loveplus-emu-ops         # 登记该 agent 该用的 skill ID（`me` 会打印）

# —— 进展简报（用户问「你在做什么 / 进展」时产出；正文由 agent 给，脚本定文件名、落盘、追加生成附录）——
$CTL report --file /tmp/01_emu-gui/brief.md     # 写 output/quick-report/<日期时间>_<agent>.md
$CTL report --text "短补一句"                    # 短文本（--file - 读 stdin）
$CTL report --list                              # 列已有简报（时间前缀倒序）
$CTL report --no-appendix ...                   # 不追加「个人待办 / 名下板项」生成附录

# —— 记忆索引 ——
$CTL memory-index            # 打印
$CTL memory-index --write    # 写 memory/MEMORY.md

# —— 框架维护 ——
# skill 源是 CLI 中立的 skills/<id>/SKILL.md；各 CLI 的目录是生成镜像
python3 multiagents/sync_skills.py            # 镜像到 .opencode/skills、.claude/skills、.agents/skills
python3 multiagents/sync_skills.py --check     # 只查漂移（有漂移 exit 1）
$CTL init                                      # 初始化自检：各档字段引用的实例是否都在
$CTL init --fix                                # 顺带创建缺失的 /tmp/<agent>/
$CTL onboard status                            # 初次安装进度（源 state/first_run.json；能机器判定的步骤现算）
$CTL onboard step 3 done                       # 记一步（todo/doing/done/skip）
$CTL onboard finish                            # 标记完成（此后 me 不再挂引导提示）
$CTL onboard reset                             # 清零重来

# 改「项目通用文件」（代码库/脚本/配置/源/规则/skill/README）——CLI 原生 edit 没有跨进程互斥
$CTL file edit <路径> --old "旧" --new "新"     # 精确替换（--all 全替换 / --dry-run / --diff）
$CTL file write <路径> --content-file -        # 整文件替换；append 追加
$CTL file read <路径> [--offset N --limit N]   # 上共享锁读
$CTL file locks                                # 谁占着锁 + 最近编辑留痕
$CTL file who <路径>                           # 谁 claims 了这个路径

# —— 输出语言（资源字符串；源语言 zh，译文在 multiagents/locales/）——
$CTL lang                                       # 看当前语言与可选语言
$CTL lang ja                                    # 持久切换（写 multiagents/state/settings.json）
$CTL --lang en roster                           # 只影响本次运行（导入时预扫 argv，argparse help 也跟着变）
AGENTCTL_LANG=ja $CTL todo list                 # 环境变量：覆盖设置文件（测试/CI 用它固定 zh）
python3 multiagents/i18n_extract.py             # 改过源码里的中文原文后：更新目录（补新 msgid、删失效键）
python3 multiagents/i18n_extract.py --check     # 查空译文与占位符不一致（有则 exit 1）
```

## 测试

`multiagents/.tests/` 放框架层面的自检测试（**只读**：不写板子、记忆、档案）：

```bash
python3 multiagents/.tests/test_framework.py                                # 直接跑
python3 -m unittest discover -s multiagents/.tests -t multiagents/.tests    # 发现式
```

覆盖：`init` / `todo verify` / `memory verify --all` / `sync_skills.py --check` 四个不变量，
`card` 与 `todo list` 的 `--owner/--topic/--state` 过滤、读路径不打写提醒等只读行为，
以及各档 `claims` / `memory[]` / `skills[]` / `artifacts[]` / `board[]` 的引用完整性。
**改完框架（`agentctl.py`、skill 源、源 json）收尾跑一次。** 约定（只用标准库、只读、不写项目专有名）见 `.tests/README.md`。

## 路径约定

- 仓库根由 `agentctl.py` 自身位置推断（`parents[1]`，本文件在 `<repo>/multiagents/` 下），
  **无机器相关硬编码路径**。
- 只依赖 Python 标准库（`fcntl` 用于任务板与档案的加锁），不走项目 venv。
- 翻译目录（`multiagents/locales/`）与本地设置（`multiagents/state/settings.json`）同样由 ROOT 派生，换机器不用改。

## 常见坑

| 坑 | 说明 |
| --- | --- |
| `roster` 只给建议 | 身份必须经用户从名册里选；不得用脚本输出自行认领 |
| `attach` 拒绝名册外的名字 | 想加新身份先 `register`（防止凭空认领） |
| `rename` 只自动改源 | `rename <旧> <新>` 自动改的是**源**（档名 / `name` / `/tmp/<旧名>`（连内容搬） / `jobs[].log` / 板子认领人 / 记忆节归属 / `created_by`）并重导视图；README、skill、记忆正文里的旧名只打印「文件:行」交人工核对——叙述里的旧名常常**不该**改（历史记录），机器替换会改坏语义 |
| 译文键就是中文原文 | 改源码里的中文原文（含空格、标点）等于换 msgid，旧译文失效。改完跑 `python3 multiagents/i18n_extract.py` 更新目录，`--check` 应回到「未译 0｜占位符不一致 0」 |
| 三种切语言方式 | `--lang` 只影响本次运行；`lang <code>` 持久写 `state/settings.json`（机器本地，已 gitignore）；`AGENTCTL_LANG` 覆盖设置文件（测试与 CI 用它固定 zh） |
| 漏译是静默的 | 查不到译文就回落中文，所以缺译不会报错、也不会崩；只有 `i18n_extract.py --check` 会报 |
| docstring 不翻 | 只有用户可见输出走 `i18n.t`；docstring、注释、开发脚本的内部断言保持中文 |
| `json` 默认只改**自己的**档 | 当前会话匹配不到档案即报错（不猜）；显式 `--name` **写**别人的档会打印「确认无误再落盘」（读路径不打） |
| 读别人的状态（只读） | `card <agent>`（整档摘要）｜`todo list --owner <agent> [--topic N] [--state S]`｜`task list --name <agent>`｜`json get <字段> --name <agent>`｜`memory show <档>`（记忆本就共享）。**`me --name X` 不是读命令**：它把当前会话登记到 X（等价 attach） |
| 文本里别用反引号 | `json handoff '…'` 用**单引号**；反引号会被 bash 当命令替换**执行**（已踩） |
| 值解析规则 | `{…}`/`[…]`/带引号/`true`/`false`/`null`/纯整数 按 JSON，其余按字符串——所以 `add board 2.1` 存的是字符串 `2.1`，不是小数 |
| 任务板源 | `multiagents/state/todo.json`（flock 原子改）；根 `TODO.md` **是导出物**，手改必被覆盖，`todo verify` 报漂移 |
| 记忆源 | `multiagents/state/memory/**/*.json`（一档一文件）；`memory/**/*.md` **是导出物**，`memory verify --all` 报漂移 |
| 记忆正文传参 | 仿 `git commit`：`--text` ≈ `-m`（短）、`--file` ≈ `-F`（长，`--file -` 读 stdin）。**长文用 `--file`**：heredoc 里的反引号会被 bash 当命令替换**执行**（已踩） |
| `memory append --section` | 节存在→追加正文；不存在→档末尾新建一节（编号自动 `01..NN`）。`--section` 也接受编号 |
| `memory set` 的 `--title` | 两种含义按有没有 `--section` 区分：带 `--section` → 改**节**标题；不带 → 改**档**标题（节正文用 `--text`/`--file`） |
| 一档一锁 | 写操作只锁该档源 json；两个 agent 并发 append 同一档会串行化，两条都保住（实测） |
| 输入即 Markdown | `--text`/`--file` 的内容按 Markdown 解析：`## 标题` 就是节标题（**不会**再把标题行重复渲染进正文）；`append` 可一次传多节；首个 `##` 之前的文字并进档 `preamble`；`set` 只接受单节 |
| 代码围栏保护 | 正文中 ``` 围栏内的 `## xxx` **不会**被解析成新节 |
| `todo note` | 追加一条缩进备注（`notes[]`，支持多行）；备注不是任务，别用它改任务描述 |
| `todo add --topic N` | 主题号须已登记（`todo topic add`），否则拒绝；子号自动取该主题下最大者 +1 |
| 全角竖线 | 字段分隔符是 `｜`（U+FF5C），不是 ASCII `\|` |
| `claim` 冲突 | 已被他人认领时 exit=1 并提示；`release` 动别人的认领需 `--force` |
| 客户端探测 | 只有 opencode 已实测（`OPENCODE=1` + `OPENCODE_SESSION_ID`）；其余见 `clients.json` 的 `enabled=false` |
| `me` 退出码 3 | 未识别会话是**正常分支**（等用户从名册里选），不是报错；脚本已打印名册与三选项。此时**不要**写任何源 |
| `me --name` 与换绑 | 点名优先于会话匹配；若本会话此前已登记在别的档，会 stderr 提醒（原档登记保留，清理用 `json remove sessions`） |
| `file edit` 的 old / new | `--old-file` 与 `--new-file` 必须来自两个不同来源，**别把任一个写成 `/dev/stdin`**：第二次读拿不到内容，等于把匹配到的文本删掉（实测把 `def cmd_report` 整行删了，工具自身随即不可用）。若工具因改动而崩（SyntaxError / NameError），补法是 `import agentctl as a` 后用 `a.locked()` + `a.atomic_write()` + `a.log_edit()` 改回来——模块级导入不受 `main()` 崩溃影响，锁与留痕纪律不变 |
| `report` 的正文与附录 | 正文完全由 agent 给（`--text` / `--file` / stdin），脚本不替它编内容；正文之后追加一节**生成附录**（个人待办 / 名下板项 / 占用，读源现算，盖「生成物，勿手改」戳），`--no-appendix` 可关；同分钟内重复生成自动加 `-2`、`-3`，不覆盖旧简报 |
| `/tmp/<agent>/` | `new` 会建，`register` 不建；临时文件一律放这里（`claims.tmp` 默认即此路径） |
| 并发写 | 档案与任务板都靠 `flock` 原子改，**不要绕过 `agentctl.py` 手工写 json** |
| 长度规约 | `agentctl.py` **有意不拆**（几乎不改的工具）；改它之前先读 `README.md` |
| `new` vs `spawn` | `new` = **我**就是这个新档（会登记当前会话）；`spawn` = 我**造出**另一个身份（**不**登记当前会话，等它自己跑 `me`）。`new --no-attach` 与 `spawn` 等价 |
| `task` vs `todo` | `task` 写自己档案的 `todo[]`（私人清单，任务号 `a1`/`a2`…，不可被他人认领）；`todo` 是**项目任务板**（`state/todo.json`，可被认领）。`task add --board 2.1` 只在清单里做关联标注，不改板子状态 |
| `skills[]` 是自建名册 | 记录「这个 agent 该用哪些 skill」，`me` 打印出来；opencode 自身的 skill 权限（`agents.<id>.permissions` 的 `action: skill`）作用在 **opencode agent 档案**上，两者不是一回事 |
| skill 源只有一份 | 源是 CLI 中立的 `skills/<id>/SKILL.md`；`.opencode/skills/`、`.claude/skills/`、`.agents/skills/` 都是生成镜像（改源后跑 `sync_skills.py`，`--check` 查漂移）。别直接改镜像 |
| `init` 自检 | `agentctl.py init` 逐档核对 `claims` / `memory[]` / `skills[]` / `artifacts[]` / `jobs[].log` / `todo[]` / `board[]` / `sessions[]` 引用的实例是否都在；`--fix` 只自动建 `/tmp/<agent>/` |
