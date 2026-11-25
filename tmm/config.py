"""User config: ~/.config/typing-madness-meter/config.json (all keys optional)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields

from .tiers import DEFAULT_TIER_COLORS, DEFAULT_TIER_WPM


@dataclass
class Config:
    # Speed colors
    tierWpm: list = field(default_factory=lambda: list(DEFAULT_TIER_WPM))
    tierColors: list = field(default_factory=lambda: list(DEFAULT_TIER_COLORS))
    tabColor: bool = True  # color the typed session's tab by speed tier
    tint: bool = True  # tint the typed session's background as you type faster
    cooldownMs: int = 2000  # easing on the colors' way down, on top of the falling WPM
    # Score
    comboGapMs: int = 1200
    comboStep: int = 25
    maxMultiplier: float = 5
    comboMilestone: int = 25
    # Effects and behavior
    flash: bool = True  # flash the background on milestones
    milestoneBadge: bool = True  # shaking badge ("COMBO 150!") on milestones
    shake: bool = True  # shake the window on milestones
    shakePoints: int = 6  # how far the window shakes, in points
    statusBar: bool = True  # live text for the status bar component and user.typingMadness
    toasts: bool = True  # notifications on level-ups, records and achievements
    follow: bool = True  # move the meter under whichever session you start typing in
    hudHeight: int = 6  # meter pane height in rows
    autoOpen: bool = True  # reopen the meter when iTerm2 starts if it was on
    statsFile: str | None = None  # stats.json path; point at the herdr plugin's to share XP


def config_dir() -> str:
    return os.environ.get("TMM_CONFIG_DIR") or os.path.expanduser("~/.config/typing-madness-meter")


def state_dir() -> str:
    return os.environ.get("TMM_STATE_DIR") or os.path.expanduser("~/.local/state/typing-madness-meter")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load_config() -> Config:
    """Defaults overlaid with config.json. Unknown keys and wrong types are ignored."""
    cfg = Config()
    try:
        with open(config_path(), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    for fld in fields(Config):
        if fld.name not in raw:
            continue
        value, default = raw[fld.name], getattr(cfg, fld.name)
        if default is None:
            ok = value is None or isinstance(value, str)
        elif isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, (int, float)):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else:
            ok = isinstance(value, type(default))
        if ok:
            setattr(cfg, fld.name, value)
    if cfg.statsFile:
        cfg.statsFile = os.path.expanduser(cfg.statsFile)
    return cfg
