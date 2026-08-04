# Codex 多模型编排实践指南

用 AGENTS.md + Custom Agents 在 Codex CLI 上搭建「主模型编排、按任务路由模型」的工作流:重推理给 gpt-5.6-sol,机械执行给 gpt-5.6-terra,验证给 gpt-5.6-luna,主模型只做规划、拆解和综合。

本指南是 [Claude Code 版编排指南](./README.md) 的 Codex 移植版。两者共享同一套工程原则和角色设计,差异只在配置载体(TOML vs markdown frontmatter)和模型映射。

## 目录

- [与 Claude Code 版的对应关系](#与-claude-code-版的对应关系)
- [架构](#架构)
- [安装](#安装)
- [双 lane](#双-lane)
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
   主模型 (orchestrator)  规划 · 拆解 · 综合
        │
        ├──► deep-reasoner (gpt-5.6-sol)    重推理:根因分析 / 架构 / 取舍评估
        ├──► fast-worker  (gpt-5.6-terra)   机械执行:实现 / boilerplate / 批量修改
        └──► qa-runner    (gpt-5.6-luna)    验证:跑测试 / lint / 报告 pass/fail
                  │
                  └── 失败报告回流主模型 → 重新派 fast-worker 修复
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

**3. 安装用户级共享规则（主用法）:**

```bash
cp -i codex/AGENTS.md ~/.codex/AGENTS.md
```

支持该层级的 Codex 版本会加载此共享规则；若本地版本行为不同，请按本机官方文档放置并保留同一内容。

**4. 仅在需要覆盖时放置项目级 AGENTS.md:**

```bash
cp codex/AGENTS.md /path/to/your-project/AGENTS.md
```

> - Codex 会从工作目录逐级向上加载沿途所有 AGENTS.md,路径越近优先级越高,因此可以全局通用规则 + 项目特有规则分层放置。
> - 已有 AGENTS.md 的项目建议手动合并而不是覆盖。

**5. 重启 Codex 会话。**

## 双 lane

日常工作走 **light lane**。只有用户明确要求隔离、独立 QA 或证据，或任务涉及发布/外部写入、付款、迁移、不可逆删除、安全边界、全局配置/CI/toolchain、多 writer，或在 commit/push/PR 前要求高保障核验时，才进入 **verified lane**。多文件或非平凡任务不是触发条件。

默认直接处理普通工作；只在有界委派明显提升质量、速度、独立性或上下文时 spawn 对应 custom agent。按风险升级独立 QA，安全、不可逆或用户明确高保障时加 fresh read-only review。完整可审计流程仅在用户明确采用时参考 [docs/verified-lane.md](./docs/verified-lane.md)，不代表 Codex sandbox 或权限模型。

## Custom Agent 定义

每个 agent 是一个独立的 TOML 文件,`name` 字段是路由标识(与内置 agent 同名时自定义优先)。关键字段:`model`(按 agent 固定模型)、`model_reasoning_effort`、`sandbox_mode`(per-agent 沙箱权限,Claude Code 没有的能力)、指令文本。未指定的配置从父会话继承。

> ⚠️ 指令字段的确切写法(`developer_instructions = """..."""` 或 `[instructions]` 表)随 Codex CLI 版本有差异,以你安装版本的[官方 subagents 文档](https://developers.openai.com/codex/subagents)为准。下文使用 `developer_instructions` 写法。

### `codex/agents/deep-reasoner.toml`

```toml
name = "deep-reasoner"
description = "Use for reasoning-heavy phases, architecture, debugging complex issues, algorithm design. Think thoroughly, return a concise conclusion the orchestrator can act on."
model = "gpt-5.6-sol"
model_reasoning_effort = "high"
sandbox_mode = "read-only"

developer_instructions = """
You are a deep reasoning specialist. Think thoroughly through the problem,
consider alternatives, then return a concise, actionable conclusion.
Do not return your full chain of thought—only what the orchestrator needs.
"""
```

### `codex/agents/fast-worker.toml`

```toml
name = "fast-worker"
description = "Use for mechanical tasks, boilerplate, tests, formatting, simple edits. Execute efficiently."
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
sandbox_mode = "workspace-write"

developer_instructions = """
You execute mechanical work efficiently. No exploration beyond the task scope.
Report what you changed in a short summary.
"""
```

### `codex/agents/qa-runner.toml`

```toml
name = "qa-runner"
description = "Use for verification work — running tests / typecheck / lint, writing test plans from specs, reviewing test coverage, and reporting pass/fail status. Templated, checklist-driven work."
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
sandbox_mode = "workspace-write"

developer_instructions = """
You run verification, not reasoning. Execute the project's tests, typecheck,
and lint; report results as a short pass/fail summary with failing items
listed verbatim. When asked for a test plan, derive cases from the spec's
error types and edge cases in a table. Do not fix failures yourself —
report them back to the orchestrator. Do not speculate about causes.
You must not edit source files under any circumstances.
"""
```

三处 sandbox 设计说明:

- **deep-reasoner 配 `read-only`**:它的产出是结论不是代码,权限硬隔离比措辞约束更可靠——即使指令被上下文稀释,它也物理上写不了文件。
- **qa-runner 配 `workspace-write` 而非 `read-only`**:跑测试通常需要写临时产物(缓存、覆盖率报告),read-only 会让测试本身失败。「不许修源码」的约束由指令层的 "You must not edit source files" 承担。如果你的测试套件完全无写入,可收紧为 `read-only`。
- **fast-worker 配 `workspace-write`**:实现角色,必须能写。

## AGENTS.md

使用仓库中的 [`codex/AGENTS.md`](./codex/AGENTS.md) 作为短、自包含规则：普通工作默认直做；仅在有界委派明显改善结果时 spawn named custom agent；高影响工作按风险升级独立验证。项目级规则只覆盖项目事实，不重复旧的强制编排全文。

按需显式 `spawn` 可验证管道；是否选择性委派由当前任务边界决定，应以当前版本行为与日志验证。

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

**Step 3 — 可选路由 smoke。** 新开会话提交拼写修正，预期直接处理；再给独立、复杂且边界清晰的子任务，确认它可在有收益时选择 spawn。未分派不单独构成失败，应结合任务边界、当前版本与日志判断。

**Step 4 — 核对模型与结果。** 各 subagent 线程使用的模型可在线程详情中确认；应核对委派是否与任务边界和验证结果匹配。

## 注意事项

- **并行写冲突**:官方建议并行 agent 优先用于 read-heavy 任务(探索、测试、triage、摘要),write-heavy 并行要谨慎——多个 agent 同时改代码会产生冲突和协调开销。本指南的流水线是串行委派(方案 → 实现 → 验证),天然规避这个问题;如果你扩展出并行实现,考虑配合 git worktree 隔离。
- **subagent 更耗 token**:每个 subagent 独立做模型和工具调用,同等任务比单 agent 消耗更多 token。和 Claude Code 版一样:委派买的是质量和主上下文寿命,不是省钱。
- **版本差异**:Codex 的 multi-agent 能力演进很快(部分旧版本需要 `/experimental` 手动开启),字段名和默认行为可能随版本变化,遇到不一致以官方文档为准。

## 致谢

本指南的编排思路参考并受益于以下两篇分享,特此感谢:

- [@diegocabezas01 关于 Claude Code 编排的分享](https://x.com/diegocabezas01/status/2072436501263339841)
- [用 Claude Code 将三万行 Go 项目移植到 Rust:Agent Team 实践与 Harness 效率优化](https://maxlv.net/blog/porting-mihomo-to-rust-with-claude/) — Max Lv

## License

MIT
