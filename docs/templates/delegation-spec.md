# Delegation Spec vN

> Only for the optional full auditable protocol; ordinary high-assurance work does not require this file.

> 将此文件复制为 `.shiki/runs/<run-id>/spec/v1.md`。冻结后不得原地改写；语义变更新建 `v2.md` 并重新取得用户确认。

## Identity

- Run ID:
- Base full SHA:
- Active spec version:
- Request and success criteria:
- User confirmation for verified lane:

## Scope

- `allowed_write_paths` (repo-relative candidate paths only):
- `ephemeral_paths` (non-candidate temporary paths):
- Protected user scoped dirty changes:
- Explicitly excluded paths/actions:

`allowed_write_paths` is a candidate-scope declaration, not an ACL or OS sandbox. A requested write outside it is `PATH_VIOLATION` and stops for a revised spec.

## Authorized work and verification

- Candidate changes:
- QA commands and expected evidence:
- Fresh review questions:
- Required human gate / external authority:

## Frozen protocol

Candidate identity is: `base SHA + active spec version + SHA-256(binary full-index patch)`. Any candidate change invalidates prior QA/review PASS. A semantic spec change requires a new version and reconfirmation; the plan may evolve but cannot relax this spec.
