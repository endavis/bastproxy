# Project: bastproxy
# Filename: libs/net/naws.py
#
# File Description: picks the one window size the MUD link reports over NAWS
#
# By: Bast
"""Pick the window size the MUD link reports over NAWS (#308, ADR-0001).

The MUD link reports one size. In ``client`` mode (the default) it is the size of the active
client: the eligible client that most recently sent input. Eligible means connected, logged in
with the full password (view-only logins never count) and having reported a real size over NAWS.
A successful full login counts as activity, so a client that logs in and never types still sets
the size. A client's resize is stored, and a size is sent to the MUD only when it differs from
the last size sent on the current MUD link. When the active client goes, the next most recently
active eligible client takes over; with none left the last size stays.

``mudwindowsize`` selects the mode: ``client``, ``off`` (telnetlib3's default 80x25) or a pinned
``COLSxROWS``. The terminal type stays ``bastproxy`` and is not forwarded.

``WINDOW_SIZE`` is the one ``WindowSizeForwarder``. It outlives any one ``MudConnection`` and
any reload of the proxy plugin, which pushes the setting in with ``set_mode``.
"""

# Standard Library
import logging
import re
import struct
from typing import Any

# 3rd Party
from telnetlib3.telopt import IAC, NAWS, SB, SE

# Project
from bastproxy.libs.logger import get_logger

logger = get_logger(__name__)

#: telnetlib3's ``open_connection`` defaults for ``cols`` and ``rows``.
DEFAULT_COLS = 80
DEFAULT_ROWS = 25
NAWS_MAX = 65535
MODE_CLIENT = "client"
MODE_OFF = "off"

_PINNED = re.compile(r"^(\d{1,5})x(\d{1,5})$")

Size = tuple[int, int]


def naws_frame(cols: int, rows: int) -> bytes:
    """Return ``IAC SB NAWS <cols><rows> IAC SE`` with each value clamped and IAC escaped."""
    cols = max(0, min(NAWS_MAX, cols))
    rows = max(0, min(NAWS_MAX, rows))
    body = struct.pack("!HH", cols, rows).replace(IAC, IAC + IAC)
    return IAC + SB + NAWS + body + IAC + SE


class WindowSizeForwarder:
    """Track the clients' window sizes and send the chosen one to the MUD."""

    def __init__(self) -> None:
        """Start in ``client`` mode with no clients and no MUD link."""
        self._mode: str | Size = MODE_CLIENT
        self._clients: dict[str, Any] = {}
        self._order: list[str] = []
        self._last: Size | None = None
        self._sent: Size | None = None
        self._mud_writer: Any = None

    def reset(self) -> None:
        """Return to the initial state (for tests)."""
        self._mode = MODE_CLIENT
        self._clients = {}
        self._order = []
        self._last = None
        self._sent = None
        self._mud_writer = None

    # ------------------------------------------------------------------ settings

    def set_mode(self, value: str) -> None:
        """Select ``client``, ``off`` or a pinned ``COLSxROWS``; a bad value acts as ``client``."""
        text = str(value).strip().lower()
        mode: str | Size = MODE_CLIENT
        if text == MODE_OFF:
            mode = MODE_OFF
        elif text != MODE_CLIENT:
            match = _PINNED.match(text)
            if match and all(1 <= int(g) <= NAWS_MAX for g in match.groups()):
                mode = (int(match.group(1)), int(match.group(2)))
            else:
                logger.warning(
                    "mudwindowsize %r is not client, off or COLSxROWS (1 to %d); using client",
                    value,
                    NAWS_MAX,
                )
        self._mode = mode
        self._safe_update()

    # ------------------------------------------------------------------ client hooks

    def client_ready(self, conn: Any) -> None:
        """A client logged in; a full login counts as activity, a view-only one is ignored."""
        try:
            if conn.view_only:
                return
            self._clients[conn.uuid] = conn
            self._touch(conn.uuid)
            self._update()
        except Exception:
            logger.exception("Could not track the window size of client %s", conn.uuid)

    def client_input(self, conn: Any) -> None:
        """A logged-in client sent input: it becomes the active client."""
        try:
            if conn.uuid not in self._clients:
                return
            self._touch(conn.uuid)
            self._update()
        except Exception:
            logger.exception("Could not track the window size of client %s", conn.uuid)

    def client_resized(self, conn: Any) -> None:
        """A client reported a size; send it only if that client is the active one."""
        del conn
        self._safe_update()

    def client_gone(self, conn: Any) -> None:
        """A client disconnected: the next most recently active eligible client takes over."""
        try:
            self._clients.pop(conn.uuid, None)
            if conn.uuid in self._order:
                self._order.remove(conn.uuid)
            self._update()
        except Exception:
            logger.exception("Could not drop the window size of client %s", conn.uuid)

    def _touch(self, uuid: str) -> None:
        if uuid in self._order:
            self._order.remove(uuid)
        self._order.append(uuid)

    @staticmethod
    def _eligible(conn: Any) -> bool:
        return bool(conn.connected and conn.naws_reported and conn.cols > 0 and conn.rows > 0)

    # ------------------------------------------------------------------ choosing

    def target(self) -> Size:
        """Return the (cols, rows) the MUD should have, and remember it as the last choice."""
        if self._mode == MODE_OFF:
            return (DEFAULT_COLS, DEFAULT_ROWS)
        if isinstance(self._mode, tuple):
            return self._mode
        for uuid in reversed(self._order):
            conn = self._clients.get(uuid)
            if conn is not None and self._eligible(conn):
                self._last = (int(conn.cols), int(conn.rows))
                return self._last
        return self._last or (DEFAULT_COLS, DEFAULT_ROWS)

    # ------------------------------------------------------------------ MUD link

    def mud_reply(self) -> Size:
        """Return (rows, cols) for ``MudTelnetClient.send_naws`` and note it as sent."""
        cols, rows = self.target()
        self._sent = (cols, rows)
        return (rows, cols)

    def mud_connected(self, writer: Any) -> None:
        """Remember the MUD writer and send the size if it differs from the one sent."""
        self._mud_writer = writer
        self._safe_update()

    def mud_disconnected(self) -> None:
        """Forget the MUD writer; the next link starts with nothing sent."""
        self._mud_writer = None
        self._sent = None

    def _safe_update(self) -> None:
        try:
            self._update()
        except Exception:
            logger.exception("Could not send the window size to the mud")

    def _update(self) -> None:
        """Send the target size when NAWS is on for the MUD link and it changed."""
        size = self.target()
        writer = self._mud_writer
        if writer is None or writer.is_closing():
            return
        if writer.local_option.enabled(NAWS) is not True or size == self._sent:
            return
        writer.send_iac(naws_frame(*size))
        self._sent = size
        logging.getLogger("data.mud").info("%-12s : NAWS %dx%d", "to_mud", size[0], size[1])


WINDOW_SIZE = WindowSizeForwarder()
