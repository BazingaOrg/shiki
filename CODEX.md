# Codex 多模型编排实践指南

用 AGENTS.md + Custom Agents 在 Codex CLI 上搭建「主模型端到端负责、复杂任务按需路由」的工作流：日常工作直接处理，实质性推理、可分离实施和独立验证分别交给 gpt-5.6-sol、gpt-5.6-terra 与 gpt-5.6-luna。

本指南是 [Claude Code 版编排指南](./README.md) 的 Codex 移植版。两者共享同一套工程原则和角色设计,差异只在配置载体(TOML vs markdown frontmatter)和模型映射。

## 目录

- [与 Claude Code 版的对应关系](#与-claude-code-版的对应关系)
- [架构](#架构)
- [安装](#安装)
- [Custom Agent 定义](#custom-agent-定义)
- [AGENTS.md](#agentsmd)
- [并发配置](#并发配置)
- [验证委派真的发生了](#验证委派真的发生了)
- [注意事项](#注意事项)

## 与 Claude Code 版的对应关系

| | Claude Code | Codex |
|---|---|---|
| 指令文件 | CLAUDE.md | AGENTS.md |
| agent 定义 | `~/.claude/agents/*.md`(YAML frontmatter) | `~/.codex/agents/*.toml` |
| 项目级 agent | `<项目>/.claude/agents/` | `<项目>/.codex/agents/` |
| deep-reasoner | Opus | gpt-5.6-sol |
| fast-worker | Sonnet | gpt-5.6-terra |
| qa-runner | Haiku | gpt-5.6-luna |
| 检查运行中的委派 | Task 调用 + Ctrl+O | `/agent` 命令 |
| per-agent 沙箱权限 | 无 | 有(`sandbox_mode`) |

模型映射依据官方定位:sol 是旗舰,适合需要规划、工具使用、验证的模糊多步工作;terra 适合偏速度效率的并行 worker(探索、read-heavy 扫描、大文件审查);luna 是最快最便宜档。

## 架构

```
你 (Goal + Context)
        │
        ▼
   主模型 (orchestrator)  直接处理 · 路由 · 综合
        │
        ├──► 直接处理 → 定向验证 → 已验证结果
        ├──► deep-reasoner (gpt-5.6-sol)    实质性根因分析 / 架构 / 取舍评估
        ├──► fast-worker  (gpt-5.6-terra)   重复 / 批量 / 可分离实施
        └──► qa-runner    (gpt-5.6-luna)    实质性或高容量独立验证
                  │
                  └── 失败报告回流主模型 → 决定直接修复或重新委派
```

## 安装

假设你已 clone 本仓库并位于仓库根目录。

**1. 备份现有配置(务必先做):**

```bash
mkdir -p ~/codex-config-backup
cp -r ~/.codex/agents ~/codex-config-backup/agents 2>/dev/null
cp ~/.codex/config.toml ~/codex-config-backup/ 2>/dev/null
cp /path/to/your-project/AGENTS.md ~/codex-config-backup/ 2>/dev/null
```

**2. 添加三个 custom agent(全局生效):**

```bash
mkdir -p ~/.codex/agents
cp codex/agents/deep-reasoner.toml codex/agents/fast-worker.toml codex/agents/qa-runner.toml ~/.codex/agents/
```

**3. 放置 AGENTS.md 到你的项目根目录:**

```bash
cp codex/AGENTS.md /path/to/your-project/AGENTS.md
```

> - Codex 会从工作目录逐级向上加载沿途所有 AGENTS.md,路径越近优先级越高,因此可以全局通用规则 + 项目特有规则分层放置。
> - 已有 AGENTS.md 的项目建议手动合并而不是覆盖。

**4. 重启 Codex 会话。**

## Custom Agent 定义

每个 agent 是一个独立的 TOML 文件，`name` 字段是路由标识。`description` 同时约束自动发现边界：它应说明适用的实质性任务，也应排除主模型可以直接完成的小任务。其他关键字段包括 `model`、`model_reasoning_effort`、`sandbox_mode` 和指令文本；未指定的配置从父会话继承。

> ⚠️ 指令字段的确切写法(`developer_instructions = """..."""` 或 `[instructions]` 表)随 Codex CLI 版本有差异，以你安装版本的[官方 subagents 文档](https://developers.openai.com/codex/subagents)为准。仓库当前使用 `developer_instructions` 写法。

完整定义以 [`codex/agents/`](./codex/agents/) 中的 TOML 为准，避免文档副本与实际配置漂移。

三处 sandbox 设计说明:

- **deep-reasoner 配 `read-only`**:它的产出是结论不是代码,权限硬隔离比措辞约束更可靠——即使指令被上下文稀释,它也物理上写不了文件。
- **qa-runner 配 `workspace-write` 而非 `read-only`**:跑测试通常需要写临时产物(缓存、覆盖率报告),read-only 会让测试本身失败。「不许修源码」的约束由指令层的 "You must not edit source files" 承担。如果你的测试套件完全无写入,可收紧为 `read-only`。
- **fast-worker 配 `workspace-write`**:实现角色,必须能写。

## AGENTS.md

完整规则以 [`codex/AGENTS.md`](./codex/AGENTS.md) 为准，避免在指南中重复维护整段指令。核心边界是：主模型默认直接处理，只在有实质收益时 spawn 边界清晰的 agent；写了计划不等于必须等待确认；安全本地工作和非破坏性验证按当前 permission mode 继续。

明确点名 agent 可以测试委派管道。未点名时，Codex 仍可能依据 `AGENTS.md` 与 agent `description` 自动委派，但这是一条有条件的路由，不是每个任务都必须 spawn 的固定流程。

High-stakes 双模型并行一条未移植:Codex 的并行 subagent 共享同一模型家族,跨家族对照(如 GPT × Claude)需要外部管道,不属于本指南范围。

## 并发配置

`~/.codex/config.toml` 中两个全局参数控制扇出:

```toml
[agents]
max_threads = 6   # 并发 agent 线程数,默认 6
max_depth = 1     # 嵌套深度,默认 1:子 agent 可被 spawn,但不能再向下递归
```

保持默认即可。官方文档提示调高 max_depth 会把宽泛的委派指令变成反复扇出,token 消耗、延迟和本地资源占用都会上升。

## 验证委派真的发生了

方法论与 Claude Code 版一致(管道测试 → 冷启动测试),工具换成 Codex 的:

**Step 1 — 检查 TOML 加载。** agent 文件如果是会话运行中新建的,重启会话。若 TOML 有非法字段或 config 路径失效,spawn 会直接失败——这类错误反而好排查。

**Step 2 — 显式委派(测管道)。** 发指令:`Spawn the deep-reasoner agent to produce a plan for <真实小需求>`。运行中用 **`/agent`** 命令查看、切换、检查各 agent 线程;主线程最终会收拢各 subagent 的结果。

**Step 3 — 冷启动(测路由边界)。** 新开会话，先给普通答疑或小检查，确认主模型直接处理；再给实质性根因分析、批量实施或高容量独立验证，不点名 agent，观察它是否在委派有明显收益时主动 spawn。

**Step 4 — 核对模型与成本。** 各 subagent 线程使用的模型可在线程详情中确认;sol/terra/luna 的单价差距显著(官方定价 sol $5/$30、terra $2.5/$15、luna $1/$6 每百万 token),委派正确与否会直接反映在账单结构上。

## 注意事项

- **并行写冲突**：只并行真正独立的工作；有依赖的阶段保持顺序。多个 agent 同时改代码会产生冲突和协调开销，如需并行实施应使用隔离工作区。
- **subagent 更耗 token**:每个 subagent 独立做模型和工具调用,同等任务比单 agent 消耗更多 token。和 Claude Code 版一样:委派买的是质量和主上下文寿命,不是省钱。
- **版本差异**:Codex 的 multi-agent 能力演进很快(部分旧版本需要 `/experimental` 手动开启),字段名和默认行为可能随版本变化,遇到不一致以官方文档为准。

## 致谢

本指南的编排思路参考并受益于以下两篇分享,特此感谢:

- [@diegocabezas01 关于 Claude Code 编排的分享](https://x.com/diegocabezas01/status/2072436501263339841)
- [用 Claude Code 将三万行 Go 项目移植到 Rust:Agent Team 实践与 Harness 效率优化](https://maxlv.net/blog/porting-mihomo-to-rust-with-claude/) — Max Lv

## License

MIT
