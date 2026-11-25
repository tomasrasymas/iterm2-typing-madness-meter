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

    def test_speed_colors_warm_up_fast(self):
        meter, fx, _ = make()
        for i in range(8):  # 0.7s of fast typing (120 WPM, top tier)
            meter.speed_colors(120, 0.8, 50, T0 + i * 100)
        tab, tint = fx.calls[-2][1], fx.calls[-1]
        self.assertTrue(tab[0] == 255 and tab[1] < 60, f"red within 0.7s, got {tab}")
        self.assertEqual(tint[1], tab)
        self.assertGreater(tint[2], 0.9)

    def test_speed_colors_cool_down_smoothly(self):
        meter, fx, _ = make()
        t = T0
        for _ in range(10):
            t += 100
            meter.speed_colors(120, 0.8, 50, t)
        tints, tabs = [], []
        for _ in range(50):  # stop typing: 5s of frames, idle the whole time
            t += 100
            meter.speed_colors(120, 0, 2000, t)
            tabs.append(fx.calls[-2][1])
            tints.append(fx.calls[-1])
        amounts = [c[2] for c in tints]
        self.assertEqual(amounts, sorted(amounts, reverse=True))  # fades, never jumps back up
        self.assertGreater(amounts[5], 0.4)  # still glowing half a second in
        self.assertIsNone(tints[-1][1])  # off by the end
        greens = [rgb for rgb in tabs if rgb and rgb[1] > rgb[0]]
        self.assertTrue(greens, "cools through green on the way out")
        self.assertIsNone(tabs[-1])
        # Never snaps from strong to off: the last visible step is faint.
        last_on = max(i for i, c in enumerate(tints) if c[1] is not None)
        self.assertLess(amounts[last_on], 0.1)

    def test_cooldown_is_configurable(self):
        def frames_until_off(cooldown):
            meter, fx, _ = make(Config(cooldownMs=cooldown))
            t = T0
            for _ in range(10):
                t += 100
                meter.speed_colors(120, 0.8, 50, t)
            for n in range(1, 200):
                t += 100
                meter.speed_colors(120, 0, 2000, t)
                if fx.calls[-1][1] is None:
                    return n
            return 999

        self.assertLess(frames_until_off(1000), frames_until_off(4000))

    def test_tab_color_and_tint_can_be_disabled(self):
        meter, fx, _ = make(Config(tabColor=False, tint=False))
        for i in range(5):
            meter.speed_colors(120, 1, 0, T0 + i * 100)
        self.assertEqual(fx.calls[-2:], [("tab", None), ("tint", None, fx.calls[-1][2])])

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
        self.assertIsNone(quantize_tint((1, 2, 3), 0.02))
        self.assertEqual(quantize_tint((1, 2, 3), 0.46), ((1, 2, 3), 0.45))
        self.assertEqual(quantize_tint([1, 2, 3], 7), ((1, 2, 3), 1.0))

    def test_shake_ends_at_rest_and_decays(self):
        offsets = shake_offsets(6, rng=lambda: 0.5)
        self.assertEqual(offsets[-1], (0, 0))
        self.assertEqual(offsets[0], (6, 0))
        self.assertLess(abs(offsets[-2][0]), 6)
        self.assertEqual(len(badge_offsets(rng=lambda: 1.0)), 12)


if __name__ == "__main__":
    unittest.main()
