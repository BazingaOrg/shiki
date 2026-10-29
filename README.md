# Shiki

面向 **Claude Code**、**Codex** 与 **Grok Build** 的多模型 agent 编排配置模板。

它不是一个可运行的应用或 agent 框架，而是一组可复用的指令文件和角色配置。主模型默认直接完成普通工作；只有有界委派能提高质量、速度、独立性或上下文管理时，才按任务分派专职 agent。

## 规则原则

入口按十条原则组织：目标优先、尊重意图、小步交付、保护所有权、先诊断、可重复验证、独立协作、凭证据发布、准确表达、保持指令精简。每条原则都有明确动作和边界；“看看”只分析，“修改”才实施，提交和发布需要对应授权。

三套模板保持自包含，适合复制安装；只保留平台委派方式的差异。设计依据、需求映射及对抗验收见 [规则的写法与验收](./docs/working-principles.md)。规则不是权限隔离，验证工具也不能自动证明模型会遵守所有规则。

## 工作方式

| 角色 | 职责 | 模型 | 推理强度 |
| --- | --- | --- | --- |
| 主模型 | 目标、判断、整合与最终交付 | 用户当前选择 | 当前会话设置 |
| `deep-reasoner` | 有界调查、方案取舍、独立审查 | 默认继承父会话 | high |
| `fast-worker` | 已确定边界的机械、批量实施 | 默认继承父会话 | medium |
| `qa-runner` | 执行指定检查并报告证据 | 默认继承父会话 | Codex/Grok low；Claude 默认 |

典型流程：

![Shiki 多模型委派架构](docs/assets/architecture/architecture.png)

图中展示角色边界与验证回流，不表示每项任务都要经过固定流程。各角色默认策略见上表；细节见对应指南。

模板默认直接处理；仅当有界委派能明确提升质量、速度、独立性或上下文时选择性分派。按生产、安全、不可逆操作等影响升级独立核验。完整规则请查看 [Claude Code 指令](./CLAUDE.md)、[Codex 指令](./codex/AGENTS.md) 与 [Grok 指令](./grok/AGENTS.md)。

用户明确要求独立 QA 或审查时必须保持独立性；高影响任务也按风险升级独立核验。验证失败由主模型根据证据路由，原因明确时可交回实施方；根因不明、方案冲突或反复无进展时回到主模型重新判断。三平台共享角色语义，但权限、调用和运行时覆盖能力按各自配置而不同。完整可审计流程是可选参考：[docs/verified-lane.md](./docs/verified-lane.md)。

角色只定义职责，不绑定模型等级。Claude 使用 `model: inherit`，Codex 和 Grok 省略角色中的 `model` 字段。显式调用参数、全局默认、provider 或 Grok role/persona 仍可能覆盖继承；安装后核对实际子会话模型。推理强度保留角色默认值，使用的模型必须支持该值。详情见各平台指南。

独立调查或审查使用新实例，只传原始目标、约束、路径和证据，不复制整个对话或把主模型结论当成前提。继续同一子任务可以恢复原实例；恢复历史不等于获得独立意见。

## 怎么提需求

三份规则入口是不同客户端的版本，不是三个不同角色。按使用的客户端选择，项目已有规则时合并所需内容：

| 客户端 | 规则入口 | 配套角色定义 |
| --- | --- | --- |
| Claude Code | [CLAUDE.md](./CLAUDE.md) | [agents/](./agents/) |
| Codex | [codex/AGENTS.md](./codex/AGENTS.md) | [codex/agents/](./codex/agents/) |
| Grok Build | [grok/AGENTS.md](./grok/AGENTS.md) | [grok/agents/](./grok/agents/) 与 [grok/roles/](./grok/roles/) |

日常说明背景、目标、约束和验收结果即可，不用每次指定角色。只有需要独立判断、隔离上下文或明确分工时，再点名委派。以下是自然语言请求，不是客户端命令；替换方括号内容后直接发送。角色示例需要先完成[快速配置](#快速配置)并确认客户端支持子 Agent。角色不可用时应报告限制，不能把主模型自审称为独立审查。

### 1. 从目标开始，交付最小可用版本

适合新功能或体验改进。主模型承担设计判断；不要求用户先指定技术方案。

```text
我想让[目标用户]在[使用场景]中更容易完成[目标]。
现在的问题是[现状与影响]，理想结果是[可观察的行为]。
必须满足[约束]，本次验收看[结果或指标]。

请先检查项目，再简述最小可用方案、影响范围和验证方式，然后完成实现。
技术细节由你判断；超出这个目标的新功能、配置或开关先找我确认。
给我实际验证结果和仍未验证的部分。本次只实施，不提交或发布。
```

### 2. 先看看问题，不改代码

适合根因调查或方案评估。明确只读范围，避免“找到了原因”被解释成修复授权。

```text
看看[问题]为什么发生。复现步骤是[步骤]，期望是[行为]，实际是[行为]。
相关线索在[日志、文件或可访问的记录]。

这次只读分析，不修改文件。先核对真实调用路径和数据，区分事实与假设。
给出最可能的原因、对应证据、还缺什么证据，以及最小修复建议和影响范围。
如果有一个适合独立调查的子问题，可以交给新的 deep-reasoner。
```

### 3. 把明确的批量修改交给 fast-worker

适合边界和做法已经确定的机械实施；复杂设计仍由主模型负责。

```text
把[限定目录或文件]中的[现有写法]统一调整为[已确定写法]。
保留[兼容行为]，验收条件是[明确条件]。

请将这部分有界实施委派给 fast-worker，说明它拥有的文件范围和不能改的内容。
由你检查结果、运行相关验证并整合。若并发写入，分别使用独立 worktree；
无法隔离时串行执行。遇到设计不确定性时返回给你判断，不扩展重构范围。
本次不提交、不推送。
```

### 4. 独立验证，再审查同一份改动

适合重要改动完成后的验收，也可用于检查已有 diff。先填入真实检查命令。

```text
对[基准提交或分支]以来、范围为[路径或功能]的改动做独立验收。
原始需求和验收条件是[要求]。本轮冻结候选，只验证和审查，不修改或提交。

先让 qa-runner 执行[项目已有的检查命令]，报告命令、退出码和失败证据，不修代码。
检查通过后，再启动全新上下文的 deep-reasoner，审查同一候选的正确性、回归风险、
边界条件和测试缺口。提供原始要求、diff 和验证证据，不把实施者的结论当成事实。

如果检查失败或候选发生变化，停止本轮验收并报告。
返回有文件位置和实际影响的发现；没有发现就明确说明，并列出未验证的部分。
```

### 5. 用 fresh context 获得独立判断

适合主线程已有较多推断、需要第二意见时。新实例只接收必要材料；复用旧实例用于跟进，不能算新意见。

```text
请启动一个新的 deep-reasoner，独立分析[有边界的问题]，只读、不改文件。
给它原始目标[目标]、约束[约束]、相关路径[路径]和可复现证据[证据]。
不要继承整段聊天，也不要让它以你目前的判断为前提；必要的假设单独标记。
如果客户端无法提供这种上下文隔离，先说明限制。

让它自行检查代码，返回结论、依据、备选解释和不确定性。
你收到结果后再与已有证据对照，指出一致点、分歧和下一步该验证什么。
```

### 6. 修复反复失败时，换调查方式

适合同一个问题已经尝试过多次修复。停止重复猜测，保留现场，避免新 Agent 重走旧路。

```text
[问题]已经修复了[次数]次，仍然出现[现象]。先停止猜测性修改。
整理原始目标、复现步骤、尝试过的方案及结果、当前 diff 和真实运行证据。
缺少观测时先说明需要采集什么，日志注意脱敏。

将这些材料交给全新上下文的 deep-reasoner，只读重新调查。
保留现有工作，不靠换 Agent 清零失败次数。
只有新证据支持修正诊断后，才在原授权范围内继续修复；否则报告阻塞和下一项取证动作。
```

这些请求不会自动授权提交、推送、发布、删除或联系用户。若确实需要这些动作，明确说明动作和目标即可，不必重复确认已经给出的同一授权。独立上下文也不保证结论正确：看证据、实际行为和验收结果，不按 Agent 数量判断质量。

## 快速配置

先克隆仓库并进入根目录。**优先将 agent 与共享规则安装为用户级配置**，再只用项目级规则覆盖该项目独有的构建命令、风险边界或例外；不要把模板直接覆盖进已有项目规则。

### Claude Code

安装三个 agent：

```bash
mkdir -p ~/.claude/agents
cp -i agents/deep-reasoner.md ~/.claude/agents/deep-reasoner.md
cp -i agents/fast-worker.md ~/.claude/agents/fast-worker.md
cp -i agents/qa-runner.md ~/.claude/agents/qa-runner.md
```

`cp -i` 会在覆盖同名文件前询问。如果目标文件已存在，请拒绝覆盖，比较现有定义与模板后再手动合并。

将 [`CLAUDE.md`](./CLAUDE.md) 作为共享规则安装到你的 Claude Code 用户级规则位置；如本地版本只支持项目规则，则手动合并到项目规则。项目级仅用于覆盖：

- 目标项目**没有** `CLAUDE.md`：可复制模板。

  ```bash
  cp CLAUDE.md /path/to/your-project/CLAUDE.md
  ```

- 目标项目**已有** `CLAUDE.md`：手动合并所需原则和委派规则，**不要直接覆盖**原有的构建命令、Git 约定和项目规则。

如需只在单个项目中使用 agent，也可以将定义放到目标项目的 `.claude/agents/` 目录。

### Codex

安装三个 custom agent：

```bash
mkdir -p ~/.codex/agents
cp -i codex/agents/deep-reasoner.toml ~/.codex/agents/deep-reasoner.toml
cp -i codex/agents/fast-worker.toml ~/.codex/agents/fast-worker.toml
cp -i codex/agents/qa-runner.toml ~/.codex/agents/qa-runner.toml
```

`cp -i` 会在覆盖同名文件前询问。如果目标文件已存在，请拒绝覆盖，比较现有定义与模板后再手动合并。

将 [`codex/AGENTS.md`](./codex/AGENTS.md) 作为用户级共享规则安装（例如支持该层级的版本可使用 `~/.codex/AGENTS.md`）；项目级仅用于覆盖：

- 目标项目**没有** `AGENTS.md`：可复制模板。

  ```bash
  cp codex/AGENTS.md /path/to/your-project/AGENTS.md
  ```

- 目标项目**已有** `AGENTS.md`：手动合并编排章节，**不要直接覆盖**现有规则。

如需项目级 custom agent，可将 TOML 定义放到目标项目的 `.codex/agents/` 目录。Codex 的配置字段和可用模型可能随版本变化，请根据本地版本调整模板。

### Grok Build

安装三个用户级 agent 与同名 roles（官方路径：`~/.grok/agents/`、`~/.grok/roles/`）：

```bash
mkdir -p ~/.grok/agents ~/.grok/roles
cp -i grok/agents/*.md ~/.grok/agents/
cp -i grok/roles/*.toml ~/.grok/roles/
```

先将 [`grok/AGENTS.md`](./grok/AGENTS.md) 作为用户级全局规则安装；项目级仅用于覆盖：

- 目标项目**没有** `AGENTS.md`：

  ```bash
  cp grok/AGENTS.md /path/to/your-project/AGENTS.md
  ```

- 目标项目**已有** `AGENTS.md`：手动合并编排章节，**不要直接覆盖**。

用户级**全局规则**请放到官方目录 `~/.grok/rules/`（对所有项目生效；项目内更深路径的规则优先）：

```bash
mkdir -p ~/.grok/rules
cp -i grok/AGENTS.md ~/.grok/rules/AGENTS.md
```

避免与 Claude 全局规则双份注入：在 `~/.grok/config.toml` 中设置（片段见 `grok/config.snippet.toml`）：

```toml
[compat.claude]
agents = false
```

项目级 agent 可放到 `<项目>/.grok/agents/`。effort / 兼容层细节见 [GROK.md](./GROK.md)。可用模型以 `grok models` 为准。

## 验证配置

不要只确认文件已复制，还要确认委派实际发生。

1. 检查三个 agent 文件是否位于预期的用户级或项目级目录，且名称与指令文件中的路由名称一致。
2. 显式要求主模型调用 `deep-reasoner` 完成一个小型方案任务，通过当前客户端提供的 agent 状态或日志确认委派发生：
   - Codex CLI：`/agent`
   - Grok Build：`Ctrl+G` 任务窗、`/config-agents`、`grok inspect`
3. 可选做路由 smoke：拼写修正应直接处理；独立、复杂且边界清晰的子任务才可能选择性委派。未分派不单独构成失败，应结合任务边界与客户端日志判断。
4. 核对实际 agent 使用的模型、effort 与配置来源；按对应平台的配置优先级解释差异，不假定三平台覆盖顺序相同。如果没有分派，优先检查指令文件是否被加载、agent 路径是否正确，以及本地版本是否支持对应配置。

验证时应关注“是否发生委派、派给谁、使用什么模型”，不要仅凭总 token 或费用推断结果。

## 仓库结构

```text
.
├── README.md                    # Claude Code / Codex / Grok 统一入口
├── CLAUDE.md                    # Claude Code 编排与工程规则模板
├── agents/                      # Claude Code agent 定义
│   ├── deep-reasoner.md
│   ├── fast-worker.md
│   └── qa-runner.md
├── CODEX.md                     # Codex 侧扩展说明
├── codex/
│   ├── AGENTS.md                # Codex 编排与工程规则模板
│   └── agents/                  # Codex custom agent 定义
│       ├── deep-reasoner.toml
│       ├── fast-worker.toml
│       └── qa-runner.toml
├── GROK.md                      # Grok Build 侧扩展说明
└── grok/
    ├── AGENTS.md                # Grok 编排与工程规则模板
    ├── config.snippet.toml      # 建议写入 ~/.grok/config.toml 的兼容片段
    ├── agents/                  # Grok agent 定义
    │   ├── deep-reasoner.md
    │   ├── fast-worker.md
    │   └── qa-runner.md
    └── roles/                   # 按 type 的 reasoning_effort 默认
        ├── deep-reasoner.toml
        ├── fast-worker.toml
        └── qa-runner.toml
```

## 使用注意

- **先合并规则，再按项目调整。** 模板中的 Git、计划文档和验证要求不一定适合所有仓库。
- **模型默认继承。** 角色文件不固定具体型号；检查调用覆盖和全局默认，安装或升级后以实际子会话为准。
- **验证 agent 只报告，不修复。** 它运行已确定的检查并回传命令、退出码和失败证据；主模型决定是否与怎样修复。
- **并行写入要谨慎。** 并发写入必须使用各自独立的 worktree，接口和所有权先确定；无法隔离就串行，整合后重新运行测试。
- **委派不等于节省成本。** 主要收益是职责隔离、验证闭环和保持主会话上下文清晰。
- **Grok 用户优先使用 `~/.grok/agents`。** 优先安装本仓库提供的 Grok 角色版本，并核对兼容层加载来源；不要假定 Claude 的角色字段和权限语义在 Grok 上完全相同。

## 参考

- [Claude Code 编排规则](./CLAUDE.md)
- [Claude Code agent 定义](./agents/)
- [Codex 扩展说明](./CODEX.md)
- [Codex 编排规则](./codex/AGENTS.md)
- [Codex custom agent 定义](./codex/agents/)
- [Grok Build 扩展说明](./GROK.md)
- [Grok 编排规则](./grok/AGENTS.md)
- [Grok agent 定义](./grok/agents/)
