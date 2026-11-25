"""Pure meter renderer: state in, ANSI frame out.

Every glyph used here is single-width, so a line's visible width equals its
character count and horizontal shake can shift lines by plain offsets.
"""

from __future__ import annotations

from dataclasses import dataclass

from .game import Live
from .tiers import tier_color, tier_index

Segment = tuple[str, str]  # (text, SGR parameters such as "1;38;5;196"; "" = default style)
Line = list[Segment]

ESC = "\x1b["
DIM = "2"


def fg(n: int, bold: bool = False) -> str:
    return f"{'1;' if bold else ''}38;5;{n}"


def seg(text: str, style: str = "") -> Segment:
    return (text, style)


@dataclass
class HudView:
    live: Live
    message: Line | None  # notice on the message row (achievement, combo break, status)
    shake: tuple[int, int]  # (dx, dy)
    width: int
    height: int
    frame: int  # seed for the sparks, so frames differ while typing


def wpm_style(wpm: float, bold: bool = False) -> str:
    """SGR foreground for a WPM: gray below the first tier, else the tier's 24-bit color."""
    rgb = tier_color(tier_index(wpm)).rgb
    color = f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}" if rgb else "38;5;250"
    return f"1;{color}" if bold else color


def bar(fraction: float, width: int, style: str) -> Line:
    f = max(0.0, min(1.0, fraction))
    filled = int(f * width + 0.5)
    return [seg("▕", DIM), seg("█" * filled, style), seg("░" * (width - filled), fg(238)), seg("▏", DIM)]


def fmt(n: float) -> str:
    return f"{int(n + 0.5):,}"


def line_width(line: Line) -> int:
    return sum(len(t) for t, _ in line)


def render_line(line: Line, dx: int, width: int) -> str:
    """Render a line shifted by dx and clipped to width."""
    out = ""
    col = 0
    if dx > 0:
        col = min(dx, width)
        out += " " * col
    skip = -dx if dx < 0 else 0
    for text, style in line:
        if skip:
            cut = min(skip, len(text))
            text = text[cut:]
            skip -= cut
        if not text:
            continue
        room = width - col
        if room <= 0:
            break
        text = text[:room]
        out += f"{ESC}{style}m{text}{ESC}0m" if style else text
        col += len(text)
    return out


SPARK_GLYPHS = ["·", "✦", "✧", "*", "+", "˙"]
SPARK_COLORS = [196, 202, 208, 214, 220, 226, 51, 201]


def spark_fill(heat: float, cells: int, seed_base: int) -> Line:
    """`cells` columns of sparks whose density follows typing heat."""
    if cells <= 0:
        return []
    count = int(heat * cells * 0.35)
    out: Line = [seg(" ")] * cells
    seed = (seed_base * 2654435761) & 0xFFFFFFFF

    def rand() -> float:
        nonlocal seed
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        return seed / 2**32

    for _ in range(count):
        at = int(rand() * cells)
        glyph = SPARK_GLYPHS[int(rand() * len(SPARK_GLYPHS))]
        out[at] = seg(glyph, fg(SPARK_COLORS[int(rand() * len(SPARK_COLORS))], True))
    return out


def with_sparks(line: Line, heat: float, width: int, seed: int) -> Line:
    """Append sparks to the free space after a line's text."""
    gap = 3
    return [*line, seg(" " * gap), *spark_fill(heat, width - line_width(line) - gap - 1, seed)]


def hud_lines(view: HudView) -> list[Line]:
    live, width = view.live, view.width
    wide = width >= 90
    wpm_s = wpm_style(live.wpm)
    m = live.multiplier
    combo_c = 201 if m >= 4 else 208 if m >= 2.5 else 221 if m >= 1.5 else 250

    wpm_line: Line = [
        seg(" "),
        seg(str(live.wpm).rjust(3), wpm_style(live.wpm, True)),
        seg(" WPM ", wpm_s),
        *bar(live.wpm / 100, 20 if wide else 10, wpm_s),
        seg(f" peak {live.session_peak_wpm}", DIM),
        seg("   COMBO ", fg(combo_c)),
        seg(str(live.combo), fg(combo_c, True)),
        seg(f" ×{live.multiplier:.1f}", fg(combo_c)),
    ]
    if wide:
        wpm_line.append(seg(f"   ACC {int(live.accuracy * 100 + 0.5)}%", DIM))

    level_line: Line = [
        seg(" "),
        seg(f"LV {live.level}", fg(141, True)),
        seg(f" {live.rank} ", fg(141)),
        *bar(live.level_xp / live.level_span if live.level_span else 0, 20 if wide else 10, fg(141)),
        seg(f" {fmt(live.level_xp)}/{fmt(live.level_span)} XP", DIM),
    ]
    if wide:
        today = live.today
        level_line.append(seg(f"   today {fmt(today['chars'])} chars · best {today['bestWpm']} wpm", DIM))

    if view.message is not None:
        message = view.message
    elif live.idle_ms > 5000:
        message = [seg(" waiting for keys… start typing in any session", DIM)]
    else:
        message = []

    return [
        with_sparks(wpm_line, live.heat, width, view.frame),
        with_sparks(level_line, live.heat, width, view.frame + 7919),
        message,
    ]


def render_frame(view: HudView) -> str:
    """Full frame: cursor home, each row cleared, synchronized output."""
    lines = hud_lines(view)
    dx, dy = view.shake
    top = 1 if view.height >= len(lines) + 2 else 0
    rows = []
    for r in range(view.height):
        i = r - top - dy
        rows.append(render_line(lines[i], dx, view.width) if 0 <= i < len(lines) else "")
    body = "\r\n".join(f"{row}{ESC}K" for row in rows)
    return f"{ESC}?2026h{ESC}H{body}{ESC}J{ESC}?2026l"
