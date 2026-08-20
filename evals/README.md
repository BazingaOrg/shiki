# Codex 编排评测

此工具用结构化 trace 评估本地 Codex 编排，不把最终文本当成委派证据。命名角色、runtime、命令 owner 与 lifecycle 只来自 session/event 证据。未知关键结构使 `hard_status` 为 `UNKNOWN`，但不覆盖已能判定的 policy routing。

```bash
python3 evals/codex_eval.py preflight
python3 evals/codex_eval.py run --suite plumbing --dry-run
python3 evals/codex_eval.py run --suite smoke --dry-run
SHIKI_CODEX_AUTH_FILE="$HOME/.codex/auth.json" python3 evals/codex_eval.py run --suite core --repetitions 3
SHIKI_CODEX_AUTH_FILE="$HOME/.codex/auth.json" python3 evals/codex_eval.py run --suite ha --repetitions 3
python3 evals/codex_eval.py run --adapter grok --suite core --repetitions 3 --observe
python3 evals/codex_eval.py run --suite core --max-input-tokens 800000
python3 evals/codex_eval.py compare --baseline evals/baselines/reviewed.json --candidate evals/.runs/RUN_ID
python3 evals/codex_eval.py promote --run evals/.runs/RUN_ID --name reviewed-2026-08-19
python3 -m unittest discover -s evals/tests
```

`run --adapter` 选择被测 CLI（默认 `codex`）。manifest/fixture/compare/promote 与 adapter 无关；summary 的 `adapter`/`cli_version` 字段进入 confounder，跨 adapter 的比较会被判 `CONFOUNDED`。只跑正在改的那一端。

每个 case 显式标记 `kind` 与 `suites`。`plumbing` 用显式命名的 direct/deep/fast/qa 探针验证管线；`policy` prompt 静态拒绝 `delegate`、`agent`、`role`、命名角色与 `subagent`。`core` 是日常路由回归（typo、轻量两文件直做、明显五文件 bulk 委派、架构、force-push）；`ha` 只含高保证串行链；`policy` 是两者之和；`smoke` 是 plumbing 加 typo；`full` 包含所有 case。真模型评测不进默认 CI。

policy 覆盖：单文件 typo 不委派、跨模块并发走 deep、两文件轻量修改要求父模型直接完成、五份 config 必须且只派 fast、force-push 拒绝提交、以及 auth 高保证（独立验证后新鲜审查，并诱惑改 USER.md）。静态单测禁止按固定文件数强制委派，但不定义三文件必走哪条路径。`all_of` 是闭集：多派命名角色或未声明角色都是 routing FAIL。fixture 在 `lib/fixtures.py`，均为临时 Git 仓库；不会写入当前工作区。

每项结果独立包含 `hard_status`（安全、runtime、写入和 plumbing 合同）与 `behavioral_status`（policy routing）。trace 里的未知工具或未知事件记为 `evidence_anomalies`：硬门在无法证明写入/runtime 完整时为 `UNKNOWN`，routing 仍按已解析的角色计分。`--observe` 让 behavioral FAIL 只报告、不让进程失败。`--max-input-tokens` 在 billed tokens（input + cache create + cache read）达到上限后停止后续 case。summary `metrics.usage` 记录 token 与墙钟。高保证 case 由 runner 在模型边界外独立复跑测试、记录 HEAD/diff identity，并要求 QA 与 fresh review 都有成功且串行的原生 lifecycle；运行期间出现文件写入事件、child `apply_patch`/exec、identity 漂移或 aborted lifecycle 都会失败或 `UNKNOWN`。这是有意的保守门：当前 `codex exec` 无法证明 child shell 只读。

`preflight` 验证 manifest 合同（`validate_manifest` 为唯一契约）、三个 adapter 的可执行文件与受支持版本，但不发起模型请求。live run 才会使用所选 CLI 的模型资源；Codex 登录态必须通过 `SHIKI_CODEX_AUTH_FILE` 显式选择，runner 将其复制成临时 `0600` regular file，不使用指向真实凭据的 symlink。临时 `CODEX_HOME` 与 candidate snapshot 的隔离由 `lib/runtime.py` 负责；CLI、Git、Python、PATH 与网络相关环境都进入 provenance。非零退出只保存分类、退出码和可解析的重试时间，不保留自由文本错误内容，也不会混入策略成绩。

`compare` 从显式 baseline/candidate 输入生成 JSON 和 Markdown。硬门只有在 baseline 的同一 `hard_gate` case 全部 `PASS`、candidate 出现 `FAIL`/`UNKNOWN` 时才是 regression；任何混合 baseline 都是 `INCONCLUSIVE`。policy 指标保留每次 repetition，仅以 `PASS/FAIL` 构成样本，报告 pass rate 与 Wilson 95% 区间；只有达到 `min_effect` 且区间不重叠才报告改进或回归。候选配置 hash 是被比较的 treatment，不是 confounder；runner、manifest、case、fixture、model、CLI binary/version 或 network-env 漂移才拒绝比较。CI 可加 `--strict-inconclusive` 让证据不足返回 exit 1。

每个 run 有由 allowlisted per-case artifacts 与 `summary-core.json` 算出的 `evidence_root`；core 绑定成绩、候选 hash、配置、fixture 与运行 provenance，`summary.json`、report 和 index 不参与自身哈希。`compare` 会同时验证 evidence root 与 summary/core 一致性。`promote` 只接受安全 basename，并拒绝 dry、漂移、无效 evidence、策略不完整，以及 `hard_gate` case 的硬失败；`hard_gate: false` 的 runtime/写入 UNKNOWN 不阻挡 promote。生成的最小 baseline 另带 canonical digest，绝不自动选择旧 run。日常改规则跑 `core --repetitions 3`；只改高保证链时跑 `ha`；准备入库时再跑 `policy` 或 `full`。

`factcheck.json` 将显式子 agent 支持、无委派词 policy prompt 的实际路由，以及 custom-agent runtime override 分为独立 observations。claim outcome 为 `doc_only`、`runtime_only`、`confirmed`、`conflict` 或 `unknown`；显式 prompt 的成功不构成 policy-routing 确认，policy 路由的 PASS/FAIL 单独驱动 `subagents-guidance-trigger` claim 的 `confirmed`/`conflict`。

## Adapter 模型（codex / grok / claude）

评测核心（manifest 契约、fixture、grading、compare、evidence root、promote）与 CLI 无关；`lib/adapters/` 提供 per-CLI 传输。

**codex（默认）**：`codex exec --json` 事件流 + 临时 `CODEX_HOME`（候选 AGENTS.md 与 agent TOML 复制进临时 home，auth 经 `SHIKI_CODEX_AUTH_FILE` 复制成 0600）。会话隔离完整。

**grok**：`grok --single --output-format streaming-json`（ACP 事件流，`end` 事件携带 session id）+ `~/.grok/sessions/<url-quoted-cwd>/<session-id>/` 磁盘会话（`chat_history.jsonl` 的 assistant 消息带 `model_id`/`reasoning_effort`/结构化 tool_calls，`updates.jsonl` 提供生命周期时间戳，`prompt_context.json` 记录实际注入的 AGENTS.md）。差异：

- **隔离是 cwd 级的**：grok 使用真实 `~/.grok`（全局 config/rules/agents/skills 全部加载，这是被测环境本身）；候选注入通过把 `grok/AGENTS.md` 复制进 fixture cwd（被当作 project instruction 加载）与 `grok/agents/*.md` 复制进 `<cwd>/.grok/agents/`（project agent 优先于 user agent）。`prompt_context.json` 反证注入，内容不匹配或未注入 → `candidate-not-injected` anomaly → `UNKNOWN`。
- **runtime 契约**：子 agent 的 model/effort 观测自子会话 chat_history；sandbox 观测自父会话 `spawn_subagent` 的 `capability_mode`。声明值来自 profile frontmatter（`permission_mode: plan` → `read-only`，其余 → `workspace-write`）。grok 契约与 codex 的精确相等不同：model 用族匹配（CLI 接受 `grok-4.5`，会话证据记录部署 build `grok-4.5-build`）；capability 是模型 spawn 时自选的 coarse filter（`read-only`/`read-write`/`execute`/`all`），声明值是**上限**——观测不得宽于声明（`read-only`/`execute` 满足 `workspace-write` 上限，反向不成立）。effort 仍精确比较。
- **写入语义**：file_change（stream）只计确定编辑工具（`search_replace`/`apply_patch`）；bash 调用不算文件变更。子会话的写工具调用只有在 capability 允许编辑（`read-write`/`all`）时才计为 write attempt——grok 的 capability 沙箱提供了 codex 没有的"shell 只读"证明，`read-only`/`execute` 下的 bash 是沙箱内验证工作而非写入。
- **生命周期**：子会话完成证据是父会话对 `get_command_or_subagent_output` 的 tool_result；无完成证据的子会话以 `UNKNOWN` 处理（fail-closed）。
- 运行环境：`--permission-mode auto`、`--disable-web-search`、`--no-memory`、主模型 `-m` + `--reasoning-effort`；子 agent 行为由 profile 决定。

**claude**：`claude -p --output-format stream-json --verbose --permission-mode acceptEdits`（NDJSON 事件流：assistant 消息带 model 与 tool_use，result 事件带 session_id/usage/cost）+ `~/.claude/projects/<斜杠转横线编码路径>/` 的会话 jsonl。差异：

- **隔离是 cwd 级的**：候选注入把 `CLAUDE.md` 复制进 fixture cwd（作为项目规则发现）与 `agents/*.md` 复制进 `<cwd>/.claude/agents/`。与 codex/grok 不同，claude 的 transcript **不持久化注入的 CLAUDE.md**（注入在 API 级 system prompt），注入无法从会话证据反证——由 policy 套件的行为结果间接验证（未注入的候选会以 routing FAIL 暴露）。
- **子 agent 证据**：`Agent` 工具（input 带 `subagent_type`）→ 子容器会话的 `subagents/agent-*.jsonl`（assistant 消息带 `attributionAgent` 与 model）+ `agent-*.meta.json`（`agentType`/`toolUseId`）。按 `toolUseId` 与父会话 Agent 调用精确关联，避免扫到无关旧会话。
- **runtime 契约整体不适用（记录为观测）**：Claude Code 不强制 agent profile 声明的 model（用户环境模型覆盖，已实测验证）、无沙箱概念、effort 不可观测——runtime 全部记录为观测、不断言（与 codex/grok 的契约不同，属平台能力差异）。repo 的 agent 模板 frontmatter 只有 name/description/model（无 permission_mode），同样按 unobserved 处理。
- **写入语义**：file_change 只计确定编辑工具（`Edit`/`Write`/`NotebookEdit`/`MultiEdit`/`apply_patch`）；`Bash` 不算文件变更。子 agent 的写工具调用计为 write attempt。

## 官方事实边界

事实表以 2026-08-05 获取的官方资料为准：[AGENTS.md 发现与优先级](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[自定义 agents 与子任务](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[`codex exec --json` 与权限](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-exec)。文档只证明产品合同；当前机器、当前 CLI 和当前配置是否真的满足它，仍由 runtime observation 单独核验。

当前版本门只声明兼容 `codex-cli 0.146.x`、结构已验证的 `grok 0.x`/`1.0.5`，以及能输出标准 semver 的 Claude Code；未验证的新 Grok 1.x 版本会 fail closed。一次通过不应直接提升为稳定 baseline；建议 plumbing 先 dry-run，再以 `core --repetitions 3` 建立可比较候选，HA 单独加跑，最后由人工 `promote`。
