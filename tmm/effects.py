"""Session-local visual effects: tab color, background tint, milestone flash,
shaking badge and window shake.

Everything is written with LocalWriteOnlyProfile, so it changes only the live
session, never the saved profile. Each touched session is marked with
user.tmmTouched; restore() puts the original look back and clears the mark,
and recover() at startup restores any session a crashed run left behind
(from its saved profile, since its live look may still be tinted).

The pure helpers at the top are unit-tested; the Effects class needs iTerm2.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Callable

RGB = tuple[int, int, int]

TOUCHED_VAR = "user.tmmTouched"
MAX_TINT = 0.28  # strongest background blend at full typing heat
FLASH_BLEND = 0.55
LOG_MAX_BYTES = 256 * 1024
SYNC_INTERVAL = 0.05  # at most ~20 profile writes per second for tint and tab color

BG_PROPS = ("background_color", "background_color_light", "background_color_dark")
TAB_COLOR_PROPS = ("tab_color", "tab_color_light", "tab_color_dark")
USE_TAB_PROPS = ("use_tab_color", "use_tab_color_light", "use_tab_color_dark")


def blend_rgb(base: tuple[float, float, float], color: RGB, amount: float) -> RGB:
    return tuple(round(b + (c - b) * amount) for b, c in zip(base, color))  # type: ignore[return-value]


def quantize_tint(rgb: RGB | None, amount: float) -> tuple[RGB, float] | None:
    """Tint state in 0.05 steps (fine enough for a smooth fade); None means no tint."""
    if rgb is None:
        return None
    q = round(min(1.0, max(0.0, amount)) * 20) / 20
    return (tuple(rgb), q) if q > 0 else None  # type: ignore[return-value]


def shake_offsets(points: int, steps: int = 6, rng: Callable[[], float] = random.random) -> list[tuple[int, int]]:
    """Window offsets for one shake: alternating left/right, decaying, ending at rest."""
    out = []
    for i in range(steps):
        amp = points * (1 - i / steps)
        side = 1 if i % 2 == 0 else -1
        out.append((round(side * amp), round((rng() * 2 - 1) * amp / 2)))
    out.append((0, 0))
    return out


def badge_offsets(steps: int = 12, amp: float = 12, rng: Callable[[], float] = random.random) -> list[tuple[int, int]]:
    """Badge margin offsets for the shaking badge, settling down."""
    out = []
    for i in range(steps):
        a = amp * (1 - i / steps)
        out.append((round((rng() * 2 - 1) * a), round((rng() * 2 - 1) * a / 2)))
    return out


def log(msg: str) -> None:
    """To iTerm2's script console and to meter.log in the state dir."""
    print(f"typing-madness-meter: {msg}", flush=True)
    try:
        from .config import state_dir

        path = os.path.join(state_dir(), "meter.log")
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
            os.replace(path, path + ".1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


class SessionLook:
    """One session's original look, and writers for the effects on top of it."""

    def __init__(self, session, profile):
        import iterm2

        self.iterm2 = iterm2
        self.session = session
        self.bg = {p: getattr(profile, p, None) for p in BG_PROPS}
        self.tab_colors = {p: getattr(profile, p, None) for p in TAB_COLOR_PROPS}
        self.use_tab = {p: getattr(profile, p, None) for p in USE_TAB_PROPS}
        self.badge_text = getattr(profile, "badge_text", None) or ""
        self.badge_top = getattr(profile, "badge_top_margin", None)
        self.badge_right = getattr(profile, "badge_right_margin", None)

    def _color(self, base, rgb: RGB):
        return self.iterm2.Color(rgb[0], rgb[1], rgb[2], base.alpha, base.color_space)

    def _bg_props(self, p, tint: tuple[RGB, float] | None, blend: float = MAX_TINT) -> None:
        for prop, base in self.bg.items():
            if base is None:
                continue
            color = base
            if tint:
                rgb, amount = tint
                color = self._color(base, blend_rgb((base.red, base.green, base.blue), rgb, amount * blend))
            getattr(p, f"set_{prop}")(color)

    def _tab_props(self, p, rgb: RGB | None) -> None:
        if rgb is None:
            for prop, value in {**self.tab_colors, **self.use_tab}.items():
                if value is not None:
                    getattr(p, f"set_{prop}")(value)
            return
        color = self.iterm2.Color(rgb[0], rgb[1], rgb[2])
        for prop in TAB_COLOR_PROPS:
            getattr(p, f"set_{prop}")(color)
        for prop in USE_TAB_PROPS:
            getattr(p, f"set_{prop}")(True)

    def _badge_props(self, p, text: str | None = None, dx: int = 0, dy: int = 0) -> None:
        p.set_badge_text(self.badge_text if text is None else text)
        if self.badge_top is not None:
            p.set_badge_top_margin(max(0, self.badge_top + dy))
        if self.badge_right is not None:
            p.set_badge_right_margin(max(0, self.badge_right + dx))

    async def apply(self, tint: tuple[RGB, float] | None, tab: RGB | None, bg: bool = True) -> None:
        p = self.iterm2.LocalWriteOnlyProfile()
        if bg:
            self._bg_props(p, tint)
        self._tab_props(p, tab)
        await self.session.async_set_profile_properties(p)

    async def flash(self, rgb: RGB) -> None:
        p = self.iterm2.LocalWriteOnlyProfile()
        self._bg_props(p, (rgb, 1.0), FLASH_BLEND)
        await self.session.async_set_profile_properties(p)

    async def badge(self, text: str | None = None, dx: int = 0, dy: int = 0) -> None:
        """Show `text` offset by (dx, dy); text=None restores the original badge."""
        p = self.iterm2.LocalWriteOnlyProfile()
        self._badge_props(p, text, dx, dy)
        await self.session.async_set_profile_properties(p)

    async def restore(self) -> None:
        p = self.iterm2.LocalWriteOnlyProfile()
        self._bg_props(p, None)
        self._tab_props(p, None)
        self._badge_props(p)
        await self.session.async_set_profile_properties(p)


async def saved_profile(connection, session):
    """The session's profile as saved in Settings, ignoring live changes."""
    import iterm2

    live = await session.async_get_profile()
    guid = live.original_guid or live.guid
    try:
        partials = await iterm2.PartialProfile.async_query(connection, guids=[guid])
        if partials:
            return await partials[0].async_get_full_profile()
    except Exception:  # noqa: BLE001
        pass
    return live


async def recover(connection, app) -> int:
    """Restore sessions a previous run left touched. Returns how many."""
    count = 0
    for window in app.terminal_windows:
        for tab in window.tabs:
            for session in tab.sessions:
                try:
                    if not await session.async_get_variable(TOUCHED_VAR):
                        continue
                    await SessionLook(session, await saved_profile(connection, session)).restore()
                    await session.async_set_variable(TOUCHED_VAR, "")
                    count += 1
                except Exception as e:  # noqa: BLE001
                    log(f"recover {session.session_id}: {e!r}")
    return count


class Effects:
    """Effects for one meter. Tint and tab color are desired state that a
    worker syncs to whichever session is the target; the previous target is
    restored when the target moves."""

    def __init__(self, connection, app):
        self.connection = connection
        self.app = app
        self.target: str | None = None
        self._looks: dict[str, SessionLook] = {}
        self._want_tint: tuple[RGB, float] | None = None
        self._want_tab: RGB | None = None
        self._applied: dict[str, object] = {}  # session id -> (tint, tab) last written
        self._flashing: set[str] = set()
        self._dirty = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self._badge_task: asyncio.Task | None = None
        self._shaking = False

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.ensure_future(self._run())

    # ---------------------------------------------------------------- desired state

    def set_target(self, session_id: str | None) -> None:
        if session_id != self.target:
            self.target = session_id
            self._dirty.set()

    def tint(self, rgb: RGB | None, amount: float) -> None:
        want = quantize_tint(rgb, amount)
        if want != self._want_tint:
            self._want_tint = want
            self._dirty.set()

    def tab(self, rgb: RGB | None) -> None:
        rgb = tuple(rgb) if rgb else None  # type: ignore[assignment]
        if rgb != self._want_tab:
            self._want_tab = rgb
            self._dirty.set()

    # ---------------------------------------------------------------- one-shots

    def flash(self, rgb: RGB, ms: int = 120) -> None:
        if self.target and self.target not in self._flashing:
            asyncio.ensure_future(self._flash(self.target, rgb, ms))

    def badge(self, text: str, ms: int = 2000) -> None:
        if not self.target:
            return
        if self._badge_task and not self._badge_task.done():
            self._badge_task.cancel()
        self._badge_task = asyncio.ensure_future(self._badge(self.target, text[:40], ms))

    def shake(self, points: int) -> None:
        if self.target and not self._shaking and points > 0:
            asyncio.ensure_future(self._shake(self.target, points))

    # ---------------------------------------------------------------- teardown

    async def restore_all(self) -> None:
        """Put every touched session back the way it was."""
        if self._worker:
            self._worker.cancel()
        if self._badge_task and not self._badge_task.done():
            self._badge_task.cancel()
        self.target = None
        self._want_tint = self._want_tab = None
        for sid, look in list(self._looks.items()):
            try:
                await look.restore()
                await look.session.async_set_variable(TOUCHED_VAR, "")
            except Exception:  # noqa: BLE001
                pass  # session already gone
        self._looks.clear()
        self._applied.clear()

    # ---------------------------------------------------------------- internals

    async def _look(self, sid: str) -> SessionLook | None:
        if sid in self._looks:
            return self._looks[sid]
        session = self.app.get_session_by_id(sid)
        if session is None:
            return None
        # A session still marked from a crashed run may have a tinted live
        # look, so its originals come from the saved profile.
        if await session.async_get_variable(TOUCHED_VAR):
            profile = await saved_profile(self.connection, session)
        else:
            profile = await session.async_get_profile()
        look = SessionLook(session, profile)
        self._looks[sid] = look
        await session.async_set_variable(TOUCHED_VAR, "1")
        return look

    async def _run(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self._sync()
            except Exception as e:  # noqa: BLE001
                log(f"effects: {e!r}")
            await asyncio.sleep(SYNC_INTERVAL)

    async def _sync(self) -> None:
        sids = set(self._applied)
        if self.target:
            sids.add(self.target)
        for sid in sids:
            want = (self._want_tint, self._want_tab) if sid == self.target else (None, None)
            if self._applied.get(sid, (None, None)) == want:
                continue
            look = await self._look(sid)
            if look is None:
                self._applied.pop(sid, None)
                self._looks.pop(sid, None)
                continue
            try:
                await look.apply(want[0], want[1], bg=sid not in self._flashing)
            except Exception:  # noqa: BLE001
                self._applied.pop(sid, None)
                self._looks.pop(sid, None)
                continue
            if want == (None, None):
                self._applied.pop(sid, None)
            else:
                self._applied[sid] = want

    async def _flash(self, sid: str, rgb: RGB, ms: int) -> None:
        self._flashing.add(sid)
        try:
            look = await self._look(sid)
            if look:
                await look.flash(rgb)
                await asyncio.sleep(ms / 1000)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._flashing.discard(sid)
            self._applied[sid] = "stale"  # force the worker to rewrite the background
            self._dirty.set()

    async def _badge(self, sid: str, text: str, ms: int) -> None:
        look = await self._look(sid)
        if look is None:
            return
        try:
            # Shake for the first ~400ms, settling down, then hold.
            for dx, dy in badge_offsets():
                await look.badge(text, dx, dy)
                await asyncio.sleep(0.033)
            await look.badge(text)
            await asyncio.sleep(max(0, ms / 1000 - 0.4))
        except asyncio.CancelledError:
            raise  # a newer badge replaces this one and restores it later
        except Exception:  # noqa: BLE001
            return
        try:
            await look.badge()
        except Exception:  # noqa: BLE001
            pass

    async def _shake(self, sid: str, points: int) -> None:
        session = self.app.get_session_by_id(sid)
        window = self.app.get_window_and_tab_for_session(session)[0] if session else None
        if window is None:
            return
        self._shaking = True
        try:
            if await window.async_get_fullscreen():
                return
            import iterm2

            frame = await window.async_get_frame()
            x, y = frame.origin.x, frame.origin.y
            try:
                for dx, dy in shake_offsets(points):
                    moved = iterm2.Frame(iterm2.Point(x + dx, y + dy), frame.size)
                    await window.async_set_frame(moved)
                    await asyncio.sleep(0.027)
            finally:
                await window.async_set_frame(frame)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._shaking = False
