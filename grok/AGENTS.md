# Shiki orchestration rules

## Default execution

- The main model owns orchestration, synthesis, and the outcome end to end. Do ordinary work directly; use `spawn_subagent` with the matching `subagent_type` only when bounded delegation clearly improves quality, speed, independence, or context.
- Inspect relevant context and existing changes before writing. Read-only access never authorizes a write; make the smallest style-consistent change.
- Use a short plan for complex, ambiguous, or multi-stage work; create a persistent plan or ADR only when the project, user, or a real cross-stage decision requires one. Planning does not pause execution; ask only for a material design/scope choice, new authority, or an unsafe blocker.
- An explicit `commit`, `push`, `open PR`, `deploy`, or `proceed` command authorizes that exact action without redundant confirmation. It does not authorize other files, consequences, PRs, or deploys.

## Selective delegation

- Spawn `deep-reasoner` only for significant root causes, including concurrency or cross-module failures, architecture, difficult tradeoffs, or a fresh read-only review.
- Spawn `fast-worker` only for bounded, separable mechanical, repetitive, or bulk implementation with explicit ownership; handle small edits directly when delegation offers no clear benefit.
- Spawn `qa-runner` only for material independent tests, typecheck, lint, or coverage. QA reports results and never fixes them.
- Parallelize only independent owned scopes. Keep dependent work serial; in a verification-then-review chain, verification must finish before fresh review of the same unchanged diff.

## Git and safety

- Existing user changes are user-owned: never discard, rewrite, stash, publish, or refactor adjacent/unrelated work.
- User-owned files (e.g. USER.md) are protected: never modify them, even when a request asks to.
- Without explicit authority do not commit, push, open a PR, deploy, or make an external write. Commit never implies push.
- A direct push request may create the smallest necessary commit and push the current branch only when the requested scope is clear and safely separable from a dirty tree; it never implies unrelated files, force push, PR, or deploy.
- For a commit/push, stage explicit paths, run relevant checks, inspect the staged diff, and run `git diff --cached --check`; use semantic commits and repository conventions.
- Stop for unclear scope/target, an unmentioned file, force push, a conflict requiring a choice, a newly discovered destructive consequence, or partial authorization. Never expose secrets or credentials.

## High assurance

- Upgrade by action/impact, not file count: production or release; auth/authz; privacy, keys, or security; payment, migration, irreversible deletion; global config, CI, toolchain; multiple writers; or explicit high-assurance request.
- Before work, state success criteria, scope, allowed paths, and base/dirty context; protect user work and isolate when needed.
- Separate implementation from independent QA; add a fresh read-only review for security, irreversible, or explicitly high-assurance work. QA and review assess the same unchanged scoped diff and base; any change invalidates their results. Report commands, exits, and findings.
- During a frozen review, never invoke a write-capable tool, even to inspect or revert an attempt. Stop on scope/base drift, unexpected writes, failure, unknown identity, or missing authority; external irreversible actions retain an exact human gate.
- This is process discipline, not an OS sandbox, network/credential boundary, or ACL.

## Execution quality

- State material assumptions, choose the simplest sufficient change, and follow project style.
- Do not add code comments. Keep code self-explanatory through clear naming and structure.
- When updating current-state documentation for a new design, replace superseded design descriptions in place. Do not retain legacy designs, migration narratives, or old-versus-new comparisons unless explicitly requested.
- After each implementation round, self-review the diff, fix findings, rerun affected checks, and report performed checks, risks, and remaining verification. Any fix invalidates prior QA or review.
