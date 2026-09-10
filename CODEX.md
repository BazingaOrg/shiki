# Codex 多模型编排实践指南

主模型直接完成普通工作，需要时使用命名 custom agent。复杂实施中持续的设计判断仍由主模型负责；明确范围的调查、机械实施和独立检查可以分派。职责规则见 [codex/AGENTS.md](./codex/AGENTS.md)。

## 模型与职责

| 角色 | 模型 | effort | 默认 sandbox |
| --- | --- | --- | --- |
| 主模型 | 当前会话选择；日常可用 Sol，困难任务考虑 Astra | 按任务选择 | 当前会话配置 |
| deep-reasoner | gpt-5.6-sol | high | read-only |
| fast-worker | gpt-5.6-terra | medium | workspace-write |
| qa-runner | gpt-5.6-luna | low | workspace-write |

Sol 负责有界复杂推理，Terra 负责已明确的实施，Luna 运行指定检查并报告结果。测试方案设计、覆盖率判断和根因分析不交给 qa-runner。需要独立审查时使用新鲜上下文，不能以主模型自审代替。

Astra 是困难任务的升级选项，不自动替换所有 worker。可以让已选择 Astra 的主模型直接处理疑难问题；当前 deep-reasoner 配置固定 Sol。模型能力与账户可用性分开确认，API 单价不能直接换算订阅额度。

## 安装

在仓库根目录执行；已有同名文件先比较并合并，不覆盖用户配置：

```bash
mkdir -p ~/.codex/agents
cp -i codex/agents/deep-reasoner.toml ~/.codex/agents/deep-reasoner.toml
cp -i codex/agents/fast-worker.toml ~/.codex/agents/fast-worker.toml
cp -i codex/agents/qa-runner.toml ~/.codex/agents/qa-runner.toml
cp -i codex/AGENTS.md ~/.codex/AGENTS.md
```

项目独有的命令和约束放项目 `AGENTS.md`，项目独有角色放 `.codex/agents/`。不要在每个项目重复安装整份全局规则。文件变化后开启新会话，再确认角色加载与实际 runtime。

## 配置与优先级

每个 TOML 必须声明 `name`、`description`、`developer_instructions`；本项目还显式设置 model、effort 与 sandbox。完整定义直接见 [codex/agents](./codex/agents/)，避免文档中的重复配置与文件漂移。

当前官方模型与 effort 解析规则：先取 spawn 显式值，再取 `[agents]` 默认，再取父会话；随后自定义角色文件中显式设置的字段具有优先级。因此不能只在 spawn 时要求 Astra，就假定覆盖了 deep-reasoner 文件里的 Sol。切换固定角色模型需调整角色配置并核验新会话。

未指定的其他配置通常继承父会话。沙箱存在独立的运行时覆盖规则：父会话的 `/permissions`、`--yolo` 等 live overrides 可以重新应用到子会话。`read-only` 是配置意图，不是无条件的物理保证；以实际子会话权限为准。QA 的 workspace-write 用于测试产物，禁止修源码仍是职责约束。

## 并发与成本

当前官方配置示例：

```toml
[agents]
max_concurrent_threads_per_session = 3
```

这里的 3 是保守示例，不是官方默认值。只在有明确并行收益时调整并发，已有 `max_threads` 是兼容别名。字段以安装版本为准，不能把最新文档字段直接写入旧 CLI 后假定生效。

只并行处理接口稳定、范围不冲突的任务。每个任务只传目标、范围、必要背景和验收条件，返回精简证据。明确故障回原实施方修复；根因不明或重复无进展时由主模型重新判断。高 effort 用于困难推理，不用于单纯等待命令结束。

## 验证

1. 检查安装文件与加载结果；显式要求调用 deep-reasoner，使用 `/agent` 查看子会话。
2. 核对实际 model、effort 和 sandbox，不只查看主会话选择器。
3. 分别测试普通任务直接完成、可选委派、明确独立 QA 后审查。
4. 运行 [evals](./evals/README.md) 的 preflight 和 dry-run，再对已支持 CLI 做小规模 live probe。

仓库 Codex adapter 当前只验证到 0.146.x。桌面可选 Astra不代表 PATH 中 CLI 或评测适配已支持新版；更新 CLI 后先验证事件结构，再更新版本门和基线。

## 官方参考

- [子任务、角色字段和模型优先级](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [当前模型与价格](https://developers.openai.com/api/docs/pricing)

## 致谢

本指南的编排思路参考并受益于以下两篇分享,特此感谢:

- [@diegocabezas01 关于 Claude Code 编排的分享](https://x.com/diegocabezas01/status/2072436501263339841)
- [用 Claude Code 将三万行 Go 项目移植到 Rust:Agent Team 实践与 Harness 效率优化](https://maxlv.net/blog/porting-mihomo-to-rust-with-claude/) — Max Lv

## License

MIT
