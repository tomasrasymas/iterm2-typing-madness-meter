"""Speed tiers shared by the meter's WPM color, the tab color and the
background tint. Tier 0 = "not fast yet" (no effect); tiers 1-4 are green,
yellow, orange and red by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RGB = tuple[int, int, int]

DEFAULT_TIER_WPM = [25, 45, 65, 85]  # minimum WPM for tiers 1..4
DEFAULT_TIER_COLORS = ["#5fd787", "#ffd75f", "#ff8700", "#ff3030"]  # colors for tiers 1..4
HYSTERESIS_WPM = 4

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class TierColor:
    hex: str | None
    rgb: RGB | None


def hex_to_rgb(hex_color: str) -> RGB:
    n = int(hex_color[1:], 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def _build_colors(hexes: list[str]) -> list[TierColor]:
    return [TierColor(None, None)] + [TierColor(h.lower(), hex_to_rgb(h)) for h in hexes]


_tier_wpm: list[float] = list(DEFAULT_TIER_WPM)
_colors: list[TierColor] = _build_colors(DEFAULT_TIER_COLORS)


def set_tier_wpm(mins: object) -> None:
    """Override the thresholds (from config). Ignores malformed input."""
    global _tier_wpm
    if (
        isinstance(mins, list)
        and len(mins) == 4
        and all(isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0 for n in mins)
        and all(mins[i] > mins[i - 1] for i in range(1, 4))
    ):
        _tier_wpm = list(mins)


def set_tier_colors(hexes: object) -> None:
    """Override the four tier colors (from config). Ignores malformed input."""
    global _colors
    if isinstance(hexes, list) and len(hexes) == 4 and all(isinstance(h, str) and _HEX.match(h) for h in hexes):
        _colors = _build_colors(hexes)


def tier_wpm_mins() -> list[float]:
    return _tier_wpm


def tier_color(tier: int) -> TierColor:
    return _colors[max(0, min(len(_colors) - 1, tier))]


def tier_index(wpm: float, mins: list[float] | None = None) -> int:
    """Tier for a WPM with no hysteresis."""
    mins = mins or _tier_wpm
    tier = 0
    for i, m in enumerate(mins):
        if wpm >= m:
            tier = i + 1
    return tier


def tier_for(wpm: float, current: int, mins: list[float] | None = None) -> int:
    """Tier for a WPM, dropping a tier only once WPM falls 4 below its floor."""
    mins = mins or _tier_wpm
    tier = tier_index(wpm, mins)
    if tier < current and wpm >= mins[current - 1] - HYSTERESIS_WPM:
        return current
    return tier


def tint_amount(wpm: float, heat: float, mins: list[float] | None = None) -> float:
    """How strong the background tint is: typing burst or sustained speed, whichever is higher."""
    mins = mins or _tier_wpm
    return min(1.0, max(heat, wpm / mins[-1]))


def tier_position(wpm: float, mins: list[float] | None = None) -> float:
    """Where a WPM sits on the color scale, as a float from 1 (first tier's
    color) to 4 (top tier's color), interpolated between thresholds."""
    mins = mins or _tier_wpm
    if wpm <= mins[0]:
        return 1.0
    for i in range(1, len(mins)):
        if wpm < mins[i]:
            return i + (wpm - mins[i - 1]) / (mins[i] - mins[i - 1])
    return float(len(mins))


def color_at(position: float) -> RGB:
    """Tier color at a fractional position (1..4), blended between neighbors."""
    position = max(1.0, min(float(len(_colors) - 1), position))
    lo = int(position)
    hi = min(lo + 1, len(_colors) - 1)
    f = position - lo
    a, b = _colors[lo].rgb, _colors[hi].rgb
    return tuple(round(x + (y - x) * f) for x, y in zip(a, b))  # type: ignore[return-value]
