# Plan: Add Grok Build support to Shiki

Date: 2026-07-28

## Goal

Add a first-class Grok Build template path parallel to Claude Code and Codex:
three named agents (`deep-reasoner`, `fast-worker`, `qa-runner`) plus an
orchestration rules file, install docs, and optional global install under
`~/.grok/`.

## Approach

1. Native `grok/` directory (not Claude-compat only).
2. Agent definitions as YAML-frontmatter Markdown under `grok/agents/`, matching
   official discovery paths: `~/.grok/agents/` and `.grok/agents/`.
3. Project rules as `grok/AGENTS.md` (spawn wording). Global rules install to
   official home path `~/.grok/rules/` (not a bare `~/.grok/AGENTS.md`).
4. Default model: `grok-4.5` for all three; differentiate with `permission_mode`
   and role instructions. Document local overrides via `grok models`.
5. Update root `README.md`; add `GROK.md` practice guide (peer of `CODEX.md`).

## Affected files

- `docs/plans/2026-07-28-grok-build-support.md` (this file)
- `grok/agents/deep-reasoner.md`
- `grok/agents/fast-worker.md`
- `grok/agents/qa-runner.md`
- `grok/AGENTS.md`
- `GROK.md`
- `README.md`
- Local install: `~/.grok/agents/*.md`, `~/.grok/rules/AGENTS.md`

## Key decisions

| Decision | Choice |
| --- | --- |
| Layout | `grok/` parallel to `codex/` |
| Model map | All `grok-4.5`; effort/light models optional later |
| deep-reasoner permission | `permission_mode: plan` (read-only style) |
| fast-worker / qa-runner permission | `permission_mode: default` |
| Global rules location | `~/.grok/rules/AGENTS.md` per project-rules docs |
| Plugin / workflow | Out of MVP scope |

## Risks

- Single available model reduces cost-tiering benefit.
- Claude-compat may also load `~/.claude/agents/`; prefer `~/.grok/agents` for Grok users.
- Frontmatter fields may evolve with Grok CLI versions.

## Steps

- [x] Add `grok/agents/*.md` from official agent profile shape
- [x] Add `grok/AGENTS.md` orchestration template
- [x] Add `GROK.md` install/verify guide
- [x] Update root `README.md`
- [x] Install into `~/.grok/agents` and `~/.grok/rules`
- [x] Verify with `grok inspect` when possible

## Implementation notes

What was built:

- `grok/agents/{deep-reasoner,fast-worker,qa-runner}.md` with official-style
  frontmatter: `name`, `description`, `model`, `prompt_mode`, `permission_mode`,
  `agents_md` (aligned with `~/.grok/bundled/agents/*`).
- `deep-reasoner` uses `permission_mode: plan` (read-only); others `default`.
- All three pin `model: grok-4.5`.
- `grok/AGENTS.md` uses explicit `spawn_subagent` / `subagent_type` wording.
- `GROK.md` documents install paths, including global rules at `~/.grok/rules/`.
- Root `README.md` updated for three platforms.

Local install (2026-07-28):

- `~/.grok/agents/{deep-reasoner,fast-worker,qa-runner}.md`
- `~/.grok/rules/AGENTS.md` (official global rules location)

Verification (`grok inspect` in this repo, Grok 0.2.112):

- Project Instructions includes `~/.grok/rules/AGENTS.md` as global.
- Agents list includes user `deep-reasoner`, `fast-worker`, `qa-runner`
  alongside builtins.

Deviations:

- No plugin packaging (deferred).
- Single model `grok-4.5` with effort tiering (high/medium/low) instead of three model IDs.

### Follow-up optimization (same day)

- Agent frontmatter: `effort: high|medium|low`.
- Roles: `grok/roles/{deep-reasoner,fast-worker,qa-runner}.toml` with
  `reasoning_effort` + `default_capability_mode`.
- `~/.grok/config.toml`: `[compat.claude] agents = false` to disable global
  `~/.claude/Claude.md` injection (project-root `Claude.md` still loads).
- Docs: `GROK.md` / `README.md` updated; `grok/config.snippet.toml` added.
- Local install refreshed under `~/.grok/agents`, `~/.grok/roles`, `~/.grok/rules`.
