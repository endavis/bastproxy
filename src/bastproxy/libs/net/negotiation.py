# Project: bastproxy
# Filename: libs/net/negotiation.py
#
# File Description: records telnet negotiation seen by telnetlib3's writers
#
# By: Bast
"""Record every telnet option negotiation as a ``TelnetNegotiation`` (#83).

``RecordingTelnetWriter`` is a ``TelnetWriterUnicode`` that both telnetlib3 protocols build
through their writer factory. Sent negotiation all goes through ``send_iac``, including the
replies telnetlib3 makes on its own. Received negotiation reaches ``handle_do``, ``handle_dont``,
``handle_will``, ``handle_wont`` and ``handle_subnegotiation`` from ``feed_byte``.

Two-byte commands (GA, EOR, NOP) are not recorded: a prompt already shows as
``NetworkDataLine.is_prompt``. Raw wire bytes are not recorded; each record keeps its own IAC
sequence as ``raw``.
"""

# Standard Library
import collections
from collections.abc import Callable
from typing import Any
from uuid import uuid4

# 3rd Party
from telnetlib3 import TelnetWriterUnicode
from telnetlib3.telopt import DO, DONT, GMCP, IAC, MSDP, SB, SE, WILL, WONT, name_option

# Project
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net import oob
from bastproxy.libs.records.enums import Direction
from bastproxy.libs.records.rtypes.telnet import TelnetNegotiation

logger = get_logger(__name__)

MUD_LINK_ID = "mud"
_VERBS: dict[bytes, str] = {DO: "DO", DONT: "DONT", WILL: "WILL", WONT: "WONT"}

# (command, option, data, raw)
ParsedNegotiation = tuple[str, bytes, bytes, bytes]


def parse_iac(buf: bytes) -> list[ParsedNegotiation]:
    """Split a buffer of bytes into its option negotiations.

    Returns a ``(command, option, data, raw)`` tuple for each DO, DONT, WILL, WONT and SB. Data
    bytes and two-byte commands are skipped. In an SB, ``IAC IAC`` is unescaped; an SB with no
    ``IAC SE`` yields its partial payload, since telnetlib3 splits some SBs over two writes. A
    bare ``IAC SE`` yields nothing.
    """
    found: list[ParsedNegotiation] = []
    i = 0
    size = len(buf)
    while i < size:
        if buf[i : i + 1] != IAC or i + 1 >= size:
            i += 1
            continue
        verb = buf[i + 1 : i + 2]
        if verb in _VERBS:
            if i + 2 >= size:
                break
            found.append((_VERBS[verb], buf[i + 2 : i + 3], b"", buf[i : i + 3]))
            i += 3
        elif verb == SB:
            j = i + 3
            payload = bytearray()
            end = size
            while j < size:
                if buf[j : j + 1] == IAC:
                    nxt = buf[j + 1 : j + 2]
                    if nxt == IAC:
                        payload.append(255)
                        j += 2
                        continue
                    if nxt == SE:
                        end = j + 2
                        break
                payload.append(buf[j])
                j += 1
            found.append(("SB", buf[i + 2 : i + 3], bytes(payload), buf[i:end]))
            i = end
        else:
            i += 2
    return found


class RecordingTelnetWriter(TelnetWriterUnicode):
    """A telnet writer that makes a ``TelnetNegotiation`` for each option negotiation.

    ``link_id`` names the link: ``"mud"`` on the client side, a fresh uuid hex on the server
    side, which ``ClientConnection`` adopts as its own uuid.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the writer and name its link."""
        super().__init__(*args, **kwargs)
        self.link_id: str = uuid4().hex if kwargs.get("server") else MUD_LINK_ID
        # A client may send GMCP or MSDP right behind its ``DO``, before the shell runs and
        # ``ClientConnection`` exists. Server writers hold those decoded messages (bounded) as
        # ``(option, args)`` until the connection takes them with its own callbacks.
        self.pending_oob: collections.deque[tuple[bytes, tuple[Any, ...]]] = collections.deque()
        if kwargs.get("server"):
            for opt in (GMCP, MSDP):
                self.set_ext_callback(opt, self._make_pending_callback(opt))

    def _make_pending_callback(self, opt: bytes) -> Callable[..., None]:
        """Build the callback that queues a decoded message for ``opt`` until it is taken."""

        def queue(*args: Any) -> None:
            if len(self.pending_oob) < self.OOB_PENDING_MAX:
                self.pending_oob.append((opt, args))
            else:
                logger.debug(
                    "Dropped a %s message: too many held before the client attached",
                    name_option(opt),
                )

        return queue

    # How many decoded GMCP/MSDP messages a server writer holds until bastproxy attaches.
    OOB_PENDING_MAX = 16

    # Called as ``(option, enabled)`` when the peer turns GMCP or MSDP on or off for this
    # (server side) link. ``ClientConnection`` sets it; ``None`` means nobody is listening.
    oob_option_callback: Callable[[bytes, bool], None] | None = None

    def _record(
        self, direction: Direction, command: str, option: bytes, data: bytes, raw: bytes
    ) -> None:
        """Create a record, never letting a records failure reach telnetlib3's parser.

        The data of a GMCP login message (``Char.Login``) is stored as ``<redacted>``, in both
        ``data`` and ``raw``, whichever way it travels.
        """
        if command == "SB" and option == GMCP:
            safe = oob.redact_gmcp_payload(data)
            if safe is not data:
                data = safe
                raw = IAC + SB + option + data.replace(IAC, IAC + IAC) + IAC + SE
        try:
            TelnetNegotiation(
                command=command,
                option=name_option(option),
                direction=direction,
                link=self.link_id,
                data=data,
                raw=raw,
            )
        except Exception:
            logger.exception("Could not record telnet %s %r", command, option)

    def send_iac(self, buf: bytes) -> None:
        """Record the negotiation in ``buf``, then send it."""
        if not self.is_closing():
            try:
                for command, option, data, raw in parse_iac(buf):
                    self._record(Direction.SENT, command, option, data, raw)
            except Exception:
                logger.exception("Could not parse sent telnet bytes")
        super().send_iac(buf)

    def _oob_changed(self, opt: bytes, enabled: bool) -> None:
        """Tell ``oob_option_callback`` that GMCP or MSDP changed state, if anyone listens.

        telnetlib3 stores ``local_option`` only after ``handle_do`` and ``handle_dont`` return,
        so it is set here first; the callback can then send on the link.
        """
        was = self.local_option.enabled(opt)
        callback = self.oob_option_callback
        if callback is None or opt not in (GMCP, MSDP) or was == enabled:
            return
        self.local_option[opt] = enabled
        try:
            callback(opt, enabled)
        except Exception:
            logger.exception("Could not handle %s changing on a link", name_option(opt))

    def handle_do(self, opt: bytes) -> bool:
        """Record a received DO, then let telnetlib3 answer."""
        self._record(Direction.RECEIVED, "DO", opt, b"", IAC + DO + opt)
        result = super().handle_do(opt)
        self._oob_changed(opt, result)
        return result

    def handle_dont(self, opt: bytes) -> None:
        """Record a received DONT, then let telnetlib3 handle it."""
        self._record(Direction.RECEIVED, "DONT", opt, b"", IAC + DONT + opt)
        super().handle_dont(opt)
        self._oob_changed(opt, False)

    def handle_will(self, opt: bytes) -> None:
        """Record a received WILL, then let telnetlib3 answer."""
        self._record(Direction.RECEIVED, "WILL", opt, b"", IAC + WILL + opt)
        super().handle_will(opt)

    def handle_wont(self, opt: bytes) -> None:
        """Record a received WONT, then let telnetlib3 handle it."""
        self._record(Direction.RECEIVED, "WONT", opt, b"", IAC + WONT + opt)
        super().handle_wont(opt)

    def handle_subnegotiation(self, buf: collections.deque[bytes]) -> None:
        """Record a received SB from a copy of the payload, then let telnetlib3 consume it."""
        try:
            items = list(buf)
            if items:
                option = items[0]
                payload = b"".join(items[1:])
                escaped = payload.replace(IAC, IAC + IAC)
                raw = IAC + SB + option + escaped + IAC + SE
                self._record(Direction.RECEIVED, "SB", option, payload, raw)
        except Exception:
            logger.exception("Could not record a telnet subnegotiation")
        super().handle_subnegotiation(buf)

    def _handle_oob_sb(
        self,
        buf: collections.deque[bytes],
        option: bytes,
        decode: Callable[[bytes, str], Any],
        deliver: Callable[[Any], None],
    ) -> None:
        """Decode a GMCP or MSDP subnegotiation with the bounded decoders in ``oob``.

        The proxy decodes only protocols negotiated on the link: an SB for an option that is
        enabled in neither direction is dropped. A payload that does not decode is dropped with
        a log of the option, the name when known and the length, and the link stays open.
        """
        label = name_option(option)
        if not (self.local_option.enabled(option) or self.remote_option.enabled(option)):
            logger.debug(
                "Dropped %s subnegotiation: %s is not negotiated on this link", label, label
            )
            return
        buf.popleft()
        payload = b"".join(buf)
        try:
            result = decode(payload, self.environ_encoding or "utf-8")
        except oob.OobDecodeError as exc:
            logger.warning(
                "Dropped a %s message (%s): name=%s length=%d",
                label,
                exc,
                exc.name or "-",
                len(payload),
            )
            return
        deliver(result)

    def _handle_sb_gmcp(self, buf: collections.deque[bytes]) -> None:
        """Decode a GMCP subnegotiation and pass ``(package, data)`` to the GMCP callback."""
        self._handle_oob_sb(
            buf, GMCP, oob.decode_gmcp, lambda result: self._ext_callback[GMCP](*result)
        )

    def _handle_sb_msdp(self, buf: collections.deque[bytes]) -> None:
        """Decode an MSDP subnegotiation and pass the variables to the MSDP callback."""
        self._handle_oob_sb(
            buf, MSDP, oob.decode_msdp, lambda result: self._ext_callback[MSDP](result)
        )
