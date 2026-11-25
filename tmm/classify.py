"""Reduce an iTerm2 keystroke to a key class. The characters are looked at
here and nowhere else, and never stored: only the class leaves this module.
"""

from __future__ import annotations

from .game import KeyClass

# macOS virtual keycodes.
DELETE = 0x33
FORWARD_DELETE = 0x75
RETURN = 0x24
KEYPAD_ENTER = 0x4C


def classify(characters: str, keycode: int, modifiers: set[str]) -> KeyClass | None:
    """Key class for a key-down, or None for keys that shouldn't count at all.

    `modifiers` holds lowercase names: "command", "control", "option", "shift".
    """
    if "command" in modifiers:
        return None
    if keycode in (DELETE, FORWARD_DELETE):
        return "backspace"
    if keycode in (RETURN, KEYPAD_ENTER):
        return "enter"
    if "control" in modifiers:
        return "other"
    if not characters:
        return "other"
    # Printable unless a control char or in the private-use area macOS uses
    # for function and arrow keys.
    u = ord(characters[0])
    if u < 0x20 or u == 0x7F or 0xF700 <= u <= 0xF8FF:
        return "other"
    return "char"


class RepeatFilter:
    """Drops autorepeat from advanced keystroke notifications.

    A held key sends repeated key-downs with no key-up in between, so a
    key-down for a keycode that is already down is a repeat. If a key-up is
    ever missed (focus moved mid-press), the next press of that key is lost
    and its key-up resets it.
    """

    def __init__(self) -> None:
        self._down: set[int] = set()

    def key_down(self, keycode: int) -> bool:
        """True if this key-down is a fresh press, False if it is a repeat."""
        if keycode in self._down:
            return False
        self._down.add(keycode)
        return True

    def key_up(self, keycode: int) -> None:
        self._down.discard(keycode)

    def clear(self) -> None:
        self._down.clear()
