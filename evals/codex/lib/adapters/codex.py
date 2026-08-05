"""Codex CLI adapter: the original `codex exec` transport, behavior unchanged."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from ..common import digest, sha
from ..evidence import write_events_evidence, write_session_evidence
from ..runtime import ENV_ALLOWLIST, run_process
from .base import EvalAdapter

VERSION = re.compile(r"\b0\.146\.\d+\b")
RUNTIME_FIELDS = ("model", "model_reasoning_effort", "sandbox_mode")


class CodexAdapter(EvalAdapter):
    name = "codex"
    binary = "codex"
    VERSION = VERSION
    default_model = "gpt-5.6-sol"
    prompt_via = "stdin"

    # -- candidate -------------------------------------------------------
    def candidate_paths(self, repo: Path) -> list[Path]:
        return [repo / "codex" / "AGENTS.md", *sorted((repo / "codex" / "agents").glob("*.toml"))]

    def snapshot(self, repo: Path, output: Path) -> dict[str, object]:
        """Copy the candidate files once; later cases never reread repository candidates."""
        snap = output / "candidate-snapshot"
        snap.mkdir(mode=0o700)
        hashes: dict[str, str] = {}
        paths = self.candidate_paths(repo)
        tomls = [path for path in paths if path.suffix == ".toml"]
        if not (repo / "codex" / "AGENTS.md").is_file() or not tomls:
            raise RuntimeError("candidate must contain codex/AGENTS.md and at least one agent TOML")
        for source in paths:
            rel = source.relative_to(repo)
            copy_rel = source.relative_to(repo / "codex")
            dest = snap / copy_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            os.chmod(dest, 0o600)
            hashes[str(rel)] = sha(dest)
        return {"path": str(snap), "hashes": hashes, "hash": digest(hashes)}

    def declared_runtime(self, snapshot: Path) -> dict[str, dict[str, str]]:
        """Declared model/effort/sandbox per custom agent, read once from the snapshot.

        The runtime contract is "observed runtime must equal the TOML declaration";
        manifest cases no longer duplicate these values.
        """
        agents_dir = snapshot / "agents"
        if not (snapshot / "AGENTS.md").is_file() or not agents_dir.is_dir():
            raise RuntimeError("candidate snapshot must contain AGENTS.md and an agents/ directory")
        declared: dict[str, dict[str, str]] = {}
        for path in sorted(agents_dir.glob("*.toml")):
            try:
                data = tomllib.loads(path.read_text())
            except tomllib.TOMLDecodeError as exc:
                raise RuntimeError(f"invalid agent TOML {path.name}: {exc}") from exc
            role = data.get("name")
            if not isinstance(role, str) or not role:
                raise RuntimeError(f"agent TOML {path.name} must declare a name")
            if role in declared:
                raise RuntimeError(f"duplicate agent role in TOMLs: {role}")
            missing = [field for field in RUNTIME_FIELDS if not isinstance(data.get(field), str)]
            if missing:
                raise RuntimeError(f"agent TOML {path.name} must declare: {', '.join(missing)}")
            declared[role] = {"model": data["model"], "effort": data["model_reasoning_effort"], "sandbox_type": data["sandbox_mode"]}
        if not declared:
            raise RuntimeError("candidate snapshot must declare at least one custom agent TOML")
        return declared

    # -- per-case lifecycle ----------------------------------------------
    def prepare(self, work: Path, snapshot: Path, effort: str) -> None:
        home = Path(tempfile.mkdtemp(prefix="shiki-codex-home-"))
        home.mkdir(mode=0o700, exist_ok=True)
        os.chmod(home, 0o700)
        shutil.copyfile(snapshot / "AGENTS.md", home / "AGENTS.md")
        shutil.copytree(snapshot / "agents", home / "agents")
        source = os.environ.get("SHIKI_CODEX_AUTH_FILE")
        if source:
            auth_source = Path(source)
            if auth_source.is_symlink() or not auth_source.is_file():
                raise RuntimeError("SHIKI_CODEX_AUTH_FILE must name a regular existing file")
            dest = home / "auth.json"
            shutil.copyfile(auth_source, dest)
            os.chmod(dest, 0o600)
        (home / "config.toml").write_text(
            f"approval_policy = 'never'\nsandbox_mode = 'workspace-write'\nmodel_reasoning_effort = '{effort}'\nweb_search = 'disabled'\n"
            "[features]\nhooks = false\napps = false\nnetwork_proxy = false\nplugins = false\nremote_plugin = false\n"
        )
        os.chmod(home / "config.toml", 0o600)
        (home / "final-schema.json").write_text(
            '{"type": "object", "additionalProperties": false, "required": ["reported_summary", "reported_delegation"], "properties": {"reported_summary": {"type": "string"}, "reported_delegation": {"type": "array", "items": {"type": "string"}}}}'
        )
        self.home = home

    def invocation(self, work: Path, prompt: str, model: str, effort: str) -> list[str]:
        return [self.info["binary"], "exec", "--strict-config", "--json", "--ignore-rules", "--color", "never", "-C", str(work), "-o", str(self.home / "final.json"), "--output-schema", str(self.home / "final-schema.json"), "--model", model]

    def run(self, work: Path, prompt: str, model: str, effort: str, timeout: int) -> tuple[int, str, str]:
        env = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
        env["CODEX_HOME"] = str(self.home)
        return run_process(self.invocation(work, prompt, model, effort), prompt=prompt, env=env, cwd=work, timeout=timeout)

    def cleanup(self) -> None:
        shutil.rmtree(getattr(self, "home", ""), ignore_errors=True)

    def stream_evidence(self, stdout: str, output: Path) -> tuple[Path, list[str]]:
        return write_events_evidence(stdout, output)

    def session_evidence(self, work: Path, output: Path) -> tuple[list[Path], list[str]]:
        sessions = sorted((self.home / "sessions").rglob("*.jsonl")) if (self.home / "sessions").exists() else []
        return write_session_evidence(sessions, output)
