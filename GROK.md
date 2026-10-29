# Grok Build 编排实践指南

主模型默认直接完成普通工作；需要时通过 `spawn_subagent` 的 `subagent_type` 选择专职角色。没有固定的分析、实施、验证流水线。共享职责与权限要求见 [grok/AGENTS.md](./grok/AGENTS.md)。

## 当前配置

| 角色 | 模型 | effort | permission_mode | role capability 默认 |
| --- | --- | --- | --- | --- |
| deep-reasoner | 默认继承 | high | plan | read-only |
| fast-worker | 默认继承 | medium | default | all |
| qa-runner | 默认继承 | low | default | execute |

角色 frontmatter 省略 `model`。使用父会话模型前检查 `[subagents.models]`、role/persona 和 spawn 覆盖；用实际子会话确认继承。

同一模型通过 effort 区分推理深度。QA 只执行指定检查并报告命令、退出码和失败证据；不设计测试、不修源码。失败由主模型判断：明确问题回实施方，根因不明或重复无进展则调整策略。

## 安装

在仓库根目录执行；已有文件先比较合并，不覆盖用户配置：

```bash
mkdir -p ~/.grok/agents ~/.grok/roles ~/.grok/rules
cp -i grok/agents/deep-reasoner.md ~/.grok/agents/deep-reasoner.md
cp -i grok/agents/fast-worker.md ~/.grok/agents/fast-worker.md
cp -i grok/agents/qa-runner.md ~/.grok/agents/qa-runner.md
cp -i grok/roles/deep-reasoner.toml ~/.grok/roles/deep-reasoner.toml
cp -i grok/roles/fast-worker.toml ~/.grok/roles/fast-worker.toml
cp -i grok/roles/qa-runner.toml ~/.grok/roles/qa-runner.toml
cp -i grok/AGENTS.md ~/.grok/rules/AGENTS.md
```

全局规则放 `~/.grok/rules/`。项目规则只放该项目的命令和例外；项目角色可放 `.grok/agents/` 和 `.grok/roles/`。安装后开启新会话，确认加载与实际模型。

## 角色和配置优先级

完整 agent 文件见 [grok/agents](./grok/agents/)，同名 role 见 [grok/roles](./grok/roles/)。Markdown frontmatter 指定 effort、permission_mode，省略 model；role TOML 指定 reasoning_effort 和 default_capability_mode。两处 effort 保持一致。

安装版本自带 `16-subagents.md` 给出的 model/effort 优先级是：spawn 显式覆盖、role 默认、persona 默认、父会话。还可通过 `[subagents.models]` 指定 per-type 模型。role 文件可被 inline `[subagents.roles.*]` 配置覆盖；不能仅凭文件内容断言最终 runtime。

`permission_mode`、`capability_mode` 与实际文件系统/网络沙箱不是同一个概念。`execute` 允许执行命令，不能据此证明 shell 不会写文件。只读审查不得修改候选；QA 产物应留在允许的临时范围。实际权限及覆盖效果需结合运行时证据核验。

主模型只并行处理接口稳定、范围不冲突的任务。独立验证后审查必须保持顺序和候选身份；普通调查与实施可以由主模型直接完成。

## 避免重复规则

若同时安装 Claude 和 Grok 全局规则，可将 [config.snippet.toml](./grok/config.snippet.toml) 合并到 `~/.grok/config.toml`：

```toml
[compat.claude]
agents = false
```

这关闭用户级 Claude 指令与 agents 兼容加载；不应删除 Claude 配置，也不能假定它关闭项目 `CLAUDE.md` 的发现。用 `grok inspect` 检查当前版本实际注入的规则与角色。

## 验证与版本

```bash
grok --version
grok models
grok inspect
python3 evals/codex_eval.py preflight
python3 evals/codex_eval.py run --adapter grok --suite plumbing --dry-run
```

在 `/config-agents` 或 `/agents` 中确认三个角色，用任务窗检查显式委派的子会话、模型与 effort。再检查普通小任务直接执行，独立核验任务按顺序分派。没有委派不单独构成普通任务失败。

Grok 1.0.24 的 direct 和 qa-runner 短请求已于 2026-09-09 实测：模型为 grok-4.6-build，QA effort 为 low。子任务由父调用结果的 subagent_id 与持久化 metadata 关联，不能按轮询顺序猜测。脱敏结构样本进入 evals 回归；这不等于完整策略套件或其他两个角色已通过 live 验收。

新版 headless 参数已移除 `--no-memory`，使用进程环境 `GROK_MEMORY=0` 关闭跨会话 memory。评测仍会加载真实用户配置与连接；fixture 隔离不等于账户隔离。未观测到 capability 或 shell 副作用时保留 UNKNOWN，不凭配置补造权限证据。详情见 [evals 指南](./evals/README.md)。

## 参考

- [官方 Grok 4.6 模型说明](https://docs.x.ai/developers/models/grok-4.6)
- 安装版本本地官方指南：`~/.grok/docs/user-guide/12-project-rules.md`、`16-subagents.md`、`13-memory.md`、`14-headless-mode.md`
- [统一入口与 Claude 配置](./README.md)
