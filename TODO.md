# 项目任务板（TODO）

> **生成物，勿手改**：源是 `multiagents/state/todo.json`，本文件由
> `python3 multiagents/agentctl.py todo export --write` 重新生成；改动请走脚本（对 JSON 加 `flock`）。
> 每条任务可被任一 agent 认领，认领是唯一的协调动作。
>
> ```bash
> python3 multiagents/agentctl.py todo list
> python3 multiagents/agentctl.py todo claim <主题号.子号> --owner <agent>
> python3 multiagents/agentctl.py todo done  1.3
> python3 multiagents/agentctl.py todo add "新任务" --topic 2
> python3 multiagents/agentctl.py todo note 1.1 "补充说明"
> python3 multiagents/agentctl.py todo export --write      # 重新生成本文件
> python3 multiagents/agentctl.py todo verify             # 检查本文件与源是否漂移
> ```
>
> 格式：`- [ ] **主题号.子号** 描述 ｜ 认领: <agent|-> ｜ 状态: <todo|doing|blocked|paused|done> ｜ 更新: <时间>`；
> 紧跟其后的**缩进子行是备注**（用 `todo note` 维护）。协议见 `multiagents/README.md`。


**主题编号**（源是 `todo.json` 的 `topics`；新增用 `todo topic add "名称"`；不复用、不回收）：

| 主题号 | 主题 | 主责 agent |
| --- | --- | --- |
| 1 | 初始化：填 .env、装依赖、认领身份、建第一个主题 | 00_yuki |

---

## 1. 项目初始化

本主题只放初始化相关的项，全过程见 skill `first-run`（源 `skills/first-run/SKILL.md`）。
做完后用 `todo topic add "主题名" --owner <agent>` 建你自己的研究主题；本板只收「可被多 agent 认领」的粗粒度项。

- [ ] **1.1** 按 skill `first-run` 完成初次安装（自检 → 依赖 → 认领身份 → 建主题） ｜ 认领: 00_yuki ｜ 状态: todo ｜ 更新: 2026-10-17 19:00
  - 默认引导员 00_yuki 认领；各步完成后用 `agentctl.py todo done 1.1` 收尾（视图会同步重导）。

---

## 已完成（归档，不再逐条跟踪）

闭环的条目从板子上摘掉后，把当时的过程细节归档到 `archive/<主题>/`，在此留一行索引：

| 原清单 | 归档位置 |
| --- | --- |
| （示例）根 `TODO.md` 的旧版本 | `archive/<主题>/TODO_root_<日期>.md` |

写到这里的内容会追加在 `TODO.md` 视图末尾；本文件是手写的（不在源 `state/todo.json` 里），
`todo` 子命令不会覆盖它。
