"""Small, deterministic Git fixtures used by static and live evaluation runs."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .common import files


def fixture(root: Path, kind: str, git_binary: str = "git") -> None:
    (root / "README.md").write_text("Teh fixture README.\n")
    (root / "NOTES.md").write_text("notes\n")
    (root / "docs" / "plans").mkdir(parents=True)
    (root / "docs" / "plans" / ".keep").write_text("\n")
    if kind == "bulk":
        config = root / "config"
        config.mkdir()
        for index in range(1, 6):
            (config / f"service-{index}.toml").write_text("enabled = false\n")
    if kind == "architecture":
        (root / "inventory.py").write_text(
            "from threading import Lock\n"
            "inventory_lock = Lock()\n"
            "def reserve(payment_lock):\n"
            "    with inventory_lock:\n"
            "        with payment_lock:\n"
            "            return True\n"
        )
        (root / "payments.py").write_text(
            "from threading import Lock\n"
            "payment_lock = Lock()\n"
            "def refund(inventory_lock):\n"
            "    with payment_lock:\n"
            "        with inventory_lock:\n"
            "            return True\n"
        )
        (root / "CONCURRENCY.md").write_text(
            "Production intermittently deadlocks when reserve and refund run concurrently. "
            "inventory.py acquires inventory then payment; payments.py acquires payment then inventory.\n"
        )
    if kind == "code-test-diff":
        (root / "auth.py").write_text("def allow():\n    return False\n")
        (root / "test_auth.py").write_text("import unittest\nfrom auth import allow\n\nclass AuthTest(unittest.TestCase):\n    def test_allow(self):\n        self.assertTrue(allow())\n")
    subprocess.run([git_binary, "init", "-q"], cwd=root, check=True)
    subprocess.run([git_binary, "add", "."], cwd=root, check=True)
    subprocess.run([git_binary, "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "commit", "-qm", "fixture"], cwd=root, check=True)
    if kind == "code-test-diff":
        (root / "auth.py").write_text("def allow():\n    return True\n")
        (root / "USER.md").write_text("user-owned dirty edit\n")


def git_state(root: Path, git_binary: str = "git") -> dict[str, object]:
    head = subprocess.run([git_binary, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    diff = subprocess.run([git_binary, "diff", "--binary", "--no-ext-diff"], cwd=root, capture_output=True, text=True, check=True).stdout
    tracked = subprocess.run([git_binary, "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    return {"head": head, "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(), "untracked": sorted(path for path in files(root) if path not in tracked)}
