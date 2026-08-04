# 精简全局编排规则计划

日期：2026-08-04

## 已确认目标

将三平台用户级入口从强制全任务编排改为“默认直做、选择性委派、按影响升级”的短规则；保留可选高级审计参考，不自动安装或要求完整协议。

## 执行计划

- [x] 核对现有入口、文档、角色定义和架构图合同，确认工作区已有改动全部保留。
- [x] 将 Claude、Codex、Grok 入口压缩为共享语义的自包含短规则，仅保留平台调用句差异。
- [x] 将 verified 协议、模板、ADR 与三份说明文档调整为可选高级参考。
- [x] 精简九个角色定义，保留范围、独立验证和 fresh review 边界。
- [x] 重绘维护型架构图三件套并从 HTML 导出 PNG。
- [x] 运行长度、对照、链接、TOML、静态图和 diff 自检，记录结果。

## 影响文件

- `CLAUDE.md`、`codex/AGENTS.md`、`grok/AGENTS.md`
- `docs/verified-lane.md`、`docs/templates/`、`docs/decisions/0001-verified-lane-boundary.md`
- `README.md`、`CODEX.md`、`GROK.md`
- 三平台九个 agent 定义
- `docs/assets/architecture/{index.html,prompt.md,architecture.png}`

## 风险

- 压缩入口不能削弱 secret、force、外部不可逆操作及用户既有改动保护。
- 三个平台有不同调用与权限模型；只能共享语义，不能暗示权限等价。
- 图与说明必须移除旧的完整状态机/审计细节，且 PNG 必须来自最终 HTML。

## Implementation Notes

- 三个全局入口重写为 38 行、约 3.3KB 的自包含规则；共同约束默认直做、选择性角色、精确授权、dirty work 保护、Git 边界和按影响升级的独立核验。平台差异只保留 Claude dispatch、Codex named custom agent、Grok `spawn_subagent`/`subagent_type` 与 parent 编排语义。
- `docs/verified-lane.md` 和两个模板改为用户明确采用时才使用的可选高级参考；ADR 追加 scope update，不改写其历史决策。
- 九个角色定义移除完整审计状态依赖，保留 bounded scope、scope/base drift、QA 不修复与 fresh read-only review 的职责边界。
- README、CODEX、GROK 改为默认直做、选择性委派和风险升级；未修改任何平台配置字段、roles、config 或用户级文件。
- 图三件套改为选择性委派与高保障 enclosure；PNG 由最终 HTML 重新导出为 3000×1900，并在原图查看器复核。

## Review Notes

- 自检通过：入口均低于 60 行和 5120B，禁用旧完整协议/强制编排短语扫描无命中，Codex TOML 可由 `tomllib` 解析，`git diff --check` 通过，SVG 禁用模式扫描与可访问性标记通过。未执行运行时或真实平台委派测试；它们依赖用户保留的客户端/账号环境。
- QA 发现 README 与 Codex/Grok 指南仍含旧的强制路由、冷启动必然 spawn 与计划确认全文；根因是首轮只压缩了入口，未同步历史指南的嵌入示例和验收口径。已改为默认直做、按收益选择性委派与 optional routing smoke，并保留真实平台 inspect/日志核对。
