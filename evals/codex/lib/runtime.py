"""Shared subprocess runtime and environment provenance."""
from __future__ import annotations

import hashlib
import os
import signal
import subprocess
from pathlib import Path

from .common import digest

ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY")


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
