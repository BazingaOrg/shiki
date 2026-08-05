"""Pure comparison and promotion gates for Codex evaluation summaries."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .common import utc


def behavioral_samples(results: list[dict[str, Any]], case: str) -> tuple[int, int]:
    rows = [row for row in results if row.get("case") == case and row.get("kind") == "policy"]
    statuses = [row.get("grade", {}).get("behavioral_status") for row in rows]
    usable = [status for status in statuses if status in {"PASS", "FAIL"}]
    return sum(status == "PASS" for status in usable), len(usable)


def _cases(summary: dict[str, Any]) -> set[str]:
    return {str(row.get("case")) for row in summary.get("results", [])}


def confounders(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ("source_drift", "dry_run"):
        if baseline.get(field) or candidate.get(field):
            reasons.append(field)
    for field in ("runner_sha256", "manifest_sha256", "suite", "model", "cli_adapter", "cli_version", "executable_sha256", "toolchain_digest", "network_env_digest"):
        if baseline.get(field) != candidate.get(field):
            reasons.append(f"{field}_drift")
    if _cases(baseline) != _cases(candidate):
        reasons.append("case_set_drift")
    base_cases = {row.get("case"): row.get("case_digest") for row in baseline.get("results", [])}
    cand_cases = {row.get("case"): row.get("case_digest") for row in candidate.get("results", [])}
    if base_cases != cand_cases:
        reasons.append("case_or_fixture_drift")
    base_fixtures = {row.get("case"): row.get("fixture_digest") for row in baseline.get("results", [])}
    cand_fixtures = {row.get("case"): row.get("fixture_digest") for row in candidate.get("results", [])}
    if base_fixtures != cand_fixtures:
        reasons.append("case_or_fixture_drift")
    return sorted(set(reasons))


def compare_summaries(baseline: dict[str, Any], candidate: dict[str, Any], wilson, min_effect: float) -> dict[str, Any]:
    reasons = confounders(baseline, candidate)
    per_case: list[dict[str, Any]] = []
    regression = False
    for case in sorted(_cases(baseline) | _cases(candidate)):
        base = [r for r in baseline.get("results", []) if r.get("case") == case]
        cand = [r for r in candidate.get("results", []) if r.get("case") == case]
        hard = any(r.get("grade", {}).get("hard_gate") for r in base + cand)
        base_hard = [r.get("grade", {}).get("hard_status") for r in base]
        cand_hard = [r.get("grade", {}).get("hard_status") for r in cand]
        clean_baseline = bool(base_hard) and all(status == "PASS" for status in base_hard)
        # INFRA_ERROR carries no behavioral evidence: on a clean baseline only FAIL/UNKNOWN is a regression.
        hard_regression = hard and clean_baseline and any(status in {"FAIL", "UNKNOWN"} for status in cand_hard)
        # A mixed baseline is deliberately not evidence of a regression.
        if hard_regression:
            regression = True
        bpass, bn = behavioral_samples(base, case)
        cpass, cn = behavioral_samples(cand, case)
        behavior = "NOT_APPLICABLE"
        binterval, cinterval = wilson(bpass, bn), wilson(cpass, cn)
        if bn or cn:
            behavior = "INCONCLUSIVE"
            if bn and cn:
                delta = cpass / cn - bpass / bn
                if delta >= min_effect and cinterval[0] > binterval[1]:
                    behavior = "IMPROVED"
                elif delta <= -min_effect and cinterval[1] < binterval[0]:
                    behavior = "REGRESSED"
                    regression = True
                elif delta == 0 and bpass == cpass and bn == cn:
                    behavior = "UNCHANGED"
        infra_only = bool(cand_hard) and all(status == "INFRA_ERROR" for status in cand_hard)
        hard_comparison = "REGRESSED" if hard_regression else ("INCONCLUSIVE" if hard and (not clean_baseline or infra_only) else "NO_REGRESSION")
        per_case.append({"case": case, "hard_baseline": base_hard, "hard_candidate": cand_hard, "hard_regression": hard_regression, "hard_comparison": hard_comparison, "behavioral": behavior, "baseline": {"pass": bpass, "n": bn, "rate": bpass / bn if bn else None, "wilson95": binterval}, "candidate": {"pass": cpass, "n": cn, "rate": cpass / cn if cn else None, "wilson95": cinterval}})
    inconclusive = any(row["hard_comparison"] == "INCONCLUSIVE" or row["behavioral"] == "INCONCLUSIVE" for row in per_case)
    return {"generated_at": utc(), "min_effect": min_effect, "rule": "behavioral change requires min_effect and non-overlapping Wilson 95% intervals; otherwise INCONCLUSIVE", "confounders": reasons, "status": "CONFOUNDED" if reasons else ("REGRESSION" if regression else ("INCONCLUSIVE" if inconclusive else "PASS")), "cases": per_case}
