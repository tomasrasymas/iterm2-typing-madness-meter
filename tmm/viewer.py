"""Meter pane: runs inside the HUD session the daemon opens. Standard library
only. It renders the views the daemon streams over the socket, posts
notifications, and asks the daemon to turn the meter off when q is pressed.

Usage: python viewer.py SOCKET [hud|demo]
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import termios
import tty

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from tmm.game import Live  # noqa: E402
from tmm.render import DIM, HudView, render_frame, render_line, seg  # noqa: E402

ENTER = "\x1b[?1049h\x1b[?25l\x1b[2J"
LEAVE = "\x1b[0m\x1b[?25h\x1b[?1049l"


def write(s: str) -> None:
    os.write(sys.stdout.fileno(), s.encode())


def size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size(sys.stdout.fileno())
        return sz.columns, sz.lines
    except OSError:
        return 80, 6


def frame_for(msg: dict) -> str:
    width, height = size()
    message = msg.get("message")
    view = HudView(
        live=Live.from_json(msg["live"]),
        message=[tuple(s) for s in message] if message is not None else None,
        shake=tuple(msg.get("shake", (0, 0))),
        width=width,
        height=height,
        frame=int(msg.get("frame", 0)),
    )
    return render_frame(view)


def waiting_frame() -> str:
    width, height = size()
    line = seg(" waiting for the Typing Madness Meter service… (is the AutoLaunch script running?)", DIM)
    return f"\x1b[H\x1b[2J\x1b[2;1H{render_line([line], 0, width)}"


def toast(title: str, body: str) -> None:
    # OSC 9: iTerm2 posts a notification under its own name.
    text = f"{title}: {body}" if body else title
    write(f"\x1b]9;{text.replace(chr(7), '').replace(chr(27), '')}\x07")


async def run(path: str, role: str) -> None:
    loop = asyncio.get_running_loop()
    quit_event = asyncio.Event()
    state: dict = {"last": "", "writer": None}

    def on_key() -> None:
        data = os.read(sys.stdin.fileno(), 64)
        if b"q" in data or b"\x03" in data or not data:
            w = state["writer"]
            if w is not None:
                w.write(b'{"type":"quit"}\n')
            quit_event.set()

    loop.add_reader(sys.stdin.fileno(), on_key)
    loop.add_signal_handler(signal.SIGWINCH, lambda: state.update(last=""))
    for sig in (signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(sig, quit_event.set)

    session = os.environ.get("ITERM_SESSION_ID", "")
    while not quit_event.is_set():
        try:
            reader, writer = await asyncio.open_unix_connection(path)
        except OSError:
            if state["last"] != "waiting":
                write(waiting_frame())
                state["last"] = "waiting"
            await asyncio.sleep(0.5)
            continue
        state["writer"] = writer
        writer.write((json.dumps({"type": "hello", "role": role, "session": session}) + "\n").encode())
        reading = asyncio.ensure_future(reader.readline())
        stopping = asyncio.ensure_future(quit_event.wait())
        try:
            while True:
                done, _ = await asyncio.wait({reading, stopping}, return_when=asyncio.FIRST_COMPLETED)
                if stopping in done:
                    break
                line = reading.result()
                if not line:
                    break
                reading = asyncio.ensure_future(reader.readline())
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("type") == "view":
                    out = frame_for(msg)
                    if out != state["last"]:
                        write(out)
                        state["last"] = out
                elif msg.get("type") == "toast":
                    toast(str(msg.get("title", "")), str(msg.get("body", "")))
        finally:
            reading.cancel()
            stopping.cancel()
            state["writer"] = None
            if quit_event.is_set():
                try:
                    await asyncio.wait_for(writer.drain(), 1.0)
                except (OSError, asyncio.TimeoutError):
                    pass
            writer.close()
        if not quit_event.is_set():
            await asyncio.sleep(0.5)  # daemon went away (restart): reconnect


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path, role = argv[1], (argv[2] if len(argv) > 2 else "hud")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd) if os.isatty(fd) else None
    try:
        if old is not None:
            tty.setraw(fd)
        write(ENTER)
        asyncio.run(run(path, role))
    except KeyboardInterrupt:
        pass
    finally:
        write(LEAVE)
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
