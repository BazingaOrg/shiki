"""Grok Build CLI adapter.

Evidence model (probe-verified on grok 0.2.118):
- `grok --single ... --output-format streaming-json` emits an ACP NDJSON
  stream: tool_call / usage / end events; `end` carries the session id.
- Every session (parent and spawned subagents) is stored under
  `~/.grok/sessions/<url-quoted-cwd>/<session-id>/` with chat_history.jsonl
  (assistant messages carry model_id, reasoning_effort and structured
  tool_calls), prompt_context.json (proves which AGENTS.md files were
  injected) and updates.jsonl (epoch timestamps for lifecycle).

Isolation is cwd-based: the candidate AGENTS.md is copied into the fixture
work dir (discovered as a project instruction) and agent profiles into
`<work>/.grok/agents/` (project agents beat user agents). The real
`~/.grok` config/rules remain loaded; that is the evaluated environment.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common import frontmatter
from ..evidence import _safe, secret_patterns, usage_values
from ..runtime import run_process
from .base import EvalAdapter

RUNTIME_FIELDS = ("name", "model", "effort", "permission_mode")
CAPABILITY_MAP = {"read-write": "workspace-write", "read-only": "read-only"}
# Capability mode is a coarse per-spawn tool filter; write-capability is the
# contract axis (read-only/execute cannot edit files; read-write/all can).
WRITE_LEVEL = {"read-only": 0, "execute": 0, "workspace-write": 1, "read-write": 1, "all": 1}
WRITE_TOOLS = {"search_replace", "apply_patch", "Bash", "bash", "run_terminal_command"}
KNOWN_NON_EVIDENCE_TOOLS = {"grep", "read_file", "list_dir", "get_command_or_subagent_output", "kill_command_or_subagent", "web_search", "web_fetch", "todo_write", "enter_plan_mode", "exit_plan_mode", "ask_user_question", "use_tool", "workflow", "monitor", "scheduler_create", "scheduler_delete", "scheduler_list", "search_tool"}
KNOWN_NON_EVIDENCE_ACP = {"thought", "text", "available_commands", "tool_call_update", "usage"}


def _epoch_to_iso(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


class GrokAdapter(EvalAdapter):
    name = "grok"
    binary = "grok"
    VERSION = re.compile(r"\b0\.\d+\.\d+\b")
    default_model = "grok-4.5"
    prompt_via = "argv"

    def runtime_contract(self, declared: dict[str, str], actual: dict[str, Any]) -> bool:
        # The CLI accepts family ids ("grok-4.5") while session evidence records the
        # deployed build ("grok-4.5-build"); a declared family matches its build.
        # Capability mode is model-chosen per spawn: the declared mode is a ceiling,
        # observed must not be broader (read-only/execute satisfy a read-write ceiling).
        model_ok = actual.get("model") == declared["model"] or str(actual.get("model", "")).startswith(declared["model"] + "-")
        sandbox = actual.get("sandbox_policy")
        sandbox_type = sandbox.get("type") if isinstance(sandbox, dict) else sandbox
        sandbox_ok = WRITE_LEVEL.get(sandbox_type, 0) <= WRITE_LEVEL.get(declared["sandbox_type"], 0)
        return model_ok and actual.get("effort") == declared["effort"] and sandbox_ok

    def __init__(self) -> None:
        super().__init__()
        self.session_id: str | None = None

    # -- candidate -------------------------------------------------------
    def candidate_paths(self, repo: Path) -> list[Path]:
        return [repo / "grok" / "AGENTS.md", *sorted((repo / "grok" / "agents").glob("*.md"))]

    def snapshot(self, repo: Path, output: Path) -> dict[str, object]:
        mds = [path for path in self.candidate_paths(repo) if path.suffix == ".md"]
        if not (repo / "grok" / "AGENTS.md").is_file() or not mds:
            raise RuntimeError("candidate must contain grok/AGENTS.md and at least one agent profile")
        return self._snapshot_candidates(repo, output, repo / "grok")

    def declared_runtime(self, snapshot: Path) -> dict[str, dict[str, str]]:
        """Declared model/effort/sandbox per custom agent, from profile frontmatter."""
        agents_dir = snapshot / "agents"
        if not (snapshot / "AGENTS.md").is_file() or not agents_dir.is_dir():
            raise RuntimeError("candidate snapshot must contain AGENTS.md and an agents/ directory")
        declared: dict[str, dict[str, str]] = {}
        for path in sorted(agents_dir.glob("*.md")):
            data = frontmatter(path)
            missing = [field for field in RUNTIME_FIELDS if not data.get(field)]
            if missing:
                raise RuntimeError(f"agent profile {path.name} must declare: {', '.join(missing)}")
            role = data["name"]
            if role in declared:
                raise RuntimeError(f"duplicate agent role in profiles: {role}")
            declared[role] = {"model": data["model"], "effort": data["effort"], "sandbox_type": "read-only" if data["permission_mode"] == "plan" else "workspace-write"}
        if not declared:
            raise RuntimeError("candidate snapshot must declare at least one custom agent profile")
        return declared

    # -- per-case lifecycle ----------------------------------------------
    def injected_paths(self, work: Path) -> tuple[str, ...]:
        return self._injected_instruction_paths(work, "AGENTS.md", ".grok/agents")

    def prepare(self, work: Path, snapshot: Path, effort: str) -> None:
        # Candidate injection via cwd discovery; prompt_context.json records it.
        self.snapshot_path = str(snapshot)
        self._inject_cwd_instructions(work, snapshot, "AGENTS.md", ".grok/agents")

    def invocation(self, work: Path, prompt: str, model: str, effort: str) -> list[str]:
        # resolve() canonicalizes macOS /var -> /private/var so the session dir key
        # grok records matches the one session_evidence looks up.
        return [self.info["binary"], "--single", prompt, "--cwd", str(work.resolve()), "--output-format", "streaming-json", "--permission-mode", "auto", "--reasoning-effort", effort, "--model", model, "--disable-web-search", "--no-memory"]

    def run(self, work: Path, prompt: str, model: str, effort: str, timeout: int) -> tuple[int, str, str]:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # test runs must not leave bytecode artifacts
        return run_process(self.invocation(work, prompt, model, effort), prompt="", env=env, cwd=work, timeout=timeout)

    def cleanup(self) -> None:
        pass

    # -- evidence --------------------------------------------------------
    def stream_evidence(self, stdout: str, output: Path) -> tuple[Path, list[str]]:
        patterns: set[str] = set()
        lines = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "invalid-json"}))
                continue
            typ = event.get("type")
            if typ == "end":
                self.session_id = event.get("sessionId")
                record = {"type": "turn.completed", "usage": usage_values(event.get("usage"))}
                lines.append(json.dumps(record, ensure_ascii=False))
            elif typ == "tool_call":
                # A file change is a definite edit tool call; bash is write-capable but
                # unobservable here (session evidence carries the capability context).
                if event.get("toolName") in {"search_replace", "apply_patch"}:
                    lines.append(json.dumps({"type": "item.started", "item": {"type": "file_change", "has_changes": True}}))
            elif typ in KNOWN_NON_EVIDENCE_ACP:
                continue
            else:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "unknown-event-type"}))
        dest = output / "events.jsonl"
        dest.write_text("\n".join(lines) + ("\n" if lines else ""))
        return dest, sorted(pattern for pattern in patterns if pattern != "local-path")

    def session_evidence(self, work: Path, output: Path) -> tuple[list[Path], list[str]]:
        if not self.session_id:
            return [], []
        base = Path.home() / ".grok" / "sessions" / urllib.parse.quote(str(work.resolve()), safe="")
        session_dirs = {path.name: path for path in sorted(base.glob("*")) if path.is_dir()} if base.is_dir() else {}
        parent_dir = session_dirs.get(self.session_id)
        role_map, capabilities, completed_tasks = self._parent_facts(parent_dir) if parent_dir else ({}, {}, set())
        target = output / "session-evidence"
        target.mkdir(parents=True, exist_ok=True)
        secret_hits: set[str] = set()
        written: list[Path] = []
        for index, sid in enumerate(sorted(session_dirs)):
            if sid == self.session_id:
                role, capability = None, None
            else:
                role = role_map.get(sid, "unknown-role")
                capability = capabilities.get(sid)
            records = self._session_records(session_dirs[sid], sid, role, capability, completed_tasks)
            if sid == self.session_id and parent_dir:
                records.extend(self._injection_check(parent_dir))
            safe_records = []
            for record in records:
                safe = _safe(record, secret_hits)
                secret_hits.update(secret_patterns(safe))
                safe_records.append(safe)
            dest = target / f"{index:02d}-{sid}.jsonl"
            dest.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in safe_records) + ("\n" if safe_records else ""))
            written.append(dest)
        return written, sorted(pattern for pattern in secret_hits if pattern != "local-path")

    def _parent_facts(self, parent_dir: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
        """Map child session ids to role and capability from the parent's spawn + wait calls."""
        spawns: list[tuple[str, str]] = []
        tasks: list[str] = []
        wait_calls: dict[str, list[str]] = {}
        completed: set[str] = set()
        for line in (parent_dir / "chat_history.jsonl").read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for call in event.get("tool_calls") or []:
                    name = call.get("name")
                    try:
                        args = json.loads(call.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if name == "spawn_subagent":
                        spawns.append((args.get("subagent_type") or "unknown-role", args.get("capability_mode")))
                    elif name == "get_command_or_subagent_output":
                        ids = args.get("task_ids") or []
                        wait_calls[call.get("id")] = ids
                        tasks.extend(ids)
            elif event.get("type") == "tool_result" and event.get("tool_call_id") in wait_calls:
                completed.update(wait_calls[event["tool_call_id"]])
        role_map: dict[str, str] = {}
        capability_map: dict[str, str] = {}
        for index, task_id in enumerate(tasks):
            role, capability = spawns[index] if index < len(spawns) else ("unknown-role", None)
            role_map[task_id] = role
            if capability:
                capability_map[task_id] = capability
        return role_map, capability_map, completed

    def _session_records(self, session_dir: Path, sid: str, role: str | None, capability: str | None, completed_tasks: set[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        chat = session_dir / "chat_history.jsonl"
        if not chat.is_file():
            return records
        model = effort = None
        for line in chat.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                records.append({"type": "evidence_anomaly", "reason": "invalid-json"})
                continue
            if event.get("type") != "assistant":
                continue
            if model is None:
                model = event.get("model_id")
                effort = event.get("reasoning_effort")
            for call in event.get("tool_calls") or []:
                name = call.get("name")
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name == "spawn_subagent":
                    records.append({"type": "response_item", "item_type": "custom_tool_call", "name": "spawn_subagent", "call_id": call.get("id"), "arguments": {"subagent_type": args.get("subagent_type"), "capability_mode": args.get("capability_mode")}})
                elif name in WRITE_TOOLS:
                    # A write-capable tool is only a write attempt when a child runs it
                    # under an edit-permitting capability (read-write/all); under
                    # read-only/execute the sandbox blocks the edit, and parent shell
                    # usage is observed through stream file_change, not an attempt.
                    if role and WRITE_LEVEL.get(CAPABILITY_MAP.get(capability, capability), 0) >= 1:
                        records.append({"type": "session_write_attempt", "tool": name})
                elif name in KNOWN_NON_EVIDENCE_TOOLS:
                    continue
                else:
                    records.append({"type": "evidence_anomaly", "reason": "unknown-tool", "name": name})
        sandbox_type = CAPABILITY_MAP.get(capability, capability) if capability else None
        records.insert(0, {"type": "session_meta", "session_id": sid, "thread_id": None, "agent_role": role, "started_at": None})
        records.insert(1, {"type": "turn_context", "model": model, "effort": effort, "sandbox_policy": {"type": sandbox_type}})
        timestamps = self._updates_timestamps(session_dir)
        if timestamps:
            started_at, completed_at = timestamps
            records.append({"type": "session_lifecycle", "phase": "task_started", "outcome": "started", "started_at": started_at, "completed_at": None})
            if role is None or sid in completed_tasks:
                records.append({"type": "session_lifecycle", "phase": "task_complete", "outcome": "completed", "started_at": started_at, "completed_at": completed_at})
        return records

    def _updates_timestamps(self, session_dir: Path) -> tuple[str, str] | None:
        updates = session_dir / "updates.jsonl"
        if not updates.is_file():
            return None
        first = last = None
        for line in updates.read_text(errors="replace").splitlines():
            try:
                ts = json.loads(line).get("timestamp")
            except json.JSONDecodeError:
                continue
            if ts is None:
                continue
            if first is None:
                first = ts
            last = ts
        start, end = _epoch_to_iso(first), _epoch_to_iso(last)
        return (start, end) if start and end else None

    def _injection_check(self, parent_dir: Path) -> list[dict[str, Any]]:
        """The candidate AGENTS.md must be the injected project instruction."""
        try:
            prompt_context = json.loads((parent_dir / "prompt_context.json").read_text())
        except (OSError, json.JSONDecodeError):
            return [{"type": "evidence_anomaly", "reason": "prompt-context-unreadable"}]
        injected = [item.get("content") for item in prompt_context.get("agents_md_files", []) if Path(str(item.get("file_path", ""))).name.lower() == "agents.md"]
        try:
            candidate = (Path(self.snapshot_path) / "AGENTS.md").read_text() if getattr(self, "snapshot_path", None) else None
        except OSError:
            candidate = None
        if not injected or (candidate is not None and candidate not in injected):
            return [{"type": "evidence_anomaly", "reason": "candidate-not-injected"}]
        return []
