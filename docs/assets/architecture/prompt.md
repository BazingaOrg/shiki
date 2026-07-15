# Shiki architecture redraw context

## Must preserve

- 保留 6 节点横向主路径：用户目标 → 主模型 → `deep-reasoner` → `fast-worker` → `qa-runner` → 已验证结果。
- 保留主模型作为唯一 focal；它负责规划、分派与综合，不承担专职 agent 的分析、实施或验证职责。
- 保留 QA FAIL 从 `qa-runner` 回到 `fast-worker` 的辅助虚线路径，验证角色只报告，不自行修复。
- 保留底部两条 platform band，并让三个角色按列对齐：Claude Code 映射 Opus / Sonnet / Haiku，Codex 映射 `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`。
- 保留配置载体：Claude Code 使用 `CLAUDE.md` 与 `agents/*.md`，Codex 使用 `codex/AGENTS.md` 与 `codex/agents/*.toml`。

## Suggested additions

- 当前事实源没有要求新增架构对象；后续若角色、模型名或配置路径变化，应先更新仓库定义，再同步图中文字、`title`、`desc` 与 PNG。
- 如需展示并行委派、高风险双模型决策或更细的验证循环，应新建配套流程图，不扩张当前 6 节点主图。

## Visual direction

- 维持从左到右的一次扫描路径，主路径强于回流线，platform band 只承担映射而不成为新节点。
- 使用暖纸 `#f5f4ed`、单一墨蓝 `#1B365D` 与暖灰；保持细线、低圆角、无渐变、无立体效果。
- 主模型是唯一墨蓝焦点，其余节点保持中性；节点和 band 使用统一基线与充足留白。
- 从 `index.html` 以 2800–3200 px 宽重新导出 PNG；不直接编辑、裁切或缩放 PNG。

## Sister boundaries

- 安装步骤、版本兼容、价格或 token、并发策略和 Git 约束属于 `README.md`、`CLAUDE.md` 与 `codex/AGENTS.md`，不进入本图。
- Claude Code 独有的高风险双模型规则留在 `CLAUDE.md`，不绘成跨平台共同机制。
- 简单任务的直接处理例外属于规则说明，不进入主路径。
- 当前没有配套 sister diagram；若未来需要展开分支逻辑，新增独立 flowchart 并在此记录路径。
