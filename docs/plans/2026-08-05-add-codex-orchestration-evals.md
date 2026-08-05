# Codex 编排评测框架

日期：2026-08-05

## 目标

为 Shiki 的 Codex 编排提供可复跑、可比较的评测。框架只把原生 session/event、Git 状态和命令退出码作为执行证据；模型最终文字只属于自述，不参与硬门判定。

## 当前结构

- `evals/codex/manifest.json`：plumbing 与 policy case 合同。
- `evals/codex/lib/fixtures.py`：隔离的临时 Git fixture。
- `evals/codex/lib/runtime.py`：候选快照、临时 `CODEX_HOME`、auth 安全复制、环境与超时处理。
- `evals/codex/lib/trace.py`：0.146.x session/event 适配、角色 runtime、命令 owner、生命周期和候选 identity。
- `evals/codex/lib/evidence.py`：allowlist 脱敏证据、secret scan、确定性 evidence root。
- `evals/codex/lib/compare.py`：硬回归与重复行为样本的保守比较。
- `evals/codex/codex_eval.py`：`preflight`、`run`、`compare`、`promote` 入口。

## 已实现合同

- [x] `plumbing|policy|smoke|full` 套件；policy prompt 静态拒绝角色名和委派提示词。
- [x] 硬安全/通路状态、策略路由状态、基础设施错误分别统计。
- [x] 精确/必需写入、保护路径、runner-owned command、runtime override、串行完成合同。
- [x] 高保障由 runner 独立核对 HEAD、binary diff、测试与写入事件；模型中介的 child command 只作观察，不能产生硬 PASS。
- [x] 每轮冻结 `codex/AGENTS.md` 和三个 custom-agent TOML；运行中源漂移阻断比较/提升。
- [x] 原始 session 只提取 allowlist 机器事实；不保存 prompt、最终消息、系统指令或完整工具输出。
- [x] compare 保留 repetitions，仅以 PASS/FAIL 形成行为样本，使用 pass rate、Wilson 95% 区间和最小效应；不生成单一总分。
- [x] evidence root 可复算；dry-run、漂移、证据损坏或不兼容输入以 `CONFOUNDED` 拒绝比较。
- [x] baseline 只能通过显式 `promote` 生成，并要求真实运行、证据健康、无硬失败和无 secret-scan 命中。
- [x] 官方文档事实与 explicit plumbing、无提示 policy routing、runtime override 三类运行观察分别记录。

## 验证与已知事实

- 静态单元测试、`py_compile`、preflight、dry-run 和 `git diff --check` 已运行。
- 0.146.x adapter 已用脱敏的真实 session shape 固化测试，覆盖 quoted JavaScript exec input、结构化退出码、`event_msg.task_complete`/`turn_aborted` 生命周期与角色 runtime。
- 旧 live probe 曾观察到 `deep-reasoner` 实际 `workspace-write`，与候选 TOML 的 `read-only` 期望冲突；旧 run 的 runner/manifest 已漂移，不可提升为当前 baseline。
- 当前 smoke live run `run-lreo919y` 的五项均为统一 `codex exit 1` 基础设施错误；它由旧 runner 生成，不具备当前 summary attestation，仅作历史失败样本，不作 baseline。
- 加入诊断后，最小复跑 `run-660k685e` 将原因确定为 Codex usage limit，并报告 2026-08-08 15:04 后再试；0 个行为样本，不构成编排结论。
- 当前只声明 0.146.x adapter；0.144.x 的历史实验不构成受支持合同。

## 后续验收

1. usage limit 恢复后运行 `smoke`；通过后再以 `policy --repetitions 5` 建立首个可比较候选。
2. 独立 QA 与 fresh read-only review 针对同一份未变 diff 复核。
3. 只有人工确认后执行 `promote`；不自动提交 baseline，不自动 commit/push。
