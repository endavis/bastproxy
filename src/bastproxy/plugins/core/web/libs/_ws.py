# Project: bastproxy
# Filename: plugins/core/web/libs/_ws.py
#
# File Description: the client socket: websocket framing glue, envelope and handler registry
#
# By: Bast
"""The client socket served at /ws, on top of the sans-I/O websockets protocol."""

# Standard Library
import asyncio
import contextlib
import inspect
import json
import secrets
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from websockets.frames import Frame, Opcode
from websockets.http11 import Request as HandshakeRequest
from websockets.protocol import State
from websockets.server import ServerProtocol

from bastproxy.libs.logger import get_logger

from . import _http
from ._http import Request
from ._tls import LOGGER_NAME

# keep module identity across a reload of the plugin (other objects hold these classes)
CANRELOAD = False

PROTOCOL_VERSION = 1
MAX_MESSAGE = 65536
SEND_QUEUE_LIMIT = 256
PING_INTERVAL = 20
PING_TIMEOUT = 20
CLOSE_TIMEOUT = 5
READ_CHUNK = 65536

CLOSE_GOING_AWAY = 1001
CLOSE_UNSUPPORTED = 1003
CLOSE_INVALID_DATA = 1007
CLOSE_POLICY = 1008
CLOSE_INTERNAL = 1011
CLOSE_SESSION_ENDED = 4001

DEFAULT_PORTS = {"http": 80, "https": 443}

Handler = Callable[["SocketConnection", dict[str, Any]], Any]


def origin_of(value: str, *, strip_path: bool = False) -> str | None:
    """Normalise an origin (lower case scheme and host, default port dropped).

    Returns None for anything that is not an http(s) origin. A url with a path, query or
    fragment is refused unless ``strip_path`` is set, which keeps only the origin part.
    """
    try:
        parts = urllib.parse.urlsplit(value.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not host or parts.username or parts.password:
        return None
    if not strip_path and (parts.path or parts.query or parts.fragment):
        return None
    if ":" in host:
        host = f"[{host}]"
    suffix = "" if port is None or port == DEFAULT_PORTS[scheme] else f":{port}"
    return f"{scheme}://{host}{suffix}"


def is_upgrade(request: Request) -> bool:
    """True when the request asks for a websocket upgrade."""
    return "websocket" in request.headers.get("upgrade", "").lower()


def envelope(kind: str, **fields: Any) -> dict[str, Any]:
    """A server message: the version and type, then the fields."""
    return {"v": PROTOCOL_VERSION, "type": kind, **fields}


def error_message(
    code: str, message: str, for_type: str | None = None, **extra: Any
) -> dict[str, Any]:
    """An error message; ``for_type`` names the client message type it answers.

    ``extra`` adds more fields, for example the ``topic`` the error is about.
    """
    fields: dict[str, Any] = {"code": code, "message": message}
    if for_type is not None:
        fields["for"] = for_type
    fields.update(extra)
    return envelope("error", **fields)


def parse_message(text: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Parse one client message into ``(message, error)``; exactly one is not None.

    The error is an error envelope for a message that is not json (``bad_json``), not an
    object with a string type (``bad_message``), or has a version other than the integer 1
    (``version``).
    """
    try:
        data = json.loads(text)
    except ValueError:
        return None, error_message("bad_json", "the message is not valid json")
    if not isinstance(data, dict):
        return None, error_message("bad_message", "a message is a json object")
    kind = data.get("type")
    for_type = kind[:64] if isinstance(kind, str) else None
    version = data.get("v")
    if not isinstance(version, int) or isinstance(version, bool) or version != PROTOCOL_VERSION:
        return None, error_message("version", f"v must be {PROTOCOL_VERSION}", for_type)
    if not isinstance(kind, str) or not kind:
        return None, error_message("bad_message", "a message needs a string type")
    return data, None


def handshake(head: bytes) -> tuple[ServerProtocol, int]:
    """Run the opening handshake over a request head.

    Returns the protocol and the status of the handshake response; its bytes are queued in
    the protocol, to be sent only when the status is 101. Raises ValueError when the head is
    not a handshake request.
    """
    protocol = ServerProtocol(origins=None, max_size=MAX_MESSAGE)
    protocol.receive_data(head)
    events = protocol.events_received()
    request = events[0] if events else None
    if not isinstance(request, HandshakeRequest):
        msg = "the request head did not parse as a handshake"
        raise ValueError(msg)
    response = protocol.accept(request)
    if response.status_code == 101:
        protocol.send_response(response)
    return protocol, response.status_code


class SocketConnection:
    """One open client socket: a send queue, a reader, a sender and a keepalive."""

    def __init__(
        self,
        protocol: ServerProtocol,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        hub: "SocketHub",
        session_id: str | None,
        session_valid: Callable[[str | None], bool],
        hello: Callable[[str], dict[str, Any]],
    ) -> None:
        self.id = secrets.token_urlsafe(8)
        self.protocol = protocol
        self.reader = reader
        self.writer = writer
        self.hub = hub
        self._session_id = session_id
        self._session_valid = session_valid
        self._hello = hello
        self._queue: asyncio.Queue[str] = asyncio.Queue(SEND_QUEUE_LIMIT)
        self._last_received = time.monotonic()
        self._fragments = bytearray()
        self._abort: asyncio.TimerHandle | None = None
        self.subscriptions: set[str] = set()

    @property
    def is_open(self) -> bool:
        """True until a close was started."""
        return self.protocol.state is State.OPEN

    def send(self, message: dict[str, Any]) -> bool:
        """Queue a message; a full queue closes the socket (1008). False when not queued."""
        if not self.is_open:
            return False
        try:
            self._queue.put_nowait(json.dumps(message, default=str))
        except asyncio.QueueFull:
            self.close(CLOSE_POLICY, "send queue full")
            return False
        return True

    def close(self, code: int, reason: str) -> None:
        """Start the close handshake; the connection is aborted if the peer does not answer."""
        if not self.is_open:
            return
        self.protocol.send_close(code, reason)
        self._flush()
        if self._abort is None:
            loop = asyncio.get_running_loop()
            self._abort = loop.call_later(CLOSE_TIMEOUT, self.writer.transport.abort)

    def _flush(self) -> None:
        """Write what the protocol has queued; an empty chunk ends the TCP connection."""
        for chunk in self.protocol.data_to_send():
            if chunk:
                self.writer.write(chunk)
            else:
                self.writer.close()

    async def run(self) -> None:
        """Serve the socket until it closes."""
        self.send(self._hello(self.id))
        tasks = [
            asyncio.create_task(self._read(), name="ws-read"),
            asyncio.create_task(self._send_loop(), name="ws-send"),
            asyncio.create_task(self._keepalive(), name="ws-keepalive"),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._abort is not None:
                self._abort.cancel()

    async def _read(self) -> None:
        while True:
            data = await self.reader.read(READ_CHUNK)
            self._last_received = time.monotonic()
            if not data:
                self.protocol.receive_eof()
                self._flush()
                return
            self.protocol.receive_data(data)
            self._flush()
            for event in self.protocol.events_received():
                if isinstance(event, Frame):
                    await self._frame(event)
            if self.protocol.state is State.CLOSED or self.protocol.eof_sent:
                return

    async def _frame(self, frame: Frame) -> None:
        if frame.opcode is Opcode.BINARY:
            self.close(CLOSE_UNSUPPORTED, "binary frames are not accepted")
        elif frame.opcode in (Opcode.TEXT, Opcode.CONT) and self.is_open:
            self._fragments += frame.data
            if frame.fin:
                payload, self._fragments = bytes(self._fragments), bytearray()
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    self.close(CLOSE_INVALID_DATA, "text frames are utf-8")
                    return
                await self._message(text)

    async def _message(self, text: str) -> None:
        parsed, error = parse_message(text)
        if parsed is None:
            if error is not None:
                self.send(error)
            return
        kind = str(parsed["type"])
        handler = self.hub.handlers.get(kind)
        if handler is None:
            self.send(error_message("unknown_type", f"unknown message type {kind[:64]!r}", kind))
            return
        try:
            async with asyncio.timeout(_http.HANDLER_TIMEOUT):
                result = handler(self, parsed)
                if inspect.isawaitable(result):
                    await result
        except Exception:
            get_logger(LOGGER_NAME).error("socket handler of %r failed", kind, exc_info=True)
            self.send(error_message("internal", "the message could not be handled", kind))

    async def _send_loop(self) -> None:
        while True:
            text = await self._queue.get()
            if not self.is_open:
                return
            self.protocol.send_text(text.encode("utf-8"))
            self._flush()
            await self.writer.drain()

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            if not self.is_open:
                continue
            if not self._session_valid(self._session_id):
                self.close(CLOSE_SESSION_ENDED, "session ended")
            elif time.monotonic() - self._last_received > PING_INTERVAL + PING_TIMEOUT:
                self.close(CLOSE_INTERNAL, "keepalive timeout")
            else:
                self.protocol.send_ping(b"")
                self._flush()


class SocketHub:
    """The open sockets and the handlers of client message types (the hook for later work)."""

    def __init__(self) -> None:
        self.handlers: dict[str, Handler] = {}
        self._connections: set[SocketConnection] = set()

    def register(self, kind: str, handler: Handler) -> None:
        """Handle client messages of a type; a handler takes (connection, message).

        It may be sync or async and runs under the handler timeout. Raises ValueError for an
        empty type or one that already has a handler.
        """
        if not kind or kind in self.handlers:
            msg = f"cannot register a handler for message type {kind!r}"
            raise ValueError(msg)
        self.handlers[kind] = handler

    def unregister(self, kind: str) -> None:
        """Drop the handler of a message type, if any."""
        self.handlers.pop(kind, None)

    def add(self, connection: SocketConnection) -> None:
        """Track an open socket."""
        self._connections.add(connection)

    def discard(self, connection: SocketConnection) -> None:
        """Stop tracking a socket."""
        self._connections.discard(connection)

    def connections(self) -> list[SocketConnection]:
        """The open sockets, as a new list."""
        return list(self._connections)

    def count(self) -> int:
        """The number of open sockets."""
        return len(self._connections)

    def close_all(self, code: int, reason: str) -> int:
        """Start closing every open socket and return how many there were."""
        connections = list(self._connections)
        for connection in connections:
            with contextlib.suppress(Exception):
                connection.close(code, reason)
        return len(connections)
