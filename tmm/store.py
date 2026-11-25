"""Persistence: stats.json and state.json in the state dir, written atomically."""

from __future__ import annotations

import hashlib
import json
import os

from .config import state_dir
from .game import Stats, empty_stats


def stats_path(override: str | None = None) -> str:
    return override or os.path.join(state_dir(), "stats.json")


def state_path() -> str:
    return os.path.join(state_dir(), "state.json")


SOCKET_MAX = 100  # macOS limits unix socket paths to 104 bytes


def socket_path() -> str:
    """meter.sock in the state dir, or in the per-user temp dir when that path is too long."""
    path = os.path.join(state_dir(), "meter.sock")
    if len(path.encode()) <= SOCKET_MAX:
        return path
    digest = hashlib.sha1(state_dir().encode()).hexdigest()[:10]
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", f"tmm-{os.getuid()}-{digest}.sock")


def write_atomic(path: str, data: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def load_stats(path: str | None = None) -> Stats:
    try:
        with open(stats_path(path), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and raw.get("version") == 1:
            return {**empty_stats(), **raw}
    except (OSError, ValueError):
        pass
    return empty_stats()


def save_stats(stats: Stats, path: str | None = None) -> None:
    write_atomic(stats_path(path), json.dumps(stats, indent=2))


def load_state() -> dict:
    """Daemon state that survives restarts: {"enabled": bool}."""
    try:
        with open(state_path(), encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    write_atomic(state_path(), json.dumps(state))
