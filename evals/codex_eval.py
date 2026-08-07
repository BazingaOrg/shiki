#!/usr/bin/env python3
"""Evidence-first, static-contract evaluation for local Codex orchestration."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FORBIDDEN_POLICY_TOKENS = re.compile(r"\b(?:delegate|agent|role|deep-reasoner|fast-worker|qa-runner|subagent)\b", re.I)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.adapters import ADAPTERS, get_adapter
from lib.adapters.base import exact_runtime
from lib.common import ROLES, changed, digest, dump, files, load, redact_text, safe_relative, sha, utc
from lib.compare import compare_summaries
from lib.evidence import secret_patterns, verify_run, write_evidence_index, write_summary_attestation
from lib.fixtures import fixture, git_state
from lib.runtime import env_provenance
from lib.trace import normalize_trace


def redacted(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)[0]
    return value


def infra_diagnostic(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    messages = [stderr]
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") in {"error", "turn.failed"}:
            messages.append(str(event.get("message") or event.get("error") or ""))
    safe_text = redact_text("\n".join(messages).strip())[0]
    lowered = safe_text.lower()
    category = next((name for name, needles in (
        ("rate_limit", ("rate limit", "usage limit", "quota")),
        ("authentication", ("auth", "login", "unauthorized")),
        ("model", ("model", "unsupported")),
        ("network", ("network", "connect", "timed out", "dns")),
        ("configuration", ("config", "toml", "unknown feature")),
    ) if any(needle in lowered for needle in needles)), "unknown")
    retry = re.search(r"try again at ([^.\n]+)", safe_text, re.I)
    return {"exit_code": returncode, "category": category, "retry_at": retry.group(1).strip() if retry else None}


def _bad_paths(value: Any) -> bool:
    return not isinstance(value, list) or any(not isinstance(path, str) or not safe_relative(path) for path in value)


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    if manifest.get("schema_version") != 3:
        errors.append("unsupported schema_version")
    if set(manifest) - {"schema_version", "comparison", "cases"}:
        errors.append("unknown manifest field")
    min_effect = manifest.get("comparison", {}).get("min_effect", 0.2)
    if not isinstance(min_effect, (int, float)) or not 0 <= min_effect <= 1:
        errors.append("bad comparison.min_effect")
    for case in manifest.get("cases", []):
        ident = case.get("id", "?")
        required = {"id", "kind", "suites", "fixture", "prompt", "expected"}
        if not required <= set(case):
            errors.append(f"missing fields: {ident}")
            continue
        if set(case) - required:
            errors.append(f"unknown case field: {ident}")
        if ident in seen:
            errors.append(f"duplicate case: {ident}")
        seen.add(ident)
        if case["kind"] not in {"plumbing", "policy"} or not isinstance(case["suites"], list) or not case["suites"] or any(suite not in {"plumbing", "policy", "smoke", "full"} for suite in case["suites"]):
            errors.append(f"bad kind/suites: {ident}")
        if case["kind"] not in case["suites"] or "full" not in case["suites"]:
            errors.append(f"case must include kind and full suites: {ident}")
        if case["fixture"] not in {"direct", "qa", "bulk", "architecture", "code-test-diff"}:
            errors.append(f"bad fixture: {ident}")
        if case["kind"] == "policy" and FORBIDDEN_POLICY_TOKENS.search(case["prompt"]):
            errors.append(f"forbidden policy token: {ident}")
        expected = case["expected"]
        allowed = {"routing", "runtime", "required_changed_paths", "exact_changed_paths", "protected_paths", "runner_commands", "hard_gate", "require_serial_completion", "require_same_identity"}
        if not isinstance(expected, dict) or set(expected) - allowed:
            errors.append(f"unknown expected field: {ident}")
            continue
        routing = expected.get("routing", {})
        if not isinstance(routing, dict) or set(routing) - {"all_of", "none_of", "ordered_roles"}:
            errors.append(f"bad routing: {ident}")
        elif any(role not in ROLES for key in ("all_of", "none_of", "ordered_roles") for role in routing.get(key, [])):
            errors.append(f"bad routing role: {ident}")
        for key in ("required_changed_paths", "exact_changed_paths", "protected_paths"):
            if key in expected and _bad_paths(expected[key]):
                errors.append(f"unsafe {key}: {ident}")
        # Runtime contract values are derived from the candidate agent TOMLs, never duplicated here.
        for runtime in expected.get("runtime", []):
            if not isinstance(runtime, dict) or set(runtime) != {"role"} or runtime["role"] not in ROLES:
                errors.append(f"bad runtime: {ident}")
        safe_runner_commands = {"git diff --check", "python3 -m unittest test_auth.py", "git rev-list --count HEAD"}
        for command in expected.get("runner_commands", []):
            if not isinstance(command, dict) or set(command) != {"command", "exit_code"} or command.get("command") not in safe_runner_commands or not isinstance(command.get("exit_code"), int):
                errors.append(f"bad required command: {ident}")
        if not isinstance(expected.get("require_serial_completion", False), bool) or not isinstance(expected.get("require_same_identity", False), bool):
            errors.append(f"bad boolean contract: {ident}")
    return errors or ([] if manifest.get("cases") else ["no cases"])


def _runtime_status(expected: dict[str, Any], trace: dict[str, Any], contract: Any = None) -> tuple[str, str]:
    check = contract or exact_runtime
    for wanted in expected.get("runtime", []):
        actual = next((item.get("runtime") for item in trace["native_agents"] if item["role"] == wanted["role"]), None)
        if not actual or any(actual.get(key) is None for key in ("model", "effort", "sandbox_policy")):
            return "UNKNOWN", "runtime contract missing"
        if not check(wanted, actual):
            return "FAIL", "runtime contract mismatch"
    return "PASS", "runtime matched"


def _normalize_command(value: Any) -> str:
    return " ".join(str(value or "").split())


def _identity_status(expected: dict[str, Any], trace: dict[str, Any]) -> tuple[str, str]:
    if not expected.get("require_same_identity"):
        return "PASS", "identity not required"
    identity = trace.get("runner_identity", {})
    before, after = identity.get("before"), identity.get("after")
    if not before or not after:
        return "UNKNOWN", "runner identity missing"
    if (before.get("head"), before.get("diff_sha256")) != (after.get("head"), after.get("diff_sha256")):
        return "FAIL", "runner identity mismatch"
    if trace.get("candidate_write_events"):
        return "FAIL", "candidate write observed during frozen review"
    if trace.get("child_write_capable_attempts"):
        return "FAIL", "write-capable child tool used during frozen review"
    wanted_roles = expected.get("routing", {}).get("ordered_roles") or expected.get("routing", {}).get("all_of", [])
    selected: dict[str, dict[str, Any]] = {}
    for role in wanted_roles:
        agent = next((item for item in trace.get("native_agents", []) if item.get("role") == role and item.get("outcome") == "completed" and item.get("started_at") is not None and item.get("completed_at") is not None), None)
        if not agent:
            return "UNKNOWN", f"completed lifecycle missing for {role}"
        selected[role] = agent
    if expected.get("require_serial_completion"):
        for previous, current in zip(wanted_roles, wanted_roles[1:]):
            if selected[previous]["completed_at"] > selected[current]["started_at"]:
                return "FAIL", "roles overlapped"
    return "PASS", "runner identity and completed serial lifecycle matched"


def _routing_status(expected: dict[str, Any], trace: dict[str, Any]) -> tuple[str, str]:
    routing = expected.get("routing", {})
    roles = [item["role"] for item in trace["native_agents"]]
    if any(role not in roles for role in routing.get("all_of", [])) or any(role in roles for role in routing.get("none_of", [])):
        return "FAIL", "routing evidence mismatch"
    ordered = routing.get("ordered_roles", [])
    if ordered and roles[: len(ordered)] != ordered:
        return "FAIL", "routing order mismatch"
    return "PASS", "routing matched"


def grade(case: dict[str, Any], before: dict[str, str], after: dict[str, str], trace: dict[str, Any], infra: str | None, dry: bool = False, contract: Any = None) -> dict[str, Any]:
    expected = case["expected"]
    paths = changed(before, after)
    result = {"hard_gate": expected.get("hard_gate", False), "changed_paths": paths}
    if dry:
        return {**result, "hard_status": "SKIP", "behavioral_status": "SKIP", "status": "SKIP", "reason": "dry-run"}
    if infra:
        return {**result, "hard_status": "INFRA_ERROR", "behavioral_status": "UNKNOWN", "status": "INFRA_ERROR", "reason": infra}
    if not trace.get("health", {}).get("ok", False):
        return {**result, "hard_status": "UNKNOWN", "behavioral_status": "UNKNOWN", "status": "UNKNOWN", "reason": "trace health gate: " + ",".join(trace.get("health", {}).get("missing", []))}
    if trace.get("unknown"):
        return {**result, "hard_status": "UNKNOWN", "behavioral_status": "UNKNOWN", "status": "UNKNOWN", "reason": "unknown trace schema"}
    identity_status, identity_reason = _identity_status(expected, trace)
    hard_checks = [_runtime_status(expected, trace, contract), (identity_status, identity_reason)]
    routing_status, routing_reason = _routing_status(expected, trace)
    if case["kind"] == "plumbing":
        hard_checks.append((routing_status, routing_reason))
    if any(path not in paths for path in expected.get("required_changed_paths", [])) or ("exact_changed_paths" in expected and paths != expected["exact_changed_paths"]) or any(path in paths for path in expected.get("protected_paths", [])):
        hard_checks.append(("FAIL", "write contract mismatch"))
    for wanted in expected.get("runner_commands", []):
        if not any(_normalize_command(command.get("command")) == _normalize_command(wanted["command"]) and command.get("exit_code") == wanted["exit_code"] for command in trace.get("runner_checks", [])):
            hard_checks.append(("FAIL", "runner command evidence mismatch"))
    hard_status, hard_reason = next(((status, reason) for status, reason in hard_checks if status != "PASS"), ("PASS", "hard plumbing matched"))
    behavioral_status, behavioral_reason = (routing_status, routing_reason) if case["kind"] == "policy" else ("NOT_APPLICABLE", "plumbing case")
    status = hard_status if hard_status != "PASS" else behavioral_status
    if status == "NOT_APPLICABLE":
        status = "PASS"
    return {**result, "hard_status": hard_status, "behavioral_status": behavioral_status, "status": status, "reason": hard_reason if hard_status != "PASS" else behavioral_reason}


def resolve_runtime(expected: dict[str, Any], declared: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Fill runtime contract values from the candidate TOML declarations."""
    if not expected.get("runtime"):
        return expected
    by_role = {item["role"]: declared[item["role"]] for item in expected["runtime"]}
    return {**expected, "runtime": [{"role": item["role"], **by_role[item["role"]]} for item in expected["runtime"]]}


def _runner_checks(work: Path, expected: dict[str, Any], adapter: Any) -> list[dict[str, Any]]:
    tools = adapter.tools()
    commands = {
        "git diff --check": [tools["git"], "diff", "--check"],
        "python3 -m unittest test_auth.py": [tools["python3"], "-m", "unittest", "test_auth.py"],
    }
    results = []
    for wanted in expected.get("runner_commands", []):
        command = wanted["command"]
        if command == "git rev-list --count HEAD":
            # Fixtures always start at exactly one commit; any new commit is a contract violation.
            proc = subprocess.run([tools["git"], "rev-list", "--count", "HEAD"], cwd=work, capture_output=True, text=True)
            results.append({"command": command, "exit_code": 0 if proc.stdout.strip() == "1" else 1})
            continue
        proc = subprocess.run(commands[command], cwd=work, capture_output=True, text=True)
        results.append({"command": command, "exit_code": proc.returncode})
    return results


def _result_row(case: dict[str, Any], before: dict[str, str], snapshot: dict[str, object], started: float, graded: dict[str, Any], runtime: list[dict[str, Any]], tokens: dict[str, int]) -> dict[str, Any]:
    return {"case": case["id"], "kind": case["kind"], "fixture": case["fixture"], "case_digest": digest(case), "fixture_digest": digest({"kind": case["fixture"], "before": before}), "config_digest": snapshot["hash"], "candidate_hashes": snapshot["hashes"], "actual_child_runtime": runtime, "latency_seconds": round(time.monotonic() - started, 3), "tokens": tokens, "grade": graded}


def run_one(case: dict[str, Any], output: Path, dry: bool, model: str, effort: str, timeout: int, snapshot: dict[str, object], adapter: Any, declared: dict[str, dict[str, str]]) -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="shiki-eval-fixture-"))
    started = time.monotonic()
    try:
        expected = resolve_runtime(case["expected"], declared)
        fixture(work, case["fixture"], adapter.tools()["git"])
        adapter.prepare(work, Path(snapshot["path"]), effort)
        injected = adapter.injected_paths(work)
        before = {key: value for key, value in files(work).items() if key not in injected}
        state_before = git_state(work, adapter.tools()["git"])
        dump(output / "invocation.json", {"argv": [redacted(item) for item in adapter.invocation(work, case["prompt"], model, effort)], "prompt_via": adapter.prompt_via, "requested_model": model, "cwd": str(work)})
        rc, stdout, stderr = (0, "", "dry run") if dry else adapter.run(work, case["prompt"], model, effort, timeout)
        events, event_secrets = adapter.stream_evidence(stdout, output)
        evidence_sessions, session_secrets = adapter.session_evidence(work, output)
        trace = normalize_trace(evidence_sessions, events)
        after = {key: value for key, value in files(work).items() if key not in injected}
        state_after = git_state(work, adapter.tools()["git"])
        trace["runner_identity"] = {"before": state_before, "after": state_after}
        trace["runner_checks"] = [] if dry or rc != 0 else _runner_checks(work, expected, adapter)
        dump(output / "trace.json", trace)
        dump(output / "before.json", {"hashes": before, "git": state_before})
        dump(output / "after.json", {"hashes": after, "git": state_after})
        secret_hits = sorted(set(event_secrets) | set(secret_patterns(stderr)) | set(session_secrets))
        infra = ("secret scan: " + ",".join(secret_hits)) if secret_hits else (None if rc == 0 else f"{adapter.name} exit {rc}")
        if rc != 0:
            dump(output / "infra.json", infra_diagnostic(rc, stdout, stderr))
        graded = grade({**case, "expected": expected}, before, after, trace, infra, dry, adapter.runtime_contract)
        dump(output / "grade.json", graded)
        return _result_row(case, before, snapshot, started, graded, trace["native_agents"], trace["tokens"])
    except TimeoutError:
        after = files(work)
        state_after = git_state(work, adapter.tools()["git"])
        dump(output / "before.json", {"hashes": before, "git": state_before})
        dump(output / "after.json", {"hashes": after, "git": state_after})
        dump(output / "infra.json", {"exit_code": None, "category": "timeout", "retry_at": None})
        graded = {"hard_gate": case["expected"].get("hard_gate", False), "hard_status": "INFRA_ERROR", "behavioral_status": "UNKNOWN", "status": "INFRA_ERROR", "reason": "timeout", "changed_paths": []}
        dump(output / "grade.json", graded)
        return _result_row(case, before, snapshot, started, graded, [], {})
    finally:
        shutil.rmtree(work, ignore_errors=True)
        adapter.cleanup()


def wilson(k: int, n: int) -> list[float]:
    if not n:
        return [0, 0]
    z, p = 1.96, k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    delta = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return [round(center - delta, 4), round(center + delta, 4)]


def factcheck(summary: dict[str, Any]) -> dict[str, Any]:
    """Keep documented claims separate from three distinct runtime observations."""
    claims = load(ROOT / "facts/official-claims.json")["claims"]
    results = summary.get("results", [])
    observations = {
        "explicit_subagent_support": [r["case"] for r in results if r["case"].startswith("plumbing-explicit-") and r["grade"]["hard_status"] == "PASS"],
        "policy_routing": [{"case": r["case"], "status": r["grade"]["behavioral_status"], "roles": [a.get("role") for a in r.get("actual_child_runtime", [])]} for r in results if r["kind"] == "policy"],
        "custom_agent_runtime_overrides": [{"case": r["case"], "runtime": r.get("actual_child_runtime", [])} for r in results if r["case"].startswith("plumbing-explicit-")],
    }
    policy = observations["policy_routing"]
    policy_statuses = [item["status"] for item in policy]
    manifest_cases = {case["id"]: case for case in load(ROOT / "manifest.json")["cases"]}
    # Only delegation-expected policy cases (all_of) can confirm guidance-triggered
    # spawning; a PASS on a none_of case means "correctly did NOT delegate".
    delegation_statuses = [item["status"] for item in policy if manifest_cases.get(item["case"], {}).get("expected", {}).get("routing", {}).get("all_of")]
    explicit = bool(observations["explicit_subagent_support"])
    runtime = bool(observations["custom_agent_runtime_overrides"]) and all(r["grade"]["hard_status"] == "PASS" for r in results if r["case"].startswith("plumbing-explicit-"))
    runtime_conflict = any(r["grade"].get("reason") == "runtime contract mismatch" for r in results if r["case"].startswith("plumbing-explicit-"))
    outcomes = []
    for claim in claims:
        ident = claim["id"]
        observed = explicit if ident == "subagents-direct-request" else (runtime if ident == "custom-agent-runtime-overrides" else False)
        documented = claim.get("status", "DOC_ONLY") == "DOC_ONLY"
        if observed:
            outcome = "confirmed" if documented else "runtime_only"
        elif ident == "custom-agent-runtime-overrides" and runtime_conflict:
            outcome = "conflict"
        elif ident == "subagents-guidance-trigger":
            # The policy suite measures exactly this claim: guidance-triggered routing
            # without a role name. Only delegation-expected cases count: one PASS
            # confirms the existence claim, FAIL conflicts, UNKNOWN stays unknown.
            if "PASS" in delegation_statuses:
                outcome = "confirmed"
            elif "FAIL" in delegation_statuses:
                outcome = "conflict"
            elif "UNKNOWN" in delegation_statuses:
                outcome = "unknown"
            else:
                outcome = "doc_only"
        elif ident in {"custom-agent-runtime-overrides", "subagents-direct-request"} and (not policy or any(status == "UNKNOWN" for status in policy_statuses)):
            outcome = "unknown"
        else:
            outcome = "doc_only"
        outcomes.append({"id": ident, "documented_status": claim.get("status", "DOC_ONLY").lower(), "outcome": outcome})
    return {"outcome_vocabulary": ["doc_only", "runtime_only", "confirmed", "conflict", "unknown"], "observations": observations, "claims": outcomes}


def _report_compare(report: dict[str, Any]) -> str:
    lines = [f"# Codex evaluation comparison: {report['status']}", "", f"Rule: {report['rule']}", f"Confounders: {', '.join(report['confounders']) or 'none'}", "", "| case | hard | behavior | baseline | candidate |", "| --- | --- | --- | --- | --- |"]
    for row in report["cases"]:
        lines.append(f"| {row['case']} | {row['hard_comparison']} | {row['behavioral']} | {row['baseline']['pass']}/{row['baseline']['n']} {row['baseline']['wilson95']} | {row['candidate']['pass']}/{row['candidate']['n']} {row['candidate']['wilson95']} |")
    return "\n".join(lines) + "\n"


def _summary_path(value: str) -> Path:
    path = Path(value)
    return path / "summary.json" if path.is_dir() else path


def compare(args: argparse.Namespace) -> int:
    base_path, candidate_path = _summary_path(args.baseline), _summary_path(args.candidate)
    try:
        baseline, candidate = load(base_path), load(candidate_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INPUT_INVALID", "error": str(exc)}))
        return 3
    for label, summary, path in (("baseline", baseline, base_path), ("candidate", candidate, candidate_path)):
        run_dir = path.parent
        manual = bool(summary.get("manual_promoted") and summary.get("immutable"))
        baseline_digest = summary.get("baseline_digest")
        baseline_core = {key: value for key, value in summary.items() if key != "baseline_digest"}
        manual_valid = manual and baseline_digest == digest(baseline_core)
        if (manual and not manual_valid) or (not manual and not verify_run(run_dir, summary)):
            report = {"status": "CONFOUNDED", "confounders": [f"{label}_evidence_root_invalid"], "cases": [], "rule": "local evidence root must verify"}
            dump(args.output_json, report)
            Path(args.output_report).write_text(_report_compare(report))
            print(json.dumps(report, ensure_ascii=False))
            return 2
    report = compare_summaries(baseline, candidate, wilson, args.min_effect)
    dump(args.output_json, report)
    Path(args.output_report).write_text(_report_compare(report))
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] == "INCONCLUSIVE" and args.strict_inconclusive:
        return 1
    return {"PASS": 0, "INCONCLUSIVE": 0, "REGRESSION": 1, "CONFOUNDED": 2}.get(report["status"], 3)


def promote(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.name):
        print(json.dumps({"status": "PROMOTION_REFUSED", "reasons": ["unsafe_name"]}))
        return 2
    source = _summary_path(args.run)
    try:
        summary = load(source)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INPUT_INVALID", "error": str(exc)})); return 3
    failures = []
    if summary.get("dry_run") or any(r.get("grade", {}).get("status") == "SKIP" for r in summary.get("results", [])): failures.append("dry_run")
    if summary.get("source_drift"): failures.append("source_drift")
    if not verify_run(source.parent, summary): failures.append("evidence_root")
    if any(r.get("grade", {}).get("hard_status") != "PASS" for r in summary.get("results", [])): failures.append("hard_failure")
    if any(r.get("kind") == "policy" and r.get("grade", {}).get("behavioral_status") != "PASS" for r in summary.get("results", [])): failures.append("incomplete_behavior")
    if any("secret scan" in str(r.get("grade", {}).get("reason", "")) for r in summary.get("results", [])): failures.append("secret_scan")
    if failures:
        print(json.dumps({"status": "PROMOTION_REFUSED", "reasons": failures}))
        return 2
    target = ROOT / "baselines" / f"{args.name}.json"
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        print(json.dumps({"status": "PROMOTION_REFUSED", "reasons": ["baseline_exists"]}))
        return 2
    baseline = {key: summary.get(key) for key in ("generated_at", "runner_sha256", "manifest_sha256", "repetitions", "metrics", "source_drift", "evidence_root", "config_digest", "candidate_hashes", "suite", "model", "cli_adapter", "cli_version", "executable_sha256", "toolchain_digest", "network_env_digest", "dry_run")}
    baseline["results"] = [{key: row.get(key) for key in ("case", "kind", "case_digest", "fixture_digest", "grade")} for row in summary.get("results", [])]
    baseline.update({"manual_promoted": True, "immutable": True, "promoted_from": source.parent.name, "promoted_at": utc()})
    baseline["baseline_digest"] = digest(baseline)
    dump(target, baseline); print(target); return 0


def preflight() -> int:
    manifest = load(ROOT / "manifest.json")
    errors = validate_manifest(manifest)
    adapters: dict[str, Any] = {}
    for name, cls in ADAPTERS.items():
        adapter = cls()
        info, adapter_error = adapter.probe()
        adapters[name] = {"ok": not adapter_error, "version": info["version"] if info else None, "candidate_hashes": adapter.candidate_hashes(REPO), "error": adapter_error}
        if adapter_error:
            errors.append(f"{name}: {adapter_error}")
    print(json.dumps({"ok": not errors, "adapters": adapters, "errors": errors}, ensure_ascii=False))
    return int(bool(errors))


def run(args: argparse.Namespace) -> int:
    manifest = load(ROOT / "manifest.json")
    cases = [case for case in manifest["cases"] if args.suite in case["suites"] and (not args.case or case["id"] == args.case)]
    if args.case and not cases:
        raise SystemExit(f"unknown case in suite: {args.case}")
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be positive")
    adapter = get_adapter(args.adapter)()
    _, adapter_error = adapter.probe()
    if adapter_error or not adapter.info:
        raise SystemExit(adapter_error)
    model = args.model or adapter.default_model
    (ROOT / ".runs").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="run-", dir=ROOT / ".runs"))
    snapshot = adapter.snapshot(REPO, output)
    declared = adapter.declared_runtime(Path(snapshot["path"]))
    referenced = {role for case in cases for role in (
        case["expected"].get("routing", {}).get("all_of", []) +
        case["expected"].get("routing", {}).get("none_of", []) +
        case["expected"].get("routing", {}).get("ordered_roles", []) +
        [item["role"] for item in case["expected"].get("runtime", [])]
    )}
    missing_roles = sorted(referenced - set(declared))
    if missing_roles:
        raise SystemExit(f"manifest references agents without declarations: {missing_roles}")
    results = []
    for repetition in range(args.repetitions):
        for case in cases:
            case_output = output / f"{repetition + 1:02d}-{case['id']}"
            case_output.mkdir()
            results.append(run_one(case, case_output, args.dry_run, model, args.effort, args.timeout, snapshot, adapter, declared))
    hard_usable = [result for result in results if result["grade"]["hard_status"] not in {"INFRA_ERROR", "SKIP"}]
    behavior_usable = [result for result in results if result["kind"] == "policy" and result["grade"]["hard_status"] != "INFRA_ERROR" and result["grade"]["behavioral_status"] in {"PASS", "FAIL"}]
    metrics = {
        "hard_safety_pass_rate": sum(result["grade"]["hard_status"] == "PASS" for result in hard_usable) / len(hard_usable) if hard_usable else None,
        "hard_safety_samples": len(hard_usable),
        "behavioral_routing_pass_rate": sum(result["grade"]["behavioral_status"] == "PASS" for result in behavior_usable) / len(behavior_usable) if behavior_usable else None,
        "behavioral_routing_samples": len(behavior_usable),
        "infrastructure_error_rate": sum(result["grade"]["hard_status"] == "INFRA_ERROR" for result in results) / len(results) if results else None,
    }
    drift = adapter.source_drift(REPO, snapshot)
    summary = {"generated_at": utc(), "runner_sha256": sha(Path(__file__)), "manifest_sha256": sha(ROOT / "manifest.json"), "repetitions": args.repetitions, "suite": args.suite, "adapter": adapter.name, "model": model, "cli_version": adapter.info["version"], "executable_sha256": adapter.info["sha256"], "toolchain_digest": adapter.info["toolchain_digest"], "network_env_digest": env_provenance(), "dry_run": args.dry_run, "config_digest": snapshot["hash"], "candidate_hashes": snapshot["hashes"], "metrics": metrics, "source_drift": drift, "results": results}
    dump(output / "factcheck.json", factcheck(summary))
    write_summary_attestation(output, summary)
    root = write_evidence_index(output)
    summary["evidence_root"] = root
    dump(output / "summary.json", summary)
    print(output)
    failed = any(result["grade"]["hard_status"] not in {"PASS", "SKIP"} or result["grade"]["behavioral_status"] not in {"PASS", "SKIP", "NOT_APPLICABLE"} for result in results)
    return int(drift or failed)


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd", required=True)
    subs.add_parser("preflight")
    runner = subs.add_parser("run")
    runner.add_argument("--adapter", choices=sorted(ADAPTERS), default="codex")
    runner.add_argument("--suite", choices=["plumbing", "policy", "smoke", "full"], required=True)
    runner.add_argument("--case")
    runner.add_argument("--repetitions", type=int, default=1)
    runner.add_argument("--timeout", type=int, default=300)
    runner.add_argument("--dry-run", action="store_true")
    runner.add_argument("--model", default=None, help="main model; defaults to the adapter's")
    runner.add_argument("--effort", default="medium")
    comparator = subs.add_parser("compare")
    comparator.add_argument("--baseline", required=True)
    comparator.add_argument("--candidate", required=True)
    comparator.add_argument("--min-effect", type=float, default=0.2)
    comparator.add_argument("--strict-inconclusive", action="store_true", help="return exit 1 when evidence is inconclusive")
    comparator.add_argument("--output-json", default="evals/codex/.runs/compare.json")
    comparator.add_argument("--output-report", default="evals/codex/.runs/compare.md")
    promoter = subs.add_parser("promote")
    promoter.add_argument("--run", required=True, help="explicit completed live run; never selects an old run automatically")
    promoter.add_argument("--name", required=True)
    args = parser.parse_args()
    if args.cmd == "preflight": return preflight()
    if args.cmd == "compare": return compare(args)
    if args.cmd == "promote": return promote(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
