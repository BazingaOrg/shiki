"""Grok Build CLI adapter.

Evidence model (probe-verified on grok 0.2.118 and structurally verified on 1.0.5 and 1.0.24):
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
import shutil
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common import frontmatter
from ..evidence import _safe, reported_cost, secret_patterns, usage_values
from ..runtime import run_process
from .base import EvalAdapter

RUNTIME_FIELDS = ("name", "model", "effort", "permission_mode")
CAPABILITY_MAP = {"read-write": "workspace-write", "read-only": "read-only"}
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
    VERSION = re.compile(r"\b(?:0\.\d+\.\d+|1\.0\.(?:5|24))\b")
    default_model = "grok-4.6"
    prompt_via = "argv"

    def runtime_contract(self, declared: dict[str, str], actual: dict[str, Any]) -> bool | None:
        # The CLI accepts family ids ("grok-4.5") while session evidence records the
        # deployed build ("grok-4.5-build"); a declared family matches its build.
        # Capability mode is model-chosen per spawn: the declared mode is a ceiling,
        # observed must not be broader (read-only/execute satisfy a read-write ceiling).
        model_ok = actual.get("model") == declared["model"] or str(actual.get("model", "")).startswith(declared["model"] + "-")
        sandbox = actual.get("sandbox_policy")
        sandbox_type = sandbox.get("type") if isinstance(sandbox, dict) else sandbox
        if not model_ok or actual.get("effort") != declared["effort"]:
            return False
        if sandbox_type not in WRITE_LEVEL:
            return None
        sandbox_ok = sandbox_type in WRITE_LEVEL and declared["sandbox_type"] in WRITE_LEVEL and WRITE_LEVEL[sandbox_type] <= WRITE_LEVEL[declared["sandbox_type"]]
        return model_ok and actual.get("effort") == declared["effort"] and sandbox_ok

    def __init__(self) -> None:
        super().__init__()
        self.session_id: str | None = None

    # -- candidate -------------------------------------------------------
    def candidate_paths(self, repo: Path) -> list[Path]:
        return [repo / "grok" / "AGENTS.md", *sorted((repo / "grok" / "agents").glob("*.md")), *sorted((repo / "grok" / "roles").glob("*.toml"))]

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
        return (*self._injected_instruction_paths(work, "AGENTS.md", ".grok/agents"), *[str(path.relative_to(work)) for path in sorted((work / ".grok/roles").glob("*.toml"))])

    def prepare(self, work: Path, snapshot: Path, effort: str) -> None:
        # Candidate injection via cwd discovery; prompt_context.json records it.
        self.snapshot_path = str(snapshot)
        self._inject_cwd_instructions(work, snapshot, "AGENTS.md", ".grok/agents")
        if (snapshot / "roles").is_dir():
            shutil.copytree(snapshot / "roles", work / ".grok" / "roles")

    def invocation(self, work: Path, prompt: str, model: str, effort: str) -> list[str]:
        # resolve() canonicalizes macOS /var -> /private/var so the session dir key
        # grok records matches the one session_evidence looks up.
        return [self.info["binary"], "--single", prompt, "--cwd", str(work.resolve()), "--output-format", "streaming-json", "--permission-mode", "auto", "--reasoning-effort", effort, "--model", model, "--disable-web-search"]

    def run(self, work: Path, prompt: str, model: str, effort: str, timeout: int) -> tuple[int, str, str]:
        env = dict(os.environ)
        env["GROK_MEMORY"] = "0"
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
                record = {"type": "turn.completed", "usage": usage_values(event.get("usage")), "reported_cost_usd": reported_cost(event.get("total_cost_usd"))}
                lines.append(json.dumps(record, ensure_ascii=False))
            elif typ == "tool_call":
                # A file change is a definite edit tool call; bash is write-capable but
                # unobservable here (session evidence carries the capability context).
                if event.get("toolName") in {"search_replace", "apply_patch"}:
                    lines.append(json.dumps({"type": "item.started", "item": {"type": "file_change", "has_changes": True}}))
            elif typ in KNOWN_NON_EVIDENCE_ACP:
                continue
            else:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "unknown-event-type", "event_type": typ}))
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
        spawns: dict[str, tuple[str, str | None]] = {}
        waits: dict[str, list[str]] = {}
        role_map: dict[str, str] = {}
        capability_map: dict[str, str] = {}
        completed: set[str] = set()
        self.child_lifecycles = {}
        for line in (parent_dir / "chat_history.jsonl").read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for call in event.get("tool_calls") or []:
                    try:
                        args = json.loads(call.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(args, dict):
                        continue
                    if call.get("name") == "spawn_subagent":
                        spawns[call.get("id")] = (args.get("subagent_type") or "unknown-role", args.get("capability_mode"))
                    elif call.get("name") == "get_command_or_subagent_output":
                        waits[call.get("id")] = args.get("task_ids") or []
            elif event.get("type") == "tool_result":
                call_id = event.get("tool_call_id")
                content = event.get("content")
                if not isinstance(content, str):
                    continue
                if call_id in spawns:
                    match = re.search(r"(?m)^subagent_id: ([A-Za-z0-9-]+)$", content)
                    if match:
                        sid = match.group(1)
                        role, capability = spawns[call_id]
                        role_map[sid] = role
                        if capability:
                            capability_map[sid] = capability
                elif call_id in waits:
                    for sid in waits[call_id]:
                        block = re.search(r"(?ms)^=== Task " + re.escape(sid) + r" ===\n(.*?)(?=^=== (?:Task |Output)|\Z)", content)
                        if block and re.search(r"(?m)^Status: completed$", block.group(1)):
                            completed.add(sid)
        for path in sorted((parent_dir / "subagents").glob("*/meta.json")):
            try:
                meta = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            sid = meta.get("child_session_id")
            if meta.get("parent_session_id") != parent_dir.name or sid != path.parent.name or meta.get("subagent_id") != sid:
                continue
            if role_map.get(sid) != meta.get("subagent_type"):
                continue
            if meta.get("status") == "completed" and meta.get("started_at") and meta.get("completed_at"):
                completed.add(sid)
                self.child_lifecycles[sid] = (meta["started_at"], meta["completed_at"])
        return role_map, capability_map, completed

    def _session_records(self, session_dir: Path, sid: str, role: str | None, capability: str | None, completed_tasks: set[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        chat = session_dir / "chat_history.jsonl"
        if not chat.is_file():
            return records
        model = effort = None
        observed_models = set()
        for line in chat.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                records.append({"type": "evidence_anomaly", "reason": "invalid-json"})
                continue
            if event.get("type") != "assistant":
                continue
            if event.get("model_id"):
                observed_models.add(event["model_id"])
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
                elif name in {"Bash", "bash", "run_terminal_command"}:
                    records.append({"type": "response_item", "item_type": "function_call", "name": "exec"})
                elif name in WRITE_TOOLS:
                    records.append({"type": "session_write_attempt", "tool": name})
                elif name in KNOWN_NON_EVIDENCE_TOOLS:
                    continue
                else:
                    records.append({"type": "evidence_anomaly", "reason": "unknown-tool", "name": name})
        sandbox_type = CAPABILITY_MAP.get(capability, capability) if capability else None
        records.insert(0, {"type": "session_meta", "session_id": sid, "thread_id": None, "agent_role": role, "started_at": None})
        records.insert(1, {"type": "turn_context", "model": model, "observed_models": sorted(observed_models), "effort": effort, "sandbox_policy": {"type": sandbox_type}})
        timestamps = getattr(self, "child_lifecycles", {}).get(sid) or self._updates_timestamps(session_dir)
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
