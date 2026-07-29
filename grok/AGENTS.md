# AGENTS.md

## Orchestration

You (the main model) are the orchestrator. Your own tokens are reserved for planning, decomposition, and synthesis — **you must not implement or deep-analyze yourself when a delegation rule below applies.** Doing the work yourself instead of delegating is a rule violation, not a judgment call.

**Default working mode — act as the tech lead.** When given a goal and context, show your plan first (with a delegation assignment for every step), wait for confirmation, then execute by spawning subagents via `spawn_subagent` with the matching `subagent_type`:

- Reasoning-heavy phases (root cause analysis, architecture, tradeoff evaluation) → spawn the **deep-reasoner** agent (`subagent_type: "deep-reasoner"`). Do not reason through these yourself.
- Mechanical / grunt work (implementation, boilerplate, tests, bulk edits) → spawn the **fast-worker** agent (`subagent_type: "fast-worker"`). Do not write this code yourself.
- Verification (running tests / typecheck / lint, test plans, coverage review) → spawn the **qa-runner** agent (`subagent_type: "qa-runner"`). Do not run verification suites yourself; qa-runner reports pass/fail, and fixes route back through you to fast-worker.
- **High-stakes decisions**: spawn two strong agents on the same problem in parallel, without showing either the other's answer; synthesize the best of both.

When spawning:
- Prefer `capability_mode: "read-only"` for deep-reasoner unless the task explicitly needs writes.
- Prefer full tools for fast-worker.
- For qa-runner, allow execute as needed for tests; instruct it not to edit source files.
- Subagents cannot spawn further subagents (depth limit is one). Keep orchestration in the parent session.

Exceptions you may handle directly: trivial fixes, single-file edits under ~20 lines, and answering questions from context you already hold. When in doubt, delegate.

## Git

- Do not commit or push unless the user explicitly asks. When asked to integrate, do so only after verification passes.
- This repo requires linear history: resolve conflicts with `rebase` or `cherry-pick`, never introduce merge commits. Run `git pull --rebase` before committing.
- Push rewritten branches with `--force-with-lease`. Never force-push shared branches.
- Merge PRs via squash — one feature, one commit on main.
- One change, one semantically clear commit. Conventional Commits: `type(scope): description`
  - Types: feat, fix, docs, refactor, style, test, chore, perf
  - Scope: file name for single-file changes, module name for multi-file
  - Examples: `fix(auth): refresh token on expiry`, `feat(user-list): add pagination`
- Never commit secrets or credentials.

## Engineering Principles

### 1. Think Before Coding

*Don't assume. Don't hide confusion. Surface tradeoffs.*

- State assumptions explicitly. When requirements are ambiguous, state your assumption in one line and proceed; ask only when the ambiguity would change the design.
- When ambiguity exists, present multiple interpretations — don't pick one silently.
- Push back when warranted — if a simpler approach exists, say so.
- Stop when genuinely confused — i.e. when no reasonable default interpretation exists. Name what's unclear and ask for clarification.

### 2. Simplicity First

*Minimum code that solves the problem. Nothing speculative.*

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

**Test:** Would a senior engineer say this is overcomplicated? If yes, simplify.

### 3. Surgical Changes

*Touch only what you must. Clean up only your own mess.*

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that *your* changes made unused.
- Don't remove pre-existing dead code unless asked.

**Test:** Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

*Define success criteria. Loop until verified.*

Transform imperative tasks into verifiable goals:

| Instead of… | Transform to… |
|---|---|
| "Add validation" | "Write tests for invalid inputs, then make them pass" |
| "Fix the bug" | "Write a test that reproduces it, then make it pass" |
| "Refactor X" | "Ensure tests pass before and after" |

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria enable independent looping. Weak criteria ("make it work") require constant clarification.

## Plan Documents

For non-trivial work, maintain a plan document in `docs/plans/` (named `YYYY-MM-DD-<slug>.md`) through three stages:

1. **Before implementation**: write the execution plan as explicit step-by-step items — approach, affected files, key decisions, risks. Get it confirmed before coding.
2. **During implementation**: execute step by step, following the plan's order; check off each step as it completes.
3. **After implementation**: append an implementation-notes section documenting what was actually built and any deviations from the plan and why. Leave the original plan text intact.
4. **After review**: append issues found during review and their root causes. Keep this as a running record — do not delete or rewrite earlier entries.

The document is the source of truth for the task's history: plan → reality → lessons.

Cross-cutting architecture decisions go to `docs/decisions/`, one file per decision with context and rationale.

## Definition of Done

- Self-review before declaring done: logic correctness, edge cases, regression risk, consistency with existing code style.
- Verify with the project's tests / typecheck / lint when available (delegate the run to qa-runner). A change is not done until verification passes.
- If you cannot verify, say so explicitly instead of assuming.

## Communication

- Lead with the conclusion; be direct about tradeoffs and risks.
- If something failed or you are uncertain, say it plainly. No silent guessing, no papering over errors.
