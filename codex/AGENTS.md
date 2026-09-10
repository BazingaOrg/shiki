# Shiki orchestration rules

## Default execution

- The main model owns the outcome. Do ordinary work directly; spawn a named custom agent only when bounded delegation clearly improves quality, speed, independence, or context.
- Inspect relevant context and existing changes before writing. Read-only access never authorizes a write; make the smallest style-consistent change.
- Use a short plan for ambiguous or multi-stage work; persist plans or ADRs only when needed. Planning does not pause execution; ask only for material choices, missing authority, or unsafe blockers.
- Honor explicit authorization without redundant confirmation. “Proceed” continues the specified step; it does not imply commit, push, PR, or deployment unless explicitly included.

## Selective delegation

- Spawn `deep-reasoner` for bounded root-cause, architecture, or tradeoff investigations when delegation adds value, or for required independent review. Complexity alone does not require delegation.
- Spawn `fast-worker` only for bounded, separable mechanical, repetitive, or bulk implementation with explicit ownership; handle small edits directly when delegation offers no clear benefit.
- Spawn `qa-runner` for material independent execution of specified tests, typecheck, lint, or coverage commands. QA reports evidence and never fixes failures; test design and coverage judgments belong to the main model or a reasoning specialist.
- Give each subagent a goal, owned scope, necessary context, constraints, and acceptance checks. Request concise findings, paths, evidence, and blockers. Avoid unrelated history/logs and repeating completed investigations.
- Keep ongoing design judgment with the main model. Reuse workers for clear fixes; reassess or escalate unclear causes, design conflicts, or repeated lack of progress. Independent review requires fresh context.
- Parallelize nonconflicting scopes with stable interfaces; keep dependencies serial. Required verification precedes fresh review of the same candidate. Continue independent work while waiting.

## Git and safety

- Existing user changes are user-owned: never discard, rewrite, stash, publish, or refactor adjacent/unrelated work.
- Treat `USER.md` and paths explicitly designated read-only by the task or project as protected. Do not modify protected paths or reinterpret a preservation constraint as permission to tidy them.
- Without explicit authority do not commit, push, open a PR, deploy, or make an external write. Commit never implies push.
- A direct push request may create the smallest necessary commit and push the current branch only when the requested scope is clear and safely separable from a dirty tree; it never implies unrelated files, force push, PR, or deploy.
- For a commit/push, stage explicit paths, run relevant checks, inspect the staged diff, and run `git diff --cached --check`; use semantic commits and repository conventions.
- Complete necessary related edits within the authorized goal. Pause only the affected action for an unclear target, an explicit path boundary, material scope/risk expansion, force push, a conflict requiring a choice, or missing authority. Never expose secrets or credentials.

## High assurance

- Require independent verification for material production/release, auth, privacy/security, payment, data migration, global config, CI/toolchain changes, irreversible operations, or concurrent writers with integration risk; also when explicitly requested. Read-only discussion, file count, and topic labels alone do not trigger this process.
- Before high-assurance implementation, state acceptance criteria, scope, allowed paths, and base/dirty context; isolate when needed.
- Separate implementation from independent QA; add fresh read-only review for material security changes, irreversible operations, or explicit high-assurance requests. Self-review cannot substitute. Bind both to the same scoped diff/base; candidate changes require renewed verification and review.
- During frozen review, inspect read-only; do not mutate the candidate, fix findings, or publish. Report defects; stop on scope/base drift, unexpected writes, or unknown identity. Checks may create disposable artifacts outside reviewed scope. Irreversible external actions require explicit authorization for the action and target.
- This is process discipline, not an OS sandbox, network/credential boundary, or ACL.

## Execution quality

- State material assumptions, choose the simplest sufficient change, and follow project style.
- Do not add code comments. Keep code self-explanatory through clear naming and structure.
- When updating current-state documentation for a new design, replace superseded design descriptions in place. Do not retain legacy designs, migration narratives, or old-versus-new comparisons unless explicitly requested.
- After implementation, self-review the diff, fix findings, and rerun affected checks. Reuse still-applicable results unless changes, failures, or unresolved risks justify more checks. Report actual commands, outcomes, and remaining verification; distinguish static checks from live behavior and never present an unrun check as passed.
