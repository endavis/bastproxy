# Project: bastproxy
# Filename: libs/net/telopt.py
#
# File Description: lets a plugin own a telnet option the core does not handle
#
# By: Bast
"""Let one plugin own a telnet option the core does not handle (#566, ADR-0012).

A plugin registers an option number through ``libs.net.protocols:telopt.register``. On the MUD
link the proxy then accepts the MUD's ``WILL`` with ``DO``, raises events for the option and sends
subnegotiations the plugin asks for. On client links it offers ``WILL`` and forwards the MUD's
subnegotiations to clients that agreed. The core never interprets the payloads.

``RecordingTelnetWriter`` asks this manager (its ``telopt_hooks``) whether it claims an option; for
a claimed option the writer answers and dispatches here and never calls telnetlib3. Every other
option behaves as before.

The events are named by option number: ``ev_libs.net.mud_telopt_<n>``,
``ev_libs.net.mud_telopt_<n>_enabled``, ``ev_libs.net.mud_telopt_<n>_disabled`` and
``ev_libs.net.client_telopt_<n>``. Their ``data`` is raw ``bytes`` with IAC unescaped.

``ev_libs.net.mud_telopt_<n>_enabled`` is raised once per MUD connection, and only after the MUD
writer is registered (``mud_connected``), so a handler can call ``send`` and reach the MUD. An
option the MUD enabled during negotiation is raised when the writer is registered.

Unregistering an option leaves it on with the MUD: no ``DONT`` is sent, because a MUD may answer
neither ``DONT`` nor ``DO`` (#586). Registering an option that is still on raises ``_enabled`` at
once, without a new ``DO``.
"""

# Standard Library
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# 3rd Party
from telnetlib3 import telopt as _t
from telnetlib3.telopt import DO, IAC, SB, SE, WILL, WONT

# Project
from bastproxy.libs.logger import get_logger
from bastproxy.libs.records.enums import Direction
from bastproxy.libs.records.events import RecordEventSpec
from bastproxy.libs.records.rtypes.telnet import TelnetProtocolMessage

logger = get_logger(__name__)

API_OWNER = "libs.net.protocols"
MUD_LINK_ID = "mud"
TELOPT_PROTOCOL = "TELOPT"

# Options telnetlib3 or the proxy handle themselves; a plugin cannot claim them. MSP, AARDWOLF
# (102) and ATCP stay claimable. ZMP is declined on purpose (#39).
BUILTIN_OPTIONS: frozenset[int] = frozenset(
    opt[0]
    for opt in (
        _t.BINARY,
        _t.ECHO,
        _t.SGA,
        _t.STATUS,
        _t.TM,
        _t.LOGOUT,
        _t.SNDLOC,
        _t.TTYPE,
        _t.EOR,
        _t.NAWS,
        _t.TSPEED,
        _t.LFLOW,
        _t.LINEMODE,
        _t.XDISPLOC,
        _t.NEW_ENVIRON,
        _t.CHARSET,
        _t.COM_PORT_OPTION,
        _t.MCCP2_COMPRESS,
        _t.MCCP3_COMPRESS,
        _t.GMCP,
        _t.MSDP,
        _t.MSSP,
        _t.MXP,
        _t.ZMP,
        _t.EXOPL,
    )
)


def frame(option: int, payload: bytes) -> bytes:
    """Frame ``payload`` as ``IAC SB <option> ... IAC SE``, escaping IAC bytes."""
    return IAC + SB + bytes([option]) + payload.replace(IAC, IAC + IAC) + IAC + SE


def mud_event(option: int) -> str:
    """The event raised for each subnegotiation the MUD sends for ``option``."""
    return f"ev_libs.net.mud_telopt_{option}"


def mud_enabled_event(option: int) -> str:
    """The event raised when ``option`` becomes enabled on the MUD link."""
    return f"ev_libs.net.mud_telopt_{option}_enabled"


def mud_disabled_event(option: int) -> str:
    """The event raised when ``option`` becomes disabled on the MUD link."""
    return f"ev_libs.net.mud_telopt_{option}_disabled"


def client_event(option: int) -> str:
    """The event raised for each subnegotiation a logged-in client sends for ``option``."""
    return f"ev_libs.net.client_telopt_{option}"


def telopt_event_specs(option: int) -> tuple[RecordEventSpec, ...]:
    """The four events of one registered option."""
    return (
        RecordEventSpec(
            mud_event(option),
            API_OWNER,
            [f"Raised once for each option {option} subnegotiation the mud sends"],
            {
                "option": "The telnet option number",
                "data": "The payload as bytes, IAC unescaped",
            },
        ),
        RecordEventSpec(
            mud_enabled_event(option),
            API_OWNER,
            [f"Raised when option {option} becomes enabled on the mud link"],
            {"option": "The telnet option number"},
        ),
        RecordEventSpec(
            mud_disabled_event(option),
            API_OWNER,
            [f"Raised when option {option} becomes disabled on the mud link"],
            {"option": "The telnet option number"},
        ),
        RecordEventSpec(
            client_event(option),
            API_OWNER,
            [f"Raised for each option {option} subnegotiation a logged-in client sends"],
            {
                "option": "The telnet option number",
                "data": "The payload as bytes, IAC unescaped",
                "client_id": "The id of the client that sent it",
                "view_only": "True when the client is view-only",
            },
        ),
    )


@dataclass
class Registration:
    """One registered option."""

    owner: str
    mud: bool = True
    client: bool = True
    forward: bool = True


class TeloptManager:
    """Holds the registered options and does their negotiation, events and sends."""

    def __init__(
        self,
        clients: dict[str, Any],
        raise_args: Callable[[str, dict[str, Any], str], None],
        api_getter: Callable[[], Any],
    ) -> None:
        """Create the manager.

        ``clients`` is the protocol manager's dict of logged-in clients (shared, not copied),
        ``raise_args`` raises an event and ``api_getter`` returns the API to use.
        """
        self._clients = clients
        self._raise_args = raise_args
        self._api_getter = api_getter
        self._regs: dict[int, Registration] = {}
        self._mud_writer: Any = None
        self._mud_enabled: set[int] = set()
        self._client_links: weakref.WeakSet[Any] = weakref.WeakSet()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def valid_option(option: object) -> bool:
        """True for an ``int`` from 0 to 254 (255 cannot appear unescaped in ``IAC SB <opt>``)."""
        return isinstance(option, int) and not isinstance(option, bool) and 0 <= option <= 254

    @staticmethod
    def _record(option: int, payload: bytes, direction: Direction, link: str) -> None:
        """Make a record of one subnegotiation, never letting a records failure out."""
        try:
            TelnetProtocolMessage(TELOPT_PROTOCOL, str(option), payload, direction, link)
        except Exception:
            logger.exception("Could not record telopt %s", option)

    def client_options(self) -> list[int]:
        """The options to offer to clients with ``WILL``."""
        return sorted(opt for opt, reg in self._regs.items() if reg.client)

    # ------------------------------------------------------------------ writer hooks

    def attach(self, writer: Any) -> None:
        """Make ``writer`` ask this manager about the options it claims."""
        writer.telopt_hooks = self
        if getattr(writer, "server", False):
            self._client_links.add(writer)

    def claims(self, opt: int, *, server: bool) -> bool:
        """True when ``opt`` is registered for this kind of link."""
        reg = self._regs.get(opt)
        if reg is None:
            return False
        return reg.client if server else reg.mud

    def on_enabled(self, writer: Any, opt: int, enabled: bool) -> None:
        """An option became enabled or disabled on a link."""
        if getattr(writer, "server", False):
            logger.debug("Client link %s: option %d enabled=%s", writer.link_id, opt, enabled)
            return
        if writer is not self._mud_writer:
            logger.debug(
                "Ignoring option %d enabled=%s from a MUD writer that is not registered",
                opt,
                enabled,
            )
            return
        if enabled:
            if opt in self._mud_enabled:
                return
            self._mud_enabled.add(opt)
            self._raise_args(mud_enabled_event(opt), {"option": opt}, str(opt))
        elif opt in self._mud_enabled:
            self._mud_enabled.discard(opt)
            self._raise_args(mud_disabled_event(opt), {"option": opt}, str(opt))

    def on_subnegotiation(self, writer: Any, opt: int, payload: bytes) -> None:
        """A subnegotiation for a claimed, negotiated option arrived."""
        if getattr(writer, "server", False):
            self._on_client_sb(writer, opt, payload)
        else:
            self._on_mud_sb(opt, payload)

    def _on_mud_sb(self, opt: int, payload: bytes) -> None:
        """Record, forward and raise a subnegotiation from the MUD."""
        reg = self._regs.get(opt)
        if reg is None:
            return
        self._record(opt, payload, Direction.RECEIVED, MUD_LINK_ID)
        if reg.forward:
            data = frame(opt, payload)
            for conn in self._enabled_clients(opt):
                try:
                    conn.writer.send_iac(data)
                except Exception:
                    logger.exception("Could not forward telopt %d to client %s", opt, conn.uuid)
                    continue
                self._record(opt, payload, Direction.SENT, conn.uuid)
        self._raise_args(mud_event(opt), {"option": opt, "data": payload}, str(opt))

    def _on_client_sb(self, writer: Any, opt: int, payload: bytes) -> None:
        """Raise a subnegotiation from a logged-in client; never forwarded to the MUD."""
        conn = self._clients.get(writer.link_id)
        if conn is None:
            logger.debug("Dropped telopt %d from a client that is not logged in", opt)
            return
        self._record(opt, payload, Direction.RECEIVED, conn.uuid)
        self._raise_args(
            client_event(opt),
            {
                "option": opt,
                "data": payload,
                "client_id": conn.uuid,
                "view_only": bool(getattr(conn, "view_only", False)),
            },
            str(opt),
        )

    def _enabled_clients(self, opt: int, client_id: str | None = None) -> list[Any]:
        """Logged-in clients with an open link that enabled ``opt``."""
        key = bytes([opt])
        return [
            conn
            for cid, conn in list(self._clients.items())
            if (client_id is None or cid == client_id)
            and not conn.writer.is_closing()
            and conn.writer.local_option.enabled(key)
        ]

    # ------------------------------------------------------------------ lifecycle

    def mud_connected(self, writer: Any) -> None:
        """Remember the MUD writer, raise ``_enabled`` for options already on, ask for the rest."""
        self._mud_writer = writer
        for opt, reg in list(self._regs.items()):
            if reg.mud:
                self._enable_if_on(opt)
        for opt in list(self._regs):
            self._request_from_mud(opt)

    def _enable_if_on(self, opt: int) -> None:
        """Raise ``_enabled`` once when the MUD already has ``opt`` on."""
        writer = self._mud_writer
        if writer is None or opt in self._mud_enabled:
            return
        if writer.remote_option.enabled(bytes([opt])):
            self._mud_enabled.add(opt)
            self._raise_args(mud_enabled_event(opt), {"option": opt}, str(opt))

    def mud_disconnected(self) -> None:
        """Forget the MUD writer; options that were enabled are disabled."""
        self._mud_writer = None
        enabled = sorted(self._mud_enabled)
        self._mud_enabled.clear()
        for opt in enabled:
            self._raise_args(mud_disabled_event(opt), {"option": opt}, str(opt))

    def client_ready(self, _conn: Any) -> None:
        """A client logged in; its negotiation already happened, so nothing is sent."""

    def client_gone(self, _conn: Any) -> None:
        """A client is gone; nothing to clean up."""

    def reset(self) -> None:
        """Drop every registration and link (for tests)."""
        self._regs.clear()
        self._mud_writer = None
        self._mud_enabled.clear()
        self._client_links = weakref.WeakSet()

    def _request_from_mud(self, opt: int) -> None:
        """Send ``DO`` when the MUD offered ``opt`` earlier and it is not enabled yet."""
        writer = self._mud_writer
        reg = self._regs.get(opt)
        if writer is None or reg is None or not reg.mud or writer.is_closing():
            return
        key = bytes([opt])
        if key in writer.peer_offered and not writer.remote_option.enabled(key):
            writer.iac(DO, key)

    def _offer_to_clients(self, opt: int) -> None:
        """Send ``WILL`` to every attached client link that has not enabled ``opt``."""
        key = bytes([opt])
        for writer in list(self._client_links):
            if writer.is_closing() or writer.local_option.enabled(key):
                continue
            writer.iac(WILL, key)

    # ------------------------------------------------------------------ registration

    def register(
        self,
        option: Any,
        owner: str,
        *,
        mud: bool = True,
        client: bool = True,
        forward: bool = True,
    ) -> bool:
        """Register ``option`` for ``owner``; False (with a warning) when it is refused."""
        if not self.valid_option(option):
            logger.warning("telopt.register: %r is not an option number (0-254)", option)
            return False
        if option in BUILTIN_OPTIONS:
            logger.warning("telopt.register: option %d is handled by the core", option)
            return False
        existing = self._regs.get(option)
        if existing is not None and existing.owner != owner:
            logger.warning(
                "telopt.register: option %d belongs to %s, not %s", option, existing.owner, owner
            )
            return False
        self._regs[option] = Registration(owner, mud, client, forward)
        self._add_events(option)
        if mud:
            self._enable_if_on(option)
            self._request_from_mud(option)
        if client:
            self._offer_to_clients(option)
        return True

    def _add_events(self, option: int) -> None:
        """Add the option's events when the events plugin is loaded."""
        api = self._api_getter()
        try:
            if not api("libs.api:api.exists")("plugins.core.events:event.add"):
                return
            for spec in telopt_event_specs(option):
                api("plugins.core.events:event.add")(
                    spec.name,
                    spec.created_by,
                    description=spec.description,
                    arg_descriptions=spec.arg_descriptions,
                )
        except Exception:
            logger.exception("Could not add the events of telopt %d", option)

    def unregister(self, option: Any, owner: str) -> bool:
        """Unregister ``option``; only its owner may. Returns True when it was removed."""
        reg = self._regs.get(option) if isinstance(option, int) else None
        if reg is None or reg.owner != owner:
            return False
        del self._regs[option]
        key = bytes([option])
        if option in self._mud_enabled:
            self._mud_enabled.discard(option)
            self._raise_args(mud_disabled_event(option), {"option": option}, str(option))
        for link in list(self._client_links):
            if not link.is_closing() and link.local_option.enabled(key):
                link.iac(WONT, key)
        return True

    def unregister_for_owner(self, owner: str) -> None:
        """Unregister every option of ``owner``."""
        for option in [opt for opt, reg in self._regs.items() if reg.owner == owner]:
            self.unregister(option, owner)

    def set_forward(self, option: Any, forward: bool, owner: str) -> bool:
        """Turn forwarding of the MUD's subnegotiations on or off; only the owner may."""
        reg = self._regs.get(option) if isinstance(option, int) else None
        if reg is None or reg.owner != owner:
            return False
        reg.forward = bool(forward)
        return True

    def get(self, option: Any) -> dict[str, Any] | None:
        """Describe a registered option, or None."""
        reg = self._regs.get(option) if isinstance(option, int) else None
        if reg is None:
            return None
        return {
            "owner": reg.owner,
            "mud": reg.mud,
            "client": reg.client,
            "forward": reg.forward,
            "mud_enabled": option in self._mud_enabled,
            "clients": [conn.uuid for conn in self._enabled_clients(option)],
        }

    # ------------------------------------------------------------------ sending

    def _sendable(self, option: Any, payload: Any, what: str) -> bool:
        """True when ``option`` is registered and ``payload`` is bytes; logs the reason if not."""
        if not self.valid_option(option):
            logger.debug("telopt %s declined: %r is not an option number", what, option)
            return False
        if option not in self._regs:
            logger.debug("telopt %s %d declined: option is not registered", what, option)
            return False
        if not isinstance(payload, bytes | bytearray):
            logger.debug(
                "telopt %s %d declined: payload is %s, not bytes",
                what,
                option,
                type(payload).__name__,
            )
            return False
        return True

    def send(self, option: Any, payload: Any) -> bool:
        """Send a subnegotiation to the MUD; False when it cannot be sent."""
        if not self._sendable(option, payload, "send"):
            return False
        writer = self._mud_writer
        if writer is None:
            logger.debug("telopt send %r declined: no MUD writer", option)
            return False
        if writer.is_closing():
            logger.debug("telopt send %r declined: MUD link is closing", option)
            return False
        if not writer.remote_option.enabled(bytes([option])):
            logger.debug("telopt send %r declined: the MUD has not enabled it", option)
            return False
        data = bytes(payload)
        try:
            writer.send_iac(frame(option, data))
        except Exception:
            logger.exception("Could not send telopt %d to the mud", option)
            return False
        self._record(option, data, Direction.SENT, MUD_LINK_ID)
        return True

    def send_client(self, option: Any, payload: Any, client_id: str | None = None) -> bool:
        """Send a subnegotiation to logged-in clients that enabled the option."""
        if not self._sendable(option, payload, "send_client"):
            return False
        data = bytes(payload)
        sent = False
        targets = self._enabled_clients(option, client_id)
        if not targets:
            logger.debug("telopt send_client %r declined: no logged-in client enabled it", option)
        for conn in targets:
            try:
                conn.writer.send_iac(frame(option, data))
            except Exception:
                logger.exception("Could not send telopt %d to client %s", option, conn.uuid)
                continue
            self._record(option, data, Direction.SENT, conn.uuid)
            sent = True
        return sent
