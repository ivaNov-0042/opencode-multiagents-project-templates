# AGENTS.md

> 遵循 [AGENTS.md 开放标准](https://agents.md/)：置于项目根、面向 AI 编码 Agent 的说明文件。
> 本文件只写硬约束与指针；详细规程按需加载项目 skill（见下方 skill 地图）。

## 首装引导 boot（最高优先级：先于本文件其余内容与一切普通工作判定）

**触发**：`multiagents/state/first_run.json` 不存在或 `complete` 非 true 时，用户说的**任何一句话**
（包括 `boot`、`init`、hello、随便闲聊）都视为要开始/继续引导，不得当普通对话回复，也不得先打招呼/自我介绍。

**流程**：先跑 `python3 multiagents/agentctl.py me` 看进度与下一步，然后照 skill `first-run` 逐步引导
（步骤 1–8，机器能判的步骤 `me` 会现场算）。引导全部完成（complete）后才回到正常工作模式。

**一次只问一个问题**（opencode 用 `question` 工具，Claude Code 用 `AskUserQuestion`，没有就普通提问；
每等用户答完再问下一个，**不得把多个问题合并在同一个 question 里**）：
1. 第一个问题只问输出语言：选项 中文 / 日本語 / English（用户也可自由输入）。选定后整轮都用它，
   用户中途换语言就跟着换、不再问。
2. 之后的每一步（认领哪个 agent、研究什么主题等）都单独各问一问，按 skill `first-run` 的顺序推进。

## 项目概览

`当前目录` 是以**主题（topic）**为组织单元的研究工作区：围绕一个主题做数据获取、清洗、分析与可视化，把脚本、数据、图表、报告与经验统一归档；目标是让每个主题的**分析过程与结论可复现、可追溯**。

## 核心原则

**按主题归档。** 同一主题的脚本、图片、数据、笔记必须放进以该主题命名的目录，不得散落仓库根或跨主题混放。

## 身份与多 agent（会话启动 / 上下文压缩后第一步）

- 先跑 `python3 multiagents/agentctl.py me`：命中当前会话即自动登记并打印身份卡（含可复述的「我是 `X`」）。
- 未识别时脚本打印名册与三个选项并返回退出码 3（名册某项 / 新增 `new <角色>` / 暂不登记）；
  此时必须让用户从名册选，**不得自行认领**。
- 临时文件一律放 `/tmp/<agent>/`；工具、任务板、记忆与档案字段细节见 skill `multiagent-workflow`；名册唯一权威是 `multiagents/`。

## 目录结构

| 目录 | 用途 | 归档规则 |
| --- | --- | --- |
| `scripts/` | 脚本 | `scripts/<主题>/<agent>/`，配 `SCRIPTS.md`；每个有作用的脚本都是资产，弃用先归档 |
| `tools/` | 第三方工具与源码 | `tools/<工具>/`，构建产物留在内部 |
| `data/` | 清洗后的数据 | `data/<主题>/` |
| `archive/` | 原始/归档数据 | `archive/<主题>/` |
| `memory/` | 记忆与规则（`.md` 是导出视图） | 见 skill `multiagent-workflow`「记忆」 |
| `multiagents/` | 名册、工作状态、源与工具 | 机器写的源收在 `state/` |
| `output/` | 产出（报告与图片） | `output/<主题>/{report,img}/` |
| `repos/` | 外部代码仓库（研究或依赖对象） | `repos/<名字>/`；clone 或 symlink 进来，默认**不入版本库**，URL + commit 记进 `memory/` |
| `src/` | 人或 AI 写的代码仓库/框架等大型代码 + 小型复用模块 | 大项目 `src/<主题>/<项目>/`，散模块按模块组织 |
| `web_doc/` | 网页/参考资料 | `web_doc/<主题>/`，一主题一独立 git（如 `web_doc/multiagents-site/` 官网） |

初始化时由引导员问清「这份代码从上游 clone 进来，还是链到你本机已有的那份」（skill `first-run` 第 2 步）；放置规则见 skill `repo-conventions` 的「外部代码仓库（`repos/`）」。

## 硬约束

- **脚本模块化**：主入口（`main.py` / `run_*.py`）≤ 200 行、单模块 ≤ 300 行；一模块一职责；禁止内联长数据。
  细节见 skill `repo-conventions`。
- **路径隐私**：禁止硬编码 `/home/`、`/Users/` 等机器路径；本地路径来自项目根 `.env`（模板 `.env.example`）。
- **保密意识**：`.env` 与任何含密钥/token/密码的文件的 **value 一律不得打印**（不进终端输出、不进日志、
  不进记忆/简报/报告）；需要展示时 key 照写、value 用 `*` 代替（如 `API_KEY=****`）。读取配置时先看
  key 名是否足够，确需验证值是否存在用「非空判断」而非回显。违者视同泄露。
  **git 提交身份同理**：公开仓库的 commit author/committer 邮箱用 GitHub noreply 地址
  （`LOCAL_GIT_*` 键，值在 `.env`），个人邮箱不得出现在提交记录里。
- **源与视图**：任务板源 `multiagents/state/todo.json`、记忆源 `multiagents/state/memory/**/*.json`；
  `TODO.md` 与 `memory/**/*.md` 是机器导出的视图，**勿手改**，读写都走 `agentctl.py`。
- **改项目通用文件走加锁接口**：各 code CLI 自带的 edit / write 是「读—改—写」，没有跨进程互斥，两个 agent
  会话同时改同一文件会丢更新（实测：12 个进程并发追加，加锁 12 行全在，不加锁只剩 4 行）。代码库本体、
  `multiagents/`、`scripts/`、`skills/`、配置、源、规则、本文件与 `README.md` 一律用
  `python3 multiagents/agentctl.py file edit|write|append <路径> …` 改（加锁 + 原子替换，留痕
  `multiagents/state/locks/edits.jsonl`）；agent 档案、任务板、记忆源由 `json` / `todo` / `memory`
  子命令写，用的是**同一把锁**。agent 自己独占的产物（自己主题下的报告 / 图 / 数据 / 笔记）可以用原生 edit。
  拿不准先 `agentctl.py file who <路径>`。

## Skill 地图（详细规程按需加载）

| skill ID | 何时加载 |
| --- | --- |
| `multiagent-workflow` | 身份与多 agent（`me`/`new`/`spawn`）、`agentctl.py` 用法、任务板、写 memory、出进展简报、改自己档案 |
| `repo-conventions` | 归档放哪、写或改脚本、碰路径与 `.env`、维护 `SCRIPTS.md`、读图前压缩 |
| `plotting-standards` | 画任何图 |
| `quant-analysis-rules` | 做数据统计、指标或下结论前 |
| `report-writing` | 写或改报告、核验口径数字、过文风门禁 |
| `rigorous-writing` | 动笔写或改写报告、README、方法说明，或要过文风体检（`style_lint.py`）时 |
| `loveplus-emu-ops` | 触摸、截图、OCR、输入模拟器，改 `loveplus_mcp.py`，挂后台任务，读模拟器截图 |
| `loveplus-nlpplus-guide` | 玩 NLP+、走流程与菜单、查或回填 UI 坐标 |
| `loveplus-siren14-re` | 解 Siren14 语音、做 3DS 静态逆向 |
| `first-run` | 第一次在本仓库跑 agent、要初始化项目时 |

中间三个是本仓库的 LovePlus 专属 skill；新主题专属 skill 按同样方式加：源放 `skills/<id>/SKILL.md`，并在上表补一行。

### skill 源与镜像

skill 源放在 CLI 中立的 `skills/<id>/SKILL.md`，一 skill 一目录。各家 code CLI 的 skill 目录不同，
用 `python3 multiagents/sync_skills.py` 镜像到 `.opencode/skills/`、`.claude/skills/`、`.agents/skills/`；
镜像目录整体是生成物（其中的 `SKILL.md` 在 frontmatter 后插一行「生成物，勿手改」注释），
`--check` 只查漂移（有漂移 exit 1）。上面 skill 地图按 ID 引用 skill，不写死任何 CLI 的目录路径。

### skill 的加载与注入

**事实**：skill 的正文**不会自动进上下文**。每个模型步只会看到一份可用 skill 列表（ID + `name` + `description`），
正文只有模型调用 `skill` 工具（或用户写 `@<skill-id>`）时才注入；注入的是**镜像**内容，所以镜像漂移等于
上下文里拿到旧规程。据此：

- **会话第一步**：跑 `python3 multiagents/agentctl.py me`。身份卡会列出本档 `skills[]`，并给出可直接照抄的
  加载清单（形如 `skill(id=multiagent-workflow)`）——**照它逐个加载，然后才动手**。这是规程：`skills[]`
  里登记的 skill 没加载就干活，等于没读过自己该守的规则。
- **按需加载，不预加载全部**：只加载跑本任务用得上的（要动模拟器才加载 `loveplus-emu-ops`）。一次把全部
  skill 塞进上下文既费 token 也稀释重点；判断依据就是上表「何时加载」。
- **本文件与 skill 的分工**：`AGENTS.md` 每次请求都进上下文，所以「必须每次遵守」的硬约束写在本文件；
  「按需查阅」的过程性细节放 skill。同一件事两处都有时，以本文件为准。
- **列表里没有该 ID 时依次查**：① `description` 是否缺失（无 description 不广告）；② 镜像是否漂移
  （`python3 multiagents/sync_skills.py --check`）；③ opencode 侧是否被 `permissions` 的 `skill` 动作 deny，
  或被 `opencode/autoinvoke: false` 从列表隐藏（隐藏后仍可显式加载）。前两条是本仓库可控项。
- **要做「每步自动注入」只有两条路**：写进本文件或配置的 `instructions`（静态、通用），或 opencode 插件钩子
  `session.hook("context")` 往 `event.system` 推文本（动态、客户端专有）；后者与「客户端无关」原则冲突，只能当可选便利层，不作为依赖。

### 默认引导员 00_haruhi

`00_haruhi`（涼宮ハルヒ，角色 `haruhi`，`display` = 框架默认引导员 / 本地 contributor）随仓库发布，其档案
`multiagents/00_haruhi.json` 是全字段实例；新用户上来先认领它（`agentctl.py me --name 00_haruhi`），
或 `new <角色>` 建自己的 agent，由它按 skill `first-run` 引导初始化。她兼任本地 contributor：经用户授意
可修改与更新框架本体（`multiagents/`、`skills/`、根规约文件），改完全套自检绿才算完。

它的开场白、人设与「目录 + 能力」自我介绍都写在 skill `first-run` 里（首装期间用户**任何一句输入**都先触发
引导；开场第一件事用选项框问用户语言，选定后用 `agentctl.py lang <code>` 落下来，开场白按语言给三份，
其中角色的标志句只做直译）。不想用这个人设，就改它档案的 `focus` / `handoff` 与 skill 的那两节。

## 收尾清单

- [ ] 产出文件已按主题归档（报告与图片在 `output/<主题>/{report,img}/`，数据在 `data/<主题>/`）
- [ ] 脚本符合模块化规则（≤200 / ≤300）；`scripts/<项目>/SCRIPTS.md` 已同步；脚本落对 `scripts/<主题>/<agent>/`，弃用脚本先进 `archive/` 再移出目录
- [ ] 代码中无硬编码机器路径（路径来自 `.env`，真实 `.env` 未进版本库）
- [ ] 报告文风已过门禁（skill `rigorous-writing` 的 `style_lint.py` 返回 0）且数字核验全 OK；关键派生量已确认口径来源
- [ ] 方法/规则已记录到 `memory/`；操作前已读过 `memory/<主题>/` 说明文件
- [ ] 工作日志已按 `memory/<项目>/diary/<日期>_<agent>.md` 写入
- [ ] 记忆改动收尾跑过 `memory verify --all`；新的通用约定已回补对应 skill 或规约文件
