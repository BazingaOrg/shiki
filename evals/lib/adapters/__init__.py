"""Adapter registry: per-CLI transports for the shared evaluation core."""
from __future__ import annotations

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .grok import GrokAdapter

ADAPTERS = {"claude": ClaudeAdapter, "codex": CodexAdapter, "grok": GrokAdapter}


def get_adapter(name: str):
    try:
        return ADAPTERS[name]
    except KeyError:
        raise SystemExit(f"unknown adapter: {name} (choose from {sorted(ADAPTERS)})") from None
