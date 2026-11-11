# Project: bastproxy
# Filename: libs/net/protocols.py
#
# File Description: terminates GMCP and MSDP and publishes them as events
#
# By: Bast
"""Terminate GMCP and MSDP on the MUD link and publish them as events (#59, ADR-0001).

``PROTOCOLS`` is the one ``ProtocolManager``. It outlives any one ``MudConnection``, which is
rebuilt on each connect, and plugins can use its APIs before the MUD connects.

For each message from the MUD, in order: make a ``TelnetProtocolMessage`` record, cache the
value, then raise ``ev_libs.net.mud_gmcp`` (once per GMCP message) or ``ev_libs.net.mud_msdp``
(once per MSDP variable). Each event gets its own copy of the data.

The proxy owns the ``Core`` GMCP package on each link: it sends its own ``Core.Hello`` and a
``Core.Supports.Set`` holding the union of the modules plugins register, and it never caches
``Core.*`` messages.
"""

# Standard Library
import copy
from typing import Any

# 3rd Party
from telnetlib3.telopt import GMCP

# Project
import bastproxy
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net import oob
from bastproxy.libs.records.enums import Direction
from bastproxy.libs.records.events import RecordEventSpec
from bastproxy.libs.records.rtypes.telnet import TelnetProtocolMessage

logger = get_logger(__name__)

API_OWNER = "libs.net.protocols"
API = BASEAPI(owner_id=API_OWNER)

MUD_LINK_ID = "mud"
MUD_GMCP_EVENT = "ev_libs.net.mud_gmcp"
MUD_MSDP_EVENT = "ev_libs.net.mud_msdp"
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
)


class ProtocolManager:
    """Holds the GMCP and MSDP state for the MUD link."""

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
        self._cap_logged = False

        self.api("libs.api:api.add.for.object")(API_OWNER, self)

    # ------------------------------------------------------------------ helpers

    def _caller_owner(self) -> str:
        """The owner id of whoever called an API."""
        return str(self.api("libs.api:caller.owner.get")(ignore_owner_list=[API_OWNER]))

    @staticmethod
    def _record(protocol: str, name: str, data: Any, direction: Direction) -> None:
        """Make a record, never letting a records failure reach the telnet parser."""
        try:
            TelnetProtocolMessage(protocol, name, data, direction, MUD_LINK_ID)
        except Exception:
            logger.exception("Could not record %s %s", protocol, name)

    def _raise(self, event: str, name_arg: str, name: str, data: Any) -> None:
        """Raise ``event`` with its own copy of ``data`` when the events plugin is loaded."""
        try:
            if not self.api("libs.api:api.exists")(EVENT_RAISE_API):
                return
            self.api(EVENT_RAISE_API)(
                event,
                event_args={name_arg: name, "data": copy.deepcopy(data)},
                calledfrom=API_OWNER,
            )
        except Exception:
            logger.exception("Could not raise %s for %s", event, name)

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
        for modules in self._owner_modules.values():
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
        self._cap_logged = False

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
        self._raise(MUD_GMCP_EVENT, "package", package, data)

    def on_mud_msdp(self, variables: dict[str, Any]) -> None:
        """Handle one decoded MSDP message from the MUD: one event per variable."""
        for variable, value in variables.items():
            self._record("MSDP", variable, value, Direction.RECEIVED)
            self._cache_set(self._msdp_cache, variable, value, merge=False)
            self._raise(MUD_MSDP_EVENT, "variable", variable, value)

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


PROTOCOLS = ProtocolManager()
