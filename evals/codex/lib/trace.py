"""Conservative trace adapter: unknown critical structure never becomes a pass."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import ROLES

# Evidence-record types written by lib/evidence.py. Anything else is unknown.
SESSION_TYPES = {"session_meta", "turn_context", "response_item", "session_lifecycle", "session_write_attempt", "evidence_anomaly"}


def normalize_trace(paths: list[Path], events: Path | None = None) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    undeclared: list[dict[str, Any]] = []
    tokens: dict[str, int] = {}
    parent: dict[str, Any] | None = None
    child_write_capable_attempts = 0

    for path in paths:
        session: dict[str, Any] = {"file": path.name, "role": None, "session_id": None, "thread_id": None, "started_at": None, "completed_at": None, "outcome": None, "runtime": None, "is_child": None}
        for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                unknown.append({"file": path.name, "line": line_number, "reason": "invalid-json"})
                continue
            typ = event.get("type")
            if typ not in SESSION_TYPES:
                unknown.append({"file": path.name, "line": line_number, "reason": "unknown-event-type"})
                continue
            if typ == "evidence_anomaly":
                unknown.append({"file": path.name, "line": line_number, "reason": event.get("reason", "evidence-anomaly")})
                continue
            if typ == "session_write_attempt":
                if session.get("role"):
                    child_write_capable_attempts += 1
                continue
            if typ == "session_lifecycle":
                if event.get("phase") == "task_started":
                    session["started_at"] = event.get("started_at") or session["started_at"]
                elif event.get("phase") == "task_complete":
                    session["completed_at"] = event.get("completed_at")
                    session["outcome"] = event.get("outcome") or "completed"
                continue
            if typ == "session_meta":
                session["session_id"] = event.get("session_id")
                session["thread_id"] = event.get("thread_id")
                session["started_at"] = event.get("started_at") or session["started_at"]
                role = event.get("agent_role")
                session["is_child"] = bool(role)
                if role:
                    # A spawn of an undeclared agent type is routing evidence, not a
                    # schema problem: it fails the routing contract instead of UNKNOWN.
                    session["role"] = role
                    if role not in ROLES:
                        undeclared.append({"file": path.name, "line": line_number, "role": role})
            elif typ == "turn_context":
                if not {"model", "effort", "sandbox_policy"} <= set(event):
                    unknown.append({"file": path.name, "line": line_number, "reason": "unknown-turn-context"})
                session["runtime"] = {"model": event.get("model"), "effort": event.get("effort"), "sandbox_policy": event.get("sandbox_policy")}
            elif typ == "response_item":
                # A write-capable tool call by a child agent is observed, never a hard pass.
                if event.get("name") == "exec" and session.get("role"):
                    child_write_capable_attempts += 1
        sessions.append(session)

    exec_completed = False
    candidate_write_events = 0
    if events and events.exists():
        for line_number, line in enumerate(events.read_text(errors="replace").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                unknown.append({"file": events.name, "line": line_number, "reason": "invalid-json"})
                continue
            if event.get("type") == "evidence_anomaly":
                unknown.append({"file": events.name, "line": line_number, "reason": event.get("reason", "evidence-anomaly")})
                continue
            if event.get("type") == "turn.completed":
                exec_completed = True
                if isinstance(event.get("usage"), dict):
                    tokens.update({key: value for key, value in event["usage"].items() if isinstance(value, int)})
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") == "file_change" and item.get("has_changes"):
                candidate_write_events += 1

    for session in sessions:
        if session["is_child"] is False:
            parent = session
        if session["role"]:
            if not session["runtime"] or any(session["runtime"].get(key) is None for key in ("model", "effort", "sandbox_policy")):
                unknown.append({"file": session["file"], "reason": "missing-runtime"})
    health_missing = []
    if not parent or not parent.get("session_id"):
        health_missing.append("parent-session_meta")
    if not parent or not parent.get("runtime"):
        health_missing.append("parent-turn_context")
    if not exec_completed:
        health_missing.append("exec-turn.completed")
    agents = [session for session in sessions if session["role"]]
    agents.sort(key=lambda item: (item["started_at"] is None, item["started_at"] or "", item["file"]))
    return {
        "native_agents": [{key: item[key] for key in ("role", "session_id", "thread_id", "started_at", "completed_at", "outcome", "runtime", "file")} for item in agents],
        "candidate_write_events": candidate_write_events,
        "child_write_capable_attempts": child_write_capable_attempts,
        "tokens": tokens,
        "unknown": unknown,
        "undeclared": undeclared,
        "health": {"ok": not health_missing, "missing": health_missing},
    }
