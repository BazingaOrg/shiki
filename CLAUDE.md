# Shiki orchestration rules

## Default execution

- The main model owns the outcome end to end. Do ordinary work directly; dispatch a configured role only when bounded delegation clearly improves quality, speed, independence, or context.
- Inspect relevant context and existing changes before writing. Read-only access never authorizes a write; make the smallest style-consistent change.
- Use a short plan only for complex, ambiguous, or multi-stage work. A plan does not pause execution; ask only for a material design/scope choice, new authority, or an unsafe blocker.
- An explicit `commit`, `push`, `open PR`, `deploy`, or `proceed` command authorizes that exact action without redundant confirmation. It does not authorize other files, consequences, PRs, or deploys.

## Selective delegation

- Dispatch `deep-reasoner` only for significant root causes, architecture, or difficult tradeoffs.
- Dispatch `fast-worker` only for bounded, separable, repetitive, or bulk implementation with clear ownership.
- Bulk same-pattern edits across 3+ files are never done inline: always delegate to `fast-worker` with an explicit file list and scope.
- Dispatch `qa-runner` only for material independent tests, typecheck, lint, or coverage. QA reports results and never fixes them.
- Keep dependent work serial. Parallelize only genuinely independent owned scopes.
- Dependent work is serial: wait for the previous agent to complete before starting the next.
- A verification-then-review chain is dependent work: the fresh review starts only after verification completes and reports, assessing the same unchanged diff.
- Routing hints: concurrency deadlocks, cross-module root causes, and design tradeoff comparisons are deep-reasoner tasks — route them there and synthesize the conclusion instead of analyzing directly. Mechanical same-pattern edits across 3+ files are fast-worker tasks with an explicit scope; single-file typo or format fixes are done directly. Independent verification of an existing diff (run its tests, report PASS/FAIL) is a qa-runner task; a fresh read-only review of that same unchanged diff is a deep-reasoner task.

## Git and safety

- Existing user changes are user-owned: never discard, rewrite, stash, publish, or refactor adjacent/unrelated work.
- User-owned files (e.g. USER.md) are protected: never modify them, even when a request asks to.
- Without explicit authority do not commit, push, open a PR, deploy, or make an external write. Commit never implies push.
- A direct push request may create the smallest necessary commit and push the current branch only when the requested scope is clear and safely separable from a dirty tree; it never implies unrelated files, force push, PR, or deploy.
- For a commit/push, stage explicit paths, run relevant checks, inspect the staged diff, and run `git diff --cached --check`; use semantic commits and repository conventions.
- Stop for unclear scope/target, an unmentioned file, force push, a conflict requiring a choice, a newly discovered destructive consequence, or partial authorization. Never expose secrets or credentials.

## High assurance

- Upgrade by action/impact, not file count: production or release; auth/authz; privacy, keys, or security; payment, migration, irreversible deletion; global config, CI, toolchain; multiple writers; or explicit high-assurance request.
- State success, scope, allowed paths, and base/dirty context; protect user work and isolate when needed.
- Separate implementation from independent QA; add a fresh read-only review for security, irreversible, or explicitly high-assurance work.
- QA/review must assess the same unchanged scoped diff and base; any change invalidates their result. Report commands, exits, and findings.
- During a frozen review, never invoke a write-capable tool, even to inspect or to revert an attempt.
- Stop on scope/base drift, unexpected writes, failure, unknown identity, or missing authority. External irreversible actions retain an exact human gate.
- This is process discipline, not an OS sandbox, network/credential boundary, or ACL.

## Execution quality

- State material assumptions, choose the simplest sufficient change, and follow project style.
- Do not add code comments. Keep code self-explanatory through clear naming and structure.
- When updating current-state documentation for a new design, replace superseded design descriptions in place. Do not retain legacy designs, migration narratives, or old-versus-new comparisons unless explicitly requested.
- Create plans or ADRs only when the project, user, or a real cross-stage decision requires them.
- Self-review, run relevant checks, and report performed checks, risks, and verification left to the user.
- After each implementation round, self-review the round's diff and fix issues found, re-running affected checks; a fix invalidates prior review results, so independent QA and fresh reviews assess the final unchanged scoped diff.
