"""Stable path, hashing, JSON, and redaction helpers."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES = {"deep-reasoner", "fast-worker", "qa-runner"}
SENSITIVE_KEY = re.compile(r"(?:authorization|bearer|cookie|token|secret|api[_-]?key|password|auth)", re.I)
SENSITIVE_VALUE = re.compile(
    r"(?:bearer\s+\S+|(?:token|secret|api[_-]?key|password|passwd|pwd)\s*[=:]\s*\S+|"
    r"gAAAA[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"https?://[^\s/@:]+:[^\s/@]+@)",
    re.I,
)
PATH_VALUE = re.compile(r"(?:/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)")


def load(path: Path | str) -> Any:
    return json.loads(Path(path).read_text())


def dump(path: Path | str, value: Any) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def files(root: Path) -> dict[str, str]:
    # __pycache__ holds deterministic bytecode artifacts of any test run, not source changes.
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}


def changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(set(before) ^ set(after) | {key for key in before if key in after and before[key] != after[key]})


def redact_text(value: Any) -> tuple[str, list[str]]:
    """Redact secret-bearing values and machine-local paths, returning matched pattern labels."""
    text = str(value)
    patterns: list[str] = []
    if SENSITIVE_VALUE.search(text):
        patterns.append("secret-value")
        text = SENSITIVE_VALUE.sub("<redacted:secret>", text)
    if PATH_VALUE.search(text):
        patterns.append("local-path")
        text = PATH_VALUE.sub("<redacted:path>", text)
    return text, patterns


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and "\\" not in value
