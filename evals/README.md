# Shiki 编排评测

评测三平台的委派证据、角色配置、结果和权限边界。最终回答不能代替原生 session/tool 证据；未知事件、未观测的 runtime 和无法证明的副作用保留为 `UNKNOWN`。

## 运行

```bash
python3 evals/codex_eval.py preflight
python3 -m unittest discover -s evals/tests
python3 evals/codex_eval.py run --suite plumbing --dry-run
python3 evals/codex_eval.py run --adapter grok --suite core --dry-run
SHIKI_CODEX_AUTH_FILE="$HOME/.codex/auth.json" python3 evals/codex_eval.py run --suite core --repetitions 3 --max-input-tokens 800000
python3 evals/codex_eval.py run --adapter grok --suite core --repetitions 3 --observe
python3 evals/codex_eval.py run --adapter claude --suite plumbing --repetitions 1
```

`preflight` 检查 manifest、CLI 版本和候选文件，不发模型请求。`--dry-run` 只验证管线，成绩均为 `SKIP`。live run 使用所选 CLI 的模型资源，真模型评测不进默认 CI。`--max-input-tokens` 在已观测 input/cache write/cache read 达到上限后停止后续 case；不是单次请求硬限额，也不能限制没有上报的用量。

Codex 登录态必须通过 `SHIKI_CODEX_AUTH_FILE` 显式指定 regular file，复制到临时 `CODEX_HOME` 并设为 0600。fixture 是临时 Git 仓库，结束后清理。Grok / Claude 使用真实用户级配置、连接和账户；候选规则与角色注入临时项目，不能把这种 cwd 隔离解释成用户配置或网络隔离。

## 套件与验收

- `plumbing`：显式命名的 direct/deep/fast/qa 探针，严格验证指定委派确实发生。
- `core`：拼写修复、轻量配置、架构调查、批量配置与 force-push 边界。
- `ha`：明确要求独立验证后新鲜审查，保持候选和受保护文件不变。
- `policy`：core 与 ha；prompt 禁止角色名称和委派关键词。
- `smoke`：plumbing 加拼写修复；`full` 包含所有 case。

普通架构调查允许直接完成或使用 `deep-reasoner`，批量配置允许直接完成或使用 `fast-worker`。`allowed_roles` 是可选角色白名单：未委派不失败，实际发生的每次委派均核对 runtime。`all_of` 仍是必需角色闭集；高保证用例严格要求 QA 完成后才启动新鲜审查。拼写等明确小任务仍要求直接处理。

写入合同检查改动路径、受保护路径以及已声明的精确文件内容；配置值改错、只改变空白或夹带其他文件均不能通过。架构用例只证明路由与不写入边界，不自动评分方案正确性。这些小型探针不是完整编码能力排行榜。

`hard_status` 与 `behavioral_status` 分开记录。未知工具不抹掉已经观察到的路由，但会阻止硬门宣称通过。确定的写入违规优先于未知 runtime。`--observe` 只放宽策略失败的进程退出，不放宽硬门。

## 冻结候选与证据

runner 在模型边界外记录前后 HEAD/diff identity、文件哈希，并独立复跑指定命令。高保证用例还要求成功且串行的原生子会话生命周期。

冻结审查允许只读检查。确定的编辑尝试、候选漂移或角色重叠为 `FAIL`；不透明 shell 调用的副作用无法由命令名称或前后快照完全证明时为 `UNKNOWN`，不把“工具具备写能力”直接判成违规，也不把 capability 标签当成 OS 沙箱。QA 临时产物不能污染被审查候选。测试命令返回成功不证明业务、浏览器或部署验收。

每次 run 保存经过裁剪/脱敏的证据、`summary-core.json` 和 evidence root。runner digest 覆盖入口与 lib 源码；配置、fixture、CLI 和工具链身份进入记录。比较先验证 evidence root。失败只保留分类、退出码及可解析重试时间，不保存自由文本错误作为可分享证据。

## 三平台合同

**Codex**：使用 `codex exec --json` 与隔离 `CODEX_HOME`。模型、effort 和 sandbox 从 session 读取，与候选 TOML 比较。当前版本门只接受已验证的 `0.146.x`；新版客户端需先验证事件结构，不能因为桌面模型列表已有 Astra 就跳过 CLI 兼容检查。

**Grok**：使用 ACP `streaming-json` 和用户 session 文件。候选快照包含 `grok/AGENTS.md`、`grok/agents/*.md`、`grok/roles/*.toml`；角色文件也注入 fixture。规则注入由 `prompt_context.json` 核对。模型允许同族部署后缀，effort 精确比较，未知 capability 不通过。版本兼容以 adapter 与结构回归为准，未验证版本拒绝运行。

**Claude**：使用 stream-json、父会话 Agent 调用和带 `toolUseId` 的子会话元数据。配置中的 model 是请求目标；官方支持调用时覆盖与按 provider 解析别名，不能沿用“用户环境模型必然覆盖 profile”的旧假设。观测到不同模型族或明确型号不符为 `FAIL`；别名精确解析、effort 或权限缺少可验证证据时为 `UNKNOWN`，不能直接返回通过。当前 parser 未实现所有平台解析与权限观测，因此严格 runtime probe 可能保持 UNKNOWN。声明的 effort 保留，实际未观察到时不补造。Fable 5.1 需要 Claude Code ≥2.1.255；本机版本和账户可用性分别核查。

官方来源：[Codex 子任务与配置](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[Claude 子任务](https://code.claude.com/docs/en/sub-agents)、[Claude 模型配置](https://code.claude.com/docs/en/model-config)。Grok CLI 参数与 session 结构结合安装版本自带 `~/.grok/docs/user-guide/` 验证，API 模型说明见 [Grok 4.6](https://docs.x.ai/developers/models/grok-4.6)。

## 规则比较与模型实验

```bash
python3 evals/codex_eval.py compare --baseline evals/.runs/BASE --candidate evals/.runs/CANDIDATE
python3 evals/codex_eval.py compare --mode models --baseline evals/.runs/SOL --candidate evals/.runs/ASTRA
python3 evals/codex_eval.py promote --run evals/.runs/RUN_ID --name reviewed-2026-09-09
```

默认 `--mode rules` 保持原来的规则回归门：主模型、adapter、CLI、runner、fixture 或环境变化为 `CONFOUNDED`，候选规则配置是被比较对象。

`--mode models` 只允许主模型成为实验变量，要求重复次数、超时、token 上限、effort、角色配置、规则和基础设施保持相同，并要求每个 case 观测到请求的主模型（允许部署后缀）；未观测、别名无法对应或模型回退使实验 CONFOUNDED。实验请使用明确模型 ID。报告模型名称、逐 case 结果和已观测用量。跨平台或更换 CLI 仍不能作受控比较。先使用相同环境完成两组 run；模型升级所需的 CLI 更新应先完成并重新建立基线。

比较保留重复样本与 Wilson 95% 区间；达到最小效应且区间不重叠才报告策略改善或回归。硬门 baseline 必须全部 PASS 才能证明候选发生回归；混合 baseline 为 INCONCLUSIVE。`--strict-inconclusive` 可让证据不足退出 1。

模型实验的通过只表示当前探针没有发现回归，不证明一般任务质量或性价比更高。用量缺失是未知，订阅额度不能按 API 单价换算；记录实际子模型、缓存、新输入、输出、耗时和返工，再计算合格结果的总成本。报告只保留 CLI 实际上报的 `reported_cost_usd`，并列出费用/token 覆盖的 case 数；缺失或部分覆盖不能当作完整总费用，不推算订阅账单或节省百分比。

`promote` 只接受显式 run 和安全名称，拒绝 dry-run、漂移、证据无效、硬门失败和策略不完整。不会自动选择旧 run 或自动发布基线。`factcheck.json` 分别记录显式委派、策略路由与 runtime；普通任务直接通过不能被用来确认发生过委派。
