import re
import time
import unittest

from tmm.game import Game
from tmm.render import HudView, hud_lines, line_width, render_frame, render_line, seg
from tmm.stats_view import stats_html, stats_lines

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip(s: str) -> str:
    return ANSI.sub("", s)


def typed(n: int, interval: float):
    g = Game()
    t = time.time() * 1000
    for _ in range(n):
        t += interval
        g.key("char", t)
    return g, t


class RenderTest(unittest.TestCase):
    def test_render_line_shifts_and_clips(self):
        line = [seg("hello"), seg(" world", "1")]
        self.assertEqual(strip(render_line(line, 2, 8)), "  hello ")
        self.assertEqual(strip(render_line(line, -3, 20)), "lo world")

    def test_lines_never_exceed_width(self):
        g, t = typed(300, 80)
        for width in (40, 80, 120):
            view = HudView(g.live(t), None, (3, 1), width, 7, 5)
            for line in hud_lines(view):
                self.assertLessEqual(len(strip(render_line(line, 3, width))), width)
            self.assertEqual(len(strip(render_frame(view)).split("\r\n")), 7)

    def test_shows_wpm_and_combo(self):
        g, t = typed(60, 100)
        wpm_line = hud_lines(HudView(g.live(t), None, (0, 0), 120, 7, 0))[0]
        text = strip(render_line(wpm_line, 0, 120))
        self.assertRegex(text, r"\d+ WPM")
        self.assertIn("COMBO 60", text)
        self.assertEqual(line_width(wpm_line), len(text))

    def test_sparks_after_text(self):
        g, t = typed(40, 50)
        lines = hud_lines(HudView(g.live(t), None, (0, 0), 140, 7, 3))
        self.assertEqual(len(lines), 3)
        first = strip(render_line(lines[0], 0, 140))
        tail = first[first.index("ACC") + 8 :]
        self.assertRegex(tail, r"[·✦✧*+˙]")
        self.assertLessEqual(len(first), 140)

    def test_stats_render(self):
        g, t = typed(200, 90)
        text = "\n".join(strip(render_line(line, 0, 200)) for line in stats_lines(g.stats, t))
        self.assertRegex(text, r"Best WPM \d+")
        self.assertIn("★ First Steps", text)
        page = stats_html(g.stats, t)
        self.assertIn("First Steps", page)
        self.assertIn("<!doctype html>", page)


if __name__ == "__main__":
    unittest.main()
