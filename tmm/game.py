"""Pure typing game engine: no I/O, time (ms since epoch) is always passed in.

Stats are plain dicts so stats.json stays byte-compatible with the herdr
plugin's format (version 1, camelCase keys).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Literal

KeyClass = Literal["char", "backspace", "enter", "other"]
Stats = dict
GameEvent = dict
"""One of:
  {"kind": "milestone", "reason": "combo" | "level" | "record", "value": int}
  {"kind": "achievement", "id": str, "title": str, "description": str}
  {"kind": "combo_break", "combo": int}
"""

WPM_WINDOW_MS = 10_000
WPM_MIN_SPAN_MS = 2_000
WPM_QUALIFY_CHARS = 25  # chars needed in the window before a WPM counts toward records
ACCURACY_WINDOW = 200
HEAT_PER_CHAR = 0.07
HEAT_TAU_MS = 700

RANKS: list[tuple[int, str]] = [
    (0, "Hunt & Peck"),
    (3, "Home Row Hero"),
    (6, "Keyboard Warrior"),
    (10, "Combo Crusher"),
    (15, "Terminal Speedster"),
    (22, "Clackmaster"),
    (30, "Keyboard Demon"),
]


def jround(x: float) -> int:
    """JavaScript Math.round: halves round up (Python's round() is banker's)."""
    return math.floor(x + 0.5)


def empty_stats() -> Stats:
    return {
        "version": 1,
        "totalChars": 0,
        "totalKeys": 0,
        "totalXp": 0,
        "bestWpm": 0,
        "bestCombo": 0,
        "days": {},
        "achievements": {},
    }


def empty_day() -> dict:
    return {"chars": 0, "keys": 0, "xp": 0, "bestWpm": 0, "bestCombo": 0}


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level`."""
    return 100 * level * level


def level_for_xp(xp: float) -> int:
    return math.floor(math.sqrt(max(0, xp) / 100))


def rank_for(level: int) -> str:
    name = RANKS[0][1]
    for minimum, rank in RANKS:
        if level >= minimum:
            name = rank
    return name


def multiplier_for(combo: int, step: int = 25, maximum: float = 5) -> float:
    return min(max(1, maximum), 1 + math.floor(combo / max(1, step)) * 0.5)


def day_key(t: float) -> str:
    """Local calendar date of a ms timestamp, as YYYY-MM-DD."""
    return datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d")


def local_hour(t: float) -> int:
    return datetime.fromtimestamp(t / 1000).hour


def streak_days(stats: Stats, t: float) -> int:
    """Consecutive days (ending today or yesterday) with at least 500 chars."""
    days = stats.get("days", {})
    chars = lambda d: days.get(d.strftime("%Y-%m-%d"), {}).get("chars", 0)  # noqa: E731
    day = datetime.fromtimestamp(t / 1000).replace(hour=12, minute=0, second=0, microsecond=0)
    if chars(day) < 500:
        day -= timedelta(days=1)
    streak = 0
    while chars(day) >= 500:
        streak += 1
        day -= timedelta(days=1)
    return streak


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    description: str
    check: Callable[["Game", float], bool]


def _night_owl(g: "Game", t: float) -> bool:
    h = local_hour(t)
    return 2 <= h < 5 and g.night_chars >= 200


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_steps", "First Steps", "Type 100 characters", lambda g, t: g.stats["totalChars"] >= 100),
    Achievement("wpm_60", "Cruising", "Reach 60 WPM", lambda g, t: g.stats["bestWpm"] >= 60),
    Achievement("wpm_100", "Ton Up", "Reach 100 WPM", lambda g, t: g.stats["bestWpm"] >= 100),
    Achievement("wpm_140", "Ludicrous Speed", "Reach 140 WPM", lambda g, t: g.stats["bestWpm"] >= 140),
    Achievement("combo_100", "Combo Starter", "Hit a 100 combo", lambda g, t: g.stats["bestCombo"] >= 100),
    Achievement("combo_500", "Unbroken", "Hit a 500 combo", lambda g, t: g.stats["bestCombo"] >= 500),
    Achievement("combo_1000", "Flow State", "Hit a 1000 combo", lambda g, t: g.stats["bestCombo"] >= 1000),
    Achievement(
        "day_10k",
        "Marathon",
        "Type 10,000 characters in one day",
        lambda g, t: g.stats["days"].get(day_key(t), {}).get("chars", 0) >= 10_000,
    ),
    Achievement(
        "streak_7", "Habit Forming", "Type 500+ characters 7 days in a row", lambda g, t: streak_days(g.stats, t) >= 7
    ),
    Achievement("night_owl", "Night Owl", "Type 200 characters between 2 and 5 AM", _night_owl),
]


@dataclass
class GameConfig:
    combo_gap_ms: int = 1200  # max gap between keys before the combo breaks
    combo_milestone: int = 25  # a combo milestone fires every this many keys
    combo_step: int = 25  # every this many combo keys add x0.5 to the multiplier
    max_multiplier: float = 5


@dataclass
class Live:
    wpm: int = 0
    session_peak_wpm: int = 0
    combo: int = 0
    multiplier: float = 1
    accuracy: float = 1
    level: int = 0
    rank: str = RANKS[0][1]
    level_xp: int = 0  # XP earned inside the current level
    level_span: int = 100  # XP the current level needs
    heat: float = 0  # 0..1 typing intensity, drives the shake
    today: dict = field(default_factory=empty_day)
    idle_ms: float = math.inf

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        if math.isinf(d["idle_ms"]):
            d["idle_ms"] = None
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Live":
        live = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if live.idle_ms is None:
            live.idle_ms = math.inf
        return live


class Game:
    def __init__(self, stats: Stats | None = None, config: GameConfig | None = None):
        self.stats: Stats = stats if stats is not None else empty_stats()
        self.config = config or GameConfig()
        self.combo = 0
        self.session_peak_wpm = 0
        self.night_chars = 0
        self._char_times: deque[float] = deque()
        self._accuracy: deque[bool] = deque()
        self._last_key_at = 0.0
        self._heat = 0.0
        self._heat_at = 0.0
        self._xp_fraction = 0.0

    def key(self, cls: KeyClass, t: float) -> list[GameEvent]:
        events = self.tick(t)
        day = self.stats["days"].setdefault(day_key(t), empty_day())
        self.stats["totalKeys"] += 1
        day["keys"] += 1
        self._last_key_at = t

        if cls == "other":
            return events
        if cls == "backspace":
            self._push_accuracy(False)
            return events

        # char or enter: a productive keystroke.
        self._push_accuracy(True)
        self.combo += 1
        self._char_times.append(t)
        self.stats["totalChars"] += 1
        day["chars"] += 1
        if 2 <= local_hour(t) < 5:
            self.night_chars += 1

        self._decay_heat(t)
        self._heat = min(1.0, self._heat + HEAT_PER_CHAR)

        cfg = self.config
        level_before = level_for_xp(self.stats["totalXp"])
        self._xp_fraction += multiplier_for(self.combo, cfg.combo_step, cfg.max_multiplier) * self.accuracy()
        gained = math.floor(self._xp_fraction)
        self._xp_fraction -= gained
        self.stats["totalXp"] += gained
        day["xp"] += gained
        level_after = level_for_xp(self.stats["totalXp"])
        if level_after > level_before:
            events.append({"kind": "milestone", "reason": "level", "value": level_after})

        if self.combo % max(1, cfg.combo_milestone) == 0:
            events.append({"kind": "milestone", "reason": "combo", "value": self.combo})
        day["bestCombo"] = max(day["bestCombo"], self.combo)
        self.stats["bestCombo"] = max(self.stats["bestCombo"], self.combo)

        wpm = self.wpm(t)
        if self._qualifies(t):
            self.session_peak_wpm = max(self.session_peak_wpm, wpm)
            day["bestWpm"] = max(day["bestWpm"], wpm)
            best = self.stats["bestWpm"]
            if wpm > best:
                # Only celebrate records that move by at least 5 WPM to avoid spam.
                if wpm // 5 > best // 5 and best > 0:
                    events.append({"kind": "milestone", "reason": "record", "value": wpm})
                self.stats["bestWpm"] = wpm

        events.extend(self._check_achievements(t))
        return events

    def tick(self, t: float) -> list[GameEvent]:
        """Advance time without a key: breaks stale combos."""
        if self.combo > 0 and t - self._last_key_at > self.config.combo_gap_ms:
            combo = self.combo
            self.combo = 0
            return [{"kind": "combo_break", "combo": combo}]
        return []

    def wpm(self, t: float) -> int:
        times = self._char_times
        while times and t - times[0] > WPM_WINDOW_MS:
            times.popleft()
        n = len(times)
        if n == 0:
            return 0
        span = min(WPM_WINDOW_MS, max(WPM_MIN_SPAN_MS, t - times[0]))
        return jround((n / 5) * (60_000 / span))

    def accuracy(self) -> float:
        n = len(self._accuracy)
        return 1.0 if n == 0 else sum(self._accuracy) / n

    def live(self, t: float) -> Live:
        self._decay_heat(t)
        level = level_for_xp(self.stats["totalXp"])
        base = xp_for_level(level)
        cfg = self.config
        return Live(
            wpm=self.wpm(t),
            session_peak_wpm=self.session_peak_wpm,
            combo=self.combo,
            multiplier=multiplier_for(self.combo, cfg.combo_step, cfg.max_multiplier),
            accuracy=self.accuracy(),
            level=level,
            rank=rank_for(level),
            level_xp=self.stats["totalXp"] - base,
            level_span=xp_for_level(level + 1) - base,
            heat=self._heat,
            today=dict(self.stats["days"].get(day_key(t)) or empty_day()),
            idle_ms=t - self._last_key_at if self._last_key_at else math.inf,
        )

    def _qualifies(self, t: float) -> bool:
        self.wpm(t)
        return len(self._char_times) >= WPM_QUALIFY_CHARS

    def _push_accuracy(self, ok: bool) -> None:
        self._accuracy.append(ok)
        if len(self._accuracy) > ACCURACY_WINDOW:
            self._accuracy.popleft()

    def _decay_heat(self, t: float) -> None:
        if self._heat_at and t > self._heat_at:
            self._heat *= math.exp(-(t - self._heat_at) / HEAT_TAU_MS)
        self._heat_at = max(t, self._heat_at)

    def _check_achievements(self, t: float) -> list[GameEvent]:
        out = []
        unlocked = self.stats["achievements"]
        for a in ACHIEVEMENTS:
            if a.id in unlocked:
                continue
            if a.check(self, t):
                unlocked[a.id] = int(t)
                out.append({"kind": "achievement", "id": a.id, "title": a.title, "description": a.description})
        return out
