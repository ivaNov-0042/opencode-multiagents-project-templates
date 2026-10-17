---
name: 仓库目录、脚本与路径规约
description: 本仓库的目录结构与归档规则、scripts/<主题>/SCRIPTS.md 规矩、脚本模块化硬约束、路径与隐私禁令、通用读图压缩。凡是要在本仓库新建脚本/目录、归档产出、或改既有脚本时加载；多 agent 流程见 multiagent-workflow，绘图见 plotting-standards。
---

<!-- 生成物，勿手改：源 `skills/repo-conventions/SKILL.md`；改完跑 `python3 multiagents/sync_skills.py` -->

# 目录、脚本与路径规约

## 目录结构与归档

| 目录 | 用途 |
| --- | --- |
| `scripts/<主题>/` | 脚本，内部用 `SCRIPTS.md` 索引 |
| `data/<主题>/` | 清洗后的中间数据 |
| `archive/<主题>/` | 原始/归档数据 |
| `output/<主题>/{report,img}/` | 报告与图片（不再新增 `report/`、`pics/` 下的主题目录） |
| `memory/<项目>/` | 常青主题文档与日记视图（源见 multiagent-workflow） |
| `tools/<工具>/` | 第三方工具与源码（预编译二进制或源码），构建产物留在各工具目录内部 |
| `repos/<名字>/` | 外部代码仓库（研究或依赖对象）：clone 或 symlink 进来，默认不入版本库 |

- 按**主题**归档：同一主题的脚本、图片、数据、笔记统一放入以该主题命名的目录，不得散落在仓库根或跨主题混放。
- 主题名用小写蛇形（如 `etf_premium`）或清晰短标识（如 `cci`），全仓库一致。

## 外部代码仓库（`repos/`）

研究对象或依赖对象是一份**别人的代码仓库**时，不要塞进 `src/`：`src/` 放自己写的模块级代码，混进上游代码后
分不清哪些是自己写的，许可与跟上游同步都变麻烦。三类东西分开放：

| 你要做的事 | 放哪 | 形态 |
| --- | --- | --- |
| 读 / 逆向 / 参考某个代码库 | `repos/<名字>/` | clone 或 symlink |
| 跑 / 构建 / 打补丁的第三方工具 | `tools/<名字>/` | 源码与构建产物都在里面 |
| 人或 AI 写的代码仓库 / 框架等**大型代码** | `src/<主题>/<项目>/` | 完整可跑的库或框架（多个模块、有自己的结构），一项目一目录，不论人写还是 AI 写 |
| 小型可复用模块（散放） | `src/` | 会被 `import` 的库代码 |

- **先问用户，别猜**：代码在上游 URL，还是本机已有一份克隆？要哪种形态？初始化时问清（skill `first-run` 第 2 步）。
- **clone 还是 symlink**：默认 `git clone <url> repos/<名字>`（自包含、能 `git log` 与切 commit、不怕上游变动）；
  磁盘紧张，或你本机已有一份克隆要复用（例如打过 patch 还要在本机跑），就用 `ln -s <你的克隆> repos/<名字>`，
  并把真实路径写进 `.env`（如 `<项目>_REPO_<名字>`）。
- **`repos/` 默认不入版本库**（`.gitignore` 已忽略）：symlink 提交后别人 clone 不到，clone 进来的上游代码也不该
  混进自己的历史。
- **复现信息写进记忆**：`memory/<项目>/` 里记 URL + commit（或 tag / branch）+ 是否打过 patch；别人照这一行
  就能拿到同一份代码。这是 `repos/` 不入版本库的补偿。
- **别手改上游代码**：要改就留 patch（`git diff > patches/<名字>.patch`），或把改动写进自己的 `scripts/`；
  patch 与记忆档一起归档，便于下次上游更新时重放。

## `SCRIPTS.md` 规矩

- **落点规约**：一个主题下多个 agent 并行写脚本时，落 `scripts/<主题>/<agent>/`（agent 名即档案名）；
  只有单 agent 小主题才直接放 `scripts/<主题>/`。跨主题的复用模块与人或 AI 写的代码仓库 / 框架进
  `src/<主题>/<项目>/`，不塞进任何 agent 目录。**每一个有作用的脚本都是重要资产**：不管多短，落盘就进
  `SCRIPTS.md` 索引、写清用途与用法；要丢弃先归档到 `archive/`（脚本即研究过程的一部分，可追溯、可复现），
  不得直接删除。
- 每个 `scripts/<项目>/` 目录**必须有** `SCRIPTS.md`：脚本用途 / 用法 / 坐标体系 / 常见坑速查表；按 agent 分目录时，
  根级 `SCRIPTS.md` 索引到各 `scripts/<项目>/<agent>/`。
- 新写脚本或用法变更时**同步更新**该文件。
- 通用抽象规则（如"低分辨率图不必压缩"）写进 skill 源或 `AGENTS.md` 硬约束；具体项目操作细节进 `SCRIPTS.md` 或 `memory/`。

## 脚本编写硬约束（模块化与上下文控制）

> 动机：Agent 读写大文件会快速消耗上下文。单文件过大 → 频繁整读/整写 → 上下文撑爆。故脚本必须模块化，主入口保持精简。

- **主入口 ≤ 200 行**：`main.py` / `run_*.py` 只做**编排**（参数解析、模块调用、流程串联），禁止堆砌业务逻辑。
- **单模块 ≤ 300 行**：超过必须继续拆分。宁可文件多，不可文件肥。
- **一个模块一个职责**：数据获取（`fetch.py`）、清洗（`clean.py`）、指标计算（`indicators.py`）、绘图（`plot.py`）、配置常量（`config.py`）、通用工具（`utils.py`）各自独立成文件。结构模板：`scripts/<主题>/{main,config,fetch,clean,analysis,plot}.py`。
- **禁止内联长数据**：硬编码的长列表、大段常量、SQL 等放进 `config.py` 或独立数据文件（`data/`、JSON/CSV），不要写死在主流程里。
- **修改既有脚本时**：优先**小步 edit**，禁止为改一处整文件重写；新增功能优先放独立模块再由入口 import。
- **读文件**：先用 `grep`/`glob` 定位行号，**带 offset/limit 局部读取**，禁止盲目整读大文件。
- **豁免**：`multiagents/agentctl.py` **有意豁免**上述长度约束——它是「几乎不用改动的工具」，读者是人和 agent 各读一次，拆多文件只增加改动时的跳跃成本。改它之前先读 `multiagents/README.md`。

## 输出文本走资源字符串（多语言）

框架代码里**用户可见的文本**不硬编码中文，写 `i18n.t("中文原文", **占位)`（`multiagents/i18n.py`）：译文在 `multiagents/locales/<lang>.json`，**键 = 中文原文**；查不到译文回落中文。

- 改了源码里的中文原文等于换 msgid，改完跑 `python3 multiagents/i18n_extract.py` 更新目录，`--check` 应回到「未译 0｜占位符不一致 0」。
- **docstring 与注释保持中文**（读者是维护者），不进目录。
- 语言优先级：`--lang` → `AGENTCTL_LANG` → `multiagents/state/settings.json` → `zh`；引导员在初次安装时把用户选的语言用 `agentctl.py lang <code>` 落下来（见 skill `first-run`）。

## 改「项目通用文件」走加锁接口

各 code CLI 自带的 edit / write 是「读—改—写」，**没有跨进程互斥**，两个 agent 同时改同一文件会丢更新
（本机实测：12 个进程并发追加，走锁 12 行全保住，不加锁只剩 4 行）。所以：

- **项目通用文件**——代码库本体、`multiagents/`、`scripts/`、`skills/`、配置、源、规则、`README.md`——
  一律用 `python3 multiagents/agentctl.py file edit|write|append <路径> …` 改（统一入口，也是这套约定的
  唯一 py 工具）：它把读—改—写放进同一把 `flock` 并原子替换，改完往 `multiagents/state/locks/edits.jsonl`
  留一行痕（谁、何时、哪个文件、±几行）。
- **自己独占的产物**（自己主题下的报告 / 图 / 数据 / 笔记）可以用 CLI 原生 edit，省 token。
- 拿不准就 `agentctl.py file who <路径>`：列出谁在 `claims.files` 里声明了它，并给改法建议。
- 等锁超时（默认 30s）的报错会给出当前占用者；确认要排队就用 `--wait`。锁随进程退出自动释放，
  不存在残留锁。
- 源 JSON（任务板、记忆、agent 档案）走 `agentctl.py` 的 `todo` / `memory` / `json` 子命令：它们的写入与
  `file` 是**同一把锁**，所以两边不会互相盖；别手改 JSON。

## 路径与隐私（禁止硬编码机器目录）

> 动机：写死 `/home/<user>/...` 会泄露机器用户名与目录结构，换机器/换仓库名即失效。

- **禁止硬编码机器路径**：任何脚本/配置不得出现 `/home/`、`/Users/`、`C:\Users\` 等含用户名的绝对路径，也不得写死本仓库在磁盘上的具体位置。
- **本地路径统一来自 `.env`**：项目根 `.env`（已被 `.gitignore` 忽略，禁止提交）提供各主题的机器路径键，命名约定 `<主题>_<用途>` 全大写（如 `<主题>_DATA_ROOT`）；`.env.example` 是可提交的占位模板，真实 `.env` 由使用者按本机填入。
- **Python 脚本**：各主题或各模块共用一个路径助手（如 `scripts/<主题>/common_paths.py`：负责读 `.env` 并导出路径常量），业务脚本 `from common_paths import *` 即可；不要在每个脚本里散落 `os.environ.get`，更不要写死。
- **Shell 脚本**：开头 `set -a; . "$(dirname "$0")/../../.env" 2>/dev/null; set +a`（或 source 项目根 `.env`），再引用 `${<主题>_DATA_ROOT}` 等变量。
- **配置/JSON**（CLI 配置、MCP 定义等）：命令路径优先用相对路径，或经 `.env` 派生的包装脚本（如 `scripts/<主题>/run_<工具>.sh`），不要把机器绝对路径写进要提交的配置。
- **兜底**：路径助手在 `.env` 缺失时应给出可读的报错或明确的默认值（如「脚本所在目录向上 N 级 = 项目根」），保证换机器仍能运行；不要静默使用空字符串。

## 通用读图规则（先压缩再 read）

- 任何图片在 `read` 之前先用 Python 压到 `/tmp/img_preview/`，只读压缩副本；压缩副本不得污染 `data/`、`output/` 或主题目录。
- 压缩目标：最长边 **≤ 618px**、JPEG 质量 **80**。仅当确需读图内文字/核对数值时，才对**原图的局部区域**裁剪后放大单独读。
- **只对最长边 > 618px 的大图压缩**；低分辨率截图（最长边 ≤ 618px）本身很小，直接 `read` 原图即可，不必压缩，文字更清晰。
- 压缩一次完成：

  ```bash
  python3 - <<'EOF'
  from PIL import Image
  import os
  os.makedirs('/tmp/img_preview', exist_ok=True)
  for src in ['图片路径1', '图片路径2']:
      dst = '/tmp/img_preview/' + os.path.basename(src).rsplit('.', 1)[0] + '.jpg'
      im = Image.open(src); im.thumbnail((618, 618))
      im.convert('RGB').save(dst, 'JPEG', quality=80)
      print(dst, os.path.getsize(dst) // 1024, 'KB')
  EOF
  ```
- 需确认原图尺寸/大小时，先 `ls -l` 或 `python3 -c "from PIL import Image; print(Image.open(p).size)"`，不要直接 read 猜测。

## 收尾（本 skill 相关）

- [ ] 产出文件已按主题归档（报告与图片在 `output/<主题>/{report,img}/`，数据在 `data/<主题>/`）
- [ ] 脚本符合模块化规则（主入口 ≤200 行、单模块 ≤300 行）；`scripts/<project>/SCRIPTS.md` 已同步；脚本落对 `scripts/<主题>/<agent>/`（每有作用脚本都进索引），弃用脚本先进 `archive/` 再移出目录
- [ ] 代码中无硬编码机器路径（路径来自 `.env` / `common_paths`，真实 `.env` 未进版本库）
- [ ] 读取图片前已压到 `/tmp/img_preview/`（>618px 的大图），未直接 read 原图
- [ ] 如有新的通用约定或能改进流程的规则，已回补对应规约文件
