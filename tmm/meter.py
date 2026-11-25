"""One meter: a game, the effects it drives and the view its HUD shows.

The daemon runs the real meter and, during a demo, a second throwaway one.
No iTerm2 imports here: effects are passed in, so this is unit-testable.
"""

from __future__ import annotations

import math
import random
import time
from typing import Callable, Protocol

from .config import Config
from .game import Game, GameConfig, GameEvent, KeyClass
from .render import DIM, Line, fg, seg
from .tiers import color_at, tier_index, tier_position, tint_amount

FLASH_RGB = (255, 40, 70)
LIVE_TEXT_INTERVAL_MS = 500
LIVE_TEXT_TTL_MS = 4000
COOL_START_MS = 1000  # pause this long and the colors start cooling down
WARM_UP_MS = 150  # time constant for heating up while typing
GLOW_OFF = 0.04  # below this glow, tab color and tint are off


def approach(current: float, target: float, dt_ms: float, rise_ms: float, fall_ms: float) -> float:
    """Exponential smoothing toward `target`, with separate rise and fall speeds."""
    tau = rise_ms if target > current else fall_ms
    return target + (current - target) * math.exp(-max(0.0, dt_ms) / max(1.0, tau))


class EffectsLike(Protocol):
    def set_target(self, session_id: str | None) -> None: ...
    def tint(self, rgb, amount: float) -> None: ...
    def tab(self, rgb) -> None: ...
    def flash(self, rgb, ms: int = 120) -> None: ...
    def badge(self, text: str, ms: int = 2000) -> None: ...
    def shake(self, points: int) -> None: ...


def now_ms() -> float:
    return time.time() * 1000


def game_config(cfg: Config) -> GameConfig:
    return GameConfig(
        combo_gap_ms=cfg.comboGapMs,
        combo_milestone=int(cfg.comboMilestone),
        combo_step=int(cfg.comboStep),
        max_multiplier=cfg.maxMultiplier,
    )


def milestone_badge(ev: GameEvent) -> str:
    if ev["reason"] == "combo":
        return f"COMBO {ev['value']}!"
    if ev["reason"] == "level":
        return f"LEVEL {ev['value']}"
    return f"{ev['value']} WPM!"


class Meter:
    def __init__(
        self,
        cfg: Config,
        game: Game,
        effects: EffectsLike,
        toast: Callable[[str, str], None] = lambda title, body: None,
        rng: Callable[[], float] = random.random,
    ):
        self.cfg = cfg
        self.game = game
        self.effects = effects
        self.toast = toast
        self.rng = rng
        self.typed_session: str | None = None
        self.dirty = False  # stats changed since the last save
        self._notice: tuple[Line, float] | None = None
        self._burst = 0.0
        self._frame = 0
        self._glow = 0.0  # 0..1 smoothed strength of the speed colors
        self._position = 1.0  # smoothed position on the tier color scale (1..4)
        self._colors_at = 0.0
        self._live_text_at = 0.0
        self.live_text = ""  # "87 wpm · 120 combo" while typing, else ""

    # ---------------------------------------------------------------- input

    def key(self, cls: KeyClass, t: float, session_id: str | None) -> None:
        self.typed_session = session_id
        self.effects.set_target(session_id)
        self.handle(self.game.key(cls, t), t)
        self.dirty = True
        if cls in ("char", "enter") and t - self._live_text_at >= LIVE_TEXT_INTERVAL_MS:
            self._live_text_at = t
            live = self.game.live(t)
            self.live_text = f"{live.wpm} wpm · {live.combo} combo"

    def show(self, line: Line, ms: float) -> None:
        self._notice = (line, now_ms() + ms)

    def celebrate(self, badge: str) -> None:
        self._burst = 3
        if self.cfg.shake:
            self.effects.shake(int(self.cfg.shakePoints))
        if self.cfg.flash:
            self.effects.flash(FLASH_RGB)
        if self.cfg.milestoneBadge:
            self.effects.badge(badge)

    def handle(self, events: list[GameEvent], t: float) -> None:
        cfg = self.cfg
        for ev in events:
            kind = ev["kind"]
            if kind == "milestone":
                self.celebrate(milestone_badge(ev))
                if ev["reason"] == "combo":
                    self.show([seg(f" ⚑ COMBO {ev['value']}! ", fg(201, True))], 1500)
                elif ev["reason"] == "level":
                    rank = self.game.live(t).rank
                    self.show([seg(f" ▲ LEVEL UP → {ev['value']} · {rank}", fg(141, True))], 3000)
                    if cfg.toasts:
                        self.toast(f"Level {ev['value']}", rank)
                else:
                    self.show([seg(f" ★ NEW RECORD {ev['value']} WPM", fg(220, True))], 3000)
                    if cfg.toasts:
                        self.toast(f"New record: {ev['value']} WPM", "")
            elif kind == "achievement":
                self.celebrate(f"★ {ev['title']}")
                self.show(
                    [seg(" ★ ACHIEVEMENT ", fg(220, True)), seg(f"{ev['title']} — {ev['description']}", fg(220))],
                    4000,
                )
                if cfg.toasts:
                    self.toast(f"Achievement: {ev['title']}", ev["description"])
            elif kind == "combo_break" and ev["combo"] >= 30:
                self.show([seg(f" ✗ combo broken at {ev['combo']}", fg(203))], 1500)

    # ---------------------------------------------------------------- frame

    def tick(self, t: float, message: Line | None = None) -> dict:
        """Advance one frame; returns the view to send to this meter's HUDs."""
        self.handle(self.game.tick(t), t)
        self._frame += 1
        live = self.game.live(t)
        if self._frame % 3 == 0:
            self.speed_colors(live.wpm, live.heat, live.idle_ms, t)
        if live.idle_ms > LIVE_TEXT_TTL_MS:
            self.live_text = ""

        amp = min(3.0, live.heat * 1.6 + self._burst)
        self._burst *= 0.88
        if self._burst < 0.05:
            self._burst = 0
        dx = round((self.rng() * 2 - 1) * amp)
        dy = 1 if amp > 1.2 and self.rng() < 0.3 else 0

        if message is None and self._notice and self._notice[1] > t:
            message = self._notice[0]
        return {
            "type": "view",
            "live": live.to_json(),
            "message": message,
            "shake": [dx, dy],
            "frame": self._frame if amp > 0.05 else 0,
        }

    def speed_colors(self, wpm: int, heat: float, idle_ms: float, t: float) -> None:
        """Tab color and background tint follow WPM. They warm up quickly while
        you type and cool down smoothly when you slow down or stop: the color
        slides back through the tiers (red, orange, yellow, green) while it
        fades out over about cfg.cooldownMs."""
        dt = t - self._colors_at if self._colors_at else 0.0
        self._colors_at = t
        cool_ms = max(1.0, float(self.cfg.cooldownMs)) / 4  # ~98% faded after cooldownMs
        if idle_ms > COOL_START_MS or tier_index(wpm) == 0:
            target_glow, target_pos = 0.0, 1.0
        else:
            target_glow, target_pos = tint_amount(wpm, heat), tier_position(wpm)
        self._glow = approach(self._glow, target_glow, dt, WARM_UP_MS, cool_ms)
        self._position = approach(self._position, target_pos, dt, WARM_UP_MS, cool_ms)

        on = self._glow >= GLOW_OFF
        rgb = color_at(round(self._position * 20) / 20) if on else None
        self.effects.tab(rgb if self.cfg.tabColor else None)
        self.effects.tint(rgb if self.cfg.tint else None, self._glow)

    def status_text(self, t: float, on: bool) -> str:
        """Text for the status bar component."""
        live = self.game.live(t)
        if on and live.idle_ms <= LIVE_TEXT_TTL_MS:
            return f"⌨ {live.wpm} wpm · {live.combo} combo · LV {live.level}"
        suffix = "" if on else " (off)"
        return f"⌨ LV {live.level} · {live.rank}{suffix}"


def hud_focused_message() -> Line:
    return [seg(" Typing Madness Meter focused: keys typed here don't count (q closes it)", DIM)]
