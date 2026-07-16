# Revert Orchestration Routing

## Goal

Restore the repository's orchestration rules and related documentation to the
state represented by commit `6f3368d99aa093afc91c90e54a437e606b71732b`,
using non-destructive revert commits.

## Scope

- Revert `6dd945d` (`docs(orchestration): align guidance and architecture`).
- Revert `4801e40` (`refactor(orchestration): use selective agent routing`).
- Verify the resulting tracked tree against `6f3368d`.
- Verify the eight global Claude and Codex configuration files against the
  corresponding files in `6f3368d`.

## Affected Files

The two target commits may restore earlier versions of:

- `CLAUDE.md`
- `codex/AGENTS.md`
- Claude and Codex agent definitions
- `README.md`
- `CODEX.md`
- Architecture diagram sources and PNG
- Prior orchestration plan documentation

This plan document is intentionally separate from the reverted tree.

## Risks

- Revert conflicts if `main` has diverged since the target commits.
- Accidental loss of unrelated changes if the worktree is not clean.
- Documentation or diagram drift if only one of the two commits is reverted.
- Global files may differ from the repository snapshot despite the repository
  revert; any mismatch will be reported rather than overwritten in this task.

## Execution Plan

- [x] Confirm the pre-existing worktree is clean apart from this new plan.
- [x] Update local `main` with `git pull --rebase origin main`.
- [x] Revert `6dd945d` without editing its generated commit message.
- [x] Revert `4801e40` without editing its generated commit message.
- [x] Confirm both revert commits and inspect worktree status.
- [x] Compare the tracked `HEAD` tree with `6f3368d`, excluding this plan.
- [x] Compare all eight global configuration files with `6f3368d` by SHA-256.
- [x] Append implementation notes.
- [x] After independent QA, append review notes and commit this plan separately.

## Verification Criteria

- Both target commits are reverted in newest-to-oldest order.
- No reset, force push, merge commit, or remote push is used.
- The tracked repository tree matches `6f3368d`, with this plan as the only
  additional uncommitted file before its later documentation commit.
- All eight global files match their `6f3368d` counterparts byte-for-byte, or
  any mismatch is explicitly reported without modifying the files.

## Implementation Notes

- `git pull --rebase origin main` reported that local `main` was already up to
  date.
- Reverted `6dd945d` as `2a26715`:
  `Revert "docs(orchestration): align guidance and architecture"`.
- Reverted `4801e40` as `28bf7f9`:
  `Revert "refactor(orchestration): use selective agent routing"`.
- Both reverts completed without conflicts. No reset, force push, merge commit,
  or remote push was used.
- `git diff 6f3368d99aa093afc91c90e54a437e606b71732b HEAD` is empty, confirming
  that the tracked tree matches the requested repository snapshot.
- The only worktree entry after the reverts is this untracked plan document.
- All eight global files under `~/.claude` and `~/.codex` match their
  `6f3368d` repository counterparts by SHA-256. No global file required
  modification.

## Review Notes

- Independent QA passed with no findings.
- The two revert commits apply the inverse patches of `6dd945d` and
  `4801e40`; patch identity checks passed.
- The tracked `HEAD` tree matches
  `6f3368d99aa093afc91c90e54a437e606b71732b`.
- SHA-256 checks passed for all eight global Claude and Codex configuration
  files against the `6f3368d` snapshot.
- Repository status and history checks passed. The revert commits and this plan
  remain local; no remote push was performed.
