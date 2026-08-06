"""Adapter interface: everything that differs between local model CLIs.

The shared core (manifest contract, fixtures, grading, comparison, evidence
root, promotion) is transport-agnostic. An adapter provides: binary probing,
candidate snapshot + runtime declarations, isolated per-case invocation, and
conversion of CLI output into the shared evidence record format consumed by
lib/trace.py.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..common import digest, sha


class EvalAdapter:
    name: str = ""
    binary: str = ""
    VERSION: re.Pattern[str] = re.compile(r"(?!x)x")  # subclass

    def __init__(self) -> None:
        self.info: dict[str, Any] | None = None

    # -- probing ---------------------------------------------------------
    def probe(self) -> tuple[dict[str, Any] | None, str | None]:
        binary = shutil.which(self.binary)
        if not binary:
            return None, f"{self.binary} executable not found"
        probe = subprocess.run([binary, "--version"], capture_output=True, text=True)
        rendered = (probe.stdout + probe.stderr).strip()
        match = self.VERSION.search(rendered)
        if probe.returncode or not match:
            return None, f"unsupported {self.binary} version: {rendered or probe.returncode}"
        tools = {name: shutil.which(name) for name in ("git", "python3")}
        if any(path is None for path in tools.values()):
            return None, "required evaluator tool not found"
        tool_hashes = {name: sha(Path(path)) for name, path in tools.items() if path}
        self.info = {"binary": binary, "version": match.group(0), "sha256": sha(Path(binary)), "tools": tools, "toolchain_digest": digest(tool_hashes)}
        return self.info, None

    def tools(self) -> dict[str, str]:
        return self.info.get("tools", {}) if self.info else {}

    def runtime_contract(self, declared: dict[str, str], actual: dict[str, Any]) -> bool:
        """Whether observed runtime (model/effort/sandbox_policy) satisfies the declared contract.

        The base contract is exact equality (codex sandbox is enforced by the CLI);
        adapters whose CLI lets the model choose capabilities override this.
        """
        sandbox = actual.get("sandbox_policy")
        sandbox_type = sandbox.get("type") if isinstance(sandbox, dict) else sandbox
        return actual.get("model") == declared["model"] and actual.get("effort") == declared["effort"] and sandbox_type == declared["sandbox_type"]

    # -- candidate -------------------------------------------------------
    def candidate_paths(self, repo: Path) -> list[Path]:
        raise NotImplementedError

    def candidate_hashes(self, repo: Path) -> dict[str, str]:
        return {str(path.relative_to(repo)): sha(path) for path in self.candidate_paths(repo)}

    def snapshot(self, repo: Path, output: Path) -> dict[str, object]:
        raise NotImplementedError

    def source_drift(self, repo: Path, snapshot: dict[str, object]) -> bool:
        current = {str(path.relative_to(repo)): sha(path) for path in self.candidate_paths(repo) if path.is_file()}
        return current != snapshot["hashes"]

    def declared_runtime(self, snapshot: Path) -> dict[str, dict[str, str]]:
        raise NotImplementedError

    # -- per-case lifecycle ----------------------------------------------
    def injected_paths(self, work: Path) -> tuple[str, ...]:
        """Work-relative files installed by prepare(); they are runner-controlled,
        not fixture content, and must not enter before/after hashing or fixture digests."""
        return ()

    def prepare(self, work: Path, snapshot: Path, effort: str) -> None:
        """Isolation setup before the run (may keep adapter state)."""

    def run(self, work: Path, prompt: str, model: str, effort: str, timeout: int) -> tuple[int, str, str]:
        """Execute one case in `work`; return (returncode, stdout, stderr)."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Release per-run resources created by prepare()."""

    def stream_evidence(self, stdout: str, output: Path) -> tuple[Path, list[str]]:
        """Convert CLI stdout stream into shared events.jsonl evidence; return (path, secret_hits)."""
        raise NotImplementedError

    def session_evidence(self, work: Path, output: Path) -> tuple[list[Path], list[str]]:
        """Write per-session evidence records; return (paths, secret_hits)."""
        raise NotImplementedError
