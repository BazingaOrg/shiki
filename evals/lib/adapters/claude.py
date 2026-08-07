"""Claude Code CLI adapter.

Evidence model (probe-verified on claude 2.1.223):
- `claude -p ... --output-format stream-json --verbose` emits NDJSON:
  assistant messages (with model and tool_use blocks), user messages
  (tool_result), system (hook noise), and a final result event with
  session_id, usage and cost.
- Sessions live under `~/.claude/projects/<slash-to-dash-encoded-cwd>/`:
  one jsonl per session. A spawned subagent (the `Agent` tool, whose
  input carries `subagent_type`) creates a child session with a
  `subagents/agent-<id>.jsonl` transcript whose assistant messages carry
  `attributionAgent` and `model`, plus an `agent-<id>.meta.json` with
  `agentType`.

Isolation is cwd-based: the candidate CLAUDE.md is copied into the
fixture work dir (discovered as a project instruction) and agent
profiles into `<work>/.claude/agents/`. Claude Code does not enforce a
profile's declared model (the user's environment model wins), has no
sandbox concept, and transcripts do not persist the injected CLAUDE.md:
runtime and injection are recorded as observations, never asserted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from ..common import digest, sha
from ..evidence import _safe, secret_patterns, usage_values
from ..runtime import run_process
from .base import EvalAdapter

VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")
RUNTIME_FIELDS = ("name", "model")
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit", "apply_patch"}
KNOWN_NON_EVIDENCE_TOOLS = {"Read", "Bash", "Grep", "Glob", "LS", "TodoWrite", "WebFetch", "WebSearch", "Task", "Agent", "KillShell", "KillBash", "TaskStop", "SendMessage", "Wait", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskOutput"}
KNOWN_NON_EVIDENCE_STREAM = {"system", "user"}


def _frontmatter(path: Path) -> dict[str, str]:
    """Minimal YAML frontmatter reader: single-line scalar keys only."""
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    result: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        if not value or value in {">", "|"}:
            continue
        result[key.strip()] = value.strip('"\'')
    return result


def _encode_project_path(path: Path) -> str:
    # claude encodes both "/" and "_" in the cwd as "-" (probe-verified); mkdtemp
    # suffixes occasionally contain underscores, so both must map.
    return str(path.resolve()).replace("/", "-").replace("_", "-")


class ClaudeAdapter(EvalAdapter):
    name = "claude"
    binary = "claude"
    VERSION = VERSION
    default_model = None  # the user's configured model is the evaluated environment
    prompt_via = "argv"

    def __init__(self) -> None:
        super().__init__()
        self.session_id: str | None = None

    def runtime_contract(self, declared: dict[str, str], actual: dict[str, Any]) -> bool:
        # Claude Code does not enforce an agent profile's declared model (the user's
        # environment model wins, as probe-verified), and has no sandbox concept nor
        # effort observation. Runtime is recorded as observation only, never asserted:
        # declared values are aspirational, not contractual, on this platform.
        return True

    # -- candidate -------------------------------------------------------
    def candidate_paths(self, repo: Path) -> list[Path]:
        return [repo / "CLAUDE.md", *sorted((repo / "agents").glob("*.md"))]

    def snapshot(self, repo: Path, output: Path) -> dict[str, object]:
        snap = output / "candidate-snapshot"
        snap.mkdir(mode=0o700)
        hashes: dict[str, str] = {}
        paths = self.candidate_paths(repo)
        mds = [path for path in paths if path.suffix == ".md"]
        if not (repo / "CLAUDE.md").is_file() or not mds:
            raise RuntimeError("candidate must contain CLAUDE.md and at least one agent profile")
        for source in paths:
            rel = source.relative_to(repo)
            copy_rel = "CLAUDE.md" if rel == Path("CLAUDE.md") else rel
            dest = snap / copy_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            os.chmod(dest, 0o600)
            hashes[str(rel)] = sha(dest)
        return {"path": str(snap), "hashes": hashes, "hash": digest(hashes)}

    def declared_runtime(self, snapshot: Path) -> dict[str, dict[str, str]]:
        agents_dir = snapshot / "agents"
        if not (snapshot / "CLAUDE.md").is_file() or not agents_dir.is_dir():
            raise RuntimeError("candidate snapshot must contain CLAUDE.md and an agents/ directory")
        declared: dict[str, dict[str, str]] = {}
        for path in sorted(agents_dir.glob("*.md")):
            data = _frontmatter(path)
            missing = [field for field in RUNTIME_FIELDS if not data.get(field)]
            if missing:
                raise RuntimeError(f"agent profile {path.name} must declare: {', '.join(missing)}")
            role = data["name"]
            if role in declared:
                raise RuntimeError(f"duplicate agent role in profiles: {role}")
            # permission_mode is optional (repo templates omit it): the sandbox
            # contract is not asserted for claude, so an absent mode stays "unobserved".
            permission_mode = data.get("permission_mode", "")
            sandbox_type = "read-only" if permission_mode == "plan" else ("workspace-write" if permission_mode == "default" else "unobserved")
            declared[role] = {"model": data["model"], "effort": "unobserved", "sandbox_type": sandbox_type}
        if not declared:
            raise RuntimeError("candidate snapshot must declare at least one custom agent profile")
        return declared

    # -- per-case lifecycle ----------------------------------------------
    def injected_paths(self, work: Path) -> tuple[str, ...]:
        return ("CLAUDE.md", *[f".claude/agents/{path.name}" for path in sorted((work / ".claude" / "agents").glob("*.md"))])

    def prepare(self, work: Path, snapshot: Path, effort: str) -> None:
        # Candidate injection via cwd discovery.
        shutil.copyfile(snapshot / "CLAUDE.md", work / "CLAUDE.md")
        agents_dir = work / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        for path in sorted((snapshot / "agents").glob("*.md")):
            shutil.copyfile(path, agents_dir / path.name)

    def invocation(self, work: Path, prompt: str, model: str, effort: str) -> list[str]:
        argv = [self.info["binary"], "-p", prompt, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits"]
        if model:
            argv += ["--model", model]
        return argv

    def run(self, work: Path, prompt: str, model: str, effort: str, timeout: int) -> tuple[int, str, str]:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return run_process(self.invocation(work, prompt, model, effort), prompt="", env=env, cwd=work, timeout=timeout)

    def cleanup(self) -> None:
        pass

    # -- evidence --------------------------------------------------------
    def stream_evidence(self, stdout: str, output: Path) -> tuple[Path, list[str]]:
        lines = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "invalid-json"}))
                continue
            typ = event.get("type")
            if typ == "result":
                self.session_id = event.get("session_id")
                record = {"type": "turn.completed", "session_id": event.get("session_id"), "usage": usage_values(event.get("usage"))}
                lines.append(json.dumps(record, ensure_ascii=False))
            elif typ == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use" and block.get("name") in WRITE_TOOLS:
                        lines.append(json.dumps({"type": "item.started", "item": {"type": "file_change", "has_changes": True}}))
            elif typ in KNOWN_NON_EVIDENCE_STREAM:
                continue
            else:
                lines.append(json.dumps({"type": "evidence_anomaly", "reason": "unknown-event-type"}))
        dest = output / "events.jsonl"
        dest.write_text("\n".join(lines) + ("\n" if lines else ""))
        return dest, []

    def session_evidence(self, work: Path, output: Path) -> tuple[list[Path], list[str]]:
        if not self.session_id:
            return [], []
        base = Path.home() / ".claude" / "projects" / _encode_project_path(work)
        parent_path = base / f"{self.session_id}.jsonl"
        if not parent_path.is_file():
            return [], []
        # Agent tool calls in the parent link to subagent transcripts via meta.toolUseId.
        spawn_calls = self._spawn_calls(parent_path)
        target = output / "session-evidence"
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        secret_hits: set[str] = set()
        # Parent session record. Note: claude transcripts do not persist the injected
        # CLAUDE.md (it lives in the API-level system prompt), so injection cannot be
        # counter-proven from session evidence; the policy suite verifies it indirectly
        # (an uninjected candidate surfaces as routing FAILs).
        parent_records = self._session_records(parent_path, self.session_id, None, None)
        dest = target / f"00-{self.session_id}.jsonl"
        dest.write_text("\n".join(json.dumps(_safe(record, secret_hits), ensure_ascii=False) for record in parent_records) + ("\n" if parent_records else ""))
        written.append(dest)
        # Subagent transcripts linked by toolUseId
        index = 1
        for transcript in sorted(base.glob("*/subagents/agent-*.jsonl")):
            meta_path = transcript.with_suffix(".meta.json")
            try:
                meta = json.loads(meta_path.read_text())
            except (OSError, json.JSONDecodeError):
                meta = {}
            tool_use_id = meta.get("toolUseId")
            if tool_use_id not in spawn_calls:
                continue  # stale session from an unrelated run
            agent_type = meta.get("agentType") or spawn_calls[tool_use_id]
            records = self._session_records(transcript, transcript.stem, agent_type, None)
            out = target / f"{index:02d}-{transcript.stem}.jsonl"
            out.write_text("\n".join(json.dumps(_safe(record, secret_hits), ensure_ascii=False) for record in records) + ("\n" if records else ""))
            written.append(out)
            index += 1
        return written, sorted(pattern for pattern in secret_hits if pattern != "local-path")

    def _spawn_calls(self, parent_path: Path) -> dict[str, str]:
        """tool_use_id -> subagent_type for Agent tool calls in the parent transcript."""
        spawns: dict[str, str] = {}
        for line in parent_path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "assistant":
                continue
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Agent":
                    args = block.get("input") or {}
                    spawns[block.get("id")] = args.get("subagent_type") if isinstance(args, dict) else None
        return spawns

    def _session_records(self, path: Path, sid: str, role: str | None, capability: str | None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        model = None
        started_at = completed_at = None
        for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                records.append({"type": "evidence_anomaly", "reason": "invalid-json"})
                continue
            typ = event.get("type")
            if typ == "assistant":
                message = event.get("message", {})
                if model is None:
                    model = message.get("model")
                if started_at is None:
                    started_at = event.get("timestamp")
                completed_at = event.get("timestamp")
                for block in message.get("content", []):
                    if block.get("type") == "tool_use":
                        name = block.get("name")
                        if name in WRITE_TOOLS:
                            records.append({"type": "session_write_attempt", "tool": name})
                        elif name == "Agent":
                            args = block.get("input") or {}
                            records.append({"type": "response_item", "item_type": "custom_tool_call", "name": "Agent", "call_id": block.get("id"), "arguments": {"subagent_type": args.get("subagent_type") if isinstance(args, dict) else None}})
                        elif name in KNOWN_NON_EVIDENCE_TOOLS:
                            continue
                        else:
                            records.append({"type": "evidence_anomaly", "reason": "unknown-tool", "name": name, "line": line_number})
            elif typ == "user":
                if started_at is None:
                    started_at = event.get("timestamp")
                completed_at = event.get("timestamp")
        records.insert(0, {"type": "session_meta", "session_id": sid, "thread_id": None, "agent_role": role, "started_at": None})
        # effort/sandbox are unobservable in Claude Code evidence (permission system,
        # not a sandbox): recorded as explicit "unobserved" markers, never asserted.
        records.insert(1, {"type": "turn_context", "model": model, "effort": "unobserved", "sandbox_policy": {"type": "unobserved"}})
        if started_at:
            records.append({"type": "session_lifecycle", "phase": "task_started", "outcome": "started", "started_at": started_at, "completed_at": None})
            if completed_at:
                records.append({"type": "session_lifecycle", "phase": "task_complete", "outcome": "completed", "started_at": started_at, "completed_at": completed_at})
        return records
