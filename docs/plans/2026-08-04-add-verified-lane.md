# Verified lane 执行计划

日期：2026-08-04

## 目标

为 Claude Code、Codex 与 Grok Build 增加一致的双 lane 协议：默认轻量委派；只在明确的高保障触发条件下进入可审计的 verified lane。首版只定义跨平台提示词与流程约束，不提供 runtime 或安全沙箱。

## 执行计划

- [x] 核对当前规则、角色定义、README 与维护型架构图的既有合同和导出方式。
- [x] 新增 verified lane 协议、委派规格与运行证据模板，并记录边界 ADR。
- [x] 将共享触发矩阵和角色职责同步到三平台规则与 agent 定义；只保留平台调用语法差异。
- [x] 更新 README、CODEX、GROK 的用户级安装与双 lane 说明，不改用户全局配置。
- [x] 按最终协议重绘架构图 HTML、同步 prompt，并从 HTML 重导 PNG。
- [x] 执行 Markdown、HTML、PNG 与变更范围的轻量自检，补充实现说明。

## 影响文件

- `docs/verified-lane.md`、`docs/templates/`
- `docs/decisions/0001-verified-lane-boundary.md`
- `CLAUDE.md`、`codex/AGENTS.md`、`grok/AGENTS.md` 与各平台 agent 定义
- `README.md`、`CODEX.md`、`GROK.md`
- `docs/assets/architecture/{index.html,architecture.png,prompt.md}`

## 风险

- 文本协议不能替代 OS sandbox、机器级 allowlist 或平台 runtime；必须明确 fail-closed 是流程约束。
- 三个平台的调用 API 不同；共享合同不得假装调用语法也一致。
- `.shiki/runs/` 默认保留未跟踪，不能因文档变更自动修改目标项目 `.gitignore`。

## Implementation Notes

- 新增 `docs/verified-lane.md` 作为跨平台规范来源，并提供 frozen spec 与 run evidence 模板；ADR 明确首版只提供提示词/流程约束和 Git 审计。
- 三套入口使用同一触发条件、candidate identity、状态/错误、角色和 stage-only 合同；差异仅保留 Claude 的 dispatch、Codex 的 spawn、Grok 的 `spawn_subagent` 调用措辞。
- 更新三类 agent：worker 只产候选，QA 绑定精确 identity 且只报告，fresh deep-reasoner 只读审查；未触及 `grok/roles/*.toml` 与 `grok/config.snippet.toml`。
- README、CODEX、GROK 改为用户级共享安装为主、项目级覆盖为辅，并说明 `.shiki/runs/` 默认未跟踪且不自动改 `.gitignore`。
- 维护型架构图重绘为 light 默认与 verified 分支，`index.html`、`prompt.md` 与从 HTML 导出的 3000×1900 PNG 已同步。使用隔离 Chrome profile；Chrome 产生的 updater/SSL 噪声未影响输出。
- 轻量自检通过：协议关键字机械扫描、所需新文件存在、SVG 可访问性与禁止模式扫描、PNG 尺寸/新鲜度及 `git diff --check`。未运行应用测试套件：本仓库本轮仅为 Markdown、TOML 与静态 HTML/PNG 文档变更。
- 补充明确执行命令的授权语义：已明确的 commit、push、PR、deploy 或继续既有确认计划不再触发重复确认，但仍受检查、candidate identity、QA/review 与精确 human gate 约束。

## Review Notes

- QA 发现 `GROK.md` 的 config snippet 相对链接漏掉 `grok/` 目录；根因是入口文档复制了仓库根目录相对路径时未按实际文件位置复核。已改为 `./grok/config.snippet.toml`，并复查本轮新增的同类 verified-lane 链接。
- QA 发现首版图的右侧 gate 与箭头贴近画布边界，且流程标签压在支线和节点附近；根因是下方 verified 链未为完整人工 gate 节点预留宽度。已移除箭头标签，将五个节点重排至 x=350–1110 的安全区，并从最终 HTML 重导 PNG。
- 用户指出已明确执行命令后仍可能被规则要求再次确认；根因是“先出计划并等待确认”未明确其与后续精确命令的优先关系。三平台规则现将精确命令视为对应动作的确认，同时列出必须重新询问的范围/目标/force-push/冲突/新破坏性后果/部分授权条件；协议同步保留 payment、migration、不可逆删除等独立 human gate。
