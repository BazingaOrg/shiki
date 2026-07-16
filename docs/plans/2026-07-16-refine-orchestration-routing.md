# Refine orchestration routing

## Goal

Align the Claude Code and Codex templates around selective delegation: the main model owns the task end to end and delegates only bounded, self-contained work when doing so materially improves quality, speed, or context isolation. Keep the surrounding documentation, agent discovery descriptions, and maintained architecture asset consistent with that behavior.

## Official basis

- OpenAI GPT-5.6 Prompt Guidance: use explicit decision rules, the fewest useful tool loops, and avoid unnecessary approval gates for safe local work.
- OpenAI Codex documentation for subagents and `AGENTS.md`: delegation is useful for bounded complex work and is influenced by repository instructions.
- Anthropic Claude Code best practices, subagents, and memory documentation: keep project instructions concise, use subagents for isolated work, and respect the active permission mode rather than adding a separate blanket approval gate.
- Kami maintained-diagram guidance: update `index.html`, the same-name PNG, and `prompt.md` together; render the PNG from HTML rather than editing it directly.

## Affected files

- `CLAUDE.md`
- `codex/AGENTS.md`
- `agents/deep-reasoner.md`
- `agents/fast-worker.md`
- `agents/qa-runner.md`
- `codex/agents/deep-reasoner.toml`
- `codex/agents/fast-worker.toml`
- `codex/agents/qa-runner.toml`
- `README.md`
- `CODEX.md`
- `docs/assets/architecture/index.html`
- `docs/assets/architecture/architecture.png`
- `docs/assets/architecture/prompt.md`
- `docs/plans/2026-07-16-refine-orchestration-routing.md`

## Execution plan

- [x] Record the original plan, decisions, risks, acceptance scenarios, and verification commands before editing.
- [x] Replace the fixed delegation pipeline in `CLAUDE.md` and `codex/AGENTS.md` with shared selective-routing rules; keep Claude-only high-stakes guidance conditional and permission-aware.
- [x] Scope plan documents to complex or multi-phase work and allow focused validation by the main model while retaining real verification as a completion requirement.
- [x] Narrow Claude and Codex agent discovery descriptions so routine answers, inspections, edits, and checks do not trigger automatic delegation.
- [x] Synchronize `README.md` and `CODEX.md` with direct handling, selective delegation, qualified automatic routing, and the revised QA failure path.
- [x] Redraw the maintained architecture asset as a hub-and-spoke routing diagram, update its redraw prompt, and export a fresh PNG from HTML.
- [x] Run focused mechanical checks and append implementation notes without rewriting this original plan.

## Key decisions

- Direct handling is the default; delegation is an optimization, not a mandatory lifecycle.
- Delegated tasks must be bounded and self-contained. Independent branches may run in parallel; dependent phases remain sequential.
- A written plan does not itself create an approval gate. Pause only for missing user input, new authority, an external or destructive action, material scope expansion, or an explicitly active Plan Mode.
- `deep-reasoner` is for substantial root-cause, architecture, and tradeoff work; `fast-worker` is for repetitive, bulk, or clearly separable implementation; `qa-runner` is for substantial or high-volume independent verification.
- QA reports return to the main model, which chooses the repair path. They do not automatically route to `fast-worker`.
- Claude may request two independent analyses for high-stakes decisions only when an additional perspective materially reduces risk. Codex receives no Claude-only rule.
- The architecture figure shows routing semantics, not installation, pricing, concurrency, or permission details.

## Risks

- Agent descriptions that remain broad could bypass the new top-level routing boundary.
- Repeated legacy snippets in `CODEX.md` could teach a fixed pipeline even after `codex/AGENTS.md` changes.
- A diagram with too many arrows could obscure the main model as the single focal point.
- HTML and PNG may drift if the PNG is not re-exported after the final SVG edit.
- TOML quoting or YAML frontmatter edits could make agent definitions unloadable.

## Representative acceptance scenarios

| Request | Expected route |
| --- | --- |
| Explain a setting, report status, review a small excerpt, or answer a clarification | Main model handles directly |
| Inspect a small number of files or run a focused read-only check | Main model handles directly |
| Make a quick targeted low-risk edit and run its focused check | Main model handles and verifies directly |
| Investigate a substantial root cause or architecture tradeoff | Delegate a bounded task to `deep-reasoner` |
| Apply repetitive, bulk, or clearly separable edits | Delegate to `fast-worker` when useful |
| Independently validate a substantial change or high-volume suite | Delegate to `qa-runner`; report returns to main model |
| QA reports a failure | Main model selects the repair path; no automatic worker handoff |
| Two tasks are dependent | Run sequentially; do not parallelize merely because agents exist |
| Safe local implementation or non-destructive verification | Continue under the active permission mode without a new approval pause |

## Verification commands

```bash
git diff --check
python3 -c 'import pathlib, tomllib; [tomllib.loads(p.read_text()) for p in pathlib.Path("codex/agents").glob("*.toml")]'
python3 -c 'from pathlib import Path; files=list(Path("agents").glob("*.md")); assert all(p.read_text().startswith("---\n") and p.read_text().count("---") >= 2 for p in files)'
rg -n "When in doubt|强制路由|固定流水线|主模型只做|route.*fast-worker|回到 fast-worker|串行委派" CLAUDE.md codex/AGENTS.md README.md CODEX.md docs/assets/architecture
file docs/assets/architecture/architecture.png
sips -g pixelWidth -g pixelHeight docs/assets/architecture/architecture.png
test docs/assets/architecture/architecture.png -nt docs/assets/architecture/index.html
```

## Implementation Notes

- Replaced the mandatory three-stage delegation language in both top-level rule templates with a shared direct-first decision boundary. The main model now owns execution and focused validation, while delegation is limited to bounded work with a material benefit.
- Kept Claude's high-stakes dual-analysis rule as a conditional Claude-only clause and tied safe local continuation to the active permission mode. No Claude-only rule was added to the Codex template.
- Narrowed plan-document creation to complex or multi-phase work. The original plan remains immutable, but plan creation no longer creates an approval pause by itself.
- Narrowed all six discovery descriptions without changing model pins, sandbox settings, or specialist instruction bodies.
- Updated README routing, validation examples, QA failure handling, and figure caption. Compressed `CODEX.md` by replacing duplicated AGENTS and TOML snippets with links to their canonical files.
- Rebuilt the architecture as a seven-node hub-and-spoke figure. Direct handling is the emphasized path; all delegated results and QA failures return to the main model. Claude/Codex mapping bands remain intact.
- Exported `architecture.png` from the final HTML with:

  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2.4 --window-size=1200,760 --screenshot=docs/assets/architecture/architecture.png "file:///Users/zhangyouxiu/Downloads/Code/shiki/docs/assets/architecture/index.html"
  ```

  The resulting PNG is 2880 × 1824, RGB, and newer than `index.html`.
- Mechanical checks passed: `git diff --check`, TOML parsing, YAML frontmatter boundary checks, stale-routing phrase search, PNG type/dimensions/freshness, and the HTML external-resource/gradient/shadow/pure-white scan.
- Deviation: none in scope. The architecture image required one visual refinement after the first render to separate role labels from agent names; the PNG was re-exported after the final HTML edit as required.
- Post-QA repair clarified the authorization boundary in both top-level templates: answer/review/diagnose/plan requests remain inspect-and-report unless a change is requested, while change/build/fix requests authorize scoped local edits and relevant non-destructive validation. It also permits explicitly authorized external actions under the active permission controls, requires specific authorization for destructive or expensive actions, and corrects the plan-document lifecycle count from three to four stages.

## Review Notes

- **Missing authorization boundary.** The first draft grouped direct handling by task size but did not distinguish inspect-and-report requests from requests that authorize local modification. Root cause: routing and mutation authority were treated as one decision. Minimal fix: both top-level templates now state that answer, explanation, review, diagnosis, plan, status, and clarification requests only inspect relevant materials and report unless the user also asks for a change; change, build, and fix requests authorize scoped local edits plus relevant non-destructive validation.
- **Authorized external actions still paused.** The first stop rule named any external action as a reason to stop, even when the user had explicitly authorized it and the active permission controls allowed it. Root cause: the approval gate did not distinguish missing authority from an already authorized action. Minimal fix: explicitly authorized external actions may proceed under the current permission mode or active permissions and approval policy; only unauthorized external writes, actions needing new authority, destructive or expensive actions without specific authorization, and material scope expansion require a pause. Broad authorization remains insufficient for destructive work.
- **Plan lifecycle count mismatch.** The heading said “three stages” while the numbered lifecycle contained four. Root cause: the original wording was not updated when the review stage was retained. Minimal fix: changed both templates to “four stages” without altering the four existing lifecycle items.
- Final QA passed all 8 representative routing scenarios. All focused checks also passed: diff whitespace, TOML parsing, YAML frontmatter boundaries, relative Markdown links, stale-routing phrase scan, architecture HTML constraints, PNG type/dimensions/freshness, diagram visual review, and cross-file routing consistency.
