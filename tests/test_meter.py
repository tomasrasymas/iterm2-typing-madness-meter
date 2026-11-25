import unittest
from datetime import datetime

from tmm.config import Config
from tmm.effects import badge_offsets, blend_rgb, quantize_tint, shake_offsets
from tmm.game import Game
from tmm.meter import Meter

T0 = datetime(2026, 11, 25, 14, 0, 0).timestamp() * 1000


class FakeEffects:
    def __init__(self):
        self.calls = []
        self.target = None

    def set_target(self, session_id):
        self.target = session_id

    def tint(self, rgb, amount):
        self.calls.append(("tint", rgb, round(amount, 2)))

    def tab(self, rgb):
        self.calls.append(("tab", rgb))

    def flash(self, rgb, ms=120):
        self.calls.append(("flash",))

    def badge(self, text, ms=2000):
        self.calls.append(("badge", text))

    def shake(self, points):
        self.calls.append(("shake", points))

    def kinds(self, kind):
        return [c for c in self.calls if c[0] == kind]


def make(cfg=None):
    fx = FakeEffects()
    toasts = []
    meter = Meter(cfg or Config(), Game(), fx, toast=lambda t, b: toasts.append(t), rng=lambda: 0.5)
    return meter, fx, toasts


class MeterTest(unittest.TestCase):
    def test_keys_target_the_typed_session(self):
        meter, fx, _ = make()
        meter.key("char", T0, "s1")
        self.assertEqual(fx.target, "s1")
        meter.key("char", T0 + 100, "s2")
        self.assertEqual(fx.target, "s2")
        self.assertTrue(meter.dirty)

    def test_combo_milestone_celebrates(self):
        meter, fx, _ = make()
        for i in range(25):
            meter.key("char", T0 + i * 300, "s1")  # ~40 WPM: no speed achievements
        self.assertEqual(fx.kinds("badge"), [("badge", "COMBO 25!")])
        self.assertEqual(fx.kinds("shake"), [("shake", 6)])
        self.assertEqual(len(fx.kinds("flash")), 1)

    def test_effects_respect_config(self):
        meter, fx, toasts = make(Config(shake=False, flash=False, milestoneBadge=False, toasts=False))
        for i in range(150):
            meter.key("char", T0 + i * 100, "s1")
        self.assertEqual(fx.kinds("badge") + fx.kinds("shake") + fx.kinds("flash"), [])
        self.assertEqual(toasts, [])

    def test_toasts_on_achievement_and_level(self):
        meter, _, toasts = make()
        for i in range(150):
            meter.key("char", T0 + i * 100, "s1")
        self.assertIn("Achievement: First Steps", toasts)
        self.assertIn("Level 1", toasts)

    def test_speed_colors_follow_tier_and_clear_when_idle(self):
        meter, fx, _ = make()
        t = T0
        for _ in range(120):
            t += 100  # 120 WPM: top tier
            meter.key("char", t, "s1")
        meter.speed_colors(meter.game.wpm(t), 0.5, 0)
        self.assertEqual(fx.calls[-2], ("tab", (255, 48, 48)))
        self.assertEqual(fx.calls[-1][0:2], ("tint", (255, 48, 48)))
        meter.speed_colors(0, 0, 5000)
        self.assertEqual(fx.calls[-2], ("tab", None))

    def test_tab_color_can_be_disabled(self):
        meter, fx, _ = make(Config(tabColor=False, tint=False))
        meter.speed_colors(120, 1, 0)
        self.assertEqual(fx.calls, [("tab", None), ("tint", None, 0)])

    def test_tick_builds_a_view(self):
        meter, _, _ = make()
        meter.key("char", T0, "s1")
        view = meter.tick(T0 + 10)
        self.assertEqual(view["type"], "view")
        self.assertEqual(view["live"]["combo"], 1)
        self.assertIsNone(view["message"])

    def test_live_text_and_status(self):
        meter, _, _ = make()
        for i in range(10):
            meter.key("char", T0 + i * 100, "s1")
        self.assertRegex(meter.live_text, r"^\d+ wpm · \d+ combo$")
        self.assertIn("combo", meter.status_text(T0 + 1000, True))
        self.assertIn("(off)", meter.status_text(T0 + 1000, False))
        meter.tick(T0 + 10_000)
        self.assertEqual(meter.live_text, "")


class EffectMathTest(unittest.TestCase):
    def test_blend(self):
        self.assertEqual(blend_rgb((0, 0, 0), (255, 100, 50), 0.5), (128, 50, 25))
        self.assertEqual(blend_rgb((10, 20, 30), (255, 255, 255), 0), (10, 20, 30))

    def test_quantize_tint(self):
        self.assertIsNone(quantize_tint(None, 1))
        self.assertIsNone(quantize_tint((1, 2, 3), 0.04))
        self.assertEqual(quantize_tint((1, 2, 3), 0.46), ((1, 2, 3), 0.5))
        self.assertEqual(quantize_tint([1, 2, 3], 7), ((1, 2, 3), 1.0))

    def test_shake_ends_at_rest_and_decays(self):
        offsets = shake_offsets(6, rng=lambda: 0.5)
        self.assertEqual(offsets[-1], (0, 0))
        self.assertEqual(offsets[0], (6, 0))
        self.assertLess(abs(offsets[-2][0]), 6)
        self.assertEqual(len(badge_offsets(rng=lambda: 1.0)), 12)


if __name__ == "__main__":
    unittest.main()
