# Shiki architecture redraw context

## Must preserve

- 主路径表达用户目标 → 主模型 → 默认直接处理或选择性角色 → 结果。
- 角色是可选且有界的 deep、worker、QA；高保障只表达同一未变 diff、独立 QA、fresh review 与精确授权。
- 不画完整状态机、`.shiki`、spec 或 patch hash；不暗示平台权限相同。

## Suggested additions

- 若完整可审计协议被用户明确采用，可另画专门审计图；当前图只画通用风险控制。

## Visual direction

- 1200×760 暖纸 `#f5f4ed`、单一墨蓝 `#1B365D`、暖灰、细线、无渐变/阴影/脚本/外部资源。
- 保持少于 9 个节点、清晰留白与安全边距；SVG 具备 `role="img"`、`title`、`desc`。HTML 改动后重导 3000px PNG。

## Sister boundaries

- 可选完整审计协议在 `docs/verified-lane.md`；平台安装与实际权限在 README、CODEX、GROK。
- 图外保留具体命令、模型版本、运行时权限和 Git 细节。
