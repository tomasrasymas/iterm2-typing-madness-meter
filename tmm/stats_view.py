"""Stats summary as styled lines (stats pane) and as HTML (status bar popover)."""

from __future__ import annotations

import html
from datetime import datetime, timedelta

from .game import ACHIEVEMENTS, Stats, day_key, level_for_xp, rank_for, streak_days
from .render import DIM, Line, fg, fmt, seg

BARS = "▁▂▃▄▅▆▇█"


def last_days(stats: Stats, now: float, n: int = 14) -> list[tuple[str, int]]:
    noon = datetime.fromtimestamp(now / 1000).replace(hour=12, minute=0, second=0, microsecond=0)
    out = []
    for i in range(n - 1, -1, -1):
        key = (noon - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append((key, stats["days"].get(key, {}).get("chars", 0)))
    return out


def stats_lines(stats: Stats, now: float) -> list[Line]:
    level = level_for_xp(stats["totalXp"])
    days = last_days(stats, now)
    peak = max(1, *(c for _, c in days))
    # Each day is a 3-cell column: a 2-cell bar over its 2-digit day number.
    bars = " ".join(BARS[min(7, int(c / peak * 7.999))] * 2 if c else "  " for _, c in days)
    labels = " ".join(k[-2:] for k, _ in days)
    today = stats["days"].get(day_key(now)) or {}
    unlocked = sum(1 for a in ACHIEVEMENTS if stats["achievements"].get(a.id))

    lines: list[Line] = [
        [seg(" TYPING MADNESS METER", fg(201, True)), seg(" · stats", DIM)],
        [],
        [
            seg(f" Level {level}", fg(141, True)),
            seg(f" · {rank_for(level)}", fg(141)),
            seg(f"    XP {fmt(stats['totalXp'])}", DIM),
        ],
        [
            seg(" Best WPM "),
            seg(str(stats["bestWpm"]), fg(220, True)),
            seg("   Best combo "),
            seg(fmt(stats["bestCombo"]), fg(208, True)),
            seg("   Streak "),
            seg(f"{streak_days(stats, now)} days", fg(114, True)),
        ],
        [
            seg(f" Total {fmt(stats['totalChars'])} chars", DIM),
            seg(f"   Today {fmt(today.get('chars', 0))} chars · best {today.get('bestWpm', 0)} wpm", DIM),
        ],
        [],
        [seg(" Last 14 days", fg(250, True)), seg(f"  (max {fmt(peak)} chars/day)", DIM)],
        [seg(f" {bars}", fg(114))],
        [seg(f" {labels}", DIM)],
        [],
        [seg(f" Achievements {unlocked}/{len(ACHIEVEMENTS)}", fg(250, True))],
    ]
    for a in ACHIEVEMENTS:
        at = stats["achievements"].get(a.id)
        if at:
            lines.append([seg(" ★ ", fg(220, True)), seg(a.title, fg(220, True)), seg(f" — {a.description}  {day_key(at)}", DIM)])
        else:
            lines.append([seg(f" ☆ {a.title} — {a.description}", DIM)])
    return lines


def stats_html(stats: Stats, now: float) -> str:
    """Self-contained HTML for the status bar popover."""
    e = html.escape
    level = level_for_xp(stats["totalXp"])
    days = last_days(stats, now)
    peak = max(1, *(c for _, c in days))
    today = stats["days"].get(day_key(now)) or {}
    cols = "".join(
        f'<div class="d"><div class="b" style="height:{max(2, round(c / peak * 60)) if c else 0}px" '
        f'title="{e(k)}: {c:,} chars"></div><span>{e(k[-2:])}</span></div>'
        for k, c in days
    )
    ach = "".join(
        f'<li class="{"on" if stats["achievements"].get(a.id) else ""}">'
        f'{"★" if stats["achievements"].get(a.id) else "☆"} <b>{e(a.title)}</b> — {e(a.description)}</li>'
        for a in ACHIEVEMENTS
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root{{color-scheme:light dark;--fg:#222;--dim:#888;--accent:#c0f;--bar:#3a9;}}
@media (prefers-color-scheme:dark){{:root{{--fg:#eee;--dim:#999;--accent:#f6f;--bar:#5fd787;}}}}
body{{font:13px -apple-system,system-ui,sans-serif;color:var(--fg);margin:12px;}}
h1{{font-size:14px;color:var(--accent);margin:0 0 8px;letter-spacing:.05em}}
.row{{display:flex;gap:16px;margin:4px 0}} .dim{{color:var(--dim)}}
.chart{{display:flex;align-items:flex-end;gap:4px;height:80px;margin:10px 0 4px}}
.d{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;flex:1;height:100%}}
.b{{width:100%;background:var(--bar);border-radius:2px}} .d span{{font-size:10px;color:var(--dim)}}
ul{{list-style:none;padding:0;margin:6px 0}} li{{color:var(--dim);margin:2px 0}} li.on{{color:var(--fg)}}
</style></head><body>
<h1>TYPING MADNESS METER</h1>
<div class="row"><b>Level {level} · {e(rank_for(level))}</b><span class="dim">XP {stats['totalXp']:,}</span></div>
<div class="row"><span>Best WPM <b>{stats['bestWpm']}</b></span><span>Best combo <b>{stats['bestCombo']:,}</b></span>
<span>Streak <b>{streak_days(stats, now)} days</b></span></div>
<div class="row dim"><span>Total {stats['totalChars']:,} chars</span>
<span>Today {today.get('chars', 0):,} chars · best {today.get('bestWpm', 0)} wpm</span></div>
<div class="chart">{cols}</div>
<div class="dim">Last 14 days (max {peak:,} chars/day)</div>
<ul>{ach}</ul>
</body></html>"""
