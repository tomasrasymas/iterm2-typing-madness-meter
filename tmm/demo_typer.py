"""Demo pane: a fake editor that "types" a code snippet by itself and feeds
each keystroke to the daemon's demo meter over the socket. Used to record
the README demo without real typing. Real stats are never touched.
Standard library only.

Usage: python demo_typer.py SOCKET
"""

from __future__ import annotations

import json
import os
import random
import signal
import socket
import sys
import time

SNIPPET = """// Typing Madness Meter: how mad is your typing?
export function madness(wpm: number, combo: number): string {
  if (wpm > 100 && combo > 200) return "keyboard demon";
  if (wpm > 65) return "on fire";
  if (wpm > 45) return "warming up";
  return "hunt and peck";
}

const today = madness(120, 250);
console.log(`today you are a ${today}`);
"""

# Typing speed (WPM) by elapsed seconds: a ramp, a pause, then a burst.
PROFILE: list[tuple[float, float | None]] = [
    (5, 25),
    (10, 45),
    (15, 65),
    (22, 95),
    (23.6, None),  # pause: the combo breaks
    (34, 125),
]

END = object()
ESC = "\x1b["


def wpm_at(seconds: float):
    """WPM for this moment, None during the pause, END once the demo is over."""
    for until, wpm in PROFILE:
        if seconds < until:
            return wpm
    return END


def out(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def header(status: str) -> None:
    out(f"{ESC}H{ESC}2K{ESC}1;38;5;201m demo.ts {ESC}0m{ESC}2m— {status}{ESC}0m\r\n{ESC}2K\r\n")


def connect(path: str, timeout: float) -> socket.socket | None:
    end = time.time() + timeout
    while time.time() < end:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            return s
        except OSError:
            s.close()
            time.sleep(0.2)
    return None


def main(argv: list[str]) -> int:
    path = argv[1]
    out(f"{ESC}?1049h{ESC}2J{ESC}?25l")
    header("waiting for the Typing Madness Meter…")
    sock = connect(path, 15)

    def send(msg: dict) -> None:
        if sock:
            try:
                sock.sendall((json.dumps(msg) + "\n").encode())
            except OSError:
                pass

    send({"type": "hello", "role": "typer", "session": os.environ.get("ITERM_SESSION_ID", "")})
    key = lambda c: send({"type": "key", "c": c})  # noqa: E731

    header("typing…")
    out(f"{ESC}3;1H")
    time.sleep(1.2)

    start = time.time()
    i = typed = 0
    while True:
        wpm = wpm_at(time.time() - start)
        if wpm is END:
            break
        if wpm is None:
            time.sleep(0.1)
            continue
        # Every ~45 chars, make a typo and fix it.
        if typed > 0 and typed % 45 == 0 and SNIPPET[i % len(SNIPPET)] != "\n":
            out("x")
            key("char")
            time.sleep(0.18)
            out("\b \b")
            key("backspace")
            time.sleep(0.12)
        ch = SNIPPET[i % len(SNIPPET)]
        i += 1
        typed += 1
        if ch == "\n":
            out(f"{ESC}K\r\n")
            key("enter")
        else:
            out(f"{ESC}38;5;252m{ch}{ESC}0m")
            key("char")
        if i % len(SNIPPET) == 0:  # wrap back to the top when the snippet runs out
            out(f"{ESC}3;1H{ESC}J")
        cps = wpm * 5 / 60
        time.sleep(1 / cps * (0.7 + random.random() * 0.6))

    header("done")
    send({"type": "done"})
    time.sleep(2.5)
    if sock:
        sock.close()
    out(f"{ESC}0m{ESC}?25h{ESC}?1049l")
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))
    sys.exit(main(sys.argv))
