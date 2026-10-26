#!/usr/bin/env python3
"""框架自检测试（stdlib unittest；**只读**：不写板子、不写记忆、不改档案）。

跑法（在仓库根）：

    python3 multiagents/.tests/test_framework.py
    python3 -m unittest discover -s multiagents/.tests -t multiagents/.tests

三类覆盖：
  1. 框架不变量：`init`、`todo verify`、`memory verify --all`、skill 镜像 `sync_skills.py --check`。
  2. 只读面：`card`、`todo list` 的 `--owner/--topic/--state` 过滤、读路径不打写提醒、
     「`card` 不改任何源」（跑完比对所有源 json 的内容）。
  3. 档案字段引用：`claims.files` / `memory[].path` / `skills[]` / `artifacts[]` / `board[]`
     指向的实例都在（与 `init` 同口径，精确到字段名报错）。

约定：只用标准库；不依赖任何具体项目名（agent 名、主题号、条目都从源现取），
因此同一份测试在任意克隆（含去项目专有的开源模板）里都能跑。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]           # multiagents/.tests/<file>.py → 仓库根
CTL = str(REPO / "multiagents" / "agentctl.py")
BOARD = REPO / "multiagents" / "state" / "todo.json"
NOBODY = "99_no_such_agent"                           # 名册里不可能有的名字


def _env() -> dict:
    """子进程环境：测试固定用中文输出（输出语言存在 state/settings.json，测试要确定性）。"""
    env = dict(os.environ)
    env["AGENTCTL_LANG"] = "zh"
    return env


def ctl(*args: str) -> subprocess.CompletedProcess:
    """跑 agentctl（cwd = 仓库根）。"""
    return subprocess.run([sys.executable, CTL, *args], cwd=REPO,
                          capture_output=True, text=True, env=_env())


def board() -> dict:
    return json.loads(BOARD.read_text(encoding="utf-8"))


def items() -> list:
    return board().get("items", [])


def agent_names() -> list:
    """名册：multiagents/*.json 里带 name 键的档（与 agentctl 的判定同口径）。"""
    out = []
    for p in sorted((REPO / "multiagents").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("name"):
            out.append(d["name"])
    return out


def owner_with_items() -> str | None:
    c = Counter(i.get("owner") for i in items() if i.get("owner") not in (None, "-", ""))
    return c.most_common(1)[0][0] if c else None


def rows_of(stdout: str) -> list:
    """`todo list` / `task list` 的条目行（含「认领:」的行）。"""
    return [l for l in stdout.splitlines() if "认领:" in l]


def truths() -> dict:
    """所有源 json 的内容快照（验证「只读命令没改档」）。"""
    out = {}
    for p in sorted((REPO / "multiagents").rglob("*.json")):
        if p.suffix != ".json" or "state/locks" in p.as_posix():
            continue
        out[p.relative_to(REPO).as_posix()] = p.read_text(encoding="utf-8")
    return out


class Invariants(unittest.TestCase):
    """框架不变量：源 ↔ 视图一致、字段引用完整。"""

    def test_init_all_instances_present(self):
        """`init` 的持久化引用必须全在。

        ⚠️ `init` 还会检查 `claims.tmp` 目录与 `jobs[].log` —— 那是 **/tmp 上的运行时状态**，
        每次重启/清理就没了，不是框架数据缺陷。所以这里**先跑 `--fix` 建出这两类临时物**，
        再断言 `init` 干净；否则测试会在每次重启后假失败（历史上就是这样）。
        `--fix` 只建缺失的 `/tmp/<agent>/` 与作业日志，不动任何源
        （`test_card_writes_nothing` 另有源比对兜底）。
        """
        fix = ctl("init", "--fix")
        self.assertEqual(fix.returncode, 0, fix.stdout + fix.stderr)
        p = ctl("init")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_todo_view_matches_truth(self):
        p = ctl("todo", "verify")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_memory_views_match_truth(self):
        p = ctl("memory", "verify", "--all")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_skill_mirrors_in_sync(self):
        p = subprocess.run([sys.executable, str(REPO / "multiagents" / "sync_skills.py"),
                            "--check"], cwd=REPO, capture_output=True, text=True, env=_env())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_translation_catalogs_complete(self):
        """locales/*.json：每条 msgid 都有译文，且占位符（名 + 格式说明符 + 转换符）与原文逐字一致。"""
        sys.path.insert(0, str(REPO / "multiagents"))
        import i18n_extract
        ids = i18n_extract.msgids()
        for path in sorted((REPO / "multiagents" / "locales").glob("*.json")):
            cat = json.loads(path.read_text(encoding="utf-8"))
            missing = [m for m in ids if not str(cat.get(m, "")).strip()]
            self.assertEqual(missing, [], f"{path.name}: {len(missing)} 条未译，如 {missing[:2]}")
            bad = [m for m in ids if cat.get(m)
                   and i18n_extract.placeholders(m) != i18n_extract.placeholders(cat[m])]
            self.assertEqual(bad, [], f"{path.name}: {len(bad)} 条占位符不一致，如 {bad[:2]}")

    def test_roster_lists_every_archive(self):
        names = agent_names()
        self.assertTrue(names, "名册为空：先 `agentctl.py new <角色>`")
        p = ctl("roster")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for n in names:
            self.assertIn(n, p.stdout, f"roster 没列出 {n}")

    def test_board_item_ids_unique(self):
        ids = [i["id"] for i in items()]
        self.assertEqual(len(ids), len(set(ids)), "板子条目号有重复")

    def test_agent_field_refs_exist(self):
        """档案引用的文件 / skill / 板项都得在（报错带 agent 名与字段）。"""
        ids = {i["id"] for i in items()}
        for p in sorted((REPO / "multiagents").glob("*.json")):
            a = json.loads(p.read_text(encoding="utf-8"))
            name = a.get("name")
            if not name:
                continue
            with self.subTest(agent=name):
                for f in (a.get("claims") or {}).get("files") or []:
                    hits = list(REPO.glob(str(f)))
                    if not hits and "*" in str(f):        # 通配没命中：退回查前缀目录（同 init）
                        prefix = str(f).split("*", 1)[0].rstrip("/")
                        hits = [prefix] if prefix and (REPO / prefix).exists() else []
                    self.assertTrue(hits, f"claims.files 指向的文件不存在：{f}")
                for m in a.get("memory") or []:
                    self.assertTrue((REPO / str(m.get("path"))).exists(),
                                    f"memory[] 指向的源不存在：{m.get('path')}")
                for s in a.get("skills") or []:
                    self.assertTrue((REPO / "skills" / str(s) / "SKILL.md").exists(),
                                    f"skills[] 里的 skill 不存在：skills/{s}/SKILL.md")
                for art in a.get("artifacts") or []:
                    self.assertTrue((REPO / str(art)).exists(),
                                    f"artifacts[] 指向的文件不存在：{art}")
                for it in a.get("board") or []:
                    self.assertIn(it, ids, f"board[] 认领的板子条目不存在：{it}")


class ReadOnlySurface(unittest.TestCase):
    """只读面：`card` 与 `todo list` 的过滤、读路径不打写提醒。"""

    def test_card_known_agent(self):
        name = agent_names()[0]
        p = ctl("card", name)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(name, p.stdout)
        self.assertIn("在做什么", p.stdout)

    def test_card_without_name(self):
        """无参 = 当前会话匹配到的档：匹配到 exit 0，匹配不到 exit 2（正常分支）。"""
        p = ctl("card")
        self.assertIn(p.returncode, (0, 2), p.stdout + p.stderr)

    def test_card_unknown_agent_exits_2(self):
        p = ctl("card", NOBODY)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("名册里没有", p.stderr)

    def test_me_unknown_name_exits_2(self):
        p = ctl("me", "--name", NOBODY)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_card_writes_nothing(self):
        before = truths()
        for n in agent_names():
            ctl("card", n)
        self.assertEqual(before, truths(), "`card` 不该改任何源")

    def test_todo_list_owner_filter(self):
        who = owner_with_items()
        if not who:
            self.skipTest("板子上还没有被认领的条目")
        p = ctl("todo", "list", "--owner", who)
        self.assertEqual(p.returncode, 0, p.stderr)
        expect = [i for i in items() if i.get("owner") == who]
        self.assertEqual(len(rows_of(p.stdout)), len(expect),
                         f"--owner {who} 应列出 {len(expect)} 项")
        for line in rows_of(p.stdout):
            self.assertIn(f"认领: {who}", line)

    def test_todo_list_topic_filter(self):
        if not items():
            self.skipTest("任务板为空")
        topic = items()[0]["topic"]
        p = ctl("todo", "list", "--topic", str(topic))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(rows_of(p.stdout)), len([i for i in items() if i["topic"] == topic]))

    def test_todo_list_state_filter(self):
        if not items():
            self.skipTest("任务板为空")
        state = items()[0].get("state") or "todo"
        p = ctl("todo", "list", "--state", state)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(rows_of(p.stdout)),
                         len([i for i in items() if (i.get("state") or "todo") == state]))

    def test_todo_list_combined_filters(self):
        who = owner_with_items()
        if not who:
            self.skipTest("板子上还没有被认领的条目")
        it = next(i for i in items() if i.get("owner") == who)
        state = it.get("state") or "todo"
        p = ctl("todo", "list", "--owner", who, "--topic", str(it["topic"]), "--state", state)
        self.assertEqual(p.returncode, 0, p.stderr)
        expect = [i for i in items() if i.get("owner") == who and i["topic"] == it["topic"]
                  and (i.get("state") or "todo") == state]
        self.assertEqual(len(rows_of(p.stdout)), len(expect))

    def test_todo_list_no_match_is_not_error(self):
        p = ctl("todo", "list", "--owner", NOBODY)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("没有匹配的条目", p.stdout)
        self.assertNotIn("── ", p.stdout, "过滤后为空时不该再打印主题标题")

    def test_read_paths_do_not_print_write_warning(self):
        name = agent_names()[0]
        for args in (("json", "get", "focus", "--name", name),
                     ("task", "list", "--name", name)):
            p = ctl(*args)
            self.assertNotIn("确认无误再落盘", p.stdout + p.stderr,
                             f"{' '.join(args)} 是只读路径，不该打写提醒")

    def test_resolve_agent_write_flag(self):
        sys.path.insert(0, str(REPO / "multiagents"))
        import agentctl as a
        me = a.current_agent()
        other = next((n for n in agent_names() if not me or n != me["name"]), None)
        if other is None:
            self.skipTest("名册里只有一个档且就是当前会话档")
        self.assertEqual(a.resolve_agent(other)[1], "", "只读路径不该返回写提醒")
        self.assertIn("确认无误再落盘", a.resolve_agent(other, write=True)[1])
        self.assertIsNone(a.resolve_agent(NOBODY)[0], "名册外的名字必须判为未知")


class Onboard(unittest.TestCase):
    """初次安装进度（state/first_run.json）：status 只读可跑；源与 skill 清单的步骤一致。"""

    def test_status_runs(self):
        p = ctl("onboard", "status")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("/", p.stdout)                      # 「x/8」进度行

    def test_truth_steps_match_skill_list(self):
        """first_run.json 的步骤 id/标题与 skill first-run 的 1–8 清单一致（档不存在则跳过）。"""
        f = REPO / "multiagents" / "state" / "first_run.json"
        if not f.exists():
            self.skipTest("state/first_run.json 还没生成（跑一次 onboard status 即有）")
        ob = json.loads(f.read_text(encoding="utf-8"))
        ids = [str(s.get("id")) for s in ob.get("steps", [])]
        self.assertEqual(ids, [str(i) for i in range(1, 9)])
        skill = (REPO / "skills" / "first-run" / "SKILL.md").read_text(encoding="utf-8")
        for s in ob.get("steps", []):
            self.assertIn(str(s.get("title")), skill,
                          f"步骤标题「{s.get('title')}」应能在 skill first-run 里找到")

if __name__ == "__main__":
    unittest.main(verbosity=2)
