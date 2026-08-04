# Optional auditable protocol

This is an advanced repository reference, not a normative dependency of the compact global rules. Use the full protocol only when the user explicitly adopts a complete auditable workflow; ordinary high-assurance work uses the shorter risk controls in the active platform rules.

## Optional full workflow

Capture success criteria, allowed paths, base/dirty context, and the required human gate. Protect user changes and isolate the candidate when needed. Keep implementation, independent QA, and—when security, irreversible impact, or explicit assurance requires it—a fresh read-only review separate.

QA and review assess the same unchanged scoped diff and base. Record commands, exit codes, and findings; a changed diff or base invalidates prior results. Stop for scope/base drift, unexpected writes, failures, unknown identity, or missing authorization.

An explicit `commit`, `push`, `open PR`, `deploy`, or `proceed` command authorizes only that action; it does not waive QA/review or authorize a new side effect. Payment, migration, irreversible deletion, and external writes retain an exact human gate. This protocol is process discipline and Git audit, not an OS sandbox, network/credential boundary, or ACL.

## Optional templates

- [Delegation spec](templates/delegation-spec.md)
- [Run evidence](templates/run-evidence.md)
