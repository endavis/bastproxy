# Project: bastproxy
# Filename: plugins/core/web/libs/_proxyclient.py
#
# File Description: a client socket as a proxy client: MUD output as spans, input to the MUD
#
# By: Bast
"""A client socket is a proxy client, so it gets the MUD's output and its input reaches the MUD."""

# Standard Library
import asyncio
import datetime
import logging
from typing import Any, cast
from uuid import uuid4

from bastproxy.libs.api import API
from bastproxy.libs.logger import echo_off_placeholder, get_logger
from bastproxy.libs.net import mxp
from bastproxy.libs.net.naws import DEFAULT_ROWS, WINDOW_SIZE
from bastproxy.libs.records import (
    NetworkData,
    NetworkDataLine,
    Originated,
    ProcessDataToMud,
)

from ._tls import LOGGER_NAME
from ._ws import (
    CLOSE_INTERNAL,
    CLOSE_POLICY,
    SocketConnection,
    SocketHub,
    envelope,
    error_message,
)

# keep module identity across a reload of the plugin (other objects hold these classes)
CANRELOAD = False

OUTPUT_QUEUE_LIMIT = 5000
MAX_DIMENSION = 65535
CONN_TYPE = "websocket"


def _dimension(value: object) -> int | None:
    """The value as a window size, or None when it is not an integer from 1 to 65535."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= MAX_DIMENSION else None


class SocketClient:
    """The proxy-client face of one client socket.

    It offers what the clients plugin and the record classes read from a telnet
    ``ClientConnection``: an id, an address, the login state, ``send_to``, a window size.
    """

    def __init__(self, socket: SocketConnection, addr: str, port: str) -> None:
        self.uuid = uuid4().hex
        self.socket = socket
        self.addr = addr
        self.port = port
        self.api = API(owner_id=f"plugins.core.web:socket:{self.uuid}")
        self.conn_type = CONN_TYPE
        self.connected = True
        self.state: dict[str, bool] = {"logged in": False}
        self.view_only = socket.view_only
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self._last_input = self.connected_time
        self.naws_reported = False
        self.cols = 80
        self.rows = DEFAULT_ROWS
        self.lines_sent = 0
        self.lines_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.mxp_enabled = False
        self.data_logger = logging.getLogger(f"data.client.{self.uuid}")
        self.queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue(OUTPUT_QUEUE_LIMIT)
        self.task: asyncio.Task[None] | None = None

    @property
    def term_type(self) -> str:
        """The terminal type shown in the client list."""
        return CONN_TYPE

    @property
    def connected_length(self) -> str:
        """How long the socket has been connected, in a human-readable format."""
        return cast(
            str,
            self.api("plugins.core.utils:timedelta.to.string")(
                self.connected_time, datetime.datetime.now(datetime.UTC)
            ),
        )

    @property
    def idle(self) -> str:
        """How long since the socket last sent input, in a human-readable format."""
        return cast(
            str,
            self.api("plugins.core.utils:timedelta.to.string")(
                self._last_input, datetime.datetime.now(datetime.UTC)
            ),
        )

    def telnet_options(self) -> tuple[list[str], list[str]]:
        """A socket negotiates no telnet options."""
        return [], []

    def send_to(self, data: object) -> None:
        """Queue a line for the writer; a full queue closes the socket (1008)."""
        if not self.connected:
            return
        if not isinstance(data, NetworkDataLine):
            get_logger(LOGGER_NAME).error(
                "socket client %s got a type that is not NetworkDataLine: %s",
                self.uuid,
                type(data),
            )
            return
        if not data.is_io:
            return
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            self.connected = False
            self.socket.close(CLOSE_POLICY, "output queue full")

    def output_message(self, line: NetworkDataLine) -> dict[str, Any]:
        """The ``output`` message for a line: its text as colour spans."""
        text = cast(str, mxp.render_for_client(line, False)).rstrip("\r\n")
        spans = self.api("plugins.core.colors:ansicode.to.spans")(text)
        return envelope("output", spans=spans, prompt=bool(line.is_prompt), record=line.uuid)

    async def write(self) -> None:
        """Send queued lines to the socket until it is closed."""
        while self.connected:
            line = await self.queue.get()
            try:
                message = self.output_message(line)
            except Exception:
                get_logger(LOGGER_NAME).error(
                    "could not render a line for socket client %s", self.uuid, exc_info=True
                )
                continue
            if not await self.socket.send_wait(message):
                return
            line.was_sent = True
            self.lines_sent += 1

    def _mud_echo_off(self) -> bool:
        mud_connection = self.api("plugins.core.proxy:mud.connection.get")()
        return bool(mud_connection and mud_connection.echo_off)

    def handle_input(self, message: dict[str, Any]) -> None:
        """Send the text of an ``input`` message to the MUD, one line at a time."""
        text = message.get("text")
        if not isinstance(text, str):
            self.socket.send(error_message("bad_message", "text must be a string", "input"))
            return
        if self.view_only:
            self.socket.send(error_message("view_only", "this session is view only", "input"))
            return
        self._last_input = datetime.datetime.now(datetime.UTC)
        echo_off = self._mud_echo_off()
        for part in text.splitlines() or [""]:
            self.lines_received += 1
            self.data_logger.info(
                "%-12s : %s", "client_read", echo_off_placeholder(part) if echo_off else part
            )
            WINDOW_SIZE.client_input(self)
            line = NetworkDataLine(part, originated=Originated.CLIENT)
            line.mask_log = echo_off
            ProcessDataToMud(
                NetworkData(line, owner_id=f"client:{self.uuid}"), client_id=self.uuid
            )()

    def handle_cols(self, message: dict[str, Any]) -> None:
        """Take the window size from a ``cols`` message."""
        cols = _dimension(message.get("cols"))
        rows = _dimension(message["rows"]) if "rows" in message else DEFAULT_ROWS
        if cols is None or rows is None:
            self.socket.send(
                error_message(
                    "bad_message", f"cols and rows are integers from 1 to {MAX_DIMENSION}", "cols"
                )
            )
            return
        self.cols = cols
        self.rows = rows
        self.naws_reported = True
        WINDOW_SIZE.client_resized(self)


class SocketClients:
    """Makes each open client socket a registered proxy client."""

    def __init__(self, hub: SocketHub) -> None:
        self._hub = hub
        self._clients: dict[SocketConnection, SocketClient] = {}
        hub.register("input", self._input)
        hub.register("cols", self._cols)
        hub.add_listener(self.opened, self.closed)

    def client_for(self, conn: SocketConnection) -> SocketClient | None:
        """The proxy client of a socket, or None."""
        return self._clients.get(conn)

    def _input(self, conn: SocketConnection, message: dict[str, Any]) -> None:
        client = self._clients.get(conn)
        if client is not None:
            client.handle_input(message)

    def _cols(self, conn: SocketConnection, message: dict[str, Any]) -> None:
        client = self._clients.get(conn)
        if client is not None:
            client.handle_cols(message)

    def opened(self, conn: SocketConnection) -> None:
        """Register a new socket as a proxy client, logged in, and start its writer."""
        peer = conn.writer.get_extra_info("peername")
        addr, port = (str(peer[0]), str(peer[1])) if peer else ("-", "-")
        client = SocketClient(conn, addr, port)
        self._clients[conn] = client
        try:
            client.api("plugins.core.clients:client.add")(client)
            if client.view_only:
                client.api("plugins.core.clients:client.logged.in.set.view.only")(client.uuid)
            else:
                client.api("plugins.core.clients:client.logged.in.set")(client.uuid)
                WINDOW_SIZE.client_ready(client)
        except Exception:
            get_logger(LOGGER_NAME).error(
                "could not register socket client %s", client.uuid, exc_info=True
            )
            self._drop(conn)
            conn.close(CLOSE_INTERNAL, "could not register")
            return
        client.task = asyncio.create_task(client.write(), name=f"ws-output-{client.uuid}")

    def closed(self, conn: SocketConnection) -> None:
        """A socket ended: remove its proxy client."""
        self._drop(conn)

    def _drop(self, conn: SocketConnection) -> None:
        client = self._clients.pop(conn, None)
        if client is None:
            return
        client.connected = False
        if client.task is not None:
            client.task.cancel()
        try:
            client.api("plugins.core.clients:client.remove")(client)
        except Exception:
            get_logger(LOGGER_NAME).error(
                "could not remove socket client %s", client.uuid, exc_info=True
            )
        WINDOW_SIZE.client_gone(client)

    def close(self) -> None:
        """Drop every socket client and stop listening."""
        for conn in list(self._clients):
            self._drop(conn)
        self._hub.remove_listener(self.opened, self.closed)
        self._hub.unregister("input")
        self._hub.unregister("cols")
