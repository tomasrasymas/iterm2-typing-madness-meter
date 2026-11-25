"""The Typing Madness Meter service: an iTerm2 AutoLaunch script.

It owns the keystroke monitor, the game, the effects, the meter pane and the
socket its panes talk over. Script functions (bind them in Settings › Keys ›
Key Bindings › Invoke Script Function):

  tmm_toggle()  open the meter under the active session, or close it
  tmm_stats()   show stats in a temporary split
  tmm_reset()   clear all stats
  tmm_demo()    play the self-running demo in a new tab
"""

from __future__ import annotations

import asyncio
import signal
import time

import iterm2

from . import panes
from .classify import RepeatFilter, classify
from .config import load_config
from .effects import Effects, log, recover
from .feed import Client, Feed, socket_alive
from .game import Game, empty_stats
from .meter import Meter, game_config, hud_focused_message, now_ms
from .panes import ANCHOR_VAR, ROLE_VAR, MeterPane, focused_session
from .render import fg, seg
from .stats_view import stats_html
from .store import load_state, load_stats, save_state, save_stats, socket_path, stats_path
from .tiers import set_tier_colors, set_tier_wpm

FRAME_S = 0.033
SAVE_EVERY_MS = 5000
FOLLOW_MIN_INTERVAL_MS = 800
LIVE_VAR = "user.typingMadness"
STATUS_ID = "dev.typing-madness-meter.status"
KEY_CLASSES = {"char", "backspace", "enter", "other"}

MODIFIER_NAMES = {
    iterm2.Modifier.COMMAND: "command",
    iterm2.Modifier.CONTROL: "control",
    iterm2.Modifier.OPTION: "option",
    iterm2.Modifier.SHIFT: "shift",
}


def keystroke_parts(ks) -> tuple[str, int, set[str]]:
    """(characters, keycode, modifier names), tolerant of codes the enums don't know."""
    try:
        code = ks.keycode.value
    except ValueError:
        code = getattr(ks, "_Keystroke__key_code", -1)
    try:
        mods = {MODIFIER_NAMES[m] for m in ks.modifiers if m in MODIFIER_NAMES}
    except ValueError:
        mods = set()
    return ks.characters or "", code, mods


class Demo:
    """A running demo: a self-typing editor tab, its own meter pane and a
    throwaway meter whose stats are never saved."""

    def __init__(self, daemon: "Daemon", editor_id: str, return_id: str | None):
        self.editor_id = editor_id
        self.return_id = return_id
        self.effects = Effects(daemon.connection, daemon.app)
        stats = {**empty_stats(), "totalXp": 860}  # a few XP short of level 3, so a level-up shows early
        self.meter = Meter(
            daemon.cfg,
            Game(stats, game_config(daemon.cfg)),
            self.effects,
            toast=lambda title, body: daemon.feed.broadcast("demo", {"type": "toast", "title": title, "body": body}),
        )
        self.pane = MeterPane(daemon.connection, daemon.app, "demo", daemon.cfg.hudHeight)
        self.finishing = False

    def sessions(self) -> set[str]:
        return {s for s in (self.editor_id, self.pane.session_id) if s}


class Daemon:
    def __init__(self, connection, app):
        self.connection = connection
        self.app = app
        self.cfg = load_config()
        set_tier_wpm(self.cfg.tierWpm)
        set_tier_colors(self.cfg.tierColors)
        self.stats_file = self.cfg.statsFile
        self.effects = Effects(connection, app)
        self.meter = Meter(
            self.cfg,
            Game(load_stats(self.stats_file), game_config(self.cfg)),
            self.effects,
            toast=lambda title, body: self.feed.broadcast("hud", {"type": "toast", "title": title, "body": body}),
        )
        self.socket = socket_path()
        self.feed = Feed(self.socket, self.on_message)
        self.pane = MeterPane(connection, app, "hud", self.cfg.hudHeight)
        self.enabled = False
        self.demo: Demo | None = None
        self.stats_panes: set[str] = set()
        self.dead: set[str] = set()
        self.repeat = RepeatFilter()
        self._busy = False  # opening / moving / closing the meter pane
        self._last_follow = 0.0
        self._last_save = now_ms()
        self._live_var: tuple[str | None, str] = (None, "")

    # ---------------------------------------------------------------- startup

    async def start(self) -> None:
        restored = await recover(self.connection, self.app)
        if restored:
            log(f"restored {restored} session(s) a previous run left colored")
        await self.feed.start()
        await self.adopt_or_close_leftovers()
        if not self.enabled and load_state().get("enabled") and self.cfg.autoOpen:
            # Open now if there is a session; otherwise the first keystroke opens it.
            self.enabled = True
            self.effects.start()
            target = self.typing_target()
            if target is not None:
                await self.open_pane(target)
        self.save_state()

    async def adopt_or_close_leftovers(self) -> None:
        """Meter panes from a previous run reconnect by themselves: adopt one if
        the meter was on, close the rest."""
        want = load_state().get("enabled") and self.cfg.autoOpen
        for session in list(panes.all_sessions(self.app)):
            try:
                role = await session.async_get_variable(ROLE_VAR)
            except Exception:  # noqa: BLE001
                continue
            if not role:
                continue
            if role == "hud" and want and not self.pane.session_id:
                anchor = await session.async_get_variable(ANCHOR_VAR)
                self.pane.adopt(session.session_id, anchor if self.alive(anchor) else None)
                self.enabled = True
                self.effects.start()
                log("adopted the open meter pane")
            else:
                await panes.close(self.app, session.session_id)

    # ---------------------------------------------------------------- state

    def alive(self, session_id: str | None) -> bool:
        return bool(session_id) and session_id not in self.dead and self.app.get_session_by_id(session_id) is not None

    def own_sessions(self) -> set[str]:
        """Sessions whose keys never count: meter, demo and stats panes."""
        own = set(self.stats_panes)
        if self.pane.session_id:
            own.add(self.pane.session_id)
        if self.demo:
            own |= self.demo.sessions()
        return own

    def typing_target(self):
        """The active session, unless it is one of ours."""
        session = focused_session(self.app)
        if session is None or session.session_id in self.own_sessions():
            return None
        return session

    def save_state(self) -> None:
        try:
            save_state({"enabled": self.enabled})
        except OSError as e:
            log(f"could not save state: {e!r}")

    def save_stats(self) -> None:
        try:
            save_stats(self.meter.game.stats, self.stats_file)
            self.meter.dirty = False
        except OSError as e:
            log(f"could not save stats: {e!r}")

    # ---------------------------------------------------------------- on / off

    async def toggle(self) -> None:
        if self.enabled:
            await self.disable("toggled off")
        else:
            await self.enable()

    async def enable(self) -> None:
        target = self.typing_target()
        self.enabled = True
        self.save_state()
        self.effects.start()
        if target is not None:
            await self.open_pane(target)
        target_desc = target.session_id[:8] if target else "first session you type in"
        log(f"meter on (pane under {target_desc})")

    async def disable(self, reason: str) -> None:
        self.enabled = False
        self.save_state()
        self._busy = True
        try:
            await self.pane.close()
        finally:
            self._busy = False
        await self.effects.restore_all()
        await self.set_live_var(None, "")
        self.save_stats()
        log(f"meter off: {reason}")

    async def open_pane(self, target) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await self.pane.open(target, self.socket)
        except Exception as e:  # noqa: BLE001
            log(f"could not open the meter pane: {e!r}")
        finally:
            self._busy = False

    async def follow(self, target) -> None:
        """Move the meter pane under the session being typed in. Triggered by
        typing, not focus, so clicking around never rearranges anything."""
        t = now_ms()
        if self._busy or t - self._last_follow < FOLLOW_MIN_INTERVAL_MS:
            return
        self._busy = True
        self._last_follow = t
        try:
            await self.pane.move_under(target, self.socket)
        except Exception as e:  # noqa: BLE001
            log(f"follow failed: {e!r}")
        finally:
            self._busy = False

    # ---------------------------------------------------------------- keys

    async def keystroke_loop(self) -> None:
        advanced = iterm2.capabilities.supports_advanced_key_notifications(self.connection)
        if not advanced:
            log("this iTerm2 has no advanced key notifications: held-key autorepeat will count")
        async with iterm2.KeystrokeMonitor(self.connection, advanced=advanced) as monitor:
            while True:
                ks = await monitor.async_get()
                try:
                    self.on_keystroke(ks)
                except Exception as e:  # noqa: BLE001
                    log(f"keystroke: {e!r}")

    def on_keystroke(self, ks) -> None:
        characters, code, mods = keystroke_parts(ks)
        action = ks.action
        if action == iterm2.Keystroke.Action.KEY_UP:
            self.repeat.key_up(code)
            return
        if action == iterm2.Keystroke.Action.FLAGS_CHANGED:
            return
        if action == iterm2.Keystroke.Action.KEY_DOWN and not self.repeat.key_down(code):
            return  # autorepeat
        cls = classify(characters, code, mods)
        if cls is None or not self.enabled:
            return
        target = self.typing_target()
        if target is None:
            return
        sid = target.session_id
        if not self.alive(self.pane.session_id):
            if not self._busy:
                asyncio.ensure_future(self.open_pane(target))
        elif self.cfg.follow and sid != self.pane.anchor_id:
            asyncio.ensure_future(self.follow(target))
        self.meter.key(cls, now_ms(), sid)

    # ---------------------------------------------------------------- sessions ending

    async def termination_loop(self) -> None:
        async with iterm2.SessionTerminationMonitor(self.connection) as monitor:
            while True:
                sid = await monitor.async_get()
                self.dead.add(sid)
                self.stats_panes.discard(sid)
                if sid in (self.pane.session_id, self.pane.anchor_id):
                    asyncio.ensure_future(self.check_pane())
                if self.demo and sid in self.demo.sessions():
                    asyncio.ensure_future(self.finish_demo(0))

    async def check_pane(self) -> None:
        """After the meter pane or its anchor ended. Closing a tab or window
        ends both: reopen under the active session. Closing just the meter
        pane turns the meter off. Closing the pane it sits under closes the
        meter too."""
        await asyncio.sleep(0.3)  # both sessions of a closed tab end together
        if not self.enabled or self._busy:
            return
        pane_alive = self.alive(self.pane.session_id)
        anchor = self.pane.anchor_id
        anchor_alive = anchor is None or self.alive(anchor)
        if pane_alive and anchor_alive:
            return
        if not pane_alive and not anchor_alive:
            self.pane.session_id = self.pane.anchor_id = None
            target = self.typing_target()
            log("the meter's tab closed; reopening it under the active session")
            if target is not None:
                await self.open_pane(target)
            return
        if not pane_alive:
            await self.disable("the meter pane was closed")
        else:
            await self.disable("the session above the meter was closed")

    # ---------------------------------------------------------------- socket

    async def on_message(self, client: Client, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "hello" and client.role == "hud":
            await self.on_hud_hello(client)
        elif kind == "quit" and client.role == "hud":
            if self.enabled:
                await self.disable(f"{msg.get('reason', 'q')} pressed in the meter pane")
        elif kind == "quit" and client.role == "demo":
            await self.finish_demo(0)
        elif client.role == "typer" and self.demo:
            if kind == "key" and msg.get("c") in KEY_CLASSES:
                self.demo.meter.key(msg["c"], now_ms(), self.demo.editor_id)
            elif kind == "done":
                self.demo.meter.show([seg(" ✓ demo complete", fg(114, True))], 3000)
                asyncio.ensure_future(self.finish_demo(2.5))

    async def on_hud_hello(self, client: Client) -> None:
        """A meter pane connected. Ours, or one a previous run left behind
        (windows iTerm2 restored after this service started): adopt it if we
        have none, else close it, so there is never more than one."""
        if self._busy or not client.session or client.session == self.pane.session_id:
            return
        if self.enabled and not self.alive(self.pane.session_id) and self.alive(client.session):
            session = self.app.get_session_by_id(client.session)
            anchor = await session.async_get_variable(ANCHOR_VAR)
            self.pane.adopt(client.session, anchor if self.alive(anchor) else None)
            log("adopted a reconnected meter pane")
        else:
            await panes.close(self.app, client.session)

    # ---------------------------------------------------------------- frames

    async def frame_loop(self) -> None:
        while True:
            await asyncio.sleep(FRAME_S)
            try:
                await self.frame()
            except Exception as e:  # noqa: BLE001
                log(f"frame: {e!r}")

    async def frame(self) -> None:
        t = now_ms()
        if self.enabled:
            focused = focused_session(self.app)
            message = hud_focused_message() if focused and focused.session_id == self.pane.session_id else None
            self.feed.broadcast("hud", self.meter.tick(t, message))
            if self.cfg.statusBar:
                await self.set_live_var(self.meter.typed_session, self.meter.live_text)
        if self.demo:
            self.feed.broadcast("demo", self.demo.meter.tick(t))
        if self.meter.dirty and t - self._last_save > SAVE_EVERY_MS:
            self._last_save = t
            self.save_stats()

    async def set_live_var(self, session_id: str | None, text: str) -> None:
        """user.typingMadness on the typed session, for \\(user.typingMadness) in titles."""
        if (session_id, text) == self._live_var:
            return
        old_sid, _ = self._live_var
        self._live_var = (session_id, text)
        for sid, value in ((old_sid, ""), (session_id, text)) if old_sid != session_id else ((session_id, text),):
            session = self.app.get_session_by_id(sid) if sid else None
            if session is not None:
                try:
                    await session.async_set_variable(LIVE_VAR, value)
                except Exception:  # noqa: BLE001
                    pass

    # ---------------------------------------------------------------- stats, reset

    async def show_stats(self) -> None:
        self.save_stats()
        anchor = focused_session(self.app)
        if anchor is None:
            return
        command = panes.script_command("stats_pane.py", stats_path(self.stats_file))
        session = await panes.split_under(self.app, anchor, command, "stats", "Typing Madness Meter · stats")
        if session is None:
            return
        self.stats_panes.add(session.session_id)
        try:
            await panes.set_rows(self.app, session.session_id, anchor.session_id, 26)
        except Exception:  # noqa: BLE001
            pass
        await session.async_activate(select_tab=True, order_window_front=False)

    def reset(self) -> None:
        self.meter.game.stats = empty_stats()
        self.meter.game.session_peak_wpm = 0
        self.save_stats()
        self.meter.show([seg(" stats reset", "2")], 2000)
        log("stats reset")

    def popover_html(self) -> str:
        return stats_html(self.meter.game.stats, now_ms())

    # ---------------------------------------------------------------- demo

    async def start_demo(self) -> None:
        if self.demo:
            editor = self.app.get_session_by_id(self.demo.editor_id)
            if editor:
                await editor.async_activate()
            return
        back = focused_session(self.app)
        command = panes.script_command("demo_typer.py", self.socket)
        profile = panes.pane_profile(command)
        window = self.app.current_terminal_window
        if window is None:
            window = await iterm2.Window.async_create(self.connection, profile_customizations=profile)
            tab = window.current_tab if window else None
        else:
            tab = await window.async_create_tab(profile_customizations=profile)
        if tab is None:
            log("could not open the demo tab")
            return
        editor = tab.current_session
        await editor.async_set_variable(ROLE_VAR, "demo-editor")
        await tab.async_set_title("Typing Madness Meter · demo")
        self.demo = Demo(self, editor.session_id, back.session_id if back else None)
        self.demo.effects.start()
        self.demo.effects.set_target(editor.session_id)
        await self.demo.pane.open(editor, self.socket)

    async def finish_demo(self, delay: float) -> None:
        demo = self.demo
        if demo is None or demo.finishing:
            return
        demo.finishing = True
        await asyncio.sleep(delay)
        await demo.effects.restore_all()
        await demo.pane.close()
        await panes.close(self.app, demo.editor_id)
        if self.demo is demo:
            self.demo = None
        back = self.app.get_session_by_id(demo.return_id) if demo.return_id else None
        if back is not None:
            try:
                await back.async_activate()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- shutdown

    async def shutdown(self) -> None:
        self.save_stats()
        await self.effects.restore_all()
        if self.demo:
            await self.demo.effects.restore_all()
        self.feed.close()


async def register_functions(connection, daemon: Daemon) -> None:
    @iterm2.RPC
    async def tmm_toggle():
        await daemon.toggle()

    @iterm2.RPC
    async def tmm_stats():
        await daemon.show_stats()

    @iterm2.RPC
    async def tmm_reset():
        daemon.reset()

    @iterm2.RPC
    async def tmm_demo():
        await daemon.start_demo()

    for fn in (tmm_toggle, tmm_stats, tmm_reset, tmm_demo):
        await fn.async_register(connection)

    if not daemon.cfg.statusBar:
        return
    component = iterm2.StatusBarComponent(
        short_description="Typing Madness Meter",
        detailed_description="Live WPM, combo and level from the Typing Madness Meter. Click it for your stats.",
        knobs=[],
        exemplar="⌨ 87 wpm · 120 combo · LV 7",
        update_cadence=0.5,
        identifier=STATUS_ID,
    )

    @iterm2.StatusBarRPC
    async def tmm_status(knobs):
        return daemon.meter.status_text(now_ms(), daemon.enabled)

    @iterm2.RPC
    async def tmm_status_click(session_id):
        await component.async_open_popover(session_id, daemon.popover_html(), iterm2.Size(440, 480))

    await component.async_register(connection, tmm_status, onclick=tmm_status_click)


async def main(connection) -> None:
    path = socket_path()
    if socket_alive(path):
        log(f"already running (socket {path}); exiting")
        return
    app = await iterm2.async_get_app(connection)
    daemon = Daemon(connection, app)
    await daemon.start()
    await register_functions(connection, daemon)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        loop.add_signal_handler(sig, stop.set)

    tasks = [
        asyncio.ensure_future(daemon.keystroke_loop()),
        asyncio.ensure_future(daemon.termination_loop()),
        asyncio.ensure_future(daemon.frame_loop()),
    ]
    log(f"running (socket {path}, stats {stats_path(daemon.stats_file)})")
    stopping = asyncio.ensure_future(stop.wait())
    done, _ = await asyncio.wait([*tasks, stopping], return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        if task is not stopping and task.exception():
            log(f"stopped: {task.exception()!r}")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await daemon.shutdown()


def run() -> None:
    started = time.time()
    try:
        iterm2.run_until_complete(main, retry=False)
    finally:
        log(f"exited after {time.time() - started:.0f}s")


if __name__ == "__main__":
    run()
