# Project: bastproxy
# Filename: plugins/core/clients/_clients.py
#
# File Description: a plugin to hold information about clients
#
# By: Bast

# Standard Library
import datetime
import math
from collections.abc import KeysView, ValuesView
from functools import partial

from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net.client import ClientConnection
from bastproxy.libs.records import NetworkDataLine

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult


class BanRecord:
    def __init__(
        self, plugin_id: str, ip_addr: str, how_long: int = 600, copy: bool = False
    ) -> None:
        self.api = API(owner_id=f"{plugin_id}:Ban:{ip_addr}")
        self.plugin_id: str = plugin_id
        self.ip_addr: str = ip_addr
        self.how_long: int = how_long
        self.timer_name = f"{self.plugin_id}_banremove_{self.ip_addr}"
        # the absolute time the ban ends, None for a ban with no expiry (#640)
        self.expires_at: datetime.datetime | None = None

        if not copy and self.how_long > 0:
            self.expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
                seconds=self.how_long
            )
            self._add_timer(self.how_long)

    def _add_timer(self, seconds: float) -> None:
        """Add the one-time timer that lifts the ban."""
        api_call = self.api(f"{self.plugin_id}:client.banned.remove")
        callback = partial(api_call, self.ip_addr, auto=True)
        self.api("plugins.core.timers:timer.add")(
            self.timer_name,
            callback,
            seconds,
            onetime=True,
            plugin_id=self.plugin_id,
        )

    @property
    def has_expired(self) -> bool:
        """True if the ban has an expiry time and it has passed."""
        return self.expires_at is not None and self.expires_at <= datetime.datetime.now(
            datetime.UTC
        )

    @property
    def expires(self) -> str:
        if next_fire := self.api("plugins.core.timers:timer.next.fire.get")(self.timer_name):
            formatted: str = next_fire.strftime(self.api.time_format)
            return formatted
        return "Permanent"

    def remove(self) -> None:
        if self.api("plugins.core.timers:timer.exists")(self.timer_name):
            self.api("plugins.core.timers:timer.remove")(self.timer_name)

    def copy(self, newclass: type["BanRecord"]) -> "BanRecord":
        newrecord = newclass(self.plugin_id, self.ip_addr, self.how_long, copy=True)
        newrecord.timer_name = self.timer_name
        newrecord.expires_at = self.expires_at
        # a reload removed the old plugin's timers, so re-create it for the
        # remaining time (the timer needs at least 1 second); an expired ban
        # is dropped by the caller
        if newrecord.expires_at is not None and not newrecord.has_expired:
            remaining = (newrecord.expires_at - datetime.datetime.now(datetime.UTC)).total_seconds()
            newrecord._add_timer(max(1, math.ceil(remaining)))
        return newrecord


class ClientPlugin(BasePlugin):
    """a plugin to show connection information."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the plugin."""
        self.attributes_to_save_on_reload = ["clients", "banned"]

        self.clients: dict[str, ClientConnection] = {}
        self.banned: dict[str, BanRecord] = {}

    @RegisterPluginHook("after_load")
    def _phook_initialize(self) -> None:
        """Initialize the plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "permbanips",
            [],
            list,
            "A list of IPs that are permanently banned",
            readonly=True,
        )

        self.api("plugins.core.events:event.add")(
            f"ev_{self.plugin_id}_client_logged_in",
            self.plugin_id,
            description=["An event that is raised when a client logs in"],
            arg_descriptions={"client_uuid": "the uuid of the client"},
        )
        self.api("plugins.core.events:event.add")(
            f"ev_{self.plugin_id}_client_logged_in_view_only",
            self.plugin_id,
            description=["An event that is raised when a client logs in as a view client"],
            arg_descriptions={"client_uuid": "the uuid of the client"},
        )
        self.api("plugins.core.events:event.add")(
            f"ev_{self.plugin_id}_client_connected",
            self.plugin_id,
            description=["An event that is raised when a client connects"],
            arg_descriptions={"client_uuid": "the uuid of the client"},
        )
        self.api("plugins.core.events:event.add")(
            f"ev_{self.plugin_id}_client_disconnected",
            self.plugin_id,
            description=["An event that is raised when a client disconnects"],
            arg_descriptions={"client_uuid": "the uuid of the client"},
        )

        # This will only occur if the plugin is reloaded
        # copy the banned ips to the newly loaded class to free up the original objects and class
        if self.banned:
            get_logger(self.plugin_id).debug("Loading %s banned IPs", len(self.banned))
            for item in list(self.banned):
                record = self.banned[item].copy(BanRecord)
                if record.has_expired:
                    del self.banned[item]
                    get_logger(self.plugin_id).error(
                        "%s : ban has timed out and is no longer banned.", item
                    )
                else:
                    self.banned[item] = record

    @AddAPI("client.count", description="return the # of clients connected")
    def _api_client_count(self) -> int:
        """Return the # of clients connected."""
        return len(self.clients)

    @AddAPI("client.get", description="get a client by uuid")
    def _api_client_get(self, client_uuid: str) -> ClientConnection | None:
        """Get a client by uuid."""
        return self.clients.get(client_uuid, None)

    @AddAPI(
        "client.width.get",
        description="get a client's NAWS width, or None if it has not reported one",
    )
    def _api_client_width_get(self, client_uuid: str) -> int | None:
        """Return the width the client reported over NAWS, or None."""
        client = self.clients.get(client_uuid)
        if client is None:
            return None
        try:
            if not client.naws_reported:
                return None
            cols = int(client.cols)
        except Exception:
            get_logger(self.plugin_id).debug(
                "could not read the NAWS width of client %s", client_uuid, exc_info=True
            )
            return None
        return cols if cols > 0 else None

    @AddAPI("client.send", description="send data to a client")
    def _api_client_send(self, client_uuid: str, data: NetworkDataLine) -> None:
        """Send data to a client."""
        if client_uuid in self.clients:
            return self.clients[client_uuid].send_to(data)
        return None

    @AddAPI("client.banned.add", description="add a banned client")
    def _api_client_banned_add(self, client_uuid: str, how_long: int = 600) -> bool:
        """Add a banned client."""
        self.clients[client_uuid].connected = False
        banned: bool = self.api(f"{self.plugin_id}:client.banned.add.by.ip")(
            self.clients[client_uuid].addr, how_long
        )
        return banned

    @AddAPI("client.banned.add.by.ip", description="add a banned ip")
    def _api_client_banned_add_by_ip(self, ip_address: str, how_long: int) -> bool:
        """Add a banned ip."""
        if how_long == -1:
            permbanips = self.api("plugins.core.settings:setting.get")(self.plugin_id, "permbanips")
            if ip_address not in permbanips:
                permbanips.append(ip_address)
                self.api("plugins.core.settings:setting.set")(
                    self.plugin_id, "permbanips", permbanips
                )
                get_logger(self.plugin_id).error(
                    "%s has been banned with no expiration", ip_address
                )
                return True
        elif ip_address not in self.banned:
            ban_record = BanRecord(self.plugin_id, ip_address, how_long=how_long)
            self.banned[ip_address] = ban_record
            get_logger(self.plugin_id).error(
                "%s has been automatically banned for %s seconds", ip_address, how_long
            )
            return True

        return False

    @AddAPI("client.is.banned", description="check if a client is banned")
    def _api_client_is_banned(self, clientip: str) -> bool:
        """Check if a client is banned.

        required
          clientip - the client ip to check
        """
        permbanips = self.api("plugins.core.settings:setting.get")(self.plugin_id, "permbanips")
        return clientip in self.banned or clientip in permbanips

    @AddAPI("client.banned.remove", description="remove a banned ip")
    def _api_client_banned_remove(self, addr: str, auto: bool = False) -> bool:
        """Remove a banned ip."""
        if auto:
            msg = f"{addr} : ban has timed out and is no longer banned."
        else:
            msg = f"{addr} : unbanned through a command."
        if addr in self.banned:
            if not auto:
                self.banned[addr].remove()
            del self.banned[addr]
            get_logger(self.plugin_id).error("%s", msg)
            return True
        permbanips = self.api("plugins.core.settings:setting.get")(self.plugin_id, "permbanips")
        if addr in permbanips:
            permbanips.remove(addr)
            self.api("plugins.core.settings:setting.set")(self.plugin_id, "permbanips", permbanips)
            get_logger(self.plugin_id).error("%s", msg)
            return True

        return False

    @AddAPI("client.is.view.client", description="check if a client is a view client")
    def _api_is_client_view_client(self, client_uuid: str) -> bool:
        """Check if a client is a view client."""
        if client_uuid in self.clients:
            return self.clients[client_uuid].view_only

        return False

    @AddAPI("client.is.logged.in", description="check if a client is logged in")
    def _api_client_is_logged_in(self, client_uuid: str) -> bool:
        """Check if a client is logged in."""
        return bool(client_uuid in self.clients and self.clients[client_uuid].state["logged in"])

    @AddAPI("client.logged.in.set", description="set a client as logged in")
    def _api_client_logged_in_set(self, client_uuid: str) -> None:
        """Set a client as logged in."""
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state["logged in"] = True
            get_logger(self.plugin_id).warning(
                "Client %s logged in from %s:%s",
                client_connection.uuid,
                client_connection.addr,
                client_connection.port,
            )

            self.api("plugins.core.events:event.raise")(
                f"ev_{self.plugin_id}_client_logged_in",
                event_args={"client_uuid": client_connection.uuid},
            )

    @AddAPI(
        "client.logged.in.set.view.only",
        description="set a client as logged in for view only",
    )
    def _api_client_logged_in_set_view_only(self, client_uuid: str) -> None:
        """Set a client as logged in for view only."""
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state["logged in"] = True
            client_connection.view_only = True

            get_logger(self.plugin_id).warning(
                "View Client %s logged in from %s:%s",
                client_connection.uuid,
                client_connection.addr,
                client_connection.port,
            )

            self.api("plugins.core.events:event.raise")(
                f"ev_{self.plugin_id}_client_logged_in_view_only",
                event_args={"client_uuid": client_connection.uuid},
            )

    @AddAPI("client.add", description="add a connected client")
    def _api_client_add(self, client_connection: ClientConnection) -> None:
        """Add a connected client."""
        if client_connection.uuid in self.clients:
            get_logger(self.plugin_id).warning("Client %s already exists", client_connection.uuid)
        self.clients[client_connection.uuid] = client_connection
        self.api("plugins.core.events:event.raise")(
            f"ev_{self.plugin_id}_client_connected",
            event_args={"client_uuid": client_connection.uuid},
        )

    @AddAPI("client.remove", description="remove a connected client")
    def _api_client_remove(self, client_connection: ClientConnection) -> None:
        """Remove a connected client."""
        if client_connection.uuid in self.clients:
            del self.clients[client_connection.uuid]
            self.api("plugins.core.events:event.raise")(
                f"ev_{self.plugin_id}_client_disconnected",
                event_args={"client_uuid": client_connection.uuid},
            )
            get_logger(self.plugin_id).warning(
                "Client %s disconnected %s:%s",
                client_connection.uuid,
                client_connection.addr,
                client_connection.port,
            )

    @AddAPI("client.list", description="list all clients")
    def _api_client_list(
        self, uuid_only: bool = False
    ) -> KeysView[str] | ValuesView[ClientConnection]:
        """List all clients.

        Return the client uuids if uuid_only is set, else the client connections.
        """
        return self.clients.keys() if uuid_only else self.clients.values()

    @AddAPI("client.list.details", description="get details about each connected client")
    def _api_client_list_details(self) -> list[str]:
        """Return a block of details for each connected client."""
        if not self.clients:
            return ["No clients connected"]
        template = "%-29s : %s"
        header = self.api("plugins.core.commands:output.header.format")
        tmsg: list[str] = []
        for client in self.clients.values():
            local_options, remote_options = client.telnet_options()
            if tmsg:
                tmsg.append("")
            tmsg.extend(
                (
                    *header(f"Client {client.addr}:{client.port}"),
                    template % ("State", "View only" if client.view_only else "Active"),
                    template % ("Term Type", client.term_type),
                    template % ("Connected", client.connected_length),
                    template % ("Idle", client.idle),
                    template % ("Lines sent", f"{client.lines_sent:,}"),
                    template % ("Lines received", f"{client.lines_received:,}"),
                    template % ("Bytes sent (uncompressed)", f"{client.bytes_sent:,}"),
                    template % ("Bytes received (uncompressed)", f"{client.bytes_received:,}"),
                    template % ("Local options", ", ".join(local_options) or "-"),
                    template % ("Remote options", ", ".join(remote_options) or "-"),
                )
            )
        return tmsg

    @AddAPI(
        "client.list.formatted",
        description="get the connected and banned clients as formatted tables",
    )
    def _api_client_list_formatted(self) -> list[str]:
        """Return the connected clients and banned ips as formatted tables."""
        tmsg: list[str] = []

        color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )

        clients = [
            {
                "state": "Active",
                "address": client.addr,
                "port": client.port,
                "term_type": client.term_type,
                "connected": client.connected_length,
                "idle": client.idle,
                "view_only": str(client.view_only),
            }
            for client in self.clients.values()
        ]

        clients_columns = [
            {"name": "State", "key": "state", "width": 6},
            {"name": "Client IP", "key": "address", "width": 17},
            {"name": "Port", "key": "port", "width": 7},
            {"name": "Term Type", "key": "term_type", "width": 17},
            {"name": "Connected", "key": "connected", "width": 12},
            {"name": "Idle", "key": "idle", "width": 12},
            {"name": "View Only", "key": "view_only", "width": 8},
        ]

        tmsg.extend(
            self.api("plugins.core.utils:table.format")(
                "Clients", clients, clients_columns, color=color
            )
        )

        banned_clients = [
            {"address": item, "until": self.banned[item].expires} for item in self.banned
        ]
        permbanips = self.api("plugins.core.settings:setting.get")(self.plugin_id, "permbanips")
        banned_clients.extend({"address": item, "until": "Permanent"} for item in permbanips)

        if banned_clients:
            banned_clients_columns = [
                {"name": "Address", "key": "address", "width": 30},
                {"name": "Until", "key": "until", "width": 20},
            ]

            tmsg.append("")
            tmsg.extend(
                self.api("plugins.core.utils:table.format")(
                    "Banned IPs", banned_clients, banned_clients_columns, color=color
                )
            )

        return tmsg

    @AddParser(description="list clients that are connected")
    def _command_show(self) -> CommandResult:
        """Show all clients."""
        return CommandResult(True, self.api(f"{self.plugin_id}:client.list.formatted")())

    @AddParser(description="add or remove a banned ip")
    @AddArgument(
        "ips",
        help="a list of ips to ban or remove (this is a toggle)",
        default=None,
        nargs="*",
    )
    def _command_ban(self) -> CommandResult:
        """Required.

          ips - a list of IPs to ban or remove (this is a toggle).

        if the ip is already banned, it will be unbanned
        otherwise, it will be permanently banned
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        if not args["ips"]:
            return CommandResult(True, ["No IPs specified"])

        removed = []
        added = []

        for ip in args["ips"]:
            if self.api(f"{self.plugin_id}:client.is.banned")(ip):
                if self.api(f"{self.plugin_id}:client.banned.remove")(ip):
                    removed.append(ip)
            elif self.api(f"{self.plugin_id}:client.banned.add.by.ip")(ip, how_long=-1):
                added.append(ip)

        found_ips = set(removed + added)
        not_found = set(args["ips"]) - found_ips

        tmsg: list[str] = []
        if removed:
            tmsg.extend((f"Removed {len(removed)} IPs from the ban list", ", ".join(removed)))
        if added:
            tmsg.extend((f"Added {len(added)} IPs to the ban list", ", ".join(added)))
        if not_found:
            tmsg.extend((f"{len(not_found)} IPs were not acted on", ", ".join(not_found)))

        if not tmsg:
            tmsg = ["No changes made"]

        return CommandResult(True, tmsg)
