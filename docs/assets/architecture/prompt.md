# Shiki architecture redraw context

## Must preserve

- 保留 hub-and-spoke 语义：用户目标进入主模型，主模型是唯一 focal，并端到端负责直接处理、路由、综合、验证与修复决策。
- 保留两类出口：主模型默认走「直接处理 → 定向验证 → 已验证结果」；仅在委派有实质收益时，才分支到 `deep-reasoner`、`fast-worker` 或 `qa-runner`。
- 三个 agent 都是 bounded、self-contained 的按需分支，结果必须回到主模型；QA FAIL 也回主模型，由主模型决定直接修复或重新委派，不自动回到 `fast-worker`。
- 保留底部两条 platform band，并让三个角色按列对齐：Claude Code 映射 Opus / Sonnet / Haiku，Codex 映射 `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`。
- 保留配置载体：Claude Code 使用 `CLAUDE.md` 与 `agents/*.md`，Codex 使用 `codex/AGENTS.md` 与 `codex/agents/*.toml`。

## Suggested additions

- 如需表达复杂任务的短计划，可作为主模型节点的文字属性，不要把「写计划」画成暂停或审批节点。
- 如需展开独立并行与依赖顺序，应新建配套 flowchart；不要把当前路由总览扩张成执行时序图。
- 后续若角色、模型名或配置路径变化，应先更新仓库事实源，再同步图中文字、SVG `title`、`desc` 与 PNG。

## Visual direction

- 维持主模型为唯一墨蓝焦点；直接处理路径使用墨蓝强调，按需 agent 使用中性暖灰，结果回流使用细虚线。
- 节点总数不超过 9；当前语义节点为用户目标、主模型、直接处理、三个专职 agent 与已验证结果，共 7 个。
- 使用暖纸 `#f5f4ed`、单一墨蓝 `#1B365D` 与暖灰；细线、低圆角、无渐变、无阴影、无 3D、无纯白。
- SVG 必须包含 `role="img"`、`title` 与 `desc`，不使用外部 fetch、script、img 或网络字体；坐标尽量落在 4 px 网格。
- 每次 HTML 变化后都从 `index.html` 重新导出 2400–3200 px 宽 PNG；不直接编辑、裁切或缩放 PNG。

## Sister boundaries

- 安装步骤、版本兼容、价格或 token、permission mode、并发策略和 Git 约束属于 `README.md`、`CLAUDE.md` 与 `codex/AGENTS.md`，不进入本图。
- Claude Code 独有的条件式 high-stakes 双独立分析规则留在 `CLAUDE.md`，不绘成跨平台共同机制。
- 哪些任务可直接处理、哪些任务值得委派，以两份顶层规则和各 agent description 为事实源；本图只概括共同路由边界。
- 当前没有配套 sister diagram；若未来需要展开审批、并行或修复分支，新增独立 flowchart 并在此记录路径。
