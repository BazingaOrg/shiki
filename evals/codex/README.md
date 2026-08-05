# Codex 编排评测

此工具用结构化 trace 评估本地 Codex 编排，不把最终文本当成委派证据。命名角色、runtime、命令 owner 与 lifecycle 只来自 session/event 证据；未知关键结构一律为 `UNKNOWN`。

```bash
python3 evals/codex/codex_eval.py preflight
python3 evals/codex/codex_eval.py run --suite plumbing --dry-run
SHIKI_CODEX_AUTH_FILE="$HOME/.codex/auth.json" python3 evals/codex/codex_eval.py run --suite policy --case policy-typo-direct --timeout 180
python3 evals/codex/codex_eval.py run --suite smoke --dry-run
SHIKI_CODEX_AUTH_FILE="$HOME/.codex/auth.json" python3 evals/codex/codex_eval.py run --suite full --repetitions 5
python3 evals/codex/codex_eval.py compare --baseline evals/codex/baselines/reviewed.json --candidate evals/codex/.runs/RUN_ID
python3 evals/codex/codex_eval.py promote --run evals/codex/.runs/RUN_ID --name reviewed-2026-08-05
python3 -m unittest discover -s evals/codex/tests
```

每个 case 显式标记 `kind` 与 `suites`。`plumbing` suite 使用显式命名的 direct/deep/fast/qa 探针验证管线；`policy` prompt 静态拒绝 `delegate`、`agent`、`role`、命名角色与 `subagent`，用中性任务衡量路由。`smoke` 是低成本子集，`full` 包含所有 case。

policy 覆盖 typo 直接处理、跨模块并发架构分析、五份 config 的机械编辑、已有 diff/test 的独立验证，以及 auth 高保证验证加新鲜审查。fixture 在 `lib/fixtures.py`，均为临时 Git 仓库；不会写入当前工作区。

每项结果独立包含 `hard_status`（安全、runtime、写入和 plumbing 合同）与 `behavioral_status`（policy routing），避免一个总状态掩盖另一个。trace 保存角色 `started_at`/`completed_at`、runtime 与模型中介的命令观察，但后者不能产生硬 PASS。高保证 case 由 runner 在模型边界外独立复跑测试、记录 HEAD/diff identity，并要求 QA 与 fresh review 都有成功且串行的原生 lifecycle；运行期间出现文件写入事件、child `apply_patch`/exec、identity 漂移或 aborted lifecycle 都会失败或 `UNKNOWN`。这是有意的保守门：当前 `codex exec` 无法证明 child shell 只读。

`preflight` 验证 manifest 合同（`validate_manifest` 为唯一契约）、Codex 可执行文件及受支持的 0.146.x 版本，但不发起模型请求。live run 才会使用 Codex 资源；登录态必须通过 `SHIKI_CODEX_AUTH_FILE` 显式选择，runner 将其复制成临时 `0600` regular file，不使用指向真实凭据的 symlink。临时 `CODEX_HOME` 与 candidate snapshot 的隔离由 `lib/runtime.py` 负责；Codex、Git、Python、PATH 与网络相关环境都进入 provenance。非零退出只保存分类、退出码和可解析的重试时间，不保留自由文本错误内容，也不会混入策略成绩。

`compare` 从显式 baseline/candidate 输入生成 JSON 和 Markdown。硬门只有在 baseline 的同一 hard case 全部 `PASS`、candidate 出现 `FAIL`/`UNKNOWN`/`INFRA_ERROR` 时才是 regression；任何混合 baseline 都是 `INCONCLUSIVE`。policy 指标保留每次 repetition，仅以 `PASS/FAIL` 构成样本，报告 pass rate 与 Wilson 95% 区间；只有达到 `min_effect` 且区间不重叠才报告改进或回归。候选配置 hash 是被比较的 treatment，不是 confounder；runner、manifest、case、fixture、model、CLI binary/version 或 network-env 漂移才拒绝比较。CI 可加 `--strict-inconclusive` 让证据不足返回 exit 1。

每个 run 有由 allowlisted per-case artifacts 与 `summary-core.json` 算出的 `evidence_root`；core 绑定成绩、候选 hash、配置、fixture 与运行 provenance，`summary.json`、report 和 index 不参与自身哈希。`compare` 会同时验证 evidence root 与 summary/core 一致性。`promote` 只接受安全 basename，并拒绝任何 dry、漂移、infra、UNKNOWN、硬失败、策略不完整或无效 evidence；生成的最小 baseline 另带 canonical digest，绝不自动选择旧 run。

`factcheck.json` 将显式子 agent 支持、无委派词 policy prompt 的实际路由，以及 custom-agent runtime override 分为独立 observations。claim outcome 为 `doc_only`、`runtime_only`、`confirmed`、`conflict` 或 `unknown`；显式 prompt 的成功不构成 policy-routing 确认，policy 路由的 PASS/FAIL 单独驱动 `subagents-guidance-trigger` claim 的 `confirmed`/`conflict`。

## 官方事实边界

事实表以 2026-08-05 获取的官方资料为准：[AGENTS.md 发现与优先级](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[自定义 agents 与子任务](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[`codex exec --json` 与权限](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-exec)。文档只证明产品合同；当前机器、当前 CLI 和当前配置是否真的满足它，仍由 runtime observation 单独核验。

当前 adapter 只声明兼容 `codex-cli 0.146.x`。一次通过不应直接提升为稳定 baseline；建议 plumbing 先跑一轮，policy 至少跑五轮，再由人工执行 `promote`。
