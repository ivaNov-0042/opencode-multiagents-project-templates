#!/usr/bin/env python3
"""多 agent 并行工作流 CLI —— **统一入口**（客户端无关，纯标准库）。

协议、名册与交接规则见 `multiagents/README.md`；本文件是这一套约定**唯一的 py 工具**：
agent 档案（`multiagents/<name>.json`）、项目任务板（`TODO.md`）、记忆索引
（`memory/MEMORY.md`）的读写全部走这里，不另开脚本。

关于长度：本文件**有意**不遵守 AGENTS.md「硬约束」里的脚本模块化（主入口 ≤ 200 行 / 单模块 ≤ 300 行）。
它是「几乎不用改动的工具」——协议稳定后只在新增字段时动几次，读者是人和 agent 一次性
看懂；拆成多文件反而让「改一处要跳几个文件」。**动本文件前请先读 README.md。**

用法（`--name` 缺省时用「当前会话匹配到的档案」，匹配不到即报错，不猜）：

    agentctl.py roster [--markdown]                     打印名册与匹配建议（判定身份先跑它）
    agentctl.py register --role R [--name N] [--display D] [--focus F] [--client C]
    agentctl.py attach --name X [--title T] [--status S] [--client C]
    agentctl.py todo list | add "<描述>" --topic N | claim|done|release <id> | note <id> "<文本>"
    agentctl.py todo topic add "<名称>" | export --write | verify
    agentctl.py memory list [--sections] | show <档> [--section <编号|标题>]
    agentctl.py memory new <档> --title T | import <md 路径> [--owner X]
    agentctl.py memory append <档> [--section "<标题>"] [--text "短文" | --file <文件>]
                              # 输入按 Markdown 解析：含 `## 标题` 时以文内标题为准（可一次多节）
    agentctl.py memory set <档> --section <编号|标题> [--text/--file] | --title "<新标题>"
    agentctl.py memory export [<档>] --write | verify [--all]
    agentctl.py memory-index [--write]

    # —— 所有 agent json 操作都在这一个子命令下 ——
    agentctl.py json get    [<点路径>]                    整档或某字段（如 claims.tmp）
    agentctl.py json set    <点路径> <值>                 值按 JSON 解析，失败当字符串
    agentctl.py json add    <列表路径> <值> [--key 字段]    追加；给 --key 则按该字段 upsert
    agentctl.py json remove <列表路径> [<值> | --index N | --where 字段=值]
    agentctl.py json history "<事件>"                     追加 history（自动带时间戳）并刷新 updated
    agentctl.py json touch                                只刷新 updated / sessions[].last_seen
    agentctl.py json memory <memory/…md> [--role maintainer|contributor]   登记记忆归属
    agentctl.py json job  "<名称>" [--pid N] [--log 路径] [--note 说明]     登记长任务
    agentctl.py json handoff "<给谁：什么>"                 写交接（不带参数则读）
    agentctl.py json artifact <路径>                       追加产物路径（去重）

    # —— 改「项目通用文件」走这里（CLI 原生 edit 没有跨进程互斥，两个 agent 同改一个文件会丢更新）——
    agentctl.py file edit   <路径> --old "旧" --new "新" [--all] [--dry-run] [--diff]
    agentctl.py file edit   <路径> --old-file 旧.txt --new-file 新.txt     # 长文本走文件
    agentctl.py file write  <路径> --content-file -                        # 整文件替换
    agentctl.py file append <路径> --content "…"                           # 追加
    agentctl.py file read   <路径> [--offset N --limit N]                   # 共享锁读
    agentctl.py file locks                                                 # 谁占着锁 + 最近留痕
    agentctl.py file who    <路径>                                          # 谁 claims 了这个路径
      通用：--timeout 秒（默认 30，0=立刻失败）/ --wait（不限时等）/ --allow-outside
      锁在 multiagents/state/locks/（不进版本库），进程退出即释放；agent 自己的产物可用原生 edit。

身份规则：`roster` 只给**建议**，身份由用户从名册里选，脚本不替用户认领；
要改别人的档案必须显式 `--name`，脚本会打印提醒。
"""
from __future__ import annotations

import argparse
import difflib
import fcntl
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import i18n                 # 资源字符串（多语言输出；源语言 zh，译文在 multiagents/locales/）

ROOT = Path(__file__).resolve().parents[1]      # 本文件位于 <repo>/multiagents/ 下
MULTIAGENTS = ROOT / "multiagents"
TODO_FILE = ROOT / "TODO.md"
MEMORY_DIR = ROOT / "memory"
CLIENTS_FILE = Path(__file__).resolve().parent / "clients.json"

BAR = i18n.t("｜")                 # 任务板字段分隔符（全角竖线）
TS_MIN = "%Y-%m-%d %H:%M"

STATE_DIR = MULTIAGENTS / "state"       # 机器写的源（JSON）；人类可读的 .md 一律是它导出的视图
TODO_JSON = STATE_DIR / "todo.json"
TODO_FOOTER = STATE_DIR / "todo.footer.md"
SETTINGS_JSON = STATE_DIR / "settings.json"     # 框架自身设置（输出语言等）
TODO_MD = ROOT / "TODO.md"
REPORT_DIR = ROOT / "output" / "quick-report"    # 进展简报（report 子命令；<日期时间>_<agent>.md，正文由 agent 给）


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_min() -> str:
    return datetime.now().strftime(TS_MIN)


# ------------------------------------------------- 文件加锁与原子写（file 子命令）
#
# 2026-10-17（用户要求；原 `editfile.py` + `filelock.py` 合并进本文件）：
# 各 code CLI 自带的 edit / write 是「读—改—写」，**没有跨进程互斥**——两个 agent 会话同时改同一文件，
# 后写的会盖掉先写的（实测：12 个进程并发追加，加锁 12 行全在，不加锁只剩 4 行）。所以凡是**项目通用文件**
# （代码库本体、脚本、配置、源、规则、skill、README）一律走 `agentctl.py file …`；agent 自己的产物
# （自己主题下的报告 / 图 / 数据 / 笔记）可以用 CLI 原生 edit。
#
# 同一把锁也保护**本文件的全部写入**：agent 档案、任务板、记忆源与手改的文件都用同一套（锁键 = 仓库内
# 相对路径），不存在「两条锁保护同一文件」的空档。改成「先写临时文件再 rename」还有个副作用好处：读方
# 永远看不到写了一半的内容。
#
# 锁取在 `multiagents/state/locks/<sha1(锁键)[:12]>_<文件名>.lock` 上而不是「建文件当锁」：进程退出
# （含被 kill）内核自动释放，**不存在残留锁**；锁文件里留一行占用者信息供排障。

LOCKS_DIR = STATE_DIR / "locks"
EDIT_LOG = LOCKS_DIR / "edits.jsonl"


class LockTimeout(Exception):
    """等锁超时（`file` 子命令会把它翻成 exit 1 与一行提示）。"""


def rel_key(target) -> str:
    """锁键与留痕用的路径：仓库内给相对路径，仓库外（--allow-outside）给绝对路径。"""
    t = Path(target)
    if not t.is_absolute():
        t = ROOT / t
    t = t.resolve()
    try:
        return str(t.relative_to(ROOT))
    except ValueError:
        return str(t)


def lock_file_of(target) -> Path:
    key = rel_key(target)
    return LOCKS_DIR / f"{hashlib.sha1(key.encode()).hexdigest()[:12]}_{Path(target).name[:40]}.lock"


def held_by(target) -> str:
    """当前占用者那一行；没被占则空串（锁文件里的旧内容只当历史看）。"""
    lp = lock_file_of(target)
    if not lp.exists():
        return ""
    try:
        with open(lp, encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return ""
    except (BlockingIOError, OSError):
        txt = lp.read_text(encoding="utf-8").strip().splitlines()
        return txt[-1] if txt else i18n.t("（占用者信息缺失）")


_LABEL = None


def agent_label() -> str:
    """写入留痕用的 agent 名：按当前会话识别（一个进程只算一次），认不出写 unknown。"""
    global _LABEL
    if _LABEL is None:
        _LABEL = (current_agent() or {}).get("name") or os.environ.get("MULTIAGENTS_AGENT") or "unknown"
    return _LABEL


@contextmanager
def locked(target, timeout: float = 30.0, wait: bool = False, shared: bool = False, agent: str = ""):
    """对 target 取 flock（shared=True 取共享锁）；超时抛 LockTimeout。"""
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(lock_file_of(target), "a+", encoding="utf-8")
    deadline = None if wait else time.monotonic() + max(0.0, timeout)
    try:
        while True:
            try:
                fcntl.flock(fh, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                fh.seek(0)
                lines = fh.read().strip().splitlines()
                if deadline is not None and time.monotonic() >= deadline:
                    raise LockTimeout(
                        i18n.t(
                            "等锁超时（{timeout:g}s）：{p1}\n"
                            "  当前占用：{p2}\n"
                            "  等它做完再来（--wait 可不限时等），或先跟对方沟通",
                            timeout=timeout,
                            p1=rel_key(target),
                            p2=lines[-1] if lines else '（不明）',))
                time.sleep(0.05)
        if not shared:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{agent or agent_label()}|pid={os.getpid()}|{now_iso()}|{rel_key(target)}\n")
            fh.flush()
        yield fh
    finally:
        fh.close()          # close 即释放锁（异常路径也走这里）


def atomic_write(target, text: str) -> None:
    """同目录临时文件 + os.replace 原子替换（同文件系统内 rename 是原子的）。"""
    t = Path(target)
    t.parent.mkdir(parents=True, exist_ok=True)
    tmp = t.with_name(f"{t.name}.agentctl{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, t)


def log_edit(op: str, target, before: str, after: str) -> None:
    """每次改成后往 state/locks/edits.jsonl 追一行（谁、何时、哪个文件、行数）。"""
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"t": now_iso(), "agent": agent_label(), "op": op, "path": rel_key(target),
           "lines": [before.count("\n"), after.count("\n")]}
    with open(EDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def claimants(target, skip: str | None = None) -> list:
    """哪些 agent 的 claims.files 覆盖了这个路径（支持 glob 与目录前缀）。"""
    key = rel_key(target)
    out = set()
    for a in load_agents():
        if a.get("name") == skip:
            continue
        for f in (a.get("claims") or {}).get("files") or []:
            f = str(f).rstrip("/")
            if key == f or key.startswith(f + "/") or fnmatch.fnmatch(key, f) or fnmatch.fnmatch(key, f + "/**"):
                out.add(a.get("name", "?"))
    return sorted(out)


def resolve_repo_path(path: str, allow_outside: bool = False) -> Path:
    """仓库内路径解析；默认拒绝仓库外（防误伤）。"""
    ap = (Path(path) if Path(path).is_absolute() else ROOT / path).resolve()
    if not allow_outside and ap != ROOT and ROOT not in ap.parents:
        raise SystemExit(i18n.t("拒绝对仓库外的路径操作：{ap}（确需则加 --allow-outside）", ap=ap))
    return ap


# ---------------------------------------------------------------- 客户端探测

def detect_client() -> dict:
    """按 clients.json 的顺序探测当前客户端 → {client, session_id, evidence}。"""
    cfg = {"detect_order": [], "clients": {}}
    if CLIENTS_FILE.exists():
        try:
            cfg = json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    for name in cfg.get("detect_order", []):
        spec = cfg.get("clients", {}).get(name, {})
        if not spec.get("enabled", True):
            continue
        envspec = spec.get("env", {})
        if not envspec or not all(os.environ.get(k) == v for k, v in envspec.items()):
            continue
        sid = next((os.environ[k] for k in spec.get("session_env", []) if os.environ.get(k)), None)
        ev = ",".join(f"{k}={v}" for k, v in envspec.items())
        return {"client": name, "session_id": sid, "evidence": f"env:{ev}"}
    return {"client": "unknown", "session_id": None, "evidence": i18n.t("无匹配的环境标记")}


# ---------------------------------------------------------------- agent 档案

def load_agents() -> list:
    """读 multiagents/*.json，按 name 排序（忽略非档案 json，如 clients.json）。"""
    out = []
    if not MULTIAGENTS.exists():
        return out
    for p in sorted(MULTIAGENTS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict) or "name" not in d:
            continue
        d["_path"] = str(p)
        out.append(d)
    out.sort(key=lambda a: a.get("name", ""))
    return out


def find_agent(name: str):
    return next((a for a in load_agents() if a.get("name") == name), None)


def save_agent(agent: dict) -> Path:
    """原子写回档案（临时文件 + replace）；仅用于整体重写，字段级改动走 mutate_agent。"""
    agent = {k: v for k, v in agent.items() if not k.startswith("_")}
    p = MULTIAGENTS / f"{agent['name']}.json"
    atomic_write(p, json.dumps(agent, ensure_ascii=False, indent=2) + "\n")
    return p


def mutate_agent(name: str, fn):
    """对某个档案加锁做原子读-改-写；fn(agent) -> (ok, msg)。防两处同时改同一档丢更新。"""
    p = MULTIAGENTS / f"{name}.json"
    if not p.exists():
        return False, i18n.t("没有档案：{p}", p=p)
    with locked(p):
        agent = json.loads(p.read_text(encoding="utf-8") or "{}")
        ok, msg = fn(agent)
        if not ok:
            return False, msg
        agent.pop("_path", None)
        atomic_write(p, json.dumps(agent, ensure_ascii=False, indent=2) + "\n")
        return True, msg


def next_index() -> str:
    nums = [int(m.group(1)) for a in load_agents() if (m := re.match(r"^(\d+)_", a.get("name", "")))]
    return f"{max(nums) + 1:02d}" if nums else "01"


def _has_session(a: dict, sid) -> bool:
    return bool(sid) and any(s.get("session_id") == sid for s in a.get("sessions", []))


def candidates(agents: list, client: dict) -> list:
    """排序建议：session_id 完全匹配优先，其次 updated 较新。仅作建议，不替用户决定。"""
    sid = client.get("session_id")
    key = lambda a: (1 if _has_session(a, sid) else 0, a.get("updated", ""))
    return [{"agent": a, "hit": _has_session(a, sid)} for a in sorted(agents, key=key, reverse=True)]


def current_agent():
    """按当前会话的 session_id 在名册里找档；找不到返回 None（绝不猜）。"""
    sid = detect_client().get("session_id")
    if not sid:
        return None
    return next((a for a in load_agents() if _has_session(a, sid)), None)


def resolve_agent(name=None, write=False):
    """返回 (agent, msg)。agent 为 None 时 msg 是错误；否则 msg 非空即为提醒。

    2026-10-17（用户要求）：那句「确认无误再落盘」只在写路径给。`json get` / `task list`
    这类只读路径不打——读操作不落盘，用那句话提醒会让人以为自己在改别人的档。
    """
    if name:
        a = find_agent(name)
        if a is None:
            return None, i18n.t("名册里没有 {name}；请先 register 新建（不得凭空认领）", name=name)
        cur = current_agent()
        if cur is None or cur.get("name") != name:
            return a, (i18n.t("{name} 不是当前会话匹配到的档案；确认无误再落盘", name=name) if write else "")
        return a, ""
    a = current_agent()
    if a is None:
        return None, i18n.t("无法从当前会话判定 agent；请用 --name 指定（不得自行认领）")
    return a, ""


# ------------------------------------------------- agent 档案的字段读写（json 操作）

def parse_value(text: str):
    """值解析：`{…}`/`[…]`/带引号或 true/false/null/纯整数 按 JSON，其余按字符串。"""
    t = text.strip()
    if t[:1] in '{["' or t in ("true", "false", "null"):
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    return text


def _walk(obj, path: str, create: bool = False):
    """走到 path 的父容器，返回 (parent, leaf)；parent 可能是 dict 或 list。"""
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif create:
            cur = cur.setdefault(part, {})
        else:
            cur = cur[part]
    return cur, parts[-1]


def get_field(agent: dict, path: str):
    cur = agent
    for part in path.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur.get(part)
        if cur is None:
            return None
    return cur


def set_field(agent: dict, path: str, value) -> None:
    parent, leaf = _walk(agent, path, create=True)
    if isinstance(parent, list):
        parent[int(leaf)] = value
    else:
        parent[leaf] = value


def add_item(agent: dict, path: str, value, key: str | None = None) -> str:
    parent, leaf = _walk(agent, path, create=True)
    lst = parent.setdefault(leaf, []) if isinstance(parent, dict) else parent
    if not isinstance(lst, list):
        raise ValueError(i18n.t("{path} 不是列表", path=path))
    if key and isinstance(value, dict):
        for i, it in enumerate(lst):
            if isinstance(it, dict) and it.get(key) == value.get(key):
                lst[i] = value
                return i18n.t("{path}[{key}={p2}] 已覆盖", path=path, key=key, p2=value[key])
    if value in lst:
        return i18n.t("{path} 里已有该项（跳过）", path=path)
    lst.append(value)
    return i18n.t("{path} 追加成功（现 {p1} 项）", path=path, p1=len(lst))


def remove_item(agent: dict, path: str, value=None, index=None, where=None) -> str:
    parent, leaf = _walk(agent, path)
    lst = parent.get(leaf) if isinstance(parent, dict) else parent
    if not isinstance(lst, list):
        raise ValueError(i18n.t("{path} 不是列表", path=path))
    if index is not None:
        gone = lst.pop(index)
    elif where:
        k, _, v = where.partition("=")
        idx = next((i for i, it in enumerate(lst)
                    if isinstance(it, dict) and str(it.get(k)) == v), None)
        if idx is None:
            return i18n.t("{path} 里没有 {where}", path=path, where=where)
        gone = lst.pop(idx)
    elif value is not None and value in lst:
        lst.remove(value)
        gone = value
    else:
        return i18n.t("{path} 里没找到要移除的项", path=path)
    return i18n.t("已移除 {p0}", p0=json.dumps(gone, ensure_ascii=False))


def touch_agent(agent: dict, sid=None) -> None:
    agent["updated"] = now_iso()
    for s in agent.get("sessions", []):
        if sid and s.get("session_id") == sid:
            s["last_seen"] = now_iso()


def add_history(agent: dict, event: str) -> None:
    agent.setdefault("history", []).append({"t": now_iso(), "e": event})


def upsert_memory(agent: dict, path: str, role: str = "contributor") -> str:
    lst = agent.setdefault("memory", [])
    for m in lst:
        if m.get("path") == path:
            m["role"] = role
            return i18n.t("记忆归属已更新：{path}（{role}）", path=path, role=role)
    lst.append({"path": path, "role": role})
    return i18n.t("记忆归属已登记：{path}（{role}）", path=path, role=role)


def upsert_skills(agent: dict, skills: list) -> str:
    """登记该 agent 该用的 skill ID（本项目名册用；与 opencode 的 skill 权限不是一回事——
    后者是 agents.<id>.permissions 里 action=skill 的规则）。"""
    lst = agent.setdefault("skills", [])
    added = [s for s in skills if s and s not in lst]
    lst.extend(added)
    return f"skills ← {'、'.join(added)}" if added else i18n.t("skills 无变化")


def upsert_job(agent: dict, name: str, pid=None, log=None, note=None) -> str:
    lst = agent.setdefault("jobs", [])
    job = next((j for j in lst if j.get("name") == name), None)
    if job is None:
        job = {"name": name}
        lst.append(job)
    for k, v in (("pid", pid), ("log", log), ("note", note)):
        if v is not None:
            job[k] = v
    return i18n.t("长任务已登记：{name}（现 {p1} 项）", name=name, p1=len(lst))


# ------------------------------------------- 项目任务板（源 JSON，导出 MD）
#
# 2026-10-17 起：任务板的**源是 `multiagents/state/todo.json`**；根 `TODO.md` 是它渲染出来的
# 人类可读视图（生成物，勿手改）。条目下挂的备注进 JSON 的 `notes[]`；板尾那类手写散文放
# `todo.footer.md`，导出时原样附在末尾。为什么这么改：Markdown 当源时，"追加一条任务"
# 只能写文件末尾（新条目会掉进归档节），且人工改一行就可能让解析器整条跳过。

BOARD_HEAD = i18n.t(
                 "# 项目任务板（TODO）\n"
                 "\n"
                 "> **生成物，勿手改**：源是 `multiagents/state/todo.json`，本文件由\n"
                 "> `python3 multiagents/agentctl.py todo export --write` 重新生成；改动请走脚本（对 JSON 加 "
                 "`flock`）。\n"
                 "> 每条任务可被任一 agent 认领，认领是唯一的协调动作。\n"
                 ">\n"
                 "> ```bash\n"
                 "> python3 multiagents/agentctl.py todo list\n"
                 "> python3 multiagents/agentctl.py todo claim <主题号.子号> --owner <agent>\n"
                 "> python3 multiagents/agentctl.py todo done  1.3\n"
                 "> python3 multiagents/agentctl.py todo add \"新任务\" --topic 2\n"
                 "> python3 multiagents/agentctl.py todo note 1.1 \"补充说明\"\n"
                 "> python3 multiagents/agentctl.py todo export --write      # 重新生成本文件\n"
                 "> python3 multiagents/agentctl.py todo verify             # 检查本文件与源是否漂移\n"
                 "> ```\n"
                 ">\n"
                 "> 格式：`- [ ] **主题号.子号** 描述 ｜ 认领: <agent|-> ｜ 状态: "
                 "<todo|doing|blocked|paused|done> ｜ 更新: <时间>`；\n"
                 "> 紧跟其后的**缩进子行是备注**（用 `todo note` 维护）。协议见 `multiagents/README.md`。\n",)


def load_board() -> dict:
    if not TODO_JSON.exists():
        return {"schema": 1, "updated": "", "topics": [], "items": []}
    return json.loads(TODO_JSON.read_text(encoding="utf-8"))


def save_board(board: dict) -> None:
    board["updated"] = now_iso()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(TODO_JSON, json.dumps(board, ensure_ascii=False, indent=2) + "\n")


def mutate_board(fn):
    """对 todo.json 加锁做原子读-改-写；fn(board) -> (ok, msg)。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not TODO_JSON.exists():
        save_board({"schema": 1, "updated": "", "topics": [], "items": []})
    with locked(TODO_JSON):
        board = json.loads(TODO_JSON.read_text(encoding="utf-8") or "{}")
        ok, msg = fn(board)
        if not ok:
            return False, msg
        save_board(board)
        return True, msg


def find_item(board: dict, tid):
    return next((i for i in board.get("items", []) if str(i.get("id")) == str(tid)), None)


def next_sub_id(board: dict, topic) -> str:
    subs = [int(p[1]) for i in board.get("items", [])
            if "." in str(i.get("id", "")) and (p := str(i["id"]).split("."))[0] == str(topic)
            and p[1].isdigit()]
    return f"{topic}.{max(subs) + 1 if subs else 1}"


def render_item(it: dict) -> str:
    """条目 → Markdown 一行（+ 缩进备注）。state=done 渲染成 [x]。"""
    box = "x" if it.get("state") == "done" else " "
    line = (i18n.t(
                "- [{box}] **{p1}** {p2} {BAR} 认领: {p4} {BAR} 状态: {p5}",
                box=box,
                p1=it['id'],
                p2=it.get('task', ''),
                BAR=BAR,
                p4=it.get('owner') or '-',
                p5=it.get('state', 'todo'),))
    if it.get("updated"):
        line += i18n.t(" {BAR} 更新: {p1}", BAR=BAR, p1=it['updated'])
    for n in it.get("notes", []):
        rows = str(n).splitlines() or [""]
        line += "\n  - " + rows[0] + "".join("\n    " + r for r in rows[1:])
    return line


def render_board(board: dict) -> str:
    """整板渲染：固定表头 + 主题表（源 topics）+ 各主题条目 + 手写板尾（todo.footer.md）。"""
    out = [BOARD_HEAD, "",
           i18n.t("**主题编号**（源是 `todo.json` 的 `topics`；新增用 `todo topic add \"名称\"`；不复用、不回收）："),
           "", i18n.t("| 主题号 | 主题 | 主责 agent |"), "| --- | --- | --- |"]
    for tp in board.get("topics", []):
        out.append(f"| {tp['id']} | {tp.get('name', '')} | {tp.get('owner', '-')} |")
    out += ["", "---", ""]
    for tp in board.get("topics", []):
        out += [f"## {tp['id']}. {tp.get('title') or tp.get('name', '')}", ""]
        if tp.get("prose"):                       # 章节级手写散文（如指向细粒度清单的说明）
            out += [tp["prose"], ""]
        out += [render_item(i) for i in board.get("items", []) if i.get("topic") == tp["id"]]
        out.append("")
    if TODO_FOOTER.exists():
        out += ["---", "", TODO_FOOTER.read_text(encoding="utf-8").strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def export_board(write: bool = False) -> str:
    md = render_board(load_board())
    if write:
        TODO_MD.write_text(md, encoding="utf-8")
    return md


# ------------------------------------------- 记忆正文（源 JSON，导出 MD）
#
# 2026-10-17（用户决策「全部 JSON 化」）：`memory/**` 的**正文源也是 JSON**，与任务板同一套路，
# 且所有源 json 一律收在 `multiagents/` 下：
#   multiagents/state/memory/<项目>/<档>.json   ← 源（flock 原子读-改-写；一档一文件 ⇒ 锁粒度=一档）
#   memory/<项目>/<档>.md                       ← 导出视图（首行 HTML 注释标明源；勿手改）
# 一档 = 有序的「节（section）」列表，按 `## 标题` 切分；首个 `##` 之前的正文进 `preamble`。
# 为什么按节存：写操作以节为单位（append / set），两个 agent 同时补写**同一篇**文档时各写各的节、
# 互不覆盖——旧做法（各自整文件重写 MD）在 2026-10-17 真实发生过一次互相覆盖（见 README.md）。

MEM_STATE_DIR = STATE_DIR / "memory"

MEMORY_NOTE = (i18n.t("<!-- 生成物，勿手改：源 `{json}`；改动走 `python3 multiagents/agentctl.py memory …`，本文件由 `memory export --write` 重渲染。 -->"))


def doc_id_of(text: str) -> str:
    """各种写法（doc id / memory/…md / multiagents/state/memory/…json）→ 规范 doc id。"""
    rel = str(text).strip()
    for pre in ("multiagents/state/memory/", "memory/"):
        i = rel.find(pre)
        if i >= 0 and (i == 0 or rel[i - 1] == "/"):
            rel = rel[i + len(pre):]
            break
    for ext in (".json", ".md"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
    return rel


def memory_paths(doc: str):
    """doc → (源 json 路径, 导出 md 路径)。"""
    rel = doc_id_of(doc)
    return MEM_STATE_DIR / (rel + ".json"), MEMORY_DIR / (rel + ".md")


def memory_ids() -> list:
    return sorted(p.relative_to(MEM_STATE_DIR).as_posix()[:-5]
                  for p in MEM_STATE_DIR.rglob("*.json"))


def load_memory(doc: str) -> dict:
    jp, _ = memory_paths(doc)
    if not jp.exists():
        return {"schema": 1, "title": "", "preamble": "", "sections": []}
    return json.loads(jp.read_text(encoding="utf-8"))


def mutate_memory(doc: str, fn):
    """对某档的源 json 加锁原子读-改-写；fn(doc) -> (ok, msg)。"""
    jp, _ = memory_paths(doc)
    jp.parent.mkdir(parents=True, exist_ok=True)
    if not jp.exists():
        atomic_write(jp, json.dumps({"schema": 1, "title": "", "preamble": "", "sections": []},
                                    ensure_ascii=False, indent=2) + "\n")
    with locked(jp):
        doc_obj = json.loads(jp.read_text(encoding="utf-8") or "{}")
        ok, msg = fn(doc_obj)
        if not ok:
            return False, msg
        doc_obj["updated"] = now_iso()
        atomic_write(jp, json.dumps(doc_obj, ensure_ascii=False, indent=2) + "\n")
        return True, msg


def find_section(doc_obj: dict, ref):
    """按节编号（03）或标题（大小写不敏感）找节。"""
    secs = doc_obj.get("sections", [])
    for s in secs:
        if str(s.get("id")) == str(ref) or s.get("title") == ref:
            return s
    low = str(ref).strip().lower()
    return next((s for s in secs if str(s.get("title", "")).strip().lower() == low), None)


def next_section_id(doc_obj: dict) -> str:
    ids = [int(s["id"]) for s in doc_obj.get("sections", []) if str(s.get("id", "")).isdigit()]
    return f"{max(ids) + 1:02d}" if ids else "01"


def render_memory(doc: str, doc_obj: dict) -> str:
    """源 → Markdown 视图（生成物注释 + 标题 + preamble + 各节）。"""
    jp, _ = memory_paths(doc)
    out = [MEMORY_NOTE.format(json=jp.relative_to(ROOT).as_posix()), ""]
    if doc_obj.get("title"):
        out += [f"# {doc_obj['title']}", ""]
    if str(doc_obj.get("preamble") or "").strip():
        out += [str(doc_obj["preamble"]).strip(), ""]
    for s in doc_obj.get("sections", []):
        out += [f"## {s.get('title', '')}", ""]
        if str(s.get("body") or "").strip():
            out += [str(s["body"]).strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def export_memory(doc: str, write: bool = False) -> str:
    md = render_memory(doc, load_memory(doc))
    if write:
        _, mp = memory_paths(doc)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(md, encoding="utf-8")
    return md


def parse_memory_md(text: str) -> dict:
    """手写 Markdown → doc（标题 / preamble / 各节）；``` 代码块内的 `##` 不当标题。"""
    lines = text.splitlines()
    title, start = "", 0
    for i, l in enumerate(lines):
        if l.startswith("# "):
            title, start = l[2:].strip(), i + 1
            break
        if l.strip() and not l.startswith("<!--"):
            break
    doc_obj = {"schema": 1, "title": title, "preamble": "", "sections": []}
    cur, pre, fence = None, [], False
    for l in lines[start:]:
        if l.lstrip().startswith("```"):
            fence = not fence
            (cur["body"] if cur else pre).append(l)
            continue
        m = None if fence else re.match(r"^## +(.+?)\s*$", l)
        if m:
            cur = {"title": m.group(1), "body": []}
            doc_obj["sections"].append(cur)
            continue
        (cur["body"] if cur else pre).append(l)
    doc_obj["preamble"] = "\n".join(pre).strip()
    for n, s in enumerate(doc_obj["sections"], 1):
        s["id"] = f"{n:02d}"
        s["body"] = "\n".join(s["body"]).strip()
    return doc_obj


def split_md_sections(text: str):
    """把 Markdown 文本按顶层 `## 标题` 切成 (preamble, [(标题, 正文), …])。

    代码围栏（```）内的 `## ` 不算标题；没有 `##` 时返回 (整段文字, [])。
    这样 `--file`/`--text` 可以直接传一段（甚至一整篇）Markdown：输入里的标题就是节标题。
    """
    lines, fence = text.splitlines(), False
    pre, secs, cur = [], [], None
    for l in lines:
        if l.lstrip().startswith("```"):
            fence = not fence
            (cur[1] if cur else pre).append(l)
            continue
        m = None if fence else re.match(r"^## +(.+?)\s*$", l)
        if m:
            cur = [m.group(1), []]
            secs.append(cur)
            continue
        (cur[1] if cur else pre).append(l)
    return ("\n".join(pre).strip(), [(t, "\n".join(b).strip()) for t, b in secs])


def body_text(args):
    """正文来源，仿 git commit：`-m` ↔ `--text`（短），`-F <文件>` ↔ `--file`（长，'--file -' 读 stdin）。

    返回 (文本, 错误)。长正文用**临时文本文件**最稳：heredoc 里出现反引号会被 bash 当命令替换
    执行（本项目已踩过），临时文件只经一次 read，不受 shell 解析影响。
    """
    hint = i18n.t("需要正文（仿 git commit）：--text 用于短文本，--file 用于长文本（--file - 读 stdin）。")
    src = getattr(args, "file", None)
    if src:
        if src == "-":
            text = sys.stdin.read().strip()
            return (text, "") if text else ("", i18n.t("stdin（--file -）没读到内容；{hint}", hint=hint))
        path = Path(src)
        path = path if path.is_absolute() else ROOT / path
        if not path.exists():
            return "", i18n.t("找不到正文文件：{path}", path=path)
        text = path.read_text(encoding="utf-8").strip()
        return (text, "") if text else ("", i18n.t("正文文件是空的：{path}", path=path))
    if getattr(args, "text", None):
        return args.text, ""
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text, ""
    return "", hint


def register_ownership(name: str, jp: Path, role: str = "contributor"):
    """把「某 agent 拥有某记忆档」登记进该 agent 档案的 memory[]（归属权威处）。"""
    agent, _ = resolve_agent(name, write=True)
    if agent is None:
        return False, i18n.t("名册里没有 {name}；归属未登记（可 `json memory <路径> --role {role}` 手工登记）", name=name, role=role)
    return mutate_agent(agent["name"],
                        lambda a: (True, upsert_memory(a, jp.relative_to(ROOT).as_posix(), role)))


# ------------------------------------------------------------------ 记忆索引

def memory_index_md() -> str:
    """记忆索引（视图）：由源 json + 各 agent 档案的 memory[]（权威归属）渲染。"""
    owners = {}
    for a in load_agents():
        for m in a.get("memory", []):
            owners.setdefault(m.get("path", ""), []).append(f"{a['name']}({m.get('role', '?')})")
    rows = []
    for doc_id in memory_ids():
        doc_obj = load_memory(doc_id)
        jp, mp = memory_paths(doc_id)
        kind = "diary" if "/diary/" in f"/{doc_id}" else i18n.t("主题")
        who = ", ".join(owners.get(jp.relative_to(ROOT).as_posix(), [])) or "—"
        rows.append((mp.relative_to(MEMORY_DIR).as_posix(), kind, who,
                     str(doc_obj.get("updated", ""))[:10] or "—",
                     i18n.t("{p0} 节", p0=len(doc_obj.get('sections', []))), doc_obj.get("title") or doc_id))
    return "\n".join(
        [i18n.t("# 记忆索引（memory/）"), "",
         i18n.t(
             "> **生成物**：由 `multiagents/agentctl.py memory-index --write` 重渲染。源是 "
             "`multiagents/state/memory/**/*.json`（正文）与各 agent 档案的 `memory[]`（权威归属）。",), "",
         i18n.t("| 记忆档 | 类型 | 参与 agent | 更新 | 规模 | 一句话 |"),
         "| --- | --- | --- | --- | --- | --- |"]
        + [f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows] + [""])


# ---------------------------------------------------------------------- 命令

def cmd_roster(args) -> int:
    client, agents = detect_client(), load_agents()
    if args.markdown:
        print(i18n.t("| agent | 角色 | 状态 | 更新 | 在做 | 占用资源 |"))
        print("| --- | --- | --- | --- | --- | --- |")
        for a in agents:
            res = ", ".join(a.get("claims", {}).get("resources", [])) or "—"
            print(f"| `{a['name']}` | {a.get('role', '')} | {a.get('status', '?')} | "
                  f"{a.get('updated', '')[:16]} | {a.get('focus', '') or a.get('display', '')} | {res} |")
        return 0
    head = i18n.t("client : {p0}  （{p1}）", p0=client['client'], p1=client['evidence'])
    if client["session_id"]:
        head += f"  session={client['session_id']}"
    print(head, i18n.t("名册（{p0}）:", p0=len(agents)), sep="\n")
    for a in agents:
        res = ", ".join(a.get("claims", {}).get("resources", [])) or "—"
        doing = (a.get("focus") or a.get("display", ""))[:36]
        print(i18n.t(
                  "  {p0:<16} {p1:<7} [{p2}] {doing:<36} 占用: {res}",
                  p0=a['name'],
                  p1=a.get('status', '?'),
                  p2=a.get('updated', '')[:16],
                  doing=doing,
                  res=res,))
    hit = next((c for c in candidates(agents, client) if c["hit"]), None)
    print(i18n.t("建议  : {p0}（本会话 session_id 与该档一致）", p0=hit['agent']['name']) if hit
          else i18n.t("建议  : 无 session_id 匹配"))
    print(i18n.t("        ── 仅作建议：请把名册交给用户选（选项须含「新增一个 agent」与「暂不登记」）"))
    for a in agents:
        if a.get("handoff"):
            print(i18n.t("交接  : {p0} → {p1}", p0=a['name'], p1=a['handoff']))
    return 0


def cmd_register(args) -> int:
    name = args.name or f"{next_index()}_{args.role}"
    if find_agent(name):
        print(i18n.t("已存在同名档：{name}", name=name), file=sys.stderr)
        return 2
    now = now_iso()
    agent = {
        "name": name, "display": args.display or args.role, "role": args.role,
        "client": args.client or detect_client()["client"], "status": "active", "updated": now,
        "focus": args.focus or "", "sessions": [], "board": [], "todo": [],
        "claims": {"files": [], "tmp": f"/tmp/{name}", "resources": []},
        "memory": [], "jobs": [], "artifacts": [], "skills": ["multiagent-workflow"], "handoff": "",
        "history": [{"t": now, "e": i18n.t("建档")}],
    }
    print(i18n.t("已建档: {p0}", p0=save_agent(agent)))
    return 0


def move_tmp_dir(old: str, new: str) -> str:
    """把 `/tmp/<旧名>` 连内容搬到 `/tmp/<新名>`；两边都在时不覆盖，交人工合并。"""
    o, n = Path(f"/tmp/{old}"), Path(f"/tmp/{new}")
    if not o.exists():
        n.mkdir(parents=True, exist_ok=True)
        return i18n.t("/tmp/{old} 不存在，已建空的 /tmp/{new}", old=old, new=new)
    if n.exists():
        return i18n.t("⚠ /tmp/{old} 与 /tmp/{new} 都在，没有动；请人工合并（旧目录里可能还有日志）", old=old, new=new)
    o.rename(n)
    return i18n.t("/tmp/{old} → /tmp/{new}（连内容一起搬）", old=old, new=new)


def rename_leftovers(old: str) -> list:
    """旧名还出现在哪些文件的哪一行（只报位置）。跳过生成物与 skill 镜像，避免重复计数。"""
    skip = {"__pycache__", ".git", "node_modules", ".venv", "archive",
            ".opencode", ".claude", ".agents"}
    hits = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or p.suffix not in {".md", ".py", ".json", ".sh", ".txt", ".yml", ".yaml"}:
            continue
        if skip & set(p.parts) or "state/locks" in p.as_posix():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel == "TODO.md" or rel.startswith("memory/"):
            continue                        # 生成视图：源改了它会跟着改，不必人工看
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{rel}:{i}" for i, line in enumerate(text.splitlines(), 1) if old in line]
    return hits


def cmd_rename(args) -> int:
    """改 agent 名字：档文件名 + `name` + 源里按名字引用的地方。

    **自动改**（机器写的源）：档文件名、`name`、`claims.tmp` 与 `jobs[].log` 里的
    `/tmp/<旧名>`、任务板的认领人（`items[]` 与 `topics[]`）、记忆各节的归属 `agent`
    （含 `archived[].dropped_by`）、其他档里 `created_by == 旧名` 的引用，最后重导视图。
    **不自动改**（叙述文字）：README / skill / 记忆正文 / 简报里的旧名——机器替换容易改坏语义，
    脚本只把命中位置列出来交人工核对。
    """
    old, new = args.old, args.new
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z_.\-]*", new or ""):
        print(i18n.t("新名不合规：{new!r}（建议 `<两位序号>_<角色>`，只允许字母数字与 _ . -）", new=new), file=sys.stderr)
        return 2
    src, dst = MULTIAGENTS / f"{old}.json", MULTIAGENTS / f"{new}.json"
    if find_agent(old) is None:
        print(i18n.t("名册里没有 {old}；先 `roster` 看名册", old=old), file=sys.stderr)
        return 2
    if not src.exists() or dst.exists() or find_agent(new) is not None:
        print(i18n.t("改名不会覆盖：{p0} 已存在（或 {p1} 不是档）", p0=dst.name, p1=src.name), file=sys.stderr)
        return 2
    who = agent_label()

    # 1) 档案本体：改 name / 临时目录 / 作业日志，落一行 history，然后改文件名
    with locked(src):
        a = json.loads(src.read_text(encoding="utf-8"))
        a["name"] = new
        cl = a.setdefault("claims", {})
        if cl.get("tmp"):
            cl["tmp"] = str(cl["tmp"]).replace(f"/tmp/{old}", f"/tmp/{new}")
        for j in a.get("jobs") or []:
            if j.get("log"):
                j["log"] = str(j["log"]).replace(f"/tmp/{old}", f"/tmp/{new}")
        add_history(a, i18n.t("改名：{old} → {new}（由 {who} 执行；源引用已同步，叙述文字需人工核对）", old=old, new=new, who=who))
        atomic_write(src, json.dumps(a, ensure_ascii=False, indent=2) + "\n")
    src.rename(dst)
    print(i18n.t("档案：{p0} → {p1}（name / claims.tmp / jobs[].log 已同步）", p0=src.name, p1=dst.name))
    print(f"  {move_tmp_dir(old, new)}")

    # 2) 任务板：认领人（条目 + 主题）
    def _board(b):
        n = 0
        for row in list(b.get("items") or []) + list(b.get("topics") or []):
            if (row.get("owner") or "") == old:
                row["owner"], n = new, n + 1
        return True, i18n.t("任务板：{n} 处认领人改为 {new}", n=n, new=new)

    ok, msg = mutate_board(_board)
    print(f"  {msg}" if ok else f"  ✗ {msg}")

    # 3) 记忆：节的归属 agent（含 archived 的 dropped_by）
    n_sec = n_arc = 0
    for doc in memory_ids():
        def _mem(doc_obj):
            nonlocal n_sec, n_arc
            for s in doc_obj.get("sections") or []:
                if s.get("agent") == old:
                    s["agent"], n_sec = new, n_sec + 1
            for s in doc_obj.get("archived") or []:
                if s.get("dropped_by") == old:
                    s["dropped_by"], n_arc = new, n_arc + 1
            return True, "ok"
        mutate_memory(doc, _mem)
    print(i18n.t("  记忆：{n_sec} 节归属 + {n_arc} 条 archived 归属改为 {new}", n_sec=n_sec, n_arc=n_arc, new=new))

    # 4) 其他档里 created_by == 旧名
    n_cb = 0
    for other in load_agents():
        if other.get("name") != new and other.get("created_by") == old:
            mutate_agent(other["name"], lambda o: (o.__setitem__("created_by", new), (True, "ok"))[1])
            n_cb += 1
    print(i18n.t("  其他档 created_by：{n_cb} 处改为 {new}", n_cb=n_cb, new=new))

    # 5) 视图重导（板子 / 记忆 / 索引）
    export_board(write=True)
    for doc in memory_ids():
        export_memory(doc, write=True)
    idx = MEMORY_DIR / "MEMORY.md"
    if memory_index_md() != (idx.read_text(encoding="utf-8") if idx.exists() else ""):
        idx.write_text(memory_index_md(), encoding="utf-8")
    print(i18n.t("  已重渲染 {TODO_MD}、{p1} 档记忆视图与 {idx}", TODO_MD=TODO_MD, p1=len(memory_ids()), idx=idx))

    hits = rename_leftovers(old)
    if hits:
        print(i18n.t("  另 {p0} 处叙述文字提到旧名（不自动改，请人工核对）：", p0=len(hits)))
        for h in hits[:40]:
            print(f"    {h}")
        if len(hits) > 40:
            print(i18n.t("    …（共 {p0} 处）", p0=len(hits)))
    else:
        print(i18n.t("  没有叙述文字仍提到旧名"))
    return 0


def cmd_attach(args) -> int:
    agent = find_agent(args.name)
    if not agent:
        print(i18n.t("名册里没有 {p0}；请用 register 新建（不得凭空认领）", p0=args.name), file=sys.stderr)
        return 2
    client, sid = detect_client(), detect_client()["session_id"]
    agent.setdefault("sessions", [])
    entry = next((s for s in agent["sessions"] if s.get("session_id") == sid), None)
    if entry is None:
        entry = {"client": args.client or client["client"], "session_id": sid,
                 "attached_at": now_iso(),
                 "note": "" if sid else i18n.t("客户端未暴露会话 id")}
        agent["sessions"].append(entry)
    entry.update(last_seen=now_iso(), state="active")
    if args.title:
        entry["title"] = args.title
    agent.update(client=args.client or client["client"], status=args.status or "active",
                 updated=now_iso())
    save_agent(agent)
    print(i18n.t("已登记: {p0}（client={p1} session={p2}）", p0=agent['name'], p1=agent['client'], p2=sid or '不可探测'))
    return 0


def cmd_todo(args) -> int:
    """任务板命令。全部动作读写 `todo.json`（源），改动后自动同步导出 TODO.md。"""
    me = current_agent()
    who = args.owner or (me["name"] if me else detect_client().get("client", "unknown"))
    act = args.action

    if act == "list":
        board = load_board()
        items = board.get("items", [])
        if args.owner:                                  # 只列某个 agent 认领的条目
            items = [i for i in items if (i.get("owner") or "-") == args.owner]
        if args.topic is not None:
            items = [i for i in items if i.get("topic") == args.topic]
        if args.state:
            items = [i for i in items if (i.get("state") or "todo") == args.state]
        if not items:
            print(i18n.t("任务板为空（源 multiagents/state/todo.json）。") if not board.get("items")
                  else i18n.t("没有匹配的条目（`--owner/--topic/--state` 过滤后为空）。"))
            return 0
        for tp in board.get("topics", []):
            rows = [i for i in items if i.get("topic") == tp["id"]]
            if not rows:
                continue
            print(f"  ── {tp['id']}. {tp.get('title') or tp.get('name', '')}")
            for i in rows:
                box = "x" if i.get("state") == "done" else " "
                print(i18n.t(
                          "  [{box}] {p1:<6} {p2:<8} 认领: {p3:<16} {p4}",
                          box=box,
                          p1=i['id'],
                          p2=i.get('state', 'todo'),
                          p3=i.get('owner') or '-',
                          p4=i.get('task', ''),))
        return 0

    if act == "export":
        md = export_board(write=args.write)
        if args.write:
            print(i18n.t("已从源导出 {TODO_MD}", TODO_MD=TODO_MD))
        else:
            print(md, end="")
        return 0

    if act == "verify":
        want = render_board(load_board())
        have = TODO_MD.read_text(encoding="utf-8") if TODO_MD.exists() else ""
        if want == have:
            print(i18n.t("✓ TODO.md 与源一致"))
            return 0
        import difflib
        diff = list(difflib.unified_diff(have.splitlines(), want.splitlines(),
                                         i18n.t("TODO.md（磁盘）"), i18n.t("TODO.md（源渲染）"), lineterm=""))
        print(i18n.t("✗ 漂移：TODO.md 与源不一致，跑 `todo export --write` 重新生成（差异 {p0} 行）", p0=len(diff)))
        print("\n".join(diff[:40]))
        return 1

    def add(b):
        desc = args.text or args.id               # `add "描述" --topic N`：描述落在 id 位
        if not desc or args.topic is None:
            return False, i18n.t("add 需要 <描述> 与 --topic N")
        if args.topic not in [tp["id"] for tp in b.get("topics", [])]:
            return False, i18n.t("主题 {p0} 未登记；先 `todo topic add \"名称\"`（主题号不复用）", p0=args.topic)
        tid = next_sub_id(b, args.topic)
        b.setdefault("items", []).append({
            "id": tid, "topic": args.topic, "task": desc, "owner": args.owner or who,
            "state": args.state or "todo", "updated": now_min(), "notes": []})
        return True, i18n.t("已添加 {tid}（认领: {p1}）", tid=tid, p1=args.owner or who)

    def claim(b):
        i = find_item(b, args.id)
        if not i:
            return False, i18n.t("没有这条任务：{p0}", p0=args.id)
        if (i.get("owner") or "-") not in ("-", "", who):
            return False, i18n.t("{p0} 已被 {p1} 认领；请先沟通或让位", p0=args.id, p1=i['owner'])
        i.update(owner=who, state="doing", updated=now_min())
        return True, i18n.t("已认领 {p0}（{who}）", p0=args.id, who=who)

    def done(b):
        i = find_item(b, args.id)
        if not i:
            return False, i18n.t("没有这条任务：{p0}", p0=args.id)
        i.update(state="done", updated=now_min())
        return True, i18n.t("已完成 {p0}", p0=args.id)

    def release(b):
        i = find_item(b, args.id)
        if not i:
            return False, i18n.t("没有这条任务：{p0}", p0=args.id)
        if (i.get("owner") or "-") not in ("-", "", who) and not args.force:
            return False, i18n.t("{p0} 属于 {p1}；用 --force 才能释放", p0=args.id, p1=i['owner'])
        i.update(owner="-", state="todo", updated=now_min())
        return True, i18n.t("已释放 {p0}", p0=args.id)

    def note(b):
        i = find_item(b, args.id)
        if not i:
            return False, i18n.t("没有这条任务：{p0}", p0=args.id)
        if not args.text:
            return False, i18n.t("note 需要 <任务号> <文本>")
        i.setdefault("notes", []).append(args.text)
        i["updated"] = now_min()
        return True, i18n.t("已给 {p0} 加备注（现 {p1} 条）", p0=args.id, p1=len(i['notes']))

    def topic_add(b):
        if not args.text:
            return False, i18n.t("topic add 需要 \"名称\"")
        ids = [tp["id"] for tp in b.setdefault("topics", [])]
        new_id = max(ids) + 1 if ids else 1
        b["topics"].append({"id": new_id, "name": args.text, "owner": args.owner or who})
        return True, i18n.t("已登记主题 {new_id}：{p1}", new_id=new_id, p1=args.text)

    if act == "topic":
        if args.id != "add":
            print(i18n.t("用法：todo topic add \"主题名称\" [--owner X]"), file=sys.stderr)
            return 2
        fn = topic_add
    else:
        fn = {"add": add, "claim": claim, "done": done, "release": release, "note": note}[act]

    ok, msg = mutate_board(fn)
    print(msg, file=sys.stdout if ok else sys.stderr)
    if ok:
        export_board(write=True)
        print(i18n.t("（已同步导出 {p0}）", p0=TODO_MD.name))
    return 0 if ok else 1


def apply_json(agent: dict, args, sid) -> tuple[bool, str]:
    """`json` 子命令的唯一执行点；返回 (ok, msg)。"""
    act, path, val = args.action, args.path, args.value
    try:
        if act == "set":
            if path is None or val is None:
                return False, i18n.t("set 需要 <点路径> <值>")
            set_field(agent, path, parse_value(val))
            out = f"{path} ← {val}"
        elif act == "add":
            if path is None or val is None:
                return False, i18n.t("add 需要 <列表路径> <值>")
            out = add_item(agent, path, parse_value(val), key=args.key)
        elif act == "remove":
            if path is None:
                return False, i18n.t("remove 需要 <列表路径>（值、--index N 或 --where 字段=值）")
            out = remove_item(agent, path, value=parse_value(val) if val is not None else None,
                              index=args.index, where=args.where)
        elif act == "history":
            if not path:
                return False, i18n.t("history 需要 \"<事件>\"")
            add_history(agent, path)
            out = i18n.t("history 已追加")
        elif act == "touch":
            out = i18n.t("updated 已刷新")
        elif act == "memory":
            if not path:
                return False, i18n.t("memory 需要 <memory/…md> 路径")
            out = upsert_memory(agent, path, args.role or "contributor")
        elif act == "job":
            if not path:
                return False, i18n.t("job 需要 \"<名称>\"")
            out = upsert_job(agent, path, pid=args.pid, log=args.log, note=args.note)
        elif act == "handoff":
            set_field(agent, "handoff", path or "")
            out = i18n.t("handoff 已更新") if path else i18n.t("handoff 已清空")
        elif act == "artifact":
            if not path:
                return False, i18n.t("artifact 需要 <路径>")
            out = add_item(agent, "artifacts", path)
        else:
            return False, i18n.t("未知动作：{act}", act=act)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        return False, i18n.t("{act} 失败：{e}", act=act, e=e)
    touch_agent(agent, sid)
    return True, out


def cmd_json(args) -> int:
    agent, msg = resolve_agent(args.name, write=args.action != "get")
    if agent is None:
        print(msg, file=sys.stderr)
        return 2
    if msg:
        print(i18n.t("注意：{msg}", msg=msg), file=sys.stderr)
    if args.action == "get":
        val = get_field(agent, args.path) if args.path else \
            {k: v for k, v in agent.items() if not k.startswith("_")}
        print(val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, indent=2))
        return 0
    sid = detect_client()["session_id"]
    ok, out = mutate_agent(agent["name"], lambda a: apply_json(a, args, sid))
    print(f"{agent['name']}.json: {out}" if ok else out, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def cmd_memory_index(args) -> int:
    md = memory_index_md()
    if args.write:
        print(i18n.t("已写入 {p0}", p0=MEMORY_DIR / 'MEMORY.md'))
        (MEMORY_DIR / "MEMORY.md").write_text(md, encoding="utf-8")
    else:
        print(md, end="")
    return 0


def cmd_memory(args) -> int:
    """记忆档命令：源 multiagents/state/memory/**/*.json，人类视图 memory/**/*.md。"""
    act = args.action
    me = current_agent()
    who = args.agent or (me["name"] if me else detect_client().get("client", "unknown"))

    if act == "list":
        ids = memory_ids()
        if not ids:
            print(i18n.t("（源里还没有记忆档）"))
        for d in ids:
            doc_obj = load_memory(d)
            kind = "diary" if "/diary/" in f"/{d}" else i18n.t("主题")
            print(i18n.t(
                      "  {d:<42s} {kind:<6s} 节×{p2:<3d} {p3:<17s} {p4}",
                      d=d,
                      kind=kind,
                      p2=len(doc_obj.get('sections', [])),
                      p3=str(doc_obj.get('updated', ''))[:16],
                      p4=doc_obj.get('title', ''),))
            if args.sections:
                for s in doc_obj.get("sections", []):
                    print(f"      {str(s.get('id', '?')):>3s}  {str(s.get('title', ''))[:54]:<54s} "
                          f"{(s.get('agent') or '-')}")
        return 0

    if act == "show":
        if not args.id:
            print(i18n.t("用法：memory show <档 id> [--section <编号|标题>]"), file=sys.stderr)
            return 2
        if args.section:
            s = find_section(load_memory(args.id), args.section)
            if not s:
                print(i18n.t("没有这一节：{p0}", p0=args.section), file=sys.stderr)
                return 1
            print(f"## {s.get('title', '')}\n\n{str(s.get('body') or '').strip()}")
            return 0
        print(export_memory(args.id), end="")
        return 0

    if act in ("export", "verify"):
        ids = memory_ids() if (args.all or not args.id) else [doc_id_of(args.id)]
        if not ids:
            print(i18n.t("（源里还没有记忆档）"))
            return 0
        drift = 0
        for d in ids:
            _, mp = memory_paths(d)
            want = render_memory(d, load_memory(d))
            have = mp.read_text(encoding="utf-8") if mp.exists() else ""
            if act == "export":
                if args.write:
                    export_memory(d, write=True)
                else:
                    print(want, end="")
                continue
            if want == have:
                # 2026-10-18 修：正文为空/意外为空时 verify 也曾返回 ✓（源与视图一致地空）。
                # 空档在「忘了传 --file」时必然发生，故此处显式告警。
                doc_obj = load_memory(d)
                if not (doc_obj.get("preamble") or "").strip() and not doc_obj.get("sections"):
                    print(f"  ! {d} 内容为空（建档时可能漏传 --file/--text）")
                    drift = 1
                else:
                    print(f"  ✓ {d}")
            else:
                drift = 1
                print(i18n.t("  ✗ {d} 漂移（跑 `memory export {d} --write`）", d=d))
        if act == "export" and args.write:
            print(i18n.t("已从源导出 {p0} 档视图", p0=len(ids)))
        if act == "verify" and args.all:
            idx = MEMORY_DIR / "MEMORY.md"
            have = idx.read_text(encoding="utf-8") if idx.exists() else ""
            if memory_index_md() == have:
                print("  ✓ memory/MEMORY.md")
            else:
                drift = 1
                print(i18n.t("  ✗ memory/MEMORY.md 漂移（跑 `memory-index --write`）"))
        return drift

    if act == "import":
        if not args.id:
            print(i18n.t("用法：memory import <md 路径> [--doc <档 id>] [--owner X] [--role R] [--force]"),
                  file=sys.stderr)
            return 2
        src = Path(args.id)
        src = src if src.is_absolute() else ROOT / src
        if not src.exists():
            print(i18n.t("找不到：{src}", src=src), file=sys.stderr)
            return 1
        doc_id = doc_id_of(args.doc) if args.doc else doc_id_of(src.as_posix())
        jp, mp = memory_paths(doc_id)
        if jp.exists() and not args.force:
            print(i18n.t("{p0} 已存在；要覆盖加 --force", p0=jp.relative_to(ROOT)), file=sys.stderr)
            return 1
        doc_obj = parse_memory_md(src.read_text(encoding="utf-8"))
        if args.title:
            doc_obj["title"] = args.title
        try:
            doc_obj["source"] = src.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            doc_obj["source"] = src.resolve().as_posix()
        doc_obj["updated"] = now_iso()
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(doc_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        export_memory(doc_id, write=True)
        print(i18n.t(
                  "已导入 {doc_id}：{p1} 节 → {p2}（视图 {p3}）",
                  doc_id=doc_id,
                  p1=len(doc_obj['sections']),
                  p2=jp.relative_to(ROOT),
                  p3=mp.relative_to(ROOT),))
        if args.owner:
            ok, msg = register_ownership(args.owner, jp, args.role or "contributor")
            print(f"  {msg}", file=sys.stdout if ok else sys.stderr)
        return 0

    # —— 以下动作要写源 ——
    def do_new(doc_obj):
        if doc_obj.get("title") and not args.force:
            return False, i18n.t("该档已有标题（改标题用 `memory set <档> --title …`）")
        doc_obj["title"] = args.title or doc_obj.get("title") or doc_id_of(args.id)
        # 2026-10-18 修：`new` 此前完全没读 --text/--file，长正文被静默丢弃且仍报「已建档」。
        # 正文与标题一并给出时，正文落为 preamble（首个 `##` 之前）/ 各节（`## 标题` 逐节）。
        body_msg = ""
        wants_body = bool(args.text) or bool(args.file)
        text, err = body_text(args)
        if wants_body and err:
            return False, err
        if wants_body and text.strip():
            pre, secs = split_md_sections(text)
            if pre:
                doc_obj["preamble"] = pre.strip()
            for title, sbody in secs:
                doc_obj.setdefault("sections", []).append(
                    {"id": next_section_id(doc_obj), "title": title,
                     "agent": who, "updated": now_min(), "body": sbody})
            body_msg = (i18n.t("，正文已写入（{p0} 节 + 前言 {p1} 字）", p0=len(secs), p1=len(pre.strip()))
                        if secs else i18n.t("，正文已写入前言（{p0} 字）", p0=len(pre.strip())))
        elif wants_body:
            return False, i18n.t("正文为空（--file 指向的文件没有内容？）")
        return True, i18n.t("已建档 {p0}：{p1}{p2}", p0=doc_id_of(args.id),
                            p1=doc_obj["title"], p2=body_msg)

    def do_append(doc_obj):
        text, err = body_text(args)
        if err:
            return False, err
        if not text:
            return False, i18n.t("正文为空")
        pre, secs = split_md_sections(text)      # 输入即 Markdown：`## 标题` 就是节标题
        if pre:                                  # 首个 `##` 之前的文字并进档的 preamble
            doc_obj["preamble"] = (str(doc_obj.get("preamble") or "").rstrip()
                                   + "\n\n" + pre).strip()
        if not secs:
            if not args.section:
                return False, i18n.t("append 需要 --section <标题>，或在正文里写 `## 标题`（支持整段 Markdown）")
            secs = [(args.section, text)]
        msgs = []
        for title, body in secs:
            s = find_section(doc_obj, title)
            if s:
                s["body"] = (str(s.get("body") or "").rstrip() + "\n\n" + body).strip()
                s["agent"], s["updated"] = who, now_min()
                msgs.append(i18n.t("追加到第 {p0} 节「{p1}」", p0=s.get('id'), p1=s.get('title')))
            else:
                sid = next_section_id(doc_obj)
                doc_obj.setdefault("sections", []).append(
                    {"id": sid, "title": title, "agent": who, "updated": now_min(), "body": body})
                msgs.append(i18n.t("新建第 {sid} 节「{title}」", sid=sid, title=title))
        if args.section and secs[0][0] != args.section:
            msgs.append(i18n.t("注：正文首节的标题「{p0}」优先，--section {p1} 未用于该节", p0=secs[0][0], p1=args.section))
        return True, i18n.t("；").join(msgs) + i18n.t("（{who}）", who=who)

    def do_set(doc_obj):
        if args.preamble:                        # 改档前言（首个 `## ` 之前的文字）
            text, err = body_text(args)
            if err:
                return False, err
            if not text.strip():
                return False, i18n.t("前言为空（要清空请用 --text ''）")
            doc_obj["preamble"] = text.strip()
            return True, i18n.t("前言已改（原内容覆盖）")
        if args.title and args.section:          # 给了 --section：改的是**节**标题（不是档标题）
            s = find_section(doc_obj, args.section)
            if s is None:
                return False, i18n.t("没有这一节：{p0}（要新建请用 append）", p0=args.section)
            old = s.get("title", "")
            s["title"] = args.title
            return True, i18n.t("节标题：「{old}」→「{p1}」", old=old, p1=args.title)
        if args.title:
            old = doc_obj.get("title", "")
            doc_obj["title"] = args.title
            return True, i18n.t("标题：「{old}」→「{p1}」", old=old, p1=args.title)
        if not args.section:
            return False, i18n.t("set 需要 --section <编号|标题> 或 --title <新标题>")
        text, err = body_text(args)
        if err:
            return False, err
        if not text:
            return False, i18n.t("正文为空")
        _, secs = split_md_sections(text)
        if len(secs) > 1:
            return False, (i18n.t("set 只接受一节正文（输入里有 {p0} 个 `## 标题`）；多节请用 `memory append`（可一次追加多节）", p0=len(secs)))
        note = ""
        body = text
        if secs:                                 # 输入带了标题：作为正文交给本节，标题行不重复渲染
            body = secs[0][1]
            if secs[0][0] != args.section:
                note = i18n.t("；注：输入里的标题「{p0}」未用于改名（节名仍是「{p1}」）", p0=secs[0][0], p1=args.section)
        s = find_section(doc_obj, args.section)
        if not s:
            return False, i18n.t("没有这一节：{p0}（要新建请用 append）", p0=args.section)
        s["body"], s["agent"], s["updated"] = body, who, now_min()
        return True, i18n.t("已整体替换第 {p0} 节「{p1}」（{who}）{note}", p0=s.get('id'), p1=s.get('title'), who=who, note=note)

    def do_drop(doc_obj):
        s = find_section(doc_obj, args.section or "")
        if not s:
            return False, i18n.t("没有这一节：{p0}", p0=args.section)
        doc_obj["sections"].remove(s)
        doc_obj.setdefault("archived", []).append(dict(s, dropped_by=who, dropped_at=now_min()))
        return True, i18n.t("已下架第 {p0} 节「{p1}」（源 archived[] 里留底，可找回）", p0=s.get('id'), p1=s.get('title'))

    if not args.id:
        print(i18n.t("用法：memory {act} <档 id> …", act=act), file=sys.stderr)
        return 2
    doc_id = doc_id_of(args.id)
    ok, msg = mutate_memory(doc_id, {"new": do_new, "append": do_append,
                                     "set": do_set, "drop": do_drop}[act])
    print(msg, file=sys.stdout if ok else sys.stderr)
    if ok:
        export_memory(doc_id, write=True)
        print(i18n.t("（已同步导出 {p0}）", p0=memory_paths(doc_id)[1].relative_to(ROOT)))
    return 0 if ok else 1


# ------------------------------------------- 进展简报（用户问「agent 在做什么」时产出）
#
# 2026-10-17（用户要求）：多 agent 并行时用户难以跟踪每个 agent 在做什么。用户问「你在做什么 /
# 目前进展」时，agent 用本命令把当前状态写成一份简报归档：`output/quick-report/<日期时间>_<agent>.md`
# （命名按用户指定形式）。正文由 agent 给、脚本原样落盘（不推导、不替 agent 编内容）；正文传参仿 git commit：
# `--text`（短，≈ `-m`）、`--file`（长，≈ `-F`，`--file -` 读 stdin）。
#
# 2026-10-17（用户要求）：落盘时**追加一节生成附录**（个人待办 / 名下板项 / claims），从源现算、带
# 「生成物，勿手改」戳——读简报的人不必再翻档案才知道这人手上还压着什么。`--no-appendix` 可关。

def report_path(subject: str) -> Path:
    """<日期时间>_<agent>.md（分钟精度）；同分钟内重复时加 -2、-3…，不覆盖旧简报。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    p, i = REPORT_DIR / f"{stamp}_{subject}.md", 1
    while p.exists():
        i += 1
        p = REPORT_DIR / f"{stamp}_{subject}-{i}.md"
    return p


def list_reports(limit: int) -> int:
    """按文件名（时间前缀）倒序列出已有简报。"""
    files = (sorted(REPORT_DIR.glob("*.md"), reverse=True)[:limit] if REPORT_DIR.exists() else [])
    rel = REPORT_DIR.relative_to(ROOT)
    if not files:
        print(i18n.t("还没有简报（{rel}/ 为空）；生成：`python3 multiagents/agentctl.py report --file <简报文本>`", rel=rel))
        return 0
    print(i18n.t("{rel}/（最新 {p1} 条，文件名 <日期时间>_<agent>.md）：", rel=rel, p1=len(files)))
    for p in files:
        print(f"  {p.name}")
    return 0


def report_appendix(agent: dict, board: dict) -> str:
    """简报附录（生成物）：个人待办 + 名下板项 + 占用，读源现算，不落任何新状态。"""
    me = agent.get("name", "?")
    own = [t for t in (agent.get("todo") or []) if t.get("state") not in ("done", "dropped")]
    mine = [it for it in board.get("items", [])
            if it.get("owner") == me and it.get("state") not in ("done",)]

    def _own(t):
        s = f"`{t.get('id')}`({t.get('state', 'todo')}) {t.get('task', '')}"
        return s + (i18n.t(" →板 `{p0}`", p0=t['board']) if t.get("board") else "")

    def _item(it):
        return f"`{it['id']}`({it.get('state')}) {it.get('task', '')}"

    lines = ["", "---", "",
             i18n.t("## 附录（由 `agentctl.py report` 生成，勿手改）"), ""]
    for label, rows in ((i18n.t("个人待办"), [_own(t) for t in own]), (i18n.t("名下板项"), [_item(it) for it in mine])):
        lines.append(i18n.t("- {label} {p1} 项未完成：", label=label, p1=len(rows)) + (i18n.t("（空）") if not rows else ""))
        lines += [f"  - {r}" for r in rows]
    cl = agent.get("claims") or {}
    if cl.get("files") or cl.get("resources"):
        lines.append(i18n.t(
                         "- 占用：files {p0} 项｜resources {p1}｜tmp `{p2}`",
                         p0=len(cl.get('files') or []),
                         p1='、'.join(cl.get('resources') or []) or '—',
                         p2=cl.get('tmp') or '—',))
    lines.append(i18n.t("- 生成时间：{p0}", p0=now_iso()))
    return "\n".join(lines) + "\n"


def cmd_card(args) -> int:
    """只读打印某 agent 的工作状态（focus / 私人清单 / 名下板项 / 认领占用 / 记忆 / 交接）。

    2026-10-17（用户要求）：`me --name X` 会把当前会话**登记**到 X（等价 attach），不是读命令；
    只想看别人的进度用本命令，或 `task list --name X` / `json get <字段> --name X`。
    本命令不登记会话、不改任何档。
    """
    name = getattr(args, "name", None)
    a = find_agent(name) if name else current_agent()
    if a is None:
        print(i18n.t("名册里没有 {name}；用 `agentctl.py roster` 看名册", name=name) if name else
              i18n.t("无法从当前会话判定 agent；给个名字：`agentctl.py card <name>`"), file=sys.stderr)
        return 2
    board = load_board()
    cl = a.get("claims") or {}
    mine = [it for it in board.get("items", []) if it.get("owner") == a["name"]]
    open_mine = [it for it in mine if it.get("state") != "done"]
    own = a.get("todo") or []
    open_own = [t for t in own if t.get("state") not in ("done", "dropped")]
    rows = [i18n.t(
                "{p0} ｜ 角色 {p1}（{p2}）｜ 状态 {p3}｜ 客户端 {p4}｜ 更新 {p5}",
                p0=a['name'],
                p1=a.get('role', '?'),
                p2=a.get('display') or '',
                p3=a.get('status', '?'),
                p4=a.get('client', '?'),
                p5=str(a.get('updated') or '')[:16],),
            i18n.t("  在做什么  : {p0}", p0=a.get('focus') or '（未填）')]
    if a.get("handoff"):
        rows.append(i18n.t("  交接      : {p0}", p0=a['handoff']))
    for x in load_agents():
        if x.get("name") != a["name"] and a["name"] in str(x.get("handoff") or ""):
            rows.append(i18n.t("  收到交接  : {p0} → {p1}", p0=x['name'], p1=x.get('handoff')))
    rows.append(i18n.t("  私人清单  : 未完成 {p0} / 共 {p1}", p0=len(open_own), p1=len(own)))
    for t in open_own[:8]:
        rows.append(f"      [{TASK_MARKS.get(t.get('state'), ' ')}] {str(t.get('id')):<4} "
                    f"{t.get('state', 'todo'):<8} {t.get('task', '')}")
    rows.append(i18n.t("  名下板项  : 未完成 {p0} / 共 {p1}", p0=len(open_mine), p1=len(mine))
                + (i18n.t("　（按人过滤：`agentctl.py todo list --owner {p0}`）", p0=a['name']) if mine else ""))
    for it in (open_mine or mine)[:8]:
        box = "x" if it.get("state") == "done" else " "
        rows.append(f"      [{box}] {it['id']:<6} {it.get('state', 'todo'):<8} {it.get('task', '')}")
    files = [str(f) for f in (cl.get("files") or [])]
    rows.append(i18n.t(
                    "  认领占用  : files {p0} 项｜ tmp {p1}｜ 资源 {p2}",
                    p0=len(files),
                    p1=cl.get('tmp') or '—',
                    p2='、'.join(cl.get('resources') or []) or '—',))
    for f in files[:6]:
        rows.append(f"      · {f}")
    mem = a.get("memory") or []
    rows.append(i18n.t("  维护记忆  : {p0} 个", p0=len(mem)))
    for m in mem[:8]:
        rows.append(i18n.t("      · {p0}（{p1}）", p0=m.get('path', '?'), p1=m.get('role', '?')))
    if a.get("skills"):
        rows.append(i18n.t("  技能      : ") + i18n.t("、").join(f"`{s}`" for s in a["skills"]))
    for j in (a.get("jobs") or [])[:3]:
        rows.append(i18n.t("  作业      : {p0}（{p1}）→ {p2}", p0=j.get('name', '?'), p1=j.get('state', '?'), p2=j.get('log') or '—'))
    if a.get("artifacts"):
        rows.append(i18n.t("  产出      : {p0} 项（首项 {p1}）", p0=len(a['artifacts']), p1=a['artifacts'][0]))
    for h in (a.get("history") or [])[-3:]:
        rows.append(i18n.t("  变更      : {p0} {p1}", p0=str(h.get('t') or '')[:16], p1=h.get('e', '')))
    print("\n".join(rows))
    return 0


def cmd_report(args) -> int:
    if getattr(args, "list", False):
        return list_reports(args.limit)
    agent, msg = resolve_agent(getattr(args, "name", None), write=True)   # 会往 quick-report/ 落盘
    if agent is None:
        print(msg, file=sys.stderr)
        return 2
    if msg and getattr(args, "name", None):
        print(i18n.t("注意：{msg}", msg=msg), file=sys.stderr)
    body, err = body_text(args)
    if err:
        print(err, file=sys.stderr)
        return 1
    note = ""
    text = body + "\n"
    if not getattr(args, "no_appendix", False):
        text += report_appendix(agent, load_board())
        note = i18n.t("（含「个人待办 / 名下板项」生成附录；--no-appendix 可关）")
    path = report_path(agent["name"])
    path.write_text(text, encoding="utf-8")
    print(i18n.t("已写入 {p0}{note}", p0=path.relative_to(ROOT), note=note))
    return 0


# ------------------------------------------- 获取当前 agent（AGENTS.md「第一步」改由脚本一步做完）
#
# 2026-10-17（用户要求）：原先 AGENTS.md 把「会话启动第一步」写成 agent 的职责——读名册、让用户选、
# attach、读回 focus/board/claims。这套动作**改由脚本一步做完**：
#   me   ：按客户端/会话匹配 → 命中即自动登记（等价 attach）→ 打印身份卡（含可直接复述的
#          「我是 `X`」声明句与待办摘要）；未命中则打印名册 + 三个选项与对应命令
#          （名册某项 / 新增一个 agent / 暂不登记），**绝不自行认领**（退出码 3 供脚本判断）。
#   new  ：上面「新增一个 agent」那一支——建档 + 登记 + 建 /tmp/<agent>/ + 打身份卡，一命令完成。
# 规约本身仍以 AGENTS.md 为准，脚本只把"第一步"落地，不替代规则文本。

STATE_LABEL = {"doing": i18n.t("进行中"), "todo": i18n.t("待办"), "paused": i18n.t("暂停"), "done": i18n.t("已完成")}


def identity_card(agent: dict, board: dict) -> str:
    """身份卡：显式声明句 + 待办/占用/交接摘要（全部读自源，不猜）。"""
    me = agent.get("name", "?")
    mine = [it for it in board.get("items", []) if it.get("owner") == me]
    doing = [it for it in mine if it.get("state") == "doing"]
    own = [t for t in (agent.get("todo") or []) if t.get("state") not in ("done", "dropped")]
    sess = (agent.get("sessions") or [{}])[-1]
    cl = agent.get("claims") or {}
    rows = [i18n.t("我是 `{me}`（角色 {p1}：{p2}）—— 这句要显式声明给用户。", me=me, p1=agent.get('role', ''), p2=agent.get('display') or ''),
            i18n.t(
                "  状态 {p0}｜客户端 {p1}｜session {p2}｜档案更新 {p3}",
                p0=agent.get('status', '?'),
                p1=agent.get('client', '?'),
                p2=sess.get('session_id') or '不可探测',
                p3=str(agent.get('updated', ''))[:16],),
            f"  focus   : {agent.get('focus') or '（未填）'}"]
    if mine:
        group = {}
        for it in mine:
            group.setdefault(it.get("state") or "todo", []).append(it["id"])
        rows.append(i18n.t("  任务板  : ") + i18n.t("、").join(
            f"{STATE_LABEL.get(k, k)} {'/'.join(v)}" for k, v in group.items()) + i18n.t("（共 {p0} 项）", p0=len(mine)))
    for it in doing:
        rows.append(f"    · `{it['id']}` {it.get('task', '')}")
    if own:
        rows.append(i18n.t("  个人清单: ") + i18n.t("；").join(
            f"`{t.get('id')}`({t.get('state', 'todo')}) {t.get('task', '')}" for t in own))
    rows.append(i18n.t(
                    "  claims  : files={p0} 项｜tmp={p1}｜resources={p2}",
                    p0=len(cl.get('files') or []),
                    p1=cl.get('tmp') or '—',
                    p2='、'.join(cl.get('resources') or []) or '—',))
    rows.append(i18n.t("  记忆档  : {p0} 个", p0=len(agent.get('memory') or [])))
    if agent.get("skills"):
        rows.append(i18n.t("  技能    : ") + i18n.t("、").join(f"`{s}`" for s in agent["skills"]))
        rows.append(i18n.t("  先加载  : ") + i18n.t("，").join(f"skill(id={s})" for s in agent["skills"])
                    + i18n.t("　← 动手前用 `skill` 工具逐个加载（正文不会自动进上下文）"))
    if agent.get("handoff"):
        rows.append(i18n.t("  交接    : {p0}", p0=agent.get('handoff')))
    for a in load_agents():
        if a.get("name") != me and me in str(a.get("handoff") or ""):
            rows.append(i18n.t("  收到交接: {p0} → {p1}", p0=a['name'], p1=a.get('handoff')))
    if agent.get("created_by"):
        rows.append(i18n.t("  由谁生成: {p0}", p0=agent['created_by']))
    rows.append(i18n.t("  下一步  : `agentctl.py todo list`｜`agentctl.py report`（用户问进展时出简报）"))
    for line in onboard_hint_lines():
        rows.append("  " + line)
    return "\n".join(rows)


def cmd_me(args) -> int:
    """获取当前 agent：会话匹配 → 自动登记 → 身份卡；未匹配 → 名册 + 三选项（不认领，退出码 3）。"""
    client = detect_client()
    named = getattr(args, "name", None)
    agent = find_agent(named) if named else current_agent()      # 用户点名优先于会话匹配
    if named and agent is None:
        print(i18n.t("名册里没有 {named}；新增用 `agentctl.py new <角色>`（不得凭空认领）", named=named), file=sys.stderr)
        return 2
    if agent is None:
        print(i18n.t("无法从当前会话判定 agent（client={p0}，session={p1}）。", p0=client['client'], p1=client['session_id'] or '不可探测'))
        cmd_roster(argparse.Namespace(markdown=False))
        print(i18n.t("请让用户从上面名册里选，**不得自行认领**："))
        print(i18n.t("  1) 名册里就是某一个 → `python3 multiagents/agentctl.py me --name <name>`"))
        print(i18n.t("  2) 新增一个 agent   → `python3 multiagents/agentctl.py new <角色> --display \"…\"`"))
        print(i18n.t("  3) 暂不登记         → 不建档、不认领，本次会话不要写任何源"))
        for line in onboard_hint_lines():   # 首装提示 / 中断续跑（进度源 state/first_run.json）
            print(line)
        return 3
    if named:                    # 点名 = 登记（写操作）；只读看别人另有 card
        print(i18n.t("（`me --name <X>` 会把本次会话登记到 {p0}，等价 attach；只读查看别人的状态用 `agentctl.py card <name>`）", p0=agent['name']), file=sys.stderr)
    now, prev = now_iso(), current_agent()
    if prev and prev.get("name") != agent["name"]:
        print(i18n.t("注意：本会话此前登记在 {p0}；本次改为 {p1}（原档里的登记保留，如需清理用 `json remove sessions …`）", p0=prev['name'], p1=agent['name']), file=sys.stderr)

    def _bind(a: dict):
        """把当前客户端/会话登记进该档（等价 attach；返回 mutate_agent 要求的 (ok, msg)）。"""
        a.setdefault("sessions", [])
        e = next((s for s in a["sessions"] if s.get("session_id") == client["session_id"]), None)
        if e is None:
            e = {"client": client["client"], "session_id": client["session_id"], "attached_at": now,
                 "note": "" if client["session_id"] else i18n.t("客户端未暴露会话 id")}
            a["sessions"].append(e)
        e.update(last_seen=now, state="active")
        a.update(client=client["client"], status=a.get("status") or "active", updated=now)
        return True, i18n.t("会话已登记（{p0} / {p1}）", p0=client['client'], p1=client['session_id'] or '不可探测')

    ok, out = mutate_agent(agent["name"], _bind)
    if not ok:
        print(out, file=sys.stderr)
        return 1
    agent = find_agent(agent["name"]) or agent
    print(i18n.t("已登记本次会话到 {p0}（client={p1}，session={p2}）", p0=agent['name'], p1=client['client'], p2=client['session_id'] or '不可探测'))
    print(identity_card(agent, load_board()))
    return 0


# ------------------------------------------------- 初次安装进度（first_run.json，onboard 子命令）
#
# 2026-10-17（用户要求）：「项目是否 init 过」原先没有判断——`init` 是字段引用自检、不记状态，
# `me` 那句「刚克隆先按 first-run 引导」由名册 `created_by=="framework"` 推出，是常量；引导中途退出
# 后没有任何进度可续。这里加一份进度源 `multiagents/state/first_run.json`：
# 步骤与 skill `first-run` 的「最小可跑初始化清单」1–8 一一对应；**能机器判定的步骤现场算**
# （不信档里的自报），机器判不了的才看档里状态。入口在 `me`：无档 → 提示首装；有档未完成 →
# 打印进度并给「继续 / 重新开始 / 暂不」三选项（选项框由 agent 用客户端能力弹，脚本只负责报状态）。

ONBOARD_JSON = STATE_DIR / "first_run.json"

def onboard_steps() -> list:
    """8 步定义：id、标题（与 skill first-run 清单一致）、能否机器判定。"""
    return [
        {"id": "1", "title": "自报家门", "auto": False},
        {"id": "2", "title": "问清这次要研究什么，据此定目录", "auto": False},
        {"id": "3", "title": "配路径", "auto": True},
        {"id": "4", "title": "建虚拟环境装依赖", "auto": True},
        {"id": "5", "title": "同步 skill 镜像", "auto": True},
        {"id": "6", "title": "认领身份", "auto": True},
        {"id": "7", "title": "建研究主题", "auto": True},
        {"id": "8", "title": "报告初始化结果与下一步建议", "auto": False},
    ]

def load_onboard() -> dict:
    if not ONBOARD_JSON.exists():
        return {}
    try:
        return json.loads(ONBOARD_JSON.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return {}

def save_onboard(ob: dict) -> None:
    ob["schema"] = 1
    ob["updated"] = now_iso()
    ob["steps"] = ob.get("steps") or [{"id": s["id"], "title": s["title"], "state": "todo"}
                                      for s in onboard_steps()]
    by_id = {s["id"]: s for s in ob["steps"]}
    for s in onboard_steps():                    # 新版本加了步骤 → 补进已有档
        if s["id"] not in by_id:
            ob["steps"].append({"id": s["id"], "title": s["title"], "state": "todo"})
    atomic_write(ONBOARD_JSON, json.dumps(ob, ensure_ascii=False, indent=2) + "\n")

def mutate_onboard(fn):
    """对 first_run.json 加锁做原子读-改-写；fn(ob) -> (ok, msg)。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with locked(ONBOARD_JSON):
        ob = load_onboard()
        ok, msg = fn(ob)
        if not ok:
            return False, msg
        save_onboard(ob)
        return True, msg

def onboard_auto() -> dict:
    """机器能判定的步骤现算：返回 {step_id: (done: bool, 证据一句话)}。"""
    ev = {}
    ev["3"] = ((ROOT / ".env").exists(), i18n.t(".env 存在") if (ROOT / ".env").exists()
               else i18n.t("还没有 .env（cp .env.example .env）"))
    venv_py = ROOT / ".venv" / ("bin/python" if os.name != "nt" else "Scripts/python.exe")
    ev["4"] = (venv_py.exists(), i18n.t(".venv 可用") if venv_py.exists()
               else i18n.t("还没有 .venv"))
    try:
        r = subprocess.run([sys.executable, str(MULTIAGENTS / "sync_skills.py"), "--check"],
                           capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
        ev["5"] = (ok, i18n.t("镜像 0 漂移") if ok else i18n.t("镜像有漂移（跑 sync_skills.py）"))
    except OSError:
        ev["5"] = (False, i18n.t("sync_skills.py 跑不了"))
    ev["6"] = (current_agent() is not None,
               i18n.t("已认领 {p0}", p0=(current_agent() or {}).get('name'))
               if current_agent() else i18n.t("本会话未认领任何 agent"))
    seedless = [i for i in load_board().get("items", [])]
    topics = load_board().get("topics", [])
    ev["7"] = (len(topics) > 1, i18n.t("已有 {p0} 个主题", p0=len(topics)) if len(topics) > 1
               else i18n.t("只有初始化主题（还没有研究主题）"))
    return ev

def onboard_status_lines() -> list:
    """进度报告（给 onboard status 与 me 共用）：人可读的若干行。"""
    ob = load_onboard()
    states = {s.get("id"): (s.get("state") or "todo") for s in ob.get("steps", [])}
    auto = onboard_auto()
    done = sum(1 for s in onboard_steps() if states.get(s["id"]) == "done"
               or (s["auto"] and auto.get(s["id"], (False, ""))[0]))
    rows = []
    for s in onboard_steps():
        if s["auto"] and auto.get(s["id"], (False, ""))[0]:
            mark, note = "✓", auto[s["id"]][1]
        else:
            st = states.get(s["id"], "todo")
            mark = {"done": "✓", "doing": "…", "skip": "－"}.get(st, " ")
            note = ""
        rows.append(i18n.t("  [{m}] {id}. {title}{note}",
                           m=mark, id=s["id"], title=s["title"],
                           note=(i18n.t("　（{p0}）", p0=note) if note else "")))
    rows.insert(0, i18n.t("初次安装进度：{done}/{n}（源 {p1}）", done=done, n=len(onboard_steps()), p1=ONBOARD_JSON))
    if ob.get("complete"):
        rows[0] += i18n.t("｜已完成（{p0}）", p0=str(ob.get('completed_at', ''))[:16])
    else:
        first = next((s["id"] for s in onboard_steps()
                      if states.get(s["id"]) not in ("done", "skip")
                      and not (s["auto"] and auto.get(s["id"], (False, ""))[0])), None)
        if first:
            rows[0] += i18n.t("｜下一步：第 {p0} 步", p0=first)
    return rows

def cmd_onboard(args) -> int:
    """初次安装进度：status / step / reset / finish。源 state/first_run.json，走锁原子改。"""
    act = args.action
    if act == "status":
        for line in onboard_status_lines():
            print(line)
        if not load_onboard().get("complete"):
            print(i18n.t("续跑或重来由你定：继续就接着做下一步；重来用 `agentctl.py onboard reset`。"))
        return 0
    if act == "reset":
        def _reset(ob):
            ob.clear()
            ob["started_at"] = now_iso()
            return True, i18n.t("进度已清零（8 步回到 todo），重新开始。")
        ok, msg = mutate_onboard(_reset)
        print(msg, file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    if act == "finish":
        def _finish(ob):
            ob["complete"] = True
            ob["completed_at"] = now_iso()
            return True, i18n.t("初次安装标记完成（{p0}）。", p0=ob["completed_at"])
        ok, msg = mutate_onboard(_finish)
        print(msg, file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    # step <n> <state>
    n, st = args.step, args.state
    if st not in ("todo", "doing", "done", "skip"):
        print(i18n.t("state 只能是 todo / doing / done / skip"), file=sys.stderr)
        return 2
    def _step(ob):
        for s in ob.get("steps", []):
            if str(s.get("id")) == str(n):
                s["state"] = st
                s["at"] = now_iso()
                return True, i18n.t("第 {n} 步 → {st}：{title}", n=n, st=st, title=s.get("title"))
        return False, i18n.t("没有第 {n} 步（1–8）", n=n)
    ok, msg = mutate_onboard(_step)
    print(msg, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1

def onboard_hint_lines() -> list:
    """给 me 用的提示行：无档 → 首装提示；有档未完成 → 进度 + 三选项。"""
    guide = next((a.get("name") for a in load_agents() if a.get("created_by") == "framework"), None)
    if not guide:
        return []
    ob = load_onboard()
    if not ob:
        return [i18n.t("若这是刚克隆下来的框架：先按 skill `first-run` 引导初始化（`me --name {guide}` 就是认领框架自带的引导员）。", guide=guide)]
    if ob.get("complete"):
        return [i18n.t("初次安装已完成（{p0}）；要看进度用 `agentctl.py onboard status`，重来用 `onboard reset`。",
                       p0=str(ob.get('completed_at', ''))[:16])]
    out = onboard_status_lines()
    out.append(i18n.t("引导没做完就退过：继续就接着做下一步，重来用 `agentctl.py onboard reset`，暂不处理就先放着。"))
    return out

# ------------------------------------------- 个人待办清单（档案 todo[]，与项目任务板分家）
#
# 2026-10-17（用户要求）：agent 自己的细粒度待办也存在档案里（`todo[]`），原先只能靠通用 `json add`
# 手拼对象。这里给一套专用动作，写操作仍走 `mutate_agent`（flock 原子改）。
# 与 `todo` 子命令的分工：`todo` = **项目任务板**（`state/todo.json`，可被别人认领）；
# `task` = **我这个 agent 的私人清单**（`multiagents/<agent>.json` 的 `todo[]`，不共享、不认领）。

TASK_STATES = ("todo", "doing", "done", "dropped")
TASK_MARKS = {"done": "x", "dropped": "-"}
TASK_SET = {"done": "done", "doing": "doing", "drop": "dropped"}


def next_task_id(agent: dict) -> str:
    nums = [int(m.group(1)) for t in (agent.get("todo") or [])
            if (m := re.match(r"a(\d+)$", str(t.get("id", ""))))]
    return f"a{max(nums) + 1}" if nums else "a1"


def find_task(agent: dict, ref):
    return next((t for t in (agent.get("todo") or []) if str(t.get("id")) == str(ref)), None)


def apply_task(agent: dict, action: str, rest: list, board=None, state=None) -> tuple:
    """个人清单的写动作；返回 (ok, msg)，供 mutate_agent 用。"""
    lst = agent.setdefault("todo", [])
    if action == "add":
        if not rest:
            return False, i18n.t("task add 需要任务文本")
        t = {"id": next_task_id(agent), "task": " ".join(rest),
             "state": state or "todo", "updated": now_min()}
        if board:
            t["board"] = board
        lst.append(t)
        return True, i18n.t("已加 {p0}", p0=t['id']) + (i18n.t("（关联项目板 {board}）", board=board) if board else "")
    if not rest:
        return False, i18n.t("task {action} 需要任务号（`task list` 看现有）", action=action)
    t = find_task(agent, rest[0])
    if t is None:
        return False, i18n.t("没有这个任务号：{p0}（`task list` 看现有）", p0=rest[0])
    if action == "set":
        if len(rest) < 2:
            return False, i18n.t("task set 需要：<任务号> <新文本>")
        t["task"], t["updated"] = " ".join(rest[1:]), now_min()
        return True, i18n.t("{p0} 文本已改", p0=t['id'])
    if action in TASK_SET:
        t["state"], t["updated"] = TASK_SET[action], now_min()
        return True, f"{t['id']} → {t['state']}"
    if action == "rm":
        lst.remove(t)
        return True, i18n.t("{p0} 已删", p0=t['id'])
    return False, i18n.t("未知动作：{action}", action=action)


def cmd_task(args) -> int:
    """个人待办清单：list / add / doing / done / drop / set / rm。"""
    agent, msg = resolve_agent(getattr(args, "name", None), write=args.action != "list")
    if agent is None:
        print(msg, file=sys.stderr)
        return 2
    if msg and getattr(args, "name", None):
        print(i18n.t("注意：{msg}", msg=msg), file=sys.stderr)
    if args.action == "list":
        rows = agent.get("todo") or []
        if not rows:
            print(i18n.t("{p0} 的个人清单是空的；加一条：`agentctl.py task add \"…\"`", p0=agent['name']))
        for t in rows:
            extra = i18n.t("｜关联项目板 {p0}", p0=t['board']) if t.get("board") else ""
            print(i18n.t(
                      "  [{p0}] {p1:<4} {p2:<8} {p3}{extra}｜{p5}",
                      p0=TASK_MARKS.get(t.get('state'), ' '),
                      p1=str(t.get('id')),
                      p2=t.get('state', 'todo'),
                      p3=t.get('task', ''),
                      extra=extra,
                      p5=t.get('updated', ''),))
        mine = [it for it in load_board().get("items", []) if it.get("owner") == agent["name"]]
        if mine:
            print(i18n.t("  （项目板上有 {p0} 项在我名下：`agentctl.py todo list --owner {p1}`）", p0=len(mine), p1=agent['name']))
        return 0
    ok, out = mutate_agent(agent["name"], lambda a: apply_task(
        a, args.action, list(getattr(args, "rest", None) or []),
        board=getattr(args, "board", None), state=getattr(args, "state", None)))
    print(f"{agent['name']}.json: {out}" if ok else out, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def _file_input(inline, path, what: str) -> str:
    """取文本：`<what>-file` 优先（`-` = stdin），否则用行内短文本。"""
    if path == "-":
        return sys.stdin.read()
    if path:
        return Path(path).read_text(encoding="utf-8")
    if inline is None:
        raise SystemExit(i18n.t("{what} 缺失：短文本用 {what} \"…\"，长文本用 {what}-file <文件|->", what=what))
    return inline


def _file_save(target: Path, after: str, before: str, args, op: str) -> None:
    """落盘（除非 --dry-run）并打印一行结果；顺带提醒谁也在改这个文件。"""
    if not args.dry_run:
        if target.exists() and not target.is_file():
            raise SystemExit(i18n.t("目标不是普通文件：{target}", target=target))
        atomic_write(target, after)
        log_edit(op, target, before, after)
    mark = "[dry-run] " if args.dry_run else ""
    print(i18n.t("{mark}{op} {p2}｜行 {p3} → {p4}", mark=mark, op=op, p2=rel_key(target), p3=before.count(chr(10)), p4=after.count(chr(10))))
    if args.diff:
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=1):
            if line[:1] in "+-" and not line.startswith(("+++", "---")):
                print("  " + line)
    others = claimants(target, skip=agent_label())
    if others:
        print(i18n.t("  注意：{p0} 也 claims 了这个路径", p0='、'.join(others)))


def file_locks() -> int:
    """谁占着锁 + 最近的编辑留痕。"""
    if not LOCKS_DIR.exists():
        print(i18n.t("还没有锁目录（说明没人用过 file 子命令）"))
        return 0
    files = sorted(LOCKS_DIR.glob("*.lock"))
    print(i18n.t("锁文件 {p0} 个（flock 随进程退出自动释放，「已释放」只剩历史信息）", p0=len(files)))
    for p in files:
        lines = p.read_text(encoding="utf-8").strip().splitlines() or [""]
        last = lines[-1] or i18n.t("（空）")
        fields = last.split("|", 3)
        state = held_by(ROOT / fields[3]) if len(fields) == 4 else ""
        print(f"  {'占用中' if state else '已释放'}  {last}")
    if EDIT_LOG.exists():
        rows = [r for r in EDIT_LOG.read_text(encoding="utf-8").splitlines() if r.strip()]
        print(i18n.t("编辑留痕 {p0} 条（{p1}），最近 3 条：", p0=len(rows), p1=EDIT_LOG.relative_to(ROOT)))
        for r in rows[-3:]:
            d = json.loads(r)
            print(i18n.t(
                      "  {p0} {p1:12} {p2:6} {p3}（行 {p4}→{p5}）",
                      p0=d['t'][11:16],
                      p1=d['agent'],
                      p2=d['op'],
                      p3=d['path'],
                      p4=d['lines'][0],
                      p5=d['lines'][1],))
    return 0


def cmd_file(args) -> int:
    """file 子命令：改「项目通用文件」的加锁接口（edit / write / append / read / locks / who）。"""
    if args.action == "locks":
        return file_locks()
    if not args.path:
        raise SystemExit(i18n.t("file {p0} 要给路径（只有 locks 不用）", p0=args.action))
    target = resolve_repo_path(args.path, args.allow_outside)

    if args.action == "who":
        who = claimants(target, skip=agent_label())
        print(i18n.t("{p0}｜claims 命中：{p1}", p0=rel_key(target), p1='、'.join(who) or '（无）'))
        print(i18n.t("  改法：") + (i18n.t("走 `agentctl.py file` 加锁改") if who else
                           i18n.t("项目通用文件（代码库/脚本/规则/源）→ `agentctl.py file`；自己的产物 → 原生 edit 也行")))
        holder = held_by(target)
        if holder:
            print(i18n.t("  此刻被占用：{holder}", holder=holder))
        return 0

    if args.action == "read":
        if not target.is_file():
            raise SystemExit(i18n.t("文件不存在：{target}", target=target))
        with locked(target, args.timeout, args.wait, shared=True):
            text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        show = lines[args.offset:] if not args.limit else lines[args.offset:args.offset + args.limit]
        for i, line in enumerate(show, start=args.offset + 1):
            print(f"{i}: {line}")
        print(i18n.t("（{p0}：共 {p1} 行，显示 {p2} 行）", p0=rel_key(target), p1=len(lines), p2=len(show)), file=sys.stderr)
        return 0

    if args.action == "edit":
        if not target.is_file():
            raise SystemExit(i18n.t("文件不存在：{target}", target=target))
        old = _file_input(args.old, args.old_file, "--old")
        new = _file_input(args.new, args.new_file, "--new")
        if old == new:
            raise SystemExit(i18n.t("--old 与 --new 相同，无需修改"))
        with locked(target, args.timeout, args.wait):
            before = target.read_text(encoding="utf-8")
            n = before.count(old)
            if n == 0:
                raise SystemExit(i18n.t("{p0} 里没有与 --old 逐字一致的文本（换行/缩进/中文标点要对齐；可先 file read 确认）", p0=rel_key(target)))
            if n > 1 and not args.all:
                raise SystemExit(i18n.t("--old 文本出现 {n} 次：多带几行上下文，或加 --all 全部替换", n=n))
            _file_save(target, before.replace(old, new), before, args, "edit")
        return 0

    content = _file_input(args.content, args.content_file, "--content")      # write / append
    with locked(target, args.timeout, args.wait):
        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        if args.action == "append":
            content = before + ("" if (not before or before.endswith("\n")) else "\n") + content
        _file_save(target, content, before, args, args.action)
    return 0


# ------------------------------------------- 框架初始化自检（init）
#
# 2026-10-17（用户要求）：引导 agent 的档案要覆盖 agent 档案的**全部特性**，且每个特性引用的
# 文件都要有实例。`init` 把这件事变成可检查的不变量：逐档核对字段与其引用的实例是否都在。
# 别人克隆本框架后跑一次 `agentctl.py init`（必要时 --fix），就能知道初始化还缺什么。

def check_agent(a: dict) -> list:
    """核对一档的字段与它引用的实例；返回问题清单（每项一句人话）。"""
    name = a.get("name", "?")
    bad: list = []
    for f in (a.get("claims") or {}).get("files") or []:
        f = str(f)
        hit = glob.glob(str(ROOT / f), recursive=True)
        if not hit and "*" in f:                 # 通配没匹配上：退回查通配符前的目录
            prefix = f.split("*", 1)[0].rstrip("/")
            hit = [prefix] if prefix and (ROOT / prefix).exists() else []
        if not hit:
            bad.append(i18n.t("claims.files 指向的文件不存在：{f}", f=f))
    for m in a.get("memory") or []:
        p = str((m or {}).get("path") or "")
        if not p:
            bad.append(i18n.t("memory[] 有一条没写 path"))
        elif not (ROOT / p).exists():
            bad.append(i18n.t("memory[] 指向的源不存在：{p}", p=p))
    for s in a.get("skills") or []:
        if not (ROOT / "skills" / str(s) / "SKILL.md").exists():
            bad.append(i18n.t("skills[] 里的 skill 不存在：skills/{s}/SKILL.md", s=s))
    for art in a.get("artifacts") or []:
        if not (ROOT / str(art)).exists():
            bad.append(i18n.t("artifacts[] 指向的文件不存在：{art}", art=art))
    for j in a.get("jobs") or []:
        log = (j or {}).get("log")
        if log and not Path(str(log)).expanduser().exists():
            bad.append(i18n.t("jobs[{p0}] 的日志不存在：{log}", p0=j.get('name'), log=log))
    ids = [t.get("id") for t in a.get("todo") or []]
    for t in a.get("todo") or []:
        if not t.get("id") or not t.get("task"):
            bad.append(i18n.t("todo[] 有条目缺 id 或 task"))
    if len(ids) != len(set(ids)):
        bad.append(i18n.t("todo[] 的任务号有重复"))
    items = {i.get("id") for i in load_board().get("items", [])}
    for it in a.get("board") or []:
        if it not in items:
            bad.append(i18n.t("board[] 认领的板子条目不存在：{it}", it=it))
    for sess in a.get("sessions") or []:
        if not sess.get("session_id"):
            bad.append(i18n.t("sessions[] 有条目缺 session_id"))
    return [f"{name}: {b}" for b in bad]


def cmd_init(args) -> int:
    """框架初始化自检：核对各档字段引用的实例（文件/源/板子/skill/日志/临时目录）。"""
    agents = load_agents()
    if not agents:
        print(i18n.t("名册为空：先跑 `agentctl.py new <角色>` 建一个 agent"), file=sys.stderr)
        return 2
    problems: list = []
    for a in agents:
        tmp = Path(str((a.get("claims") or {}).get("tmp") or f"/tmp/{a.get('name')}"))
        if not tmp.is_dir():
            if args.fix:
                tmp.mkdir(parents=True, exist_ok=True)
                print(i18n.t("  已建临时目录 {tmp}", tmp=tmp))
            else:
                problems.append(i18n.t("{p0}: claims.tmp 目录不存在：{tmp}（--fix 可自动建）", p0=a.get('name'), tmp=tmp))
        for j in a.get("jobs") or []:                    # 作业日志：新克隆上必然还不存在，--fix 一并建出来
            log = str((j or {}).get("log") or "")
            if log and not Path(log).expanduser().exists() and args.fix:
                lp = Path(log).expanduser()
                lp.parent.mkdir(parents=True, exist_ok=True)
                lp.touch()
                print(i18n.t("  已建作业日志 {log}", log=log))
        problems += check_agent(a)
    n_skill = len(list((ROOT / "skills").glob("*/SKILL.md")))
    print(i18n.t(
              "名册 {p0} 档｜板子 {p1} 项｜skill 源 {n_skill} 个｜记忆档 {p3} 个",
              p0=len(agents),
              p1=len(load_board().get('items', [])),
              n_skill=n_skill,
              p3=len(list((ROOT / 'multiagents/state/memory').rglob('*.json'))),))
    if problems:
        print(i18n.t("发现 {p0} 处不一致：", p0=len(problems)))
        for p in problems:
            print(f"  ✗ {p}")
        print(i18n.t("（改完再跑一次；字段含义见记忆档 others/first_run 的字段表）"))
        return 1
    print(i18n.t("✓ 各档字段引用的实例都在：claims / memory / skills / artifacts / jobs / todo / board / sessions"))
    return 0


def spawn_summary(name: str) -> int:
    """生成/预建后的摘要（不打印身份卡——身份卡是给"它自己"用的）。"""
    b = find_agent(name) or {}
    print(i18n.t("已生成 {name}（角色 {p1}：{p2}）—— 这是**另一个** agent，本会话未登记到它", name=name, p1=b.get('role', ''), p2=b.get('display', '')))
    print(f"  skills : {'、'.join(b.get('skills') or []) or '（空）'}")
    print(f"  focus  : {b.get('focus') or '（空）'}")
    print(f"  tmp    : /tmp/{name}")
    print(i18n.t("  它启动后跑 `agentctl.py me` 会自己登记会话，并读到上面的 focus / skills"))


def cmd_spawn(args) -> int:
    """生成**另一个** agent（不是我）：建档 + 注入 skills + /tmp/<agent>/，**不**登记当前会话。

    与 `new` 的分工：`new` = 我 = 这个新档；`spawn` = 我造出一个别的身份（子 agent / 分身），
    它的客户端与会话由它自己 `me` 时登记。`new --no-attach` 与 `spawn` 等价。
    """
    me = current_agent()
    by = me["name"] if me else detect_client()["client"]
    name = args.name or f"{next_index()}_{args.role}"
    rc = cmd_register(argparse.Namespace(name=name, role=args.role, display=args.display,
                                         client=None, focus=getattr(args, "focus", None)))
    if rc:
        return rc
    skills = list(getattr(args, "skill", None) or [])
    note = getattr(args, "handoff", None)

    def _stamp(a: dict):
        a["client"] = ""                      # 它的客户端由它自己 me 时登记
        a["created_by"] = by
        a["skills"] = list(dict.fromkeys((a.get("skills") or []) + skills))
        add_history(a, i18n.t("由 {by} 生成（角色 {p1}）", by=by, p1=args.role))
        return True, f"created_by ← {by}"

    mutate_agent(name, _stamp)
    if me:
        def _tell(a: dict):
            add_history(a, i18n.t("生成 agent {name}（角色 {p1}）", name=name, p1=args.role))
            if note:
                a["handoff"] = note           # 我的 handoff = 交给它的说明；它会读到
            return True, i18n.t("已记录")
        mutate_agent(me["name"], _tell)
    elif note:
        print(i18n.t("注意：无法判定当前 agent，--handoff 未写入任何档"), file=sys.stderr)
    if not getattr(args, "no_tmp", False):
        Path(f"/tmp/{name}").mkdir(parents=True, exist_ok=True)
    return spawn_summary(name)


def cmd_new(args) -> int:
    """「新增一个 agent」分支：建档 + 登记 + 临时目录 + 身份卡。"""
    name = args.name or f"{next_index()}_{args.role}"
    rc = cmd_register(argparse.Namespace(name=name, role=args.role, display=args.display,
                                         client=None, focus=getattr(args, "focus", None)))
    if rc:
        return rc
    if getattr(args, "no_attach", False):        # = spawn 语义：只把档建出来
        if getattr(args, "skill", None):
            mutate_agent(name, lambda a: (True, upsert_skills(a, args.skill)))
        if not getattr(args, "no_tmp", False):
            Path(f"/tmp/{name}").mkdir(parents=True, exist_ok=True)
        return spawn_summary(name)
    cmd_attach(argparse.Namespace(name=name, client=None, status=None, title=None))
    if getattr(args, "skill", None):
        mutate_agent(name, lambda a: (True, upsert_skills(a, args.skill)))
    if not getattr(args, "no_tmp", False):
        tmp = Path(f"/tmp/{name}")
        tmp.mkdir(parents=True, exist_ok=True)
        print(i18n.t("已建临时目录: {tmp}（AGENTS.md：临时文件一律放这里）", tmp=tmp))
    return cmd_me(argparse.Namespace(name=name))



JSON_ACTIONS = ("get", "set", "add", "remove", "history", "touch",
                "memory", "job", "handoff", "artifact")


def cmd_lang(args) -> int:
    """查看/设置输出语言。持久设置写在 state/settings.json（源），`--lang` 只影响本次运行。"""
    code = (getattr(args, "code", None) or "").strip()
    if not code:
        print(i18n.t("当前输出语言：{p0}", p0=i18n.lang()))
        print(i18n.t("可选：{p0}", p0=", ".join(i18n.available())))
        inst = [c for c in i18n.available() if c != i18n.DEFAULT]
        if inst:
            print(i18n.t("已装翻译目录：{p0}", p0=", ".join(inst)))
        else:
            print(i18n.t("还没有翻译目录（zh 是源语言，不需要目录）"))
        print(i18n.t("换语言：python3 multiagents/agentctl.py lang en"))
        return 0
    if code not in i18n.available():
        print(i18n.t("没有 {p0} 的翻译目录；先建骨架：python3 multiagents/i18n_extract.py --new {p0}", p0=code),
              file=sys.stderr)
        return 2
    cfg = {}
    if SETTINGS_JSON.exists():
        try:
            cfg = json.loads(SETTINGS_JSON.read_text(encoding="utf-8") or "{}")
        except ValueError:
            cfg = {}
    cfg["lang"] = code
    with locked(SETTINGS_JSON):
        atomic_write(SETTINGS_JSON, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    i18n.init(code)
    print(i18n.t("输出语言已设为 {p0}（写在 multiagents/state/settings.json）", p0=code))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=i18n.t("多 agent 并行工作流 CLI（统一入口）"))
    sub = p.add_subparsers(dest="cmd", required=True)
    p.add_argument("--lang", metavar="CODE",
                   help=i18n.t("本次运行临时改用某语言的输出（zh/ja/en…）；持久设置走 `lang` 子命令"))

    r = sub.add_parser("roster", help=i18n.t("打印名册与匹配建议（判定身份先跑它）"))
    r.add_argument("--markdown", action="store_true", help=i18n.t("输出 Markdown 表（刷新 README 名册用）"))
    r.set_defaults(func=cmd_roster)
    sub.add_parser("whoami", help=i18n.t("roster 的别名")).set_defaults(func=cmd_roster, markdown=False)

    cd = sub.add_parser("card", help=i18n.t("只读打印某 agent 的工作状态（不登记会话、不改档）"))
    cd.add_argument("name", nargs="?", help=i18n.t("agent 名；省略则用当前会话匹配到的档案"))
    cd.set_defaults(func=cmd_card)

    g = sub.add_parser("register", help=i18n.t("新建 agent 档案"))
    for f in ("--role", "--name", "--display", "--focus", "--client"):
        g.add_argument(f)
    g.set_defaults(func=cmd_register)

    rn = sub.add_parser("rename", help=i18n.t("改 agent 名字（档名 + name + 源引用；叙述文字只提示）"))
    rn.add_argument("old", help=i18n.t("现名（档案里的 name）"))
    rn.add_argument("new", help=i18n.t("新名（建议 <两位序号>_<角色>）"))
    rn.set_defaults(func=cmd_rename)

    a = sub.add_parser("attach", help=i18n.t("把当前客户端与会话登记到某个 agent 档案"))
    for f in ("--name", "--title", "--status", "--client"):
        a.add_argument(f, required=(f == "--name"))
    a.set_defaults(func=cmd_attach)

    t = sub.add_parser("todo", help=i18n.t("项目任务板（源 state/todo.json；个人清单用 task）"))
    t.add_argument("action", choices=["list", "add", "claim", "done", "release", "note",
                                      "export", "verify", "topic"])
    t.add_argument("id", nargs="?", help=i18n.t("任务号（如 1.3）；add 时是描述；topic 时是 add"))
    t.add_argument("text", nargs="?", help=i18n.t("note/topic add 的文本"))
    t.add_argument("--topic", type=int, help=i18n.t("add：主题号（须已登记）；list：只列该主题"))
    t.add_argument("--owner", help=i18n.t("add：认领人；list：只列该 agent 认领的条目"))
    t.add_argument("--state", help=i18n.t("add：初始状态（默认 todo）；list：只列该状态"))
    t.add_argument("--force", action="store_true")
    t.add_argument("--write", action="store_true", help=i18n.t("export 用：写入 TODO.md"))
    t.set_defaults(func=cmd_todo)

    j = sub.add_parser("json", help=i18n.t("读写 agent 档案（所有 json 操作都在这里）"))
    j.add_argument("action", choices=list(JSON_ACTIONS), help=i18n.t("要做的动作"))
    j.add_argument("path", nargs="?", help=i18n.t("点路径 / 列表路径 / 事件文本（见文件头用法）"))
    j.add_argument("value", nargs="?")
    j.add_argument("--name", help=i18n.t("默认=当前会话匹配到的档案"))
    j.add_argument("--key", help=i18n.t("add 到对象列表时按该字段 upsert"))
    j.add_argument("--index", type=int, help=i18n.t("remove 用下标"))
    j.add_argument("--where", help=i18n.t("remove 的条件，形如 name=<工具名>"))
    j.add_argument("--role", help=i18n.t("memory 归属：maintainer / contributor"))
    j.add_argument("--pid", type=int, help=i18n.t("job 的 pid"))
    j.add_argument("--log", help=i18n.t("job 的日志路径"))
    j.add_argument("--note", help=i18n.t("job 的备注"))
    j.set_defaults(func=cmd_json)

    mm = sub.add_parser("memory", help=i18n.t("记忆正文（源 multiagents/state/memory/**/*.json，视图 memory/**/*.md）"))
    mm.add_argument("action", choices=["list", "show", "new", "import", "append", "set",
                                       "drop", "export", "verify"])
    mm.add_argument("id", nargs="?", help=i18n.t("档 id（如 <项目>/<档名>）；import 时是 md 路径"))
    mm.add_argument("--doc", help=i18n.t("import 用：目标档 id（源文件在 memory/ 外时必填）"))
    mm.add_argument("--section", help=i18n.t("节：编号（03）或标题"))
    mm.add_argument("--preamble", action="store_true", help=i18n.t("set 用：改档前言（正文用 --text/--file）"))
    mm.add_argument("--title", help=i18n.t("new/set 用：档标题；set 带 --section 时改该节标题"))
    mm.add_argument("--text", help=i18n.t("正文（短文；仿 git commit -m）"))
    mm.add_argument("--file", help=i18n.t("正文文件（长文首选，仿 git commit -F；\"-\" 读 stdin）"))
    mm.add_argument("--agent", help=i18n.t("写入归属的 agent，默认=当前会话匹配到的"))
    mm.add_argument("--owner", help=i18n.t("import 用：把归属登记进该 agent 档案的 memory[]"))
    mm.add_argument("--role", help=i18n.t("import 用：归属角色（maintainer/contributor/author）"))
    mm.add_argument("--sections", action="store_true", help=i18n.t("list 用：列出各节"))
    mm.add_argument("--all", action="store_true", help=i18n.t("export/verify 用：所有档 + MEMORY.md"))
    mm.add_argument("--write", action="store_true")
    mm.add_argument("--force", action="store_true")
    mm.set_defaults(func=cmd_memory)

    m = sub.add_parser("memory-index", help=i18n.t("生成/打印 memory/MEMORY.md 索引"))
    m.add_argument("--write", action="store_true")
    m.set_defaults(func=cmd_memory_index)

    rp = sub.add_parser("quick-report", aliases=["report"],
                        help=i18n.t("进展简报（用户问「在做什么」时写一份到 output/quick-report/；与 output/<主题>/report/ 的研究报告分开）"))
    rp.add_argument("--name", help=i18n.t("归属 agent（默认本会话匹配到的档）"))
    rp.add_argument("--text", help=i18n.t("简报正文（短文本，仿 git commit -m）"))
    rp.add_argument("--file", help=i18n.t("简报正文文件（长文本，--file - 读 stdin，仿 git commit -F）"))
    rp.add_argument("--list", action="store_true", help=i18n.t("只列已有简报，不生成"))
    rp.add_argument("--no-appendix", action="store_true",
                    help=i18n.t("不追加生成的「个人待办 / 名下板项」附录"))
    rp.add_argument("--limit", type=int, default=20, help=i18n.t("--list 显示条数（默认 20）"))
    rp.set_defaults(func=cmd_report)

    me = sub.add_parser("me", help=i18n.t("获取当前 agent（会话匹配→自动登记→身份卡；未识别则给名册与三选项）"))
    me.add_argument("--name", help=i18n.t("用户点名时指定档名（不指定则按当前会话匹配）"))
    me.set_defaults(func=cmd_me)

    nw = sub.add_parser("new", help=i18n.t("新增一个 agent 档案并登记（建档+登记+临时目录+身份卡）"))
    nw.add_argument("role", help=i18n.t("角色短标识，如 analyst / reviewer"))
    nw.add_argument("--name", help=i18n.t("档名（默认 <序号>_<角色>）"))
    nw.add_argument("--display", help=i18n.t("中文职责描述（身份卡里显示）"))
    nw.add_argument("--focus", help=i18n.t("当前焦点（默认空）"))
    nw.add_argument("--skill", action="append", help=i18n.t("该 agent 该用的 skill ID（可重复）"))
    nw.add_argument("--no-attach", action="store_true", help=i18n.t("只把档建出来，不登记当前会话（等价 spawn）"))
    nw.add_argument("--no-tmp", action="store_true", help=i18n.t("不建 /tmp/<agent>/ 临时目录"))
    nw.set_defaults(func=cmd_new)

    sp = sub.add_parser("spawn", help=i18n.t("生成另一个 agent（建档+注入 skills+临时目录，不登记当前会话）"))
    sp.add_argument("role", help=i18n.t("角色短标识，如 helper"))
    sp.add_argument("--name", help=i18n.t("档名（默认 <序号>_<角色>）"))
    sp.add_argument("--display", help=i18n.t("中文职责描述"))
    sp.add_argument("--focus", help=i18n.t("给它设的初始焦点"))
    sp.add_argument("--skill", action="append", help=i18n.t("注入的 skill ID（可重复）"))
    sp.add_argument("--handoff", help=i18n.t("同时把我的 handoff 写成交给它的说明（覆盖我原 handoff）"))
    sp.add_argument("--no-tmp", action="store_true", help=i18n.t("不建 /tmp/<agent>/"))
    sp.set_defaults(func=cmd_spawn)

    tk = sub.add_parser("task", help=i18n.t("我自己的待办清单（写档案 todo[]；项目任务板是 todo）"))
    tk.add_argument("action", choices=("list", "add", "doing", "done", "drop", "set", "rm"))
    tk.add_argument("rest", nargs="*", help=i18n.t("add: <文本>；set: <任务号> <新文本>；其余: <任务号>"))
    tk.add_argument("--board", help=i18n.t("add 时关联项目板号（如 2.1）"))
    tk.add_argument("--state", choices=TASK_STATES, help=i18n.t("add 时的初始状态（默认 todo）"))
    tk.add_argument("--name", help=i18n.t("改谁的档（默认本会话匹配到的）"))
    tk.set_defaults(func=cmd_task)

    ob = sub.add_parser("onboard", help=i18n.t("初次安装进度（源 state/first_run.json）：status / step / reset / finish"))
    ob.add_argument("action", choices=("status", "step", "reset", "finish"),
                    help=i18n.t("status=看进度 / step=记一步 / reset=清零重来 / finish=标记完成"))
    ob.add_argument("step", nargs="?", help=i18n.t("step 用：第几步（1–8）"))
    ob.add_argument("state", nargs="?", help=i18n.t("step 用：todo / doing / done / skip"))
    ob.set_defaults(func=cmd_onboard)

    it = sub.add_parser("init", help=i18n.t("框架初始化自检：核对各档字段引用的实例是否都在"))
    it.add_argument("--fix", action="store_true", help=i18n.t("顺带创建缺失的 /tmp/<agent>/"))
    it.set_defaults(func=cmd_init)

    fp = sub.add_parser("file", help=i18n.t("改项目通用文件的加锁接口（读—改—写在同一把锁里）"))
    fp.add_argument("action", choices=("edit", "write", "append", "read", "locks", "who"),
                    help=i18n.t("edit=精确替换 / write=整文件 / append=追加 / read=共享锁读 / locks / who"))
    fp.add_argument("path", nargs="?", help=i18n.t("仓库内相对路径（locks 不用）"))
    fp.add_argument("--old", help=i18n.t("要被替换的文本（edit）"))
    fp.add_argument("--old-file", help=i18n.t("旧文本文件（- = stdin）"))
    fp.add_argument("--new", help=i18n.t("替换成的文本"))
    fp.add_argument("--new-file", help=i18n.t("新文本文件（- = stdin）"))
    fp.add_argument("--all", action="store_true", help=i18n.t("--old 匹配多处时全部替换"))
    fp.add_argument("--content", help=i18n.t("内容（write / append）"))
    fp.add_argument("--content-file", help=i18n.t("内容文件（- = stdin）"))
    fp.add_argument("--offset", type=int, default=0, help=i18n.t("read：从第几行开始（0 基）"))
    fp.add_argument("--limit", type=int, help=i18n.t("read：显示多少行"))
    fp.add_argument("--timeout", type=float, default=30.0, help=i18n.t("等锁秒数（默认 30，0=立刻失败）"))
    fp.add_argument("--wait", action="store_true", help=i18n.t("不限时等锁"))
    fp.add_argument("--dry-run", action="store_true", help=i18n.t("只预演，不落盘"))
    fp.add_argument("--diff", action="store_true", help=i18n.t("打印改动的行"))
    fp.add_argument("--allow-outside", action="store_true", help=i18n.t("允许操作仓库外的文件"))
    fp.set_defaults(func=cmd_file)
    lg = sub.add_parser("lang", help=i18n.t("查看/设置输出语言（持久写入 state/settings.json）"))
    lg.add_argument("code", nargs="?", help=i18n.t("语言代码；省略则只查看当前与可选语言"))
    lg.set_defaults(func=cmd_lang)

    return p


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "lang", None):
        i18n.init(args.lang)
    try:
        return args.func(args)
    except LockTimeout as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
