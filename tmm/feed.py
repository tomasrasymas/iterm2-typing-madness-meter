"""Unix socket between the daemon and the processes it runs in sessions.

NDJSON both ways. Each client starts with
  {"type": "hello", "role": "hud" | "demo" | "typer", "session": "<iTerm2 session id>"}
then:
  daemon -> hud/demo   {"type": "view", ...}            a frame to render
                       {"type": "toast", "title", "body"} post a notification
  hud/demo -> daemon   {"type": "quit"}                  q pressed: turn the meter off
  typer -> daemon      {"type": "key", "c": "<key class>"} | {"type": "done"}
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
from dataclasses import dataclass, field
from typing import Awaitable, Callable

MAX_BUFFER = 64 * 1024  # skip frames for a client that stopped reading


@dataclass(eq=False)
class Client:
    writer: asyncio.StreamWriter
    role: str = ""
    session: str = ""  # iTerm2 session id (the UUID part of ITERM_SESSION_ID)
    extra: dict = field(default_factory=dict)

    def send(self, msg: dict) -> None:
        if self.writer.is_closing() or self.writer.transport.get_write_buffer_size() > MAX_BUFFER:
            return
        self.writer.write((json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode())


def session_uuid(iterm_session_id: str) -> str:
    """ITERM_SESSION_ID is "w0t1p0:UUID"; the API uses just the UUID."""
    return iterm_session_id.rsplit(":", 1)[-1]


def socket_alive(path: str) -> bool:
    """Is another daemon already listening on this socket?"""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(0.5)
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        s.close()


class Feed:
    def __init__(
        self,
        path: str,
        on_message: Callable[[Client, dict], Awaitable[None] | None],
        on_disconnect: Callable[[Client], None] = lambda c: None,
    ):
        self.path = path
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.clients: set[Client] = set()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        old = os.umask(0o077)
        try:
            self._server = await asyncio.start_unix_server(self._handle, path=self.path)
        finally:
            os.umask(old)

    def close(self) -> None:
        if self._server:
            self._server.close()
        for c in list(self.clients):
            c.writer.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def broadcast(self, role: str, msg: dict) -> None:
        for c in list(self.clients):
            if c.role == role:
                c.send(msg)

    def by_role(self, role: str) -> list[Client]:
        return [c for c in self.clients if c.role == role]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = Client(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "hello":
                    client.role = str(msg.get("role", ""))
                    client.session = session_uuid(str(msg.get("session", "")))
                    self.clients.add(client)
                result = self.on_message(client, msg)
                if asyncio.iscoroutine(result):
                    await result
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.clients.discard(client)
            writer.close()
            self.on_disconnect(client)
