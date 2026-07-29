# Grok Build 多模型编排实践指南

用 AGENTS.md + 自定义 agent 定义在 Grok Build 上搭建「主模型编排、按任务路由专职 agent」的工作流：重推理给 `deep-reasoner`，机械执行给 `fast-worker`，验证给 `qa-runner`，主模型只做规划、拆解和综合。

本指南是 [Claude Code / Codex 编排模板](./README.md) 的 Grok Build 移植版。三者共享同一套工程原则和角色设计；差异在配置载体、模型映射和官方路径。

字段与发现路径以本机 Grok 用户指南为准（`~/.grok/docs/user-guide/`，尤其是 `12-project-rules.md` 与 `16-subagents.md`）。

## 目录

- [与 Claude Code / Codex 的对应关系](#与-claude-code--codex-的对应关系)
- [架构](#架构)
- [安装](#安装)
- [Agent 定义](#agent-定义)
- [Reasoning effort 分层](#reasoning-effort-分层)
- [避免 Claude 规则双份注入](#避免-claude-规则双份注入)
- [AGENTS.md 与全局规则](#agentsmd-与全局规则)
- [验证委派真的发生了](#验证委派真的发生了)
- [注意事项](#注意事项)

## 与 Claude Code / Codex 的对应关系

| | Claude Code | Codex | Grok Build |
|---|---|---|---|
| 指令文件 | `CLAUDE.md` | `AGENTS.md` | `AGENTS.md`（也认 `CLAUDE.md`） |
| agent 定义 | `~/.claude/agents/*.md` | `~/.codex/agents/*.toml` | `~/.grok/agents/*.md` |
| 项目级 agent | `<项目>/.claude/agents/` | `<项目>/.codex/agents/` | `<项目>/.grok/agents/` |
| 用户级全局规则 | `~/.claude/` 等 | 逐级 `AGENTS.md` | **`~/.grok/rules/*.md`** |
| deep-reasoner | Opus | `gpt-5.6-sol` | `grok-4.5` + effort **high** + `plan` |
| fast-worker | Sonnet | `gpt-5.6-terra` | `grok-4.5` + effort **medium** |
| qa-runner | Haiku | `gpt-5.6-luna` | `grok-4.5` + effort **low** |
| 检查运行中的委派 | Task 调用 + 日志 | `/agent` | 任务窗 `Ctrl+G`、`/config-agents`、`grok inspect` |
| 子 agent 调用 | Task / 委派 | spawn custom agent | `spawn_subagent` + `subagent_type` |

模型名称以本地 `grok models` 为准；不可用时改 frontmatter 中的 `model`。

## 架构

```
你 (Goal + Context)
        │
        ▼
   主模型 (orchestrator)  规划 · 拆解 · 综合
        │
        ├──► deep-reasoner (grok-4.5, high, plan)     重推理
        ├──► fast-worker  (grok-4.5, medium, default) 机械执行
        └──► qa-runner    (grok-4.5, low, default)    验证报告
                  │
                  └── 失败报告回流主模型 → 重新派 fast-worker 修复
```

官方约束：子 agent **不能再 spawn**（深度为 1）。编排必须留在主会话。

## 安装

假设已 clone 本仓库并位于仓库根目录。

**1. 备份现有配置（建议先做）：**

```bash
mkdir -p ~/grok-config-backup
cp -R ~/.grok/agents ~/grok-config-backup/agents 2>/dev/null
cp -R ~/.grok/roles ~/grok-config-backup/roles 2>/dev/null
cp -R ~/.grok/rules ~/grok-config-backup/rules 2>/dev/null
cp ~/.grok/config.toml ~/grok-config-backup/ 2>/dev/null
```

**2. 安装三个用户级 agent + 同名 roles：**

```bash
mkdir -p ~/.grok/agents ~/.grok/roles
cp -i grok/agents/deep-reasoner.md ~/.grok/agents/deep-reasoner.md
cp -i grok/agents/fast-worker.md ~/.grok/agents/fast-worker.md
cp -i grok/agents/qa-runner.md ~/.grok/agents/qa-runner.md
cp -i grok/roles/deep-reasoner.toml ~/.grok/roles/deep-reasoner.toml
cp -i grok/roles/fast-worker.toml ~/.grok/roles/fast-worker.toml
cp -i grok/roles/qa-runner.toml ~/.grok/roles/qa-runner.toml
```

**3. 放置编排规则：**

- **项目级（推荐写入仓库）：**

  ```bash
  cp grok/AGENTS.md /path/to/your-project/AGENTS.md
  ```

  已有 `AGENTS.md` 时手动合并 Orchestration 等章节，不要直接覆盖项目特有规则。

- **用户级全局规则（对所有项目生效）：**

  按官方 Project Rules 文档，用户级规则目录是 `~/.grok/rules/`（不是 `~/.grok/AGENTS.md`）：

  ```bash
  mkdir -p ~/.grok/rules
  cp -i grok/AGENTS.md ~/.grok/rules/AGENTS.md
  ```

  全局规则会先加载；项目内更深层的 `AGENTS.md` 优先级更高。

**4. 关闭 Claude 全局 agents 兼容（推荐，避免双份编排）：**

将 [`grok/config.snippet.toml`](./config.snippet.toml) 合并进 `~/.grok/config.toml`：

```toml
[compat.claude]
agents = false
```

等价环境变量：`GROK_CLAUDE_AGENTS_ENABLED=false`。详见 [避免 Claude 规则双份注入](#避免-claude-规则双份注入)。

**5. 项目级 agent（可选）：** 复制到 `<项目>/.grok/agents/`；roles 可放到 `<项目>/.grok/roles/`。

**6. 重启 Grok 会话**，或新开一个会话使发现结果生效。

## Agent 定义

每个 agent 是带 YAML frontmatter 的 Markdown，与官方 agent profile 一致。发现优先级（高到低）：CLI `--agent-profile` → config `[agent]` → 项目 `.grok/agents/` → 用户 `~/.grok/agents/` → bundled。

关键 frontmatter（对齐 bundled agents + effort 分层）：

| 字段 | 含义 |
| --- | --- |
| `name` | 路由名，即 `spawn_subagent` 的 `subagent_type` |
| `description` | 主模型决定何时委派时使用 |
| `model` | 固定模型，或 `inherit` 继承父会话 |
| `effort` | 该 agent 的 reasoning effort（`high` / `medium` / `low` 等，以模型菜单为准） |
| `prompt_mode` | 本模板使用 `full` |
| `permission_mode` | `plan`（只读规划）或 `default` |
| `agents_md` | `true`：子会话加载项目规则 |

### 本模板三件套

| Agent | model | effort | permission_mode | 说明 |
| --- | --- | --- | --- | --- |
| `deep-reasoner` | `grok-4.5` | `high` | `plan` | 只读推理，产出结论 |
| `fast-worker` | `grok-4.5` | `medium` | `default` | 可写文件，短报告变更 |
| `qa-runner` | `grok-4.5` | `low` | `default` | 可跑测试；指令禁止改源码 |

若本地出现更轻量模型（例如文档中的 `grok-build`），可将 `fast-worker` / `qa-runner` 的 `model` 改为该 ID，并用 `grok models` 确认可用。

也可在 `~/.grok/config.toml` 用 per-type 覆盖模型：

```toml
[subagents.models]
deep-reasoner = "grok-4.5"
fast-worker = "grok-4.5"
qa-runner = "grok-4.5"
```

## Reasoning effort 分层

同一模型（当前默认 `grok-4.5`）下，用 **effort** 模拟 Claude/Codex 的「重 / 中 / 轻」分层。

### 官方解析顺序（`16-subagents.md`）

有效 model / reasoning effort 优先级（高 → 低）：

1. spawn 时显式覆盖  
2. **Role 默认**（`reasoning_effort`）  
3. **Persona 默认**  
4. **父会话**（例如 `[models] default_reasoning_effort`）

本模板用两层保险：

1. **Agent frontmatter `effort:`**（与 skills 字段名一致；插件生态常用）  
2. **同名 Role 文件** `~/.grok/roles/<name>.toml` 中的 `reasoning_effort`（官方 role 字段）

```toml
# grok/roles/deep-reasoner.toml
description = "Reasoning-heavy phases: root cause, architecture, tradeoffs"
default_capability_mode = "read-only"
reasoning_effort = "high"
```

Roles 发现路径：项目 `.grok/roles/*.toml`、用户 `~/.grok/roles/*.toml`，以及 `config.toml` 的 `[subagents.roles.*]`（inline 优先于文件）。

> 父会话若设 `default_reasoning_effort = "high"`，未配置 effort 的子 agent 会继承 high。qa-runner / fast-worker **必须**显式压低，否则三档退化成一档。

`grok-4.5` 当前菜单档位通常为 `high` / `medium` / `low`；以 `grok models` 与 TUI `/effort` 为准。

## 避免 Claude 规则双份注入

Grok 默认开启 Claude 兼容。若同时存在：

- `~/.grok/rules/AGENTS.md`（Shiki Grok 全局编排）
- `~/.claude/Claude.md` 或 `~/.claude/CLAUDE.md`（Claude Code 全局编排）

主会话会**双份注入**近乎相同的 Orchestration 文本。

### 推荐配置

```toml
# ~/.grok/config.toml
[compat.claude]
agents = false   # 不注入 ~/.claude/Claude.md，也不扫 ~/.claude/agents
# skills = true  # 默认；仍可用 Claude skills
# rules  = true  # 仅影响 ~/.claude/rules/，不是 Claude.md
```

| 开关 | 作用 |
| --- | --- |
| `agents = false` | 停用 `~/.claude/` 下命名指令文件与 `~/.claude/agents`；`grok inspect` 中对应项显示 `[disabled]` |
| `rules = false` | 停用 `~/.claude/rules/`，**不**控制仓库根 `CLAUDE.md` |
| 项目根 `CLAUDE.md` / `Claude.md` | 官方仍会识别（与 Claude Code 工作流兼容），**不受** `agents` 开关影响 |

因此：

- **全局双份**：用 `compat.claude.agents = false` 解决。  
- **项目内双份**（仓库既有 `CLAUDE.md` 又有全局 Grok 规则）：换只含 `AGENTS.md` 的项目，或接受两份并存并避免内容冲突。  
- **仍使用 Claude Code**：保留 `~/.claude/Claude.md` 与 `~/.claude/agents`；只在 Grok 侧关 compat 即可，不必删除 Claude 配置。

验证：

```bash
grok inspect
# 期望：~/.claude/Claude.md 带 [disabled] 或不再有效注入
# 期望：仍有 ~/.grok/rules/AGENTS.md 与 user agents deep-reasoner / fast-worker / qa-runner
```

## AGENTS.md 与全局规则

**内容与 Claude / Codex 版大体一致**：Git、Engineering Principles、Plan Documents、Definition of Done、Communication 可原样共用。Grok 版差异：

1. 委派动词明确为 **spawn**，并写出 `subagent_type` 字符串。
2. 补充 `capability_mode` 与 **depth=1** 约束。
3. 保留 high-stakes 双 agent 并行（Grok 原生支持并行 subagent）。

主模型通过 `spawn_subagent` 启动子会话；自定义 agent 的 `name` 必须与路由名一致。

## 验证委派真的发生了

不要只确认文件已复制。

1. 运行 `grok inspect`，确认：
   - Project Instructions 含 `~/.grok/rules/AGENTS.md`
   - `~/.claude/Claude.md` 为 disabled（若已关 compat agents）
   - Agents 含 user：`deep-reasoner` / `fast-worker` / `qa-runner`
2. 在 TUI 中打开 `/config-agents`（或 `/agents`），列表含上述三个。
3. 显式要求：spawn `deep-reasoner` 做小型方案；用 `Ctrl+G` 任务窗确认子会话与 effort。
4. 新开会话，不点名 agent，给需要分析/实现的任务，确认主模型按规则主动分派。
5. 核对子 agent 的 model / effort；未分派时检查规则是否加载、agent 路径、以及 `GROK_SUBAGENTS` / `[subagents] enabled`。

验证关注点：**是否委派、派给谁、用什么模型 / effort**。

## 注意事项

- **先合并规则，再按项目调整。** 模板里的 Git / 计划文档约定不一定适合所有仓库；全局 `~/.grok/rules/` 会影响所有项目。
- **模型可相同，effort 分层。** 默认全是 `grok-4.5`，用 high/medium/low 拉开推理成本。
- **qa-runner 只报告，不修复。** 失败回主模型再派 `fast-worker`。
- **并行写文件要谨慎。** 默认可串行：分析 → 实施 → 验证；隔离写入可用 `isolation: worktree`。
- **Grok 用户优先 `~/.grok/agents` + `compat.claude.agents = false`。** 避免 Claude 模型名与双份规则。
- **委派不等于省钱。** 收益是职责隔离、验证闭环、主会话上下文更干净；effort 分层是额外杠杆。

## 参考

- [统一入口 README](./README.md)
- [Grok 编排规则模板](./grok/AGENTS.md)
- [Grok agent 定义](./grok/agents/)
- [Grok roles](./grok/roles/)
- [config 片段](./grok/config.snippet.toml)
- 本机文档：`~/.grok/docs/user-guide/12-project-rules.md`、`16-subagents.md`、`05-configuration.md`（Harness compatibility）
