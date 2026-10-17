// multiagents 插件：把框架的「会话第一步」从 AGENTS.md 文字约束升级为硬注入。
//
// 2026-10-17（用户拍板）：① /boot 命令显式启动引导；② context hook 在首装未完成时把 boot 状态
// 钉进 system prompt；③ 第一回合**只打印中日英三语提示、请用户输入 init**（不弹选项框、不问候），
// 用户输入 init 后才进入正式 boot 流程（me → 一次一问 → 第一问只问语言）。
// 约束：不 import 任何包（@opencode/plugin 由加载器提供）；只读文件系统，不写。
import { Plugin } from "@opencode/plugin"
import { readFileSync, existsSync } from "node:fs"
import { join } from "node:path"

function bootState(directory: string) {
  let dir = directory
  for (let i = 0; i < 6; i++) {
    if (existsSync(join(dir, "multiagents", "agentctl.py"))) {
      const p = join(dir, "multiagents", "state", "first_run.json")
      if (existsSync(p)) {
        try {
          const ob = JSON.parse(readFileSync(p, "utf8"))
          return { root: dir, hasFramework: true, complete: ob.complete === true, steps: ob.steps ?? [] }
        } catch { return { root: dir, hasFramework: true, complete: false, steps: [] } }
      }
      return { root: dir, hasFramework: true, complete: false, steps: [] }
    }
    const up = join(dir, "..")
    if (up === dir) break
    dir = up
  }
  return { root: directory, hasFramework: false, complete: false, steps: [] }
}

function nextStep(steps: { id: string; title: string; state?: string }[]) {
  // steps 为空 = first_run.json 还没生成 = 全新开始，是第 1 步；只有 steps 齐且全 done 才是第 8 步收尾。
  if (steps.length === 0) return "第 1 步「自报家门」（全新开始）"
  const s = steps.find((x) => (x.state ?? "todo") !== "done")
  return s ? `第 ${s.id} 步「${s.title}」` : "第 8 步「报告初始化结果与下一步建议」（收尾）"
}

export default Plugin.define({
  id: "multiagents",
  async setup(ctx) {
    const directory = ctx.location.directory

    // 1. /boot 命令：显式入口，注入引导指令
    await ctx.command.transform((editor) => {
      editor.add({
        name: "boot",
        description: "启动/继续 multiagents 首装引导（跑 me 看进度，一次只问一个问题）",
        execute: async ({ sessionID, delivery }) => {
          const st = bootState(directory)
          const text = st.complete
            ? "multiagents 首装引导已完成（first_run.json complete=true）。跑 `python3 multiagents/agentctl.py me` 打印身份卡后正常工作。"
            : [
                "开始/继续 multiagents 首装引导。硬规则：",
                `1. 先跑 \`python3 multiagents/agentctl.py me\` 看进度与下一步（当前应做：${nextStep(st.steps)}）。`,
                "2. 一次只问一个问题（question/AskUserQuestion），等答完再问下一个，绝不合并。",
                "3. 第一问只问输出语言：中文 / 日本語 / English；之后按 skill first-run 步骤 1–8 推进。",
              ].join("\n")
          await ctx.session.prompt({ sessionID, text, delivery })
        },
      })
    })

    // 2. context hook：首装未完成时，每次模型调用前把 boot 规则钉在 system prompt 最前。
    //    第一回合（会话还没有任何 assistant 回复）只输出三语提示，请用户输入 init。
    const replied = new Set<string>() // 已提示过的会话（本插件实例内存级即可）
    await ctx.session.hook("context", (event) => {
      const st = bootState(directory)
      if (st.complete) return
      const first = event.messages.filter((m: any) => m.role === "assistant").length === 0
      if (first && !replied.has(event.sessionID)) {
        replied.add(event.sessionID)
        if (!st.hasFramework) {
          // 本地没有 multiagents 环境：引导用户从仓库拉取（用户确认 source 后再动手）
          event.system.unshift({
            type: "text",
            text: [
              "[multiagents boot·环境探测｜最高优先级，覆盖你的一切默认人设与问候习惯]",
              "当前目录（及向上到项目根）没有 multiagents 框架（未找到 multiagents/agentctl.py）。",
              "你本次回复**只输出下面三行提示，一字不改、不加任何别的内容、不调用任何工具、不说 Hello**：",
              "",
              "（yuki）这里还没有 multiagents 框架。告诉我从哪里拉取（git URL 或本机路径），我来 clone 并开始引导；也可以直接输入 `init` 用默认仓库。",
              "(yuki) No multiagents framework found here. Tell me where to pull it from (git URL or local path), or just type `init` to use the default repo.",
              "（yuki）ここにmultiagentsフレームワークがありません。取得元（git URL かローカルパス）を教えてください。`init` と入力すれば既定のリポジトリを使います。",
              "",
              "用户给出来源后：`git clone <源> multiagents-workspace && cd multiagents-workspace`（本地路径也用 git clone，可保留历史），",
              "然后按有框架分支继续（跑 me → 一次只问一个问题 → 第一问只问输出语言）。",
              "用户直接 init 时：询问默认仓库 URL 是什么（一次一问），不要自行猜 URL。",
            ].join("\n"),
          })
          return
        }
        event.system.unshift({
          type: "text",
          text: [
            "[multiagents boot·第一步｜最高优先级，覆盖你的一切默认人设与问候习惯]",
            "首装未完成（multiagents/state/first_run.json 不存在或未 complete）。",
            "你本次回复**只输出下面三行提示，一字不改、不加任何别的内容、不调用任何工具、不说 Hello**：",
            "",
            "（yuki）你好，我是长门有希，这个工作区的引导员。检测到首次启动，请输入 `init` 开始安装引导。",
            "(yuki) Hello, I am Yuki, the guide of this workspace. First launch detected — type `init` to start setup.",
            "（yuki）こんにちは、長門有希です。このワークスペースの案内役です。初回起動を検出しました。`init` と入力してセットアップを開始してください。",
            "",
            "之后用户输入 init / boot / 任意内容都视为启动引导：跑 `python3 multiagents/agentctl.py me` 看进度，",
            "然后一次只问一个问题（第一问只问输出语言：中文/日本語/English），按 skill first-run 推进。",
          ].join("\n"),
        })
        return
      }
      if (!st.hasFramework) {
        event.system.unshift({
          type: "text",
          text: [
            "[multiagents boot·环境探测] 本地没有 multiagents 框架。用户输入会被视为提供拉取来源或要求用默认仓库：",
            "有来源 → git clone 到子目录（本地路径同样用 git clone）；无来源 → 问清默认仓库 URL（一次一问，不猜）。",
            "clone 完成后 cd 进去按首装流程继续（me → 一次只问一个问题 → 第一问只问输出语言）。",
          ].join("\n"),
        })
        return
      }
      event.system.unshift({
        type: "text",
        text: [
          "[multiagents boot] 首装引导进行中（first_run.json 未 complete）。用户任何输入（init/hello/闲聊）都是引导的一部分：",
          `先跑 \`python3 multiagents/agentctl.py me\` 看进度（下一步：${nextStep(st.steps)}）；`,
          "然后一次只问一个问题：第一问只问输出语言（中文/日本語/English），之后按 skill first-run 推进。",
          "不得先打招呼/自我介绍，不得把多个问题合并进一个 question。",
        ].join("\n"),
      })
      event.system.push({
        type: "text",
        text: "[multiagents boot·重申] 首装未完成：回复必须服从本 system 最前的 [multiagents boot] 规则，不得当普通对话。",
      })
    })

    // 3. title hook：首装会话标题固定
    await ctx.session.hook("title", (event) => {
      const st = bootState(directory)
      if (st.complete) return
      event.result = "multiagents 首装引导"
    })
  },
})
