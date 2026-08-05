"""Candidate snapshots and isolated subprocess lifecycle."""
from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import tomllib
from pathlib import Path

from .common import digest, sha

ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY")
RUNTIME_FIELDS = ("model", "model_reasoning_effort", "sandbox_mode")


def candidate_paths(repo: Path) -> list[Path]:
    return [repo / "codex" / "AGENTS.md", *sorted((repo / "codex" / "agents").glob("*.toml"))]


def candidate_hashes(repo: Path) -> dict[str, str]:
    return {str(path.relative_to(repo)): sha(path) for path in candidate_paths(repo)}


def snapshot_candidate(repo: Path, output: Path) -> dict[str, object]:
    """Copy the candidate files once; later cases never reread repository candidates."""
    snap = output / "candidate-snapshot"
    snap.mkdir(mode=0o700)
    hashes: dict[str, str] = {}
    paths = candidate_paths(repo)
    tomls = [path for path in paths if path.suffix == ".toml"]
    if not (repo / "codex" / "AGENTS.md").is_file() or not tomls:
        raise RuntimeError("candidate must contain codex/AGENTS.md and at least one agent TOML")
    for source in paths:
        rel = source.relative_to(repo / "codex")
        dest = snap / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        os.chmod(dest, 0o600)
        hashes[str(rel)] = sha(dest)
    return {"path": str(snap), "hashes": hashes, "hash": digest(hashes)}


def declared_runtime(snapshot: Path) -> dict[str, dict[str, str]]:
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


def source_drift(repo: Path, snapshot: dict[str, object]) -> bool:
    current = {str(path.relative_to(repo / "codex")): sha(path) for path in candidate_paths(repo) if path.is_file()}
    return current != snapshot["hashes"]


def config(home: Path, snapshot: Path, effort: str = "medium") -> None:
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


def env_for(home: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
    env["CODEX_HOME"] = str(home)
    return env


def env_provenance() -> str:
    values = {key: hashlib.sha256(os.environ[key].encode()).hexdigest() for key in ENV_ALLOWLIST if key in os.environ}
    return digest(values)


def run_process(argv: list[str], *, prompt: str, env: dict[str, str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=cwd, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        raise TimeoutError("timeout")
    except BaseException:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise
    return proc.returncode, stdout, stderr
