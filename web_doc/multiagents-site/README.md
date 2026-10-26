# multiagents · GitHub Pages 介绍单页

部署：仓库 Settings → Pages → Source 选 `main` 分支根目录即可；访问 `https://<user>.github.io/<repo>/`。

内容：架构背景 + 核心解决问题 + 快速开始（使用者 / AI Agent）+ 目录分工 + agentctl 设计要点 + 技能体系，
三语（`index.html` 中文、`en.html` English、`ja.html` 日本語，顶部切换）。纯静态无外部依赖。
更新流程：改 `index.html` / `en.html` / `ja.html` → commit → push。

## 站点里两段入口的口径（与页面保持同步）

**使用者操作**：`git clone` → `cd` → 启动 Agent 环境（Antigravity、OpenCode、Claude Code 等）。
OpenCode 中输入 `/boot`，Antigravity 会话启动时自动加载规则。引导员 00_yuki 协助完成初始化（交互语言、主题、.env、认领身份）。

**AI Agent 操作**：`git clone` → `cd` → 会话第一步 `python3 multiagents/agentctl.py me`
（自动识别 Antigravity、OpenCode、Claude Code 会话标识，未匹配时列出名册供用户明确选定，不得自行认领）；按身份卡清单加载 skills[]；
首装未完成时一次只问一个问题（第一问确认交互语言），照 skill `first-run` 步骤 1–8 推进。
任务写入走加锁接口（file / todo / memory），收尾运行 `init` / `verify` / `.tests`。
