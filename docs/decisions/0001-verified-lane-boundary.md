# ADR 0001：Verified lane 是流程协议，不是安全 runtime

日期：2026-08-04
状态：Accepted

## Context

Shiki 面向多个 agent 客户端，需要在默认快速协作之外，为高影响任务提供可复核的候选、验证与人工准入路径。不同客户端没有共同的机器级沙箱、allowlist 或工作流 runtime。

## Decision

首版采用跨平台的提示词/流程协议：默认走 light lane；满足明确触发条件时，由用户确认后进入 verified lane。verified lane 冻结可版本化 spec，在完整 base SHA 的隔离 worktree 中产出候选，绑定 QA 与 fresh deep-reasoner 的只读审查，并默认只 stage 精确补丁。

`allowed_write_paths` 是 repo-relative 的候选写入范围，`ephemeral_paths` 单列；越界按流程 fail closed。它们不是 ACL，也不是完整 sandbox。`.shiki/runs/` 记录审计资料，但默认不改目标项目 `.gitignore`，不自动 stage、commit、push、PR 或 deploy。

## Consequences

- 能形成可复查的 Git 事后审计与人工 gate；不能保证进程、网络、凭据或文件系统隔离。
- 不等同于 Claude Architect 或任何平台专有 runtime；各平台只在 agent 调用语法上不同。
- 如需机器级控制，后续应独立设计 runtime、身份、密钥与 OS sandbox 方案，而不是把它隐含进本协议。

## Superseding / Scope update — 2026-08-04

全局入口现为短、自包含且默认选择性委派的规则。本 ADR 仅保留为用户明确采用完整可审计流程时的仓库参考：不自动安装，不要求普通高保障工作使用，也不代表各平台有相同 runtime 或权限能力。
