"""Write only redacted, allowlisted evaluation artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import SENSITIVE_KEY, digest, dump, load, redact_text, sha

ALLOWED_EVENT_TYPES = {"thread.started", "turn.started", "turn.completed", "item.started", "item.completed"}
ALLOWED_ITEM_TYPES = {"command_execution", "collabToolCall", "collab_tool_call", "file_change"}
KNOWN_NON_EVIDENCE_ITEM_TYPES = {"agent_message", "reasoning"}
KNOWN_NON_EVIDENCE_TOOLS = {"send_message", "wait_agent", "wait_threads", "write_stdin", "read_thread_terminal"}


def _minimal_tool_output(value: Any) -> dict[str, Any]:
    """Extract only the exit-code fact from otherwise free-form output."""
    result: dict[str, Any] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if "exit_code" in item and item["exit_code"] is not None:
                result["exit_code"] = item["exit_code"]
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            try:
                decoded = json.loads(item)
            except json.JSONDecodeError:
                return
            visit(decoded)

    visit(value)
    return result


def _minimal_exec_arguments(value: Any, patterns: set[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        command = value.get("cmd") or value.get("command")
    else:
        command = None
        if isinstance(value, str):
            match = re.search(r'(?<![\w-])["\']?(?:cmd|command)["\']?\s*:\s*("(?:[^"\\]|\\.)*")', value)
            if match:
                try:
                    command = json.loads(match.group(1))
                except json.JSONDecodeError:
                    command = None
    return {"cmd": _safe(command, patterns)} if command else {}


def _safe(value: Any, patterns: set[str]) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if SENSITIVE_KEY.search(str(key)):
                patterns.add("secret-key")
                result[key] = "<redacted:secret>"
            else:
                result[key] = _safe(item, patterns)
        return result
    if isinstance(value, list):
        return [_safe(item, patterns) for item in value]
    if isinstance(value, str):
        text, found = redact_text(value)
        patterns.update(found)
        return text
    return value


def secret_patterns(value: Any) -> list[str]:
    found: set[str] = set()
    _safe(value, found)
    return sorted(pattern for pattern in found if pattern != "local-path")


def usage_values(value: Any) -> dict[str, int]:
    """Token counters are numbers, never secrets: keep int values without key redaction."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, int)}


def _session_record(event: dict[str, Any], patterns: set[str]) -> dict[str, Any] | None:
    typ = event.get("type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if typ == "session_meta":
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        subagent = source.get("subagent") if isinstance(source.get("subagent"), dict) else {}
        spawn = subagent.get("thread_spawn") if isinstance(subagent.get("thread_spawn"), dict) else {}
        return {"type": typ, "session_id": payload.get("id") or event.get("session_id"), "thread_id": payload.get("thread_id") or event.get("thread_id"), "agent_role": spawn.get("agent_role"), "started_at": event.get("timestamp")}
    if typ == "turn_context":
        return {"type": typ, "model": payload.get("model"), "effort": payload.get("effort"), "sandbox_policy": _safe(payload.get("sandbox_policy"), patterns)}
    if typ == "event_msg" and payload.get("type") in {"task_started", "task_complete", "turn_aborted"}:
        # Persist only lifecycle facts. In particular, task_complete also carries the
        # final message, which is deliberately not part of shareable evidence.
        return {
            "type": "session_lifecycle",
            "phase": "task_complete" if payload["type"] in {"task_complete", "turn_aborted"} else "task_started",
            "outcome": "aborted" if payload["type"] == "turn_aborted" else ("completed" if payload["type"] == "task_complete" else "started"),
            "started_at": payload.get("started_at") or event.get("timestamp"),
            "completed_at": payload.get("completed_at") if payload["type"] in {"task_complete", "turn_aborted"} else None,
        }
    if typ == "turn.completed":
        return {"type": "session_lifecycle", "phase": "task_complete", "completed_at": event.get("timestamp") or payload.get("completed_at")}
    if typ == "response_item":
        item = payload
        if item.get("type") in {"function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"}:
            item_type = item.get("type")
            name = item.get("name")
            record = {"type": typ, "item_type": item_type, "name": name, "call_id": item.get("call_id") or item.get("id")}
            if item_type in {"function_call", "custom_tool_call"}:
                raw = item.get("arguments") or item.get("input")
                if name == "apply_patch":
                    return {"type": "session_write_attempt", "tool": "apply_patch"}
                if name == "exec":
                    record["arguments"] = _minimal_exec_arguments(raw, patterns)
                elif name in {"spawn_agent", "collaboration.spawn_agent"}:
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except json.JSONDecodeError:
                            raw = {}
                    record["arguments"] = {key: raw.get(key) for key in ("agent_type", "task_name", "fork_turns") if isinstance(raw, dict) and raw.get(key) is not None}
                elif name and "collab" in name:
                    record["arguments"] = {}
                elif name in KNOWN_NON_EVIDENCE_TOOLS:
                    return None
                else:
                    return {"type": "evidence_anomaly", "reason": "unknown-tool", "name": name}
            else:
                # Keep only machine lifecycle/exit fields from tool output. Free-form
                # messages, prompts and instruction text never enter the evidence set.
                record["output"] = _minimal_tool_output(item.get("output"))
            return record
        return None
    return None


def write_records(paths: list[Path], output: Path, record_fn) -> tuple[list[Path], list[str]]:
    """Write per-line evidence records for raw session files via record_fn(event, patterns) -> record | None."""
    target = output / "session-evidence"
    target.mkdir(parents=True, exist_ok=True)
    secret_hits: set[str] = set()
    written: list[Path] = []
    for index, path in enumerate(paths):
        lines = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "invalid-json"}))
                continue
            patterns: set[str] = set()
            record = record_fn(event, patterns)
            if record:
                secret_hits.update(secret_patterns(record))
                secret_hits.update(patterns)
                lines.append(json.dumps(record, ensure_ascii=False))
        dest = target / f"{index:02d}-{path.name}"
        dest.write_text("\n".join(lines) + ("\n" if lines else ""))
        written.append(dest)
    return written, sorted(secret_hits)


def write_session_evidence(paths: list[Path], output: Path) -> tuple[list[Path], list[str]]:
    """Codex session evidence (raw codex session jsonl -> shared record format)."""
    return write_records(paths, output, _session_record)


def write_events_evidence(stdout: str, output: Path) -> tuple[Path, list[str]]:
    patterns: set[str] = set()
    lines = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            lines.append(json.dumps({"type": "evidence_anomaly", "reason": "invalid-json"}))
            continue
        typ = event.get("type")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if typ not in ALLOWED_EVENT_TYPES:
            lines.append(json.dumps({"type": "evidence_anomaly", "reason": "unknown-event-type"}))
            continue
        if item and item.get("type") not in ALLOWED_ITEM_TYPES | KNOWN_NON_EVIDENCE_ITEM_TYPES:
            lines.append(json.dumps({"type": "evidence_anomaly", "reason": "unknown-item-type"}))
            continue
        if not item or item.get("type") in ALLOWED_ITEM_TYPES:
            record = {"type": typ, "timestamp": event.get("timestamp"), "usage": usage_values(event.get("usage"))}
            if item:
                record["item"] = {"type": item.get("type"), "id": item.get("id"), "command": _safe(item.get("command"), patterns), "exit_code": item.get("exit_code"), "has_changes": item.get("type") == "file_change"}
            patterns.update(secret_patterns(record))
            lines.append(json.dumps(record, ensure_ascii=False))
    dest = output / "events.jsonl"
    dest.write_text("\n".join(lines) + ("\n" if lines else ""))
    return dest, sorted(pattern for pattern in patterns if pattern != "local-path")


EXCLUDED_ROOT_NAMES = {"evidence-index.json", "summary.json", "report.md"}


def summary_core(summary: dict[str, Any]) -> dict[str, Any]:
    result_keys = ("case", "kind", "fixture", "case_digest", "fixture_digest", "config_digest", "grade")
    return {
        key: summary.get(key)
        for key in (
            "runner_sha256", "manifest_sha256", "repetitions", "suite", "adapter", "model",
            "cli_version", "executable_sha256", "toolchain_digest", "network_env_digest",
            "dry_run", "config_digest", "candidate_hashes", "metrics", "source_drift",
        )
    } | {"results": [{key: row.get(key) for key in result_keys} for row in summary.get("results", [])]}


def write_summary_attestation(output: Path, summary: dict[str, Any]) -> None:
    dump(output / "summary-core.json", summary_core(summary))


def evidence_entries(output: Path) -> list[dict[str, Any]]:
    """The finite, shareable evidence set.  Indexes and summaries never attest themselves."""
    entries: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*")):
        # candidate-snapshot is an execution input, intentionally excluded from shareable evidence.
        if path.is_file() and path.name not in EXCLUDED_ROOT_NAMES and "candidate-snapshot" not in path.parts:
            entries.append({"path": str(path.relative_to(output)), "sha256": sha(path), "bytes": path.stat().st_size, "redacted": True})
    return entries


def evidence_root(entries: list[dict[str, Any]]) -> str:
    """Hash canonical allowlisted records rather than an index file that contains its own hash."""
    canonical = [{key: entry[key] for key in ("path", "sha256", "bytes", "redacted")} for entry in sorted(entries, key=lambda item: item["path"])]
    return digest(canonical)


def verify_evidence_root(output: Path, expected: str) -> bool:
    return bool(expected) and evidence_root(evidence_entries(output)) == expected


def verify_run(output: Path, summary: dict[str, Any]) -> bool:
    attestation = output / "summary-core.json"
    return attestation.is_file() and load(attestation) == summary_core(summary) and verify_evidence_root(output, summary.get("evidence_root", ""))


def write_evidence_index(output: Path) -> str:
    entries = evidence_entries(output)
    dump(output / "evidence-index.json", {"entries": entries})
    return evidence_root(entries)
