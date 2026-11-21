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
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import uuid4

# 3rd Party
from telnetlib3 import TelnetWriterUnicode
from telnetlib3.telopt import (
    DO,
    DONT,
    GMCP,
    IAC,
    MCCP3_COMPRESS,
    MSDP,
    MSSP,
    MXP,
    SB,
    SE,
    WILL,
    WONT,
    name_option,
)

# Project
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net import oob
from bastproxy.libs.net.telopt import BUILTIN_OPTIONS
from bastproxy.libs.records.enums import Direction
from bastproxy.libs.records.rtypes.telnet import TelnetNegotiation

logger = get_logger(__name__)

MUD_LINK_ID = "mud"
_VERBS: dict[bytes, str] = {DO: "DO", DONT: "DONT", WILL: "WILL", WONT: "WONT"}

# (command, option, data, raw)
ParsedNegotiation = tuple[str, bytes, bytes, bytes]


def option_names(options: Mapping[bytes, bool | None]) -> list[str]:
    """Return the sorted names of the options that are currently enabled."""
    return sorted(name_option(opt) for opt, on in options.items() if on is True)


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


class TeloptHooks(Protocol):
    """What the writer asks of the owner of plugin-claimed telnet options (#566)."""

    def claims(self, opt: int, *, server: bool) -> bool:
        """True when ``opt`` is claimed for this kind of link."""
        ...

    def client_logged_in(self, writer: Any) -> bool:
        """True when the client link ``writer`` belongs to a client that has logged in."""
        ...

    def on_enabled(self, writer: Any, opt: int, enabled: bool) -> None:
        """A claimed option was enabled or disabled on ``writer``'s link."""
        ...

    def on_subnegotiation(self, writer: Any, opt: int, payload: bytes) -> None:
        """A subnegotiation for a claimed, negotiated option arrived."""
        ...


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
        # Set by a parsed ``SB MCCP3`` that was offered and agreed on a server writer; the
        # server protocol takes it and starts its own bounded inflater (#329).
        self.mccp3_start_requested: bool = False
        # Every option the peer sent ``WILL`` for on this link, kept for a plugin that claims it
        # later (#566). telnetlib3's ``rejected_will`` misses the options it knows by name.
        self.peer_offered: set[bytes] = set()
        if kwargs.get("server"):
            for opt in (GMCP, MSDP):
                self.set_ext_callback(opt, self._make_pending_callback(opt))
            self.set_ext_callback(MSSP, self._drop_client_mssp)
            self.set_ext_callback(MXP, self._drop_client_mxp)

    @staticmethod
    def _drop_client_mssp(_variables: dict[str, Any]) -> None:
        """MSSP describes the game, so MSSP from a client is dropped, never stored (#60)."""
        logger.debug("Dropped an MSSP message from a client")

    @staticmethod
    def _drop_client_mxp(_payload: bytes) -> None:
        """An ``SB MXP`` from a client is dropped, never stored (#61)."""
        logger.debug("Dropped an MXP subnegotiation from a client")

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

    # Answers for options a plugin claimed with ``telopt.register`` (#566); ``None`` claims none.
    # An SB for an unowned option outside BUILTIN_OPTIONS is dropped, not passed on (#586).
    # On a client link a claimable option is negotiated only with a logged-in client: a ``DO``
    # before login or for an unclaimed option gets ``WONT``, and an ``SB`` before login is
    # discarded (#703). A client's ``WILL`` for such an option is answered ``DONT`` (#705).
    telopt_hooks: TeloptHooks | None = None

    # Called as ``(option)`` after a received ``DONT`` is handled; ``None`` means nobody listens.
    # The MUD link uses it to start the TTYPE cycle again (#547).
    dont_callback: Callable[[bytes], None] | None = None

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
        """Tell ``oob_option_callback`` that GMCP, MSDP or MSSP changed state (and MXP), if anyone
        listens.

        telnetlib3 stores ``local_option`` only after ``handle_do`` and ``handle_dont`` return,
        so it is set here first; the callback can then send on the link.
        """
        was = self.local_option.enabled(opt)
        callback = self.oob_option_callback
        if callback is None or opt not in (GMCP, MSDP, MSSP, MXP) or was == enabled:
            return
        self.local_option[opt] = enabled
        try:
            callback(opt, enabled)
        except Exception:
            logger.exception("Could not handle %s changing on a link", name_option(opt))

    def _telopt_claims(self, opt: bytes) -> bool:
        """True when a plugin claimed ``opt`` for this link; a hooks failure counts as no."""
        hooks = self.telopt_hooks
        if hooks is None or len(opt) != 1:
            return False
        try:
            return bool(hooks.claims(opt[0], server=bool(self.server)))
        except Exception:
            logger.exception("Could not check whether option %s is claimed", name_option(opt))
            return False

    def _client_logged_in(self) -> bool:
        """True when this client link's client has logged in; a hooks failure counts as no."""
        hooks = self.telopt_hooks
        if hooks is None:
            return False
        try:
            return bool(hooks.client_logged_in(self))
        except Exception:
            logger.exception("Could not check whether a client has logged in")
            return False

    def _telopt_enabled(self, opt: bytes, enabled: bool) -> None:
        """Tell the hooks a claimed option changed state."""
        hooks = self.telopt_hooks
        if hooks is None:
            return
        try:
            hooks.on_enabled(self, opt[0], enabled)
        except Exception:
            logger.exception("Could not handle option %s changing on a link", name_option(opt))

    def handle_do(self, opt: bytes) -> bool:
        """Record a received DO, then let telnetlib3 answer."""
        self._record(Direction.RECEIVED, "DO", opt, b"", IAC + DO + opt)
        if self.server and len(opt) == 1 and opt[0] not in BUILTIN_OPTIONS:
            if not (self._telopt_claims(opt) and self._client_logged_in()):
                # unclaimed, or the client has not logged in: refuse it (#703)
                if not self.local_option.enabled(opt) and not self.is_closing():
                    self.send_iac(IAC + WONT + opt)
                return False
            # a claimed option: accept it, answering only when we did not offer it ourselves
            if not self.local_option.enabled(opt):
                if not self.pending_option.enabled(WILL + opt) and not self.is_closing():
                    self.send_iac(IAC + WILL + opt)
                self.local_option[opt] = True
                self._telopt_enabled(opt, True)
            return True
        was_mxp = opt == MXP and self.local_option.enabled(MXP) is True
        result = super().handle_do(opt)
        if opt == MXP and result and not was_mxp and self.server and not self.is_closing():
            # MXP starts on this link: tell the client (#61); send_iac records it
            self.send_iac(IAC + SB + MXP + IAC + SE)
        self._oob_changed(opt, result)
        return result

    def handle_dont(self, opt: bytes) -> None:
        """Record a received DONT, then let telnetlib3 handle it."""
        self._record(Direction.RECEIVED, "DONT", opt, b"", IAC + DONT + opt)
        claimed_on = self.server and self._telopt_claims(opt) and self.local_option.enabled(opt)
        super().handle_dont(opt)
        if claimed_on:
            self.local_option[opt] = False
            self._telopt_enabled(opt, False)
        self._oob_changed(opt, False)
        callback = self.dont_callback
        if callback is not None:
            try:
                callback(opt)
            except Exception:
                logger.exception("Could not handle DONT %s on a link", name_option(opt))

    def handle_will(self, opt: bytes) -> None:
        """Record a received WILL, then let telnetlib3 answer."""
        self._record(Direction.RECEIVED, "WILL", opt, b"", IAC + WILL + opt)
        self.peer_offered.add(opt)
        if self.server and len(opt) == 1 and opt[0] not in BUILTIN_OPTIONS:
            # the proxy never uses a claimable option from the client side (a claimed one is
            # our local option, offered with WILL): refuse it, before and after login (#705).
            # Every WILL is answered, as RFC 1143 does for an option it does not agree to.
            if not self.is_closing():
                self.send_iac(IAC + DONT + opt)
            self.remote_option[opt] = False
            return
        if not self.server and self._telopt_claims(opt):
            # a claimed option: accept it with DO unless our own DO is what the MUD answered
            if not self.remote_option.enabled(opt):
                if not self.pending_option.enabled(DO + opt) and not self.is_closing():
                    self.send_iac(IAC + DO + opt)
                self.remote_option[opt] = True
                self._telopt_enabled(opt, True)
            return
        super().handle_will(opt)

    def handle_wont(self, opt: bytes) -> None:
        """Record a received WONT, then let telnetlib3 handle it."""
        self._record(Direction.RECEIVED, "WONT", opt, b"", IAC + WONT + opt)
        claimed_on = (
            not self.server and self._telopt_claims(opt) and self.remote_option.enabled(opt)
        )
        super().handle_wont(opt)
        if claimed_on:
            self._telopt_enabled(opt, False)

    def handle_subnegotiation(self, buf: collections.deque[bytes]) -> None:
        """Record a received SB from a copy of the payload, then dispatch it.

        A claimed option goes to its plugin. An option outside ``BUILTIN_OPTIONS`` that no plugin
        owns is dropped with a debug log. Everything else goes to telnetlib3.
        """
        if (
            self.server
            and buf
            and len(buf[0]) == 1
            and buf[0][0] not in BUILTIN_OPTIONS
            and not self._client_logged_in()
        ):
            # options negotiated only after login: discard before it is recorded or dispatched
            logger.debug(
                "Dropped a subnegotiation: %s before the client logged in", name_option(buf[0])
            )
            buf.clear()
            return
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
        if buf and self._telopt_claims(buf[0]):
            self._handle_telopt_sb(buf)
            return
        if buf and len(buf[0]) == 1 and buf[0][0] not in BUILTIN_OPTIONS:
            # no plugin owns it and the core never handles it: telnetlib3 must not see it (#586)
            logger.debug(
                "Dropped a subnegotiation: %s is not owned by a plugin", name_option(buf[0])
            )
            buf.clear()
            return
        super().handle_subnegotiation(buf)

    def _handle_telopt_sb(self, buf: collections.deque[bytes]) -> None:
        """Consume an SB for a claimed option and give its payload to the hooks (#566).

        An SB for an option that is enabled in neither direction is dropped, as for GMCP.
        """
        option = buf.popleft()
        payload = b"".join(buf)
        buf.clear()
        if not (self.local_option.enabled(option) or self.remote_option.enabled(option)):
            logger.debug("Dropped a subnegotiation: %s is not negotiated", name_option(option))
            return
        hooks = self.telopt_hooks
        if hooks is None:
            return
        try:
            hooks.on_subnegotiation(self, option[0], payload)
        except Exception:
            logger.exception("Could not handle a subnegotiation for %s", name_option(option))

    def _handle_oob_sb(
        self,
        buf: collections.deque[bytes],
        option: bytes,
        decode: Callable[[bytes, str], Any],
        deliver: Callable[[Any], None],
    ) -> None:
        """Decode a GMCP, MSDP or MSSP subnegotiation with the bounded decoders in ``oob``.

        The proxy decodes only protocols negotiated on the link: an SB for an option that is
        enabled in neither direction is dropped. A payload that does not decode is dropped with
        a log of the option, the name when known and the length, and the link stays open.

        These limits stay on telnetlib3 5.0.3, which decodes whatever arrives and limits only
        the nesting depth (100): here the payload size, MSDP depth and value count, and names
        are checked as well (#330).
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

    def _handle_sb_mssp(self, buf: collections.deque[bytes]) -> None:
        """Decode an MSSP subnegotiation and pass the table to the MSSP callback (#60)."""
        self._handle_oob_sb(
            buf, MSSP, oob.decode_mssp, lambda result: self._ext_callback[MSSP](result)
        )

    def _handle_sb_mccp3(self, buf: collections.deque[bytes]) -> None:
        """Handle ``SB MCCP3``; on a server writer, start only when offered and agreed (#329).

        telnetlib3's own MCCP3 decompression is never used on a client link: this never sets
        ``mccp3_active``. telnetlib3 5.0.3 would start inflating on any ``SB MCCP3``, agreed or
        not, and does not limit the output relative to the input. The stream starts only when
        the proxy offered ``WILL MCCP3`` and the client answered ``DO MCCP3``; the server protocol
        then inflates it with a bound.
        Any other ``SB MCCP3`` is dropped and the data after it stays plain. The MUD link
        keeps telnetlib3's handling.
        """
        if not self.server:
            super()._handle_sb_mccp3(buf)
            return
        buf.popleft()
        if self.local_option.enabled(MCCP3_COMPRESS):
            self.mccp3_start_requested = True
        else:
            logger.debug("Dropped an SB MCCP3 from a client: MCCP3 is not agreed on this link")
