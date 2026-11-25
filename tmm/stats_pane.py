"""Stats pane: a static summary in a temporary split; any key closes it.
Standard library only.

Usage: python stats_pane.py [STATS_FILE]
"""

from __future__ import annotations

import os
import signal
import sys
import termios
import time
import tty

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from tmm.render import DIM, render_line, seg  # noqa: E402
from tmm.stats_view import stats_lines  # noqa: E402
from tmm.store import load_stats  # noqa: E402


def draw(stats_file: str | None) -> None:
    try:
        sz = os.get_terminal_size(sys.stdout.fileno())
        width, height = sz.columns, sz.lines
    except OSError:
        width, height = 80, 24
    lines = stats_lines(load_stats(stats_file), time.time() * 1000)
    lines += [[], [seg(" press any key to close", DIM)]]
    rows = [f"{render_line(line, 0, width)}\x1b[K" for line in lines[:height]]
    sys.stdout.write("\x1b[H" + "\r\n".join(rows) + "\x1b[J")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    stats_file = argv[1] if len(argv) > 1 else None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd) if os.isatty(fd) else None
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    signal.signal(signal.SIGWINCH, lambda *_: draw(stats_file))
    try:
        if old is not None:
            tty.setraw(fd)
        draw(stats_file)
        os.read(fd, 16)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
