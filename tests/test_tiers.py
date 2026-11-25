import unittest

from tmm.render import wpm_style
from tmm.tiers import (
    DEFAULT_TIER_COLORS,
    color_at,
    tier_position,
    DEFAULT_TIER_WPM,
    hex_to_rgb,
    set_tier_colors,
    set_tier_wpm,
    tier_color,
    tier_for,
    tier_index,
    tier_wpm_mins,
    tint_amount,
)


class TiersTest(unittest.TestCase):
    def test_custom_colors(self):
        set_tier_colors(["#000001", "#000002", "#000003", "#Ff0000"])
        try:
            self.assertEqual(tier_color(4).hex, "#ff0000")
            self.assertEqual(tier_color(4).rgb, (255, 0, 0))
            self.assertIsNone(tier_color(0).hex)
            self.assertEqual(wpm_style(200, True), "1;38;2;255;0;0")
            self.assertEqual(wpm_style(1), "38;5;250")
            set_tier_colors(["red", "#00ff00", "#0000ff", "#ffffff"])  # not hex: ignored
            self.assertEqual(tier_color(1).hex, "#000001")
        finally:
            set_tier_colors(DEFAULT_TIER_COLORS)
        self.assertEqual(hex_to_rgb("#5fd787"), (95, 215, 135))

    def test_default_tiers(self):
        self.assertEqual(DEFAULT_TIER_WPM, [25, 45, 65, 85])
        self.assertEqual(tier_index(24), 0)
        self.assertEqual(tier_index(25), 1)
        self.assertEqual(tier_index(50), 2)
        self.assertEqual(tier_index(70), 3)
        self.assertEqual(tier_index(90), 4)

    def test_hysteresis(self):
        self.assertEqual(tier_for(43, 2), 2)  # 45 floor, within 4
        self.assertEqual(tier_for(40, 2), 1)
        self.assertEqual(tier_for(90, 1), 4)  # going up is immediate

    def test_tint_amount(self):
        self.assertEqual(tint_amount(85, 0), 1)
        self.assertAlmostEqual(tint_amount(42.5, 0), 0.5)
        self.assertEqual(tint_amount(10, 0.9), 0.9)

    def test_custom_thresholds(self):
        set_tier_wpm([10, 20, 30, 40])
        try:
            self.assertEqual(tier_wpm_mins(), [10, 20, 30, 40])
            set_tier_wpm([50, 40, 30, 20])  # not increasing
            set_tier_wpm("fast")  # wrong type
            self.assertEqual(tier_wpm_mins(), [10, 20, 30, 40])
        finally:
            set_tier_wpm(DEFAULT_TIER_WPM)

    def test_color_scale(self):
        self.assertEqual(tier_position(10), 1.0)
        self.assertEqual(tier_position(35), 1.5)  # halfway from 25 to 45
        self.assertEqual(tier_position(200), 4.0)
        self.assertEqual(color_at(1), (95, 215, 135))  # green
        self.assertEqual(color_at(4), (255, 48, 48))  # red
        self.assertEqual(color_at(3.5), (255, 92, 24))  # between orange and red
        self.assertEqual(color_at(9), (255, 48, 48))  # clamped


if __name__ == "__main__":
    unittest.main()
