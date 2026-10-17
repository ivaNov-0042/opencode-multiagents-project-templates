# multiagents · GitHub Pages 单页站

部署：仓库 Settings → Pages → Source 选 `main` 分支根目录即可；访问 `https://<user>.github.io/<repo>/`。

内容：hero + 由来（opencode v2 多窗口 TUI 的协同缺口）+ 特性 + 快速开始（写给人类 / 写给 AI）+ 目录分工，
双语（`index.html` 中文、`en.html` English，右上角切换）。纯静态无依赖。
更新流程：改 `index.html` / `en.html` → commit → push。

## 站点里两段入口的口径（与页面保持同步）

**写给人类**：`git clone` → `cd` → `opencode` → 输入 `/boot`（推荐；任何其他输入也会触发引导）。
引导员 yuki 三语提示输入 `init`，之后带你走完 8 步初始化，你只需要回答问题。

**写给 AI（agent）**：`git clone` → `cd` → continue——会话第一步 `python3 multiagents/agentctl.py me`
（命中即自动登记，认不出时列名册让用户选，不得自行认领）；按身份卡「先加载」清单加载 skills[]；
首装未完成时一次只问一个问题（第一问只问输出语言），照 skill `first-run` 步骤 1–8 推进。
目标目录没有本框架时：clone 到子目录后用 Code Mode 的 `session_move` 把会话移进去，无需用户手动 cd。
干活写入走锁（file / todo / memory），收尾跑 `init` / `verify` / `.tests`。
