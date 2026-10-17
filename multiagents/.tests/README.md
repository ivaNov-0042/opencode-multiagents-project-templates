# multiagents/.tests/ —— 框架自检测试

放**框架层面**的测试：不变量（源 ↔ 视图、字段引用完整性）与工具行为（只读面、退出码）。
不放主题研究代码的测试——那些跟各自的 `scripts/<主题>/` 走。

## 跑法（在仓库根）

```bash
python3 multiagents/.tests/test_framework.py                                # 直接跑（verbose）
python3 -m unittest discover -s multiagents/.tests -t multiagents/.tests    # 发现式跑
```

## 约定

- **只用标准库**（`unittest` / `subprocess`），不引入 pytest 等第三方依赖——`agentctl.py` 自身也不依赖第三方。
- **测试只读**：不写板子、不写记忆、不改档案。要验证「某命令不改档」就用前后快照比对
  （`test_card_writes_nothing`），而不是靠人眼。
- **不写具体项目名**：agent 名、主题号、板子条目全部从 `multiagents/state/todo.json` 与
  `multiagents/*.json` 现取，因此同一份测试在任意克隆（含去项目专有的开源模板）里都能跑。
- 断言要落在**机器可判**的量上（行数、退出码、源快照），不要只断言「输出里有某个词」。
- 目录名带点：不放业务代码，也不会被 `agentctl.py` 的档案扫描碰到（它只认 `multiagents/*.json`）。
  **注意** pytest 的默认 `norecursedirs` 含 `.*`，用 pytest 收集要显式给路径或改 ini；
  本目录默认用 stdlib `unittest` 跑，不依赖 pytest。

## 加新测试

在 `test_framework.py` 里加 `TestCase` 方法，或另起 `test_<主题>.py`（同样放本目录、同样只读）。
新测试同样遵守上面两条硬约束：只读、不写项目专有名。
