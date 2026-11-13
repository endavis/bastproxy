# Project: bastproxy
# Filename: libs/net/protocols.py
#
# File Description: terminates GMCP, MSDP and MSSP and publishes them as events
#
# By: Bast
"""Terminate GMCP, MSDP and MSSP on the MUD link and publish them as events (#59, #60, ADR-0001).

MXP (#61) is not decoded here. This manager tracks the MUD's MXP line modes
(``mxp_line_mode``), logs the MUD's ``SB MXP`` start and, when an MXP client logs in or turns
MXP on, sends it the MUD's default mode. Stripping and the per-client copy live in ``mxp``.
It also keeps the secure-mode element, entity, attribute-list and tag definitions the MUD sent
(#333): a redefinition replaces, ``DELETE`` removes, ``ADD``/``REMOVE`` of an entity append;
at most ``MXP_MAX_DEFINITIONS`` definitions and ``MXP_MAX_DEFINITION_CHARS`` characters are
kept (a new definition over a limit is dropped), and a disconnect clears them. An MXP client
that logs in or turns MXP on gets them as ``ESC[1z`` + tag + ``\r\n`` lines after the mode.

``PROTOCOLS`` is the one ``ProtocolManager``. It outlives any one ``MudConnection``, which is
rebuilt on each connect, and plugins can use its APIs before the MUD connects.

For each message from the MUD, in order: make a ``TelnetProtocolMessage`` record, cache the
value, then raise ``ev_libs.net.mud_gmcp`` (once per GMCP message) or ``ev_libs.net.mud_msdp``
(once per MSDP variable). Each event gets its own copy of the data.

MSSP: the MUD's table is stored whole (a new table replaces the old one, and a disconnect clears
it), sent to every logged-in client with MSSP enabled, and raised once as
``ev_libs.net.mud_mssp`` with the whole table. A client gets the stored table when it logs in or
answers ``DO MSSP``; the plaintext ``MSSP-REQUEST`` form is not supported. MSSP from a client is
dropped.

The proxy owns the ``Core`` GMCP package on each link: it sends its own ``Core.Hello`` and a
``Core.Supports.Set`` holding the union of the modules plugins register and the modules of the
logged-in clients that negotiated GMCP, and it never caches or forwards ``Core.*`` messages.

Client links: the proxy offers GMCP, MSDP and MSSP to each client. A client gets data only once it has
logged in (view-only included) and answered ``DO``. Live GMCP is re-encoded for each client by
its own ``Core.Supports``, MSDP goes to every MSDP client, and a client that joins or enables a
protocol late gets the cached values. From a client, ``Core.Hello`` is absorbed,
``Core.Supports.*`` updates that client's modules, ``Core.Ping`` is answered on its link, other
GMCP and the MSDP commands ``LIST``, ``SEND`` and ``REPORT`` go to the MUD only from a logged-in
client that is not view-only, and the data of ``Char.Login`` is recorded as ``<redacted>``.
"""

# Standard Library
import copy
from typing import Any

# 3rd Party
from telnetlib3.telopt import GMCP, MSDP, MSSP, MXP

# Project
import bastproxy
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net import mxp, oob
from bastproxy.libs.records.enums import Direction
from bastproxy.libs.records.events import RecordEventSpec
from bastproxy.libs.records.rtypes.telnet import TelnetProtocolMessage

logger = get_logger(__name__)

API_OWNER = "libs.net.protocols"
API = BASEAPI(owner_id=API_OWNER)

MUD_LINK_ID = "mud"
CLIENT_MSDP_COMMANDS = frozenset({"LIST", "SEND", "REPORT"})
MUD_GMCP_EVENT = "ev_libs.net.mud_gmcp"
MUD_MSDP_EVENT = "ev_libs.net.mud_msdp"
MUD_MSSP_EVENT = "ev_libs.net.mud_mssp"
EVENT_RAISE_API = "plugins.core.events:event.raise"

PROTOCOL_EVENTS: tuple[RecordEventSpec, ...] = (
    RecordEventSpec(
        MUD_GMCP_EVENT,
        API_OWNER,
        ["Raised once for each GMCP message the mud sends, other than Core.*"],
        {
            "package": "The GMCP package name, such as Char.Vitals",
            "data": "The decoded JSON data, or None; a copy the callback may keep",
        },
    ),
    RecordEventSpec(
        MUD_MSDP_EVENT,
        API_OWNER,
        ["Raised once for each MSDP variable the mud sends"],
        {
            "variable": "The MSDP variable name",
            "data": "The decoded value, a str, list or dict; a copy the callback may keep",
        },
    ),
    RecordEventSpec(
        MUD_MSSP_EVENT,
        API_OWNER,
        ["Raised once for each MSSP table the mud sends"],
        {
            "data": "The whole MSSP table, str or list of str values; a copy the callback may keep",
        },
    ),
)


class ProtocolManager:
    """Holds the GMCP, MSDP and MSSP state for the MUD link."""

    def __init__(self) -> None:
        """Create the manager with empty state and register its APIs."""
        self.api: BASEAPI = API
        # owner id -> {lower-cased module: version}
        self._owner_modules: dict[str, dict[str, int]] = {}
        self._mud_writer: Any = None
        self._hello_sent = False
        self._last_supports: list[str] | None = None
        self._gmcp_cache: dict[str, Any] = {}
        self._msdp_cache: dict[str, Any] = {}
        self._mssp: dict[str, Any] = {}
        self._cap_logged = False
        # MXP line modes of the MUD link (#61)
        self._mxp_default: mxp.MxpMode = mxp.MxpMode.OPEN
        self._mxp_current: mxp.MxpMode = mxp.MxpMode.OPEN
        # Definition capture keeps its own carried state: ESC[4z covers only the next tag (#333).
        self._mxp_capture_current: mxp.MxpMode = mxp.MxpMode.OPEN
        self._mxp_capture_pending = False
        # secure-mode definitions, in order, by (kind, name) (#333)
        self._mxp_defs: dict[tuple[str, str], list[str]] = {}
        self._mxp_defs_chars = 0
        self._mxp_defs_full_logged = False
        # uuid -> ClientConnection, for clients that are logged in
        self._clients: dict[str, Any] = {}

        self.api("libs.api:api.add.for.object")(API_OWNER, self)

    # ------------------------------------------------------------------ helpers

    def _caller_owner(self) -> str:
        """The owner id of whoever called an API."""
        return str(self.api("libs.api:caller.owner.get")(ignore_owner_list=[API_OWNER]))

    @staticmethod
    def _record(
        protocol: str, name: str, data: Any, direction: Direction, link: str = MUD_LINK_ID
    ) -> None:
        """Make a record, never letting a records failure reach the telnet parser.

        The data of a login package such as ``Char.Login`` is stored as ``<redacted>``.
        """
        if protocol == "GMCP" and oob.is_credential_package(name):
            data = oob.REDACTED
        try:
            TelnetProtocolMessage(protocol, name, data, direction, link)
        except Exception:
            logger.exception("Could not record %s %s", protocol, name)

    def _raise(self, event: str, name_arg: str, name: str, data: Any) -> None:
        """Raise ``event`` with its own copy of ``data`` when the events plugin is loaded."""
        self._raise_args(event, {name_arg: name, "data": data}, name)

    def _raise_args(self, event: str, args: dict[str, Any], label: str) -> None:
        """Raise ``event`` with a deep copy of ``args`` when the events plugin is loaded."""
        try:
            if not self.api("libs.api:api.exists")(EVENT_RAISE_API):
                return
            self.api(EVENT_RAISE_API)(
                event,
                event_args=copy.deepcopy(args),
                calledfrom=API_OWNER,
            )
        except Exception:
            logger.exception("Could not raise %s for %s", event, label)

    def _cache_set(self, cache: dict[str, Any], key: str, value: Any, merge: bool) -> None:
        """Store ``value`` under ``key``, honoring ``CACHE_MAX_ENTRIES``."""
        if key not in cache and len(cache) >= oob.CACHE_MAX_ENTRIES:
            if not self._cap_logged:
                self._cap_logged = True
                logger.warning(
                    "The protocol cache holds %d entries; new keys are forwarded but not cached "
                    "until the mud reconnects",
                    oob.CACHE_MAX_ENTRIES,
                )
            return
        stored = oob.merge_gmcp(cache[key], value) if merge and key in cache else value
        cache[key] = copy.deepcopy(stored)

    # ------------------------------------------------------------------ supports

    def union(self) -> dict[str, int]:
        """The modules to announce: lower-cased name to the highest version."""
        merged: dict[str, int] = {}
        sources = list(self._owner_modules.values())
        sources.extend(
            getattr(conn, "gmcp_modules", {})
            for conn in self._clients.values()
            if conn.gmcp_enabled
        )
        for modules in sources:
            for name, version in modules.items():
                merged[name] = max(version, merged.get(name, 0))
        return merged

    def _send_supports_if_changed(self) -> None:
        """Send ``Core.Supports.Set`` when the union differs from what was last sent."""
        writer = self._mud_writer
        if writer is None or not self._hello_sent or writer.is_closing():
            return
        payload = oob.supports_payload(self.union())
        if payload == (self._last_supports or []):
            return
        self._last_supports = payload
        writer.send_gmcp("Core.Supports.Set", payload)

    # ------------------------------------------------------------------ MUD link

    def mud_connected(self, writer: Any) -> None:
        """Remember the MUD writer; handle a ``WILL GMCP`` that arrived before it was known."""
        self._mud_writer = writer
        if writer.remote_option.enabled(GMCP):
            self.on_mud_will_gmcp(GMCP)

    def mud_disconnected(self) -> None:
        """Forget the MUD writer and clear the per-connection state."""
        self._mud_writer = None
        self._hello_sent = False
        self._last_supports = None
        self._gmcp_cache.clear()
        self._msdp_cache.clear()
        self._mssp = {}
        self._cap_logged = False
        self._mxp_defs = {}
        self._mxp_defs_chars = 0
        self._mxp_defs_full_logged = False
        self._mxp_reset()

    def _mxp_reset(self) -> None:
        """Return the MUD's MXP modes to open."""
        self._mxp_default = mxp.MxpMode.OPEN
        self._mxp_current = mxp.MxpMode.OPEN
        self._mxp_capture_current = mxp.MxpMode.OPEN
        self._mxp_capture_pending = False

    def mxp_line_mode(self, text: str, *, ended: bool, enabled: bool) -> mxp.MxpMode | None:
        """Track the MUD's MXP modes over one received piece of a line (#61).

        Returns the mode at the start of ``text``, or None (and resets the modes) when MXP is
        not enabled on the MUD link. A piece that did not end its line carries its mode over to
        the next piece; at the end of a line the mode returns to the default.
        """
        if not enabled:
            self._mxp_reset()
            return None
        start = self._mxp_current
        scan = mxp.scan_definitions(
            text, self._mxp_capture_current, self._mxp_default, self._mxp_capture_pending
        )
        self._mxp_store(scan.tags)
        modes = mxp.scan_modes(text, start, self._mxp_default)
        default = modes.default
        self._mxp_default = default
        self._mxp_current = default if ended else modes.current
        self._mxp_capture_current = default if ended else scan.current
        self._mxp_capture_pending = False if ended else scan.pending
        return start

    def _mxp_drop(self, tag: str) -> None:
        """Log once per MUD connection that a definition was dropped for a limit."""
        if not self._mxp_defs_full_logged:
            self._mxp_defs_full_logged = True
            logger.warning(
                "MXP definition limit reached, dropping new definitions (e.g. %.60s)", tag
            )

    def _mxp_store(self, tags: list[str]) -> None:
        """Apply the definition ``tags`` to the stored definitions (#333)."""
        for tag in tags:
            if any(c in tag for c in "\r\n\x1b"):
                continue
            parsed = mxp.definition_key(tag)
            if parsed is None:
                continue
            key, action = parsed
            old = self._mxp_defs.get(key)
            if action == "delete":
                if old is not None:
                    self._mxp_defs_chars -= sum(len(t) for t in old)
                    del self._mxp_defs[key]
                continue
            freed = sum(len(t) for t in old) if old is not None and action == "set" else 0
            if (
                old is None and len(self._mxp_defs) >= mxp.MXP_MAX_DEFINITIONS
            ) or self._mxp_defs_chars - freed + len(tag) > mxp.MXP_MAX_DEFINITION_CHARS:
                self._mxp_drop(tag)
                continue
            if action == "add" and old is not None:
                old.append(tag)
            else:
                self._mxp_defs.pop(key, None)
                self._mxp_defs[key] = [tag]
            self._mxp_defs_chars += len(tag) - freed

    def _mxp_replay(self) -> str:
        """The stored definitions as ``ESC[1z`` + tag + ``\\r\\n`` lines."""
        return "".join(f"\x1b[1z{tag}\r\n" for tags in self._mxp_defs.values() for tag in tags)

    def on_mud_mxp(self, payload: bytes) -> None:
        """Log an ``SB MXP`` from the MUD; the payload is not kept (#61)."""
        logger.debug("MXP subnegotiation from the mud, %d bytes", len(payload))

    def _mxp_sync(self, conn: Any) -> None:
        """Tell a logged-in MXP client the MUD's default mode, then the stored definitions.

        The mode goes only when it is not open (#61); the definitions go in order (#333).
        """
        if not getattr(conn, "mxp_enabled", False) or conn.writer.is_closing():
            return
        payload = mxp.sync_escape(self._mxp_default) + self._mxp_replay()
        if not payload:
            return
        try:
            conn.writer.write(payload)
        except Exception:
            logger.exception("Could not send the MXP mode to client %s", conn.uuid)

    def on_mud_will_gmcp(self, _opt: bytes) -> None:
        """Send ``Core.Hello`` once per connection, then the supports union if not empty."""
        writer = self._mud_writer
        if writer is None or not writer.remote_option.enabled(GMCP) or writer.is_closing():
            return
        if not self._hello_sent:
            self._hello_sent = True
            writer.send_gmcp(
                "Core.Hello", {"client": "bastproxy", "version": bastproxy.__version__}
            )
        self._send_supports_if_changed()

    def on_mud_gmcp(self, package: str, data: Any) -> None:
        """Handle one decoded GMCP message from the MUD."""
        self._record("GMCP", package, data, Direction.RECEIVED)
        if package.lower().startswith("core."):
            return
        self._cache_set(self._gmcp_cache, package, data, merge=True)
        for conn in self._targets(GMCP):
            if oob.package_wanted(package, conn.gmcp_modules):
                self._send_gmcp_to_client(conn, package, data)
        self._raise(MUD_GMCP_EVENT, "package", package, data)

    def on_mud_msdp(self, variables: dict[str, Any]) -> None:
        """Handle one decoded MSDP message from the MUD: one event per variable."""
        for variable, value in variables.items():
            self._record("MSDP", variable, value, Direction.RECEIVED)
            self._cache_set(self._msdp_cache, variable, value, merge=False)
            for conn in self._targets(MSDP):
                self._send_msdp_to_client(conn, variable, value)
            self._raise(MUD_MSDP_EVENT, "variable", variable, value)

    def on_mud_mssp(self, variables: dict[str, Any]) -> None:
        """Handle one decoded MSSP table from the MUD: record, store, send, raise (#60)."""
        self._record("MSSP", "", variables, Direction.RECEIVED)
        self._mssp = copy.deepcopy(variables)
        for conn in self._targets(MSSP):
            self._send_mssp_to_client(conn)
        self._raise_args(MUD_MSSP_EVENT, {"data": variables}, "MSSP")

    # ------------------------------------------------------------------ client links

    def _targets(self, opt: bytes) -> list[Any]:
        """The logged-in clients that negotiated ``opt`` and whose link is open."""
        enabled = {GMCP: "gmcp_enabled", MSDP: "msdp_enabled", MSSP: "mssp_enabled"}[opt]
        return [
            conn
            for conn in list(self._clients.values())
            if getattr(conn, enabled) and not conn.writer.is_closing()
        ]

    def _send_gmcp_to_client(self, conn: Any, package: str, data: Any) -> None:
        """Send one GMCP message to a client and record it."""
        try:
            conn.writer.send_gmcp(package, copy.deepcopy(data))
        except Exception:
            logger.exception("Could not send GMCP %s to client %s", package, conn.uuid)
            return
        self._record("GMCP", package, data, Direction.SENT, conn.uuid)

    def _send_msdp_to_client(self, conn: Any, variable: str, value: Any) -> None:
        """Send one MSDP variable to a client and record it."""
        try:
            conn.writer.send_msdp({variable: copy.deepcopy(value)})
        except Exception:
            logger.exception("Could not send MSDP %s to client %s", variable, conn.uuid)
            return
        self._record("MSDP", variable, value, Direction.SENT, conn.uuid)

    def _send_mssp_to_client(self, conn: Any) -> None:
        """Send the stored MSSP table to a client and record it; an empty table sends nothing."""
        if not self._mssp:
            return
        table = copy.deepcopy(self._mssp)
        try:
            conn.writer.send_mssp(table)
        except Exception:
            logger.exception("Could not send MSSP to client %s", conn.uuid)
            return
        self._record("MSSP", "", table, Direction.SENT, conn.uuid)

    def _replay(
        self,
        conn: Any,
        *,
        gmcp: bool = True,
        msdp: bool = True,
        mssp: bool = True,
        known: dict[str, int] | None = None,
    ) -> None:
        """Send the cached values and the stored MSSP table to one client.

        GMCP packages go only when the client's modules want them and, with ``known`` given,
        its previous modules did not.
        """
        if conn.writer.is_closing():
            return
        if gmcp and conn.gmcp_enabled:
            for package, value in list(self._gmcp_cache.items()):
                if oob.package_wanted(package, conn.gmcp_modules) and not (
                    known is not None and oob.package_wanted(package, known)
                ):
                    self._send_gmcp_to_client(conn, package, value)
        if msdp and conn.msdp_enabled:
            for variable, value in list(self._msdp_cache.items()):
                self._send_msdp_to_client(conn, variable, value)
        if mssp and conn.mssp_enabled:
            self._send_mssp_to_client(conn)

    def client_ready(self, conn: Any) -> None:
        """A client logged in: it now receives data, replay the cache and count its modules."""
        self._clients[conn.uuid] = conn
        self._replay(conn)
        self._mxp_sync(conn)
        self._send_supports_if_changed()

    def client_gone(self, conn: Any) -> None:
        """A client disconnected: drop it, and shrink the union if it had modules in it."""
        if self._clients.pop(conn.uuid, None) is not None:
            self._send_supports_if_changed()

    def client_option_changed(self, conn: Any, opt: bytes, enabled: bool) -> None:
        """A client turned GMCP, MSDP or MSSP on or off (``DO`` or ``DONT``)."""
        if opt == GMCP and not enabled:
            conn.gmcp_modules = {}
        if conn.uuid not in self._clients:
            return
        if opt == MXP:
            if enabled:
                self._mxp_sync(conn)
            return
        if enabled:
            self._replay(conn, gmcp=opt == GMCP, msdp=opt == MSDP, mssp=opt == MSSP)
        elif opt == GMCP:
            self._send_supports_if_changed()

    def _core_from_client(self, conn: Any, package: str, data: Any, *, ready: bool) -> None:
        """Handle a ``Core.*`` message from a client; none is passed on to the MUD."""
        verb = package.lower()
        if verb == "core.ping":
            if ready:
                self._send_gmcp_to_client(conn, "Core.Ping", None)
            return
        if verb not in ("core.supports.set", "core.supports.add", "core.supports.remove"):
            return  # Core.Hello and the rest: absorbed
        old: dict[str, int] = dict(conn.gmcp_modules)
        parsed = oob.parse_supports(data)
        new: dict[str, int]
        if verb.endswith(".set"):
            new = parsed
        elif verb.endswith(".add"):
            new = dict(old)
            for name, version in parsed.items():
                if name not in new and len(new) >= oob.CLIENT_MAX_MODULES:
                    continue
                new[name] = max(version, new.get(name, 0))
        else:
            new = {name: version for name, version in old.items() if name not in parsed}
        conn.gmcp_modules = new
        if ready:
            self._replay(conn, msdp=False, mssp=False, known=old)
            self._send_supports_if_changed()

    def on_client_gmcp(self, conn: Any, package: str, data: Any) -> None:
        """Handle one decoded GMCP message from a client."""
        if not conn.gmcp_enabled:
            return
        ready = conn.uuid in self._clients
        if package.lower().startswith("core."):
            # a client sends its Core.Supports before it logs in; keep it for later
            if ready or package.lower().startswith("core.supports."):
                if ready:
                    self._record("GMCP", package, data, Direction.RECEIVED, conn.uuid)
                self._core_from_client(conn, package, data, ready=ready)
            return
        if not ready:
            logger.debug("Dropped GMCP %s from client %s: not logged in", package, conn.uuid)
            return
        self._record("GMCP", package, data, Direction.RECEIVED, conn.uuid)
        if conn.view_only:
            logger.debug("Dropped GMCP %s from client %s: view only", package, conn.uuid)
            return
        writer = self._mud_writer
        if writer is None or writer.is_closing() or not writer.remote_option.enabled(GMCP):
            return
        try:
            writer.send_gmcp(package, data)
        except Exception:
            logger.exception("Could not forward GMCP %s to the mud", package)
            return
        self._record("GMCP", package, data, Direction.SENT)

    def on_client_msdp(self, conn: Any, variables: dict[str, Any]) -> None:
        """Handle one decoded MSDP message from a client: only some commands go to the MUD."""
        if conn.uuid not in self._clients or not conn.msdp_enabled:
            return
        for variable, value in variables.items():
            self._record("MSDP", variable, value, Direction.RECEIVED, conn.uuid)
        wanted = {
            variable.upper(): value
            for variable, value in variables.items()
            if variable.upper() in CLIENT_MSDP_COMMANDS
        }
        writer = self._mud_writer
        if (
            conn.view_only
            or not wanted
            or writer is None
            or writer.is_closing()
            or not writer.remote_option.enabled(MSDP)
        ):
            return
        try:
            writer.send_msdp(wanted)
        except Exception:
            logger.exception("Could not forward MSDP to the mud")
            return
        for variable, value in wanted.items():
            self._record("MSDP", variable, value, Direction.SENT)

    # ------------------------------------------------------------------ APIs

    @AddAPI(
        "gmcp.modules.add",
        description="add GMCP modules to the Core.Supports.Set the proxy sends to the mud",
    )
    def _api_gmcp_modules_add(self, modules: list[str], owner_id: str | None = None) -> list[str]:
        """Add modules such as ``"Char 1"`` for an owner; returns the accepted modules."""
        owner = owner_id or self._caller_owner()
        parsed = oob.parse_supports(modules)
        if parsed:
            current = self._owner_modules.setdefault(owner, {})
            for name, version in parsed.items():
                current[name] = max(version, current.get(name, 0))
            self._send_supports_if_changed()
        return oob.supports_payload(parsed)

    @AddAPI(
        "gmcp.modules.remove",
        description="remove GMCP modules (all of them when none are given) of an owner",
    )
    def _api_gmcp_modules_remove(
        self, modules: list[str] | None = None, owner_id: str | None = None
    ) -> None:
        """Remove the named modules of an owner, or all of that owner's modules."""
        owner = owner_id or self._caller_owner()
        if modules is None:
            self._owner_modules.pop(owner, None)
        elif owner in self._owner_modules:
            for name in oob.parse_supports(modules):
                self._owner_modules[owner].pop(name, None)
            if not self._owner_modules[owner]:
                del self._owner_modules[owner]
        self._send_supports_if_changed()

    @AddAPI(
        "gmcp.modules.remove.for.owner",
        description="remove every GMCP module an owner registered",
    )
    def _api_gmcp_modules_remove_for_owner(self, owner_id: str) -> None:
        """Remove every module of ``owner_id``."""
        self._owner_modules.pop(owner_id, None)
        self._send_supports_if_changed()

    @AddAPI("gmcp.supports.get", description="get the GMCP modules the proxy announces")
    def _api_gmcp_supports_get(self) -> list[str]:
        """The union as the sorted list ``Core.Supports.Set`` carries."""
        return oob.supports_payload(self.union())

    @AddAPI("gmcp.cache.get", description="get the cached GMCP values from the mud")
    def _api_gmcp_cache_get(self, package: str | None = None) -> Any:
        """A copy of one cached package value (None if absent), or of the whole cache."""
        if package is None:
            return copy.deepcopy(self._gmcp_cache)
        return copy.deepcopy(self._gmcp_cache.get(package))

    @AddAPI("msdp.cache.get", description="get the cached MSDP values from the mud")
    def _api_msdp_cache_get(self, variable: str | None = None) -> Any:
        """A copy of one cached variable value (None if absent), or of the whole cache."""
        if variable is None:
            return copy.deepcopy(self._msdp_cache)
        return copy.deepcopy(self._msdp_cache.get(variable))

    @AddAPI("mssp.cache.get", description="get the MSSP table the mud sent")
    def _api_mssp_cache_get(self, variable: str | None = None) -> Any:
        """A copy of one MSSP variable (None if absent), or of the whole table."""
        if variable is None:
            return copy.deepcopy(self._mssp)
        return copy.deepcopy(self._mssp.get(variable))


PROTOCOLS = ProtocolManager()
