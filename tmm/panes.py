"""Opening, moving, sizing and closing the sessions the daemon owns: the meter
pane (HUD), the demo panes and the stats pane.

Each owned session is tagged with user.tmmRole so a restarted daemon can
find (and adopt or close) what a previous run left behind.
"""

from __future__ import annotations

import os
import shlex
import sys

import iterm2

from .effects import log

ROLE_VAR = "user.tmmRole"
ANCHOR_VAR = "user.tmmAnchor"
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))




def script_command(script: str, *args: str) -> str:
    """Command line running one of our stdlib-only scripts with this Python."""
    parts = [sys.executable, "-I", os.path.join(ROOT, "tmm", script), *args]
    return " ".join(shlex.quote(p) for p in parts)


def pane_profile(command: str) -> iterm2.LocalWriteOnlyProfile:
    p = iterm2.LocalWriteOnlyProfile()
    p.set_use_custom_command("Yes")
    p.set_command(command)
    p.set_close_sessions_on_end(True)
    p.set_badge_text("")
    p.set_unlimited_scrollback(False)
    p.set_scrollback_lines(0)
    p.set_allow_title_setting(False)
    return p


def focused_session(app) -> iterm2.Session | None:
    window = app.current_terminal_window
    if window is None or window.current_tab is None:
        return None
    return window.current_tab.current_session


def all_sessions(app):
    for window in app.terminal_windows:
        for tab in window.tabs:
            yield from tab.sessions


async def split_under(app, anchor, command: str, role: str, name: str) -> iterm2.Session | None:
    session = await anchor.async_split_pane(vertical=False, before=False, profile_customizations=pane_profile(command))
    if session is None:
        return None
    await session.async_set_variable(ROLE_VAR, role)
    try:
        await session.async_set_name(name)
    except Exception:  # noqa: BLE001
        pass
    return session


async def set_rows(app, pane_id: str, neighbor_id: str, rows: int) -> None:
    """Give `pane_id` `rows` rows, taking or giving the difference to `neighbor_id`."""
    await app.async_refresh()
    pane, neighbor = app.get_session_by_id(pane_id), app.get_session_by_id(neighbor_id)
    if pane is None or neighbor is None:
        return
    _, tab = app.get_window_and_tab_for_session(pane)
    if tab is None:
        return
    total = pane.grid_size.height + neighbor.grid_size.height
    rows = max(2, min(rows, total // 2))
    pane.preferred_size = iterm2.Size(pane.grid_size.width, rows)
    neighbor.preferred_size = iterm2.Size(neighbor.grid_size.width, total - rows)
    await tab.async_update_layout()


async def close(app, session_id: str | None) -> None:
    session = app.get_session_by_id(session_id) if session_id else None
    if session is not None:
        try:
            await session.async_close(force=True)
        except Exception:  # noqa: BLE001
            pass


class MeterPane:
    """The meter pane for one role ("hud" for the real meter, "demo")."""

    def __init__(self, connection, app, role: str, rows: int):
        self.connection = connection
        self.app = app
        self.role = role
        self.rows = rows
        self.session_id: str | None = None
        self.anchor_id: str | None = None  # the session the pane sits under
        self.closing: set[str] = set()  # sessions we closed on purpose

    def command(self, socket_path: str) -> str:
        return script_command("viewer.py", socket_path, self.role)

    async def open(self, anchor, socket_path: str) -> bool:
        session = await split_under(self.app, anchor, self.command(socket_path), self.role, "Typing Madness Meter")
        if session is None:
            return False
        self.session_id = session.session_id
        await self._anchored(anchor)
        return True

    async def move_under(self, target, socket_path: str) -> bool:
        """Move the pane under `target`; reopens it there if iTerm2 can't move sessions."""
        pane = self.app.get_session_by_id(self.session_id) if self.session_id else None
        if pane is None:
            return await self.open(target, socket_path)
        try:
            await self.app.async_move_session(pane, target, False, False)
        except Exception as e:  # noqa: BLE001
            log(f"move failed ({e!r}); reopening the meter under the new session")
            await self.close()
            return await self.open(target, socket_path)
        await self._anchored(target)
        return True

    async def _anchored(self, anchor) -> None:
        self.anchor_id = anchor.session_id
        session = self.app.get_session_by_id(self.session_id)
        if session is not None:
            await session.async_set_variable(ANCHOR_VAR, anchor.session_id)
        # Splitting focuses the new pane; give focus back to the anchor.
        await anchor.async_activate(select_tab=True, order_window_front=False)
        try:
            await set_rows(self.app, self.session_id, anchor.session_id, self.rows)
        except Exception as e:  # noqa: BLE001
            log(f"resize failed: {e!r}")

    async def close(self) -> None:
        if self.session_id:
            self.closing.add(self.session_id)
            await close(self.app, self.session_id)
        self.session_id = None
        self.anchor_id = None

    def adopt(self, session_id: str, anchor_id: str | None) -> None:
        self.session_id = session_id
        self.anchor_id = anchor_id or None
