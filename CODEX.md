# Codex 多模型编排实践指南

主模型直接完成普通工作，需要时使用命名 custom agent。复杂实施中持续的设计判断仍由主模型负责；明确范围的调查、机械实施和独立检查可以分派。职责规则见 [codex/AGENTS.md](./codex/AGENTS.md)。

## 模型与职责

| 角色 | 模型 | effort | 职责 |
| --- | --- | --- | --- |
| 主模型 | 用户选择 | 当前会话 | 判断与整合 |
| deep-reasoner | 默认继承 | high | 只读调查或独立审查 |
| fast-worker | 默认继承 | medium | 有界机械实施 |
| qa-runner | 默认继承 | low | 运行指定检查，不修源码 |

角色 TOML 省略 `model`，保留职责和推理强度。轻量角色不表示必须使用较弱模型。测试设计与覆盖判断由主模型负责；独立审查使用全新上下文。

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

每个 TOML 必须声明 `name`、`description`、`developer_instructions`；本项目保留 effort 与 sandbox 字段，省略 model。完整定义直接见 [codex/agents](./codex/agents/)，避免文档中的重复配置与文件漂移。

模型解析先取显式 spawn 值，再取 `[agents]` 默认，再取父会话；自定义角色文件中的显式模型设置会覆盖该选择。本模板不固定模型；若希望跟随主会话，也须检查全局默认和调用参数。不要把省略字段当作已观测到继承。

当前官方文档说明子 Agent 继承父会话权限，自定义角色不能建立独立沙箱。模板 sandbox 字段保留给旧版本评测合同；不要据此声称当前客户端强制只读。QA 不改源码、审查不改候选属于职责约束；实际权限须核验。

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
