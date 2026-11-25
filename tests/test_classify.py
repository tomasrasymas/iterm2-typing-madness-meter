import unittest

from tmm.classify import DELETE, FORWARD_DELETE, KEYPAD_ENTER, RETURN, RepeatFilter, classify

A = 0x00  # keycode for "a"
LEFT = 0x7B


class ClassifyTest(unittest.TestCase):
    def test_printable_chars(self):
        self.assertEqual(classify("a", A, set()), "char")
        self.assertEqual(classify("A", A, {"shift"}), "char")
        self.assertEqual(classify("å", A, {"option"}), "char")
        self.assertEqual(classify(" ", 0x31, set()), "char")

    def test_command_shortcuts_ignored(self):
        self.assertIsNone(classify("t", 0x11, {"command"}))
        self.assertIsNone(classify("\x7f", DELETE, {"command"}))

    def test_backspace_and_enter(self):
        self.assertEqual(classify("\x7f", DELETE, set()), "backspace")
        self.assertEqual(classify("", FORWARD_DELETE, {"function"}), "backspace")
        self.assertEqual(classify("\r", RETURN, set()), "enter")
        self.assertEqual(classify("\x03", KEYPAD_ENTER, {"numpad"}), "enter")

    def test_other_keys(self):
        self.assertEqual(classify("c", 0x08, {"control"}), "other")
        self.assertEqual(classify("", LEFT, {"function"}), "other")  # arrow: private use area
        self.assertEqual(classify("\x1b", 0x35, set()), "other")  # escape
        self.assertEqual(classify("\t", 0x30, set()), "other")
        self.assertEqual(classify("", 0x7A, set()), "other")


class RepeatFilterTest(unittest.TestCase):
    def test_held_key_counts_once(self):
        f = RepeatFilter()
        self.assertTrue(f.key_down(A))
        self.assertFalse(f.key_down(A))
        self.assertFalse(f.key_down(A))
        f.key_up(A)
        self.assertTrue(f.key_down(A))

    def test_rollover_counts_each_key(self):
        f = RepeatFilter()
        self.assertTrue(f.key_down(A))
        self.assertTrue(f.key_down(0x01))
        f.key_up(A)
        self.assertTrue(f.key_down(A))


if __name__ == "__main__":
    unittest.main()
