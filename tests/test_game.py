import unittest
from datetime import datetime, timedelta

from tmm.game import (
    Game,
    GameConfig,
    day_key,
    empty_stats,
    level_for_xp,
    multiplier_for,
    rank_for,
    streak_days,
    xp_for_level,
)

T0 = datetime(2026, 11, 25, 14, 0, 0).timestamp() * 1000


def type_chars(g: Game, n: int, interval_ms: float, start: float = T0):
    """Type `n` chars at a fixed interval, returning (events, time of last key)."""
    events = []
    t = start
    for _ in range(n):
        events.extend(g.key("char", t))
        t += interval_ms
    return events, t - interval_ms


def day(n: int) -> dict:
    return {"chars": n, "keys": n, "xp": 0, "bestWpm": 0, "bestCombo": 0}


class GameTest(unittest.TestCase):
    def test_wpm_100ms_per_char_over_10s(self):
        g = Game()
        _, end = type_chars(g, 101, 100)
        # 101 chars in the 10s window: (101 / 5) * (60000 / 10000) = 121.2
        self.assertEqual(g.wpm(end), 121)

    def test_old_chars_drop_out_of_window(self):
        g = Game()
        _, end = type_chars(g, 50, 100)
        self.assertEqual(g.wpm(end + 20_000), 0)

    def test_short_bursts_use_min_span(self):
        g = Game()
        _, end = type_chars(g, 5, 10)
        # 5 chars in 40ms would be 1500 WPM; floored span gives 30.
        self.assertEqual(g.wpm(end), 30)

    def test_combo_grows_and_breaks_after_gap(self):
        g = Game()
        _, end = type_chars(g, 40, 150)
        self.assertEqual(g.combo, 40)
        self.assertEqual(g.tick(end + 1300), [{"kind": "combo_break", "combo": 40}])
        self.assertEqual(g.combo, 0)

    def test_key_after_gap_reports_break_and_restarts(self):
        g = Game()
        _, end = type_chars(g, 10, 100)
        events = g.key("char", end + 5000)
        self.assertIn({"kind": "combo_break", "combo": 10}, events)
        self.assertEqual(g.combo, 1)

    def test_combo_milestones_every_25(self):
        g = Game()
        events, _ = type_chars(g, 100, 100)
        combos = [e["value"] for e in events if e["kind"] == "milestone" and e["reason"] == "combo"]
        self.assertEqual(combos, [25, 50, 75, 100])

    def test_combo_milestone_configurable(self):
        g = Game(config=GameConfig(combo_milestone=40))
        events, _ = type_chars(g, 100, 100)
        combos = [e["value"] for e in events if e["kind"] == "milestone" and e["reason"] == "combo"]
        self.assertEqual(combos, [40, 80])

    def test_backspace_lowers_accuracy_keeps_combo(self):
        g = Game()
        type_chars(g, 9, 100)
        g.key("backspace", T0 + 1000)
        self.assertEqual(g.combo, 9)
        self.assertAlmostEqual(g.accuracy(), 0.9)

    def test_other_keys_count_as_keys_not_chars(self):
        g = Game()
        g.key("other", T0)
        self.assertEqual(g.stats["totalKeys"], 1)
        self.assertEqual(g.stats["totalChars"], 0)
        self.assertEqual(g.combo, 0)

    def test_xp_uses_combo_multiplier(self):
        self.assertEqual(multiplier_for(0), 1)
        self.assertEqual(multiplier_for(25), 1.5)
        self.assertEqual(multiplier_for(100), 3)
        self.assertEqual(multiplier_for(10_000), 5)
        g = Game()
        type_chars(g, 50, 100)
        # 24 chars at 1x, 25 at 1.5x, 1 at 2x = 24 + 37.5 + 2 = 63.5
        self.assertEqual(g.stats["totalXp"], 63)

    def test_scoring_configurable(self):
        self.assertEqual(multiplier_for(20, 10, 5), 2)
        self.assertEqual(multiplier_for(1000, 10, 3), 3)
        g = Game(config=GameConfig(combo_step=10, max_multiplier=2))
        type_chars(g, 40, 100)
        # 9 chars x1, 10 x1.5, 21 x2 (capped) = 9 + 15 + 42 = 66
        self.assertEqual(g.stats["totalXp"], 66)

    def test_level_curve_and_ranks(self):
        self.assertEqual(xp_for_level(3), 900)
        self.assertEqual(level_for_xp(899), 2)
        self.assertEqual(level_for_xp(900), 3)
        self.assertEqual(rank_for(0), "Hunt & Peck")
        self.assertEqual(rank_for(12), "Combo Crusher")
        self.assertEqual(rank_for(99), "Keyboard Demon")

    def test_level_up_milestone(self):
        g = Game()
        events, _ = type_chars(g, 120, 100)
        self.assertIn({"kind": "milestone", "reason": "level", "value": 1}, events)

    def test_achievements_unlock_once(self):
        g = Game()
        events, _ = type_chars(g, 150, 100)
        firsts = [e for e in events if e["kind"] == "achievement" and e["id"] == "first_steps"]
        self.assertEqual(len(firsts), 1)
        for a in ("first_steps", "combo_100", "wpm_60"):
            self.assertIn(a, g.stats["achievements"])

    def test_wpm_records_need_enough_chars(self):
        g = Game()
        type_chars(g, 10, 50)
        self.assertEqual(g.stats["bestWpm"], 0)
        type_chars(g, 40, 50, T0 + 500)
        self.assertGreater(g.stats["bestWpm"], 0)

    def test_day_stats_keyed_by_local_date(self):
        g = Game()
        type_chars(g, 3, 100)
        self.assertEqual(g.stats["days"][day_key(T0)]["chars"], 3)

    def test_streak(self):
        stats = empty_stats()
        base = datetime.fromtimestamp(T0 / 1000)
        key = lambda o: (base - timedelta(days=o)).strftime("%Y-%m-%d")  # noqa: E731
        for o in (1, 2, 3):
            stats["days"][key(o)] = day(600)
        self.assertEqual(streak_days(stats, T0), 3)
        stats["days"][key(0)] = day(700)
        self.assertEqual(streak_days(stats, T0), 4)
        stats["days"][key(2)]["chars"] = 10
        self.assertEqual(streak_days(stats, T0), 2)

    def test_heat_rises_and_decays(self):
        g = Game()
        _, end = type_chars(g, 30, 60)
        hot = g.live(end).heat
        self.assertGreater(hot, 0.5)
        self.assertLess(g.live(end + 3000).heat, 0.05)

    def test_live_round_trips_through_json(self):
        g = Game()
        live = g.live(T0)
        self.assertIsNone(live.to_json()["idle_ms"])
        back = type(live).from_json(live.to_json())
        self.assertEqual(back, live)


if __name__ == "__main__":
    unittest.main()
