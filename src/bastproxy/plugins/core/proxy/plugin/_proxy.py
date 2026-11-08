# Project: bastproxy
# Filename: plugins/core/proxy/_proxy.py
#
# File Description: a plugin to handle settings and information about the proxy
#
# By: Bast

# Standard Library
import datetime
import os
import platform
import signal
import sys
import time
from pathlib import Path
from typing import Any

# 3rd Party
try:
    import psutil
except ImportError:
    print("Please install required libraries. psutil is missing.")
    print("From the root of the project: uv sync --all-extras")
    sys.exit(1)
try:
    import humanize
except ImportError:
    print("Please install required libraries. humanize is missing.")
    print("From the root of the project: uv sync --all-extras")
    sys.exit(1)

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.net.mud import MudConnection
from bastproxy.libs.records import (
    LogRecord,
    NetworkData,
    NetworkDataLine,
    SendDataDirectlyToClient,
    SendDataDirectlyToMud,
)
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser
from bastproxy.plugins.core.events import RegisterToEvent


def is_connected_address(raddr: Any) -> bool:
    """Return True if a psutil connection's remote address is a populated address.

    psutil reports ``raddr`` as an ``(ip, port)`` named tuple for a connected
    socket and as an empty tuple otherwise. The named tuple type lives in a
    private psutil module whose location changes between releases, so check
    its shape instead of its type.

    Args:
        raddr: The ``raddr`` field of a psutil connection.

    Returns:
        True if ``raddr`` is a non-empty tuple with ``ip`` and ``port`` fields.

    """
    return (
        isinstance(raddr, tuple)
        and len(raddr) > 0
        and hasattr(raddr, "ip")
        and hasattr(raddr, "port")
    )


class ProxyPlugin(BasePlugin):
    """a plugin to show connection information."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.proxypw = None
        self.proxyvpw = None
        self.mudpw = None
        self.mud_connection: MudConnection | None = None
        self.attributes_to_save_on_reload = ["mud_connection"]

    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        """Initialize the plugin."""
        restartproxymessage = "@RPlease restart the proxy for the changes to take effect.@w"

        # Network Settings
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "listenport",
            9999,
            int,
            "the port for the proxy to listen on",
            aftersetmessage=restartproxymessage,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "ipv4",
            True,
            bool,
            "add an IPv4 listener",
            aftersetmessage=restartproxymessage,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "ipv4address",
            "localhost",
            str,
            "the IPv4 hostname to bind to",
            aftersetmessage=restartproxymessage,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "ipv6",
            False,
            bool,
            "add an IPv6 listener",
            aftersetmessage=restartproxymessage,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "ipv6address",
            "ip6-localhost",
            str,
            "the IPv6 hostname to bind to",
            aftersetmessage=restartproxymessage,
        )

        # Mud Settings
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "mudhost", "", str, "the hostname/ip of the mud"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "mudport", 0, int, "the port of the mud"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "username", "", str, "the mud username"
        )

        # Output and Command Settings
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "linelen",
            80,
            int,
            "the line length for internal output data, does not affect data that comes from the mud or clients",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "preamble", "#BP", str, "the preamble for any proxy output"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "preamblecolor", "@C", "color", "the preamble color"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "preambleerrorcolor",
            "@R",
            "color",
            "the preamble color for an error line",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "cmdseperator",
            "|",
            str,
            "the seperator for sending multiple commands",
        )

        self.api("plugins.core.events:event.add")(
            f"ev_{self.plugin_id}_shutdown",
            self.plugin_id,
            description=["event when the proxy is shutting down"],
            arg_descriptions={"None": None},
        )

        ssc = self.api("plugins.core.ssc:baseclass.get")()
        self.proxypw = ssc(
            "proxypw",
            self.plugin_id,
            self.plugin_info.data_directory,
            desc="Proxy password",
            default="defaultpass",
        )
        self.proxyvpw = ssc(
            "proxypwview",
            self.plugin_id,
            self.plugin_info.data_directory,
            desc="Proxy View password",
            default="defaultviewpass",
        )
        self.mudpw = ssc(
            "mudpw",
            self.plugin_id,
            self.plugin_info.data_directory,
            desc="Mud password",
        )

    @AddAPI("mud.is.connected", description="check if the mud is connected")
    def _api_mud_is_connected(self) -> bool:
        """Check if the mud is connected."""
        return bool(self.mud_connection and self.mud_connection.connected)

    @AddAPI("mud.connection.get", description="get the mud connection")
    def _api_mud_connection_get(self) -> MudConnection | None:
        """Get the mud connection."""
        return self.mud_connection

    @AddAPI("preamble.get", description="get the preamble")
    def _api_preamble_get(self):
        """Get the preamble."""
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, "preamble")

    @AddAPI("preamble.color.get", description="get the preamble color")
    def _api_preamble_color_get(self, error=False):
        """Get the preamble color."""
        if error:
            return self.api("plugins.core.settings:setting.get")(
                self.plugin_id, "preambleerrorcolor"
            )
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, "preamblecolor")

    @RegisterToEvent(event_name="ev_libs.net.mud_mudconnect")
    def _eventcb_sendusernameandpw(self):
        """If username and password are set, then send them when the proxy.

        connects to the mud.
        """
        if self.api("plugins.core.settings:setting.get")(self.plugin_id, "username") != "":
            SendDataDirectlyToMud(
                NetworkData(
                    self.api("plugins.core.settings:setting.get")(self.plugin_id, "username")
                ),
                show_in_history=False,
            )()
            pasw = self.api(f"{self.plugin_id}:ssc.mudpw.get")()
            if pasw != "":
                SendDataDirectlyToMud(NetworkData(pasw))()

    @AddParser(description="list proxy info")
    def _command_info(self):
        """Show info about the proxy."""
        template = "%-15s : %s"
        started = "Unknown"
        if self.api.proxy_start_time:
            started = self.api.proxy_start_time.strftime(self.api.time_format)

        uptime = self.api("plugins.core.utils:timedelta.to.string")(
            self.api.proxy_start_time, datetime.datetime.now(datetime.UTC)
        )

        tmsg = [
            *(
                *self.api("plugins.core.commands:output.header.format")("Proxy Info"),
                template % ("Started", started),
                template % ("Uptime", uptime),
                "",
                *self.api("plugins.core.commands:output.header.format")("Mud Info"),
            ),
        ]
        if self.mud_connection and self.mud_connection.connected:
            if self.mud_connection.connected_time:
                tmsg.extend(
                    (
                        template
                        % (
                            "Connected",
                            self.mud_connection.connected_time.strftime(self.api.time_format),
                        ),
                        template
                        % (
                            "Uptime",
                            self.api("plugins.core.utils:timedelta.to.string")(
                                self.mud_connection.connected_time,
                                datetime.datetime.now(datetime.UTC),
                            ),
                        ),
                        template % ("Host", self.mud_connection.addr),
                        template % ("Port", self.mud_connection.port),
                        template % ("Options", ""),
                    )
                )
                # options = self.mud_connection.options_info()
                # tmsg.extend(f"     {i}" for i in options)
        else:
            tmsg.append(template % ("Mud", "disconnected"))

        tmsg.append("")

        tmsg.extend(self.api("plugins.core.clients:client.list.formatted")())
        return True, tmsg

    @AddParser(description="disconnect from the mud")
    def _command_disconnect(self):
        """Disconnect from the mud."""
        if self.mud_connection and self.mud_connection.connected:
            self.mud_connection.disconnect_from_mud()
            self.mud_connection = None

            return True, ["Attempted to close the connection to the mud"]
        return True, ["The proxy is not connected to the mud"]

    @AddParser(description="connect to the mud")
    def _command_connect(self):
        """Connect to the mud."""
        if self.mud_connection and self.mud_connection.connected:
            return True, ["The proxy is currently connected to the mud"]

        self.mud_connection = MudConnection(
            self.api("plugins.core.settings:setting.get")(self.plugin_id, "mudhost"),
            self.api("plugins.core.settings:setting.get")(self.plugin_id, "mudport"),
        )

        self.api("libs.asynch:task.add")(self.mud_connection.connect_to_mud, "Mud Connect Task")

        return True, ["Connecting to the mud"]

    @AddAPI("proxy.shutdown", description="shutdown the proxy")
    def _api_proxy_shutdown(self):
        """Shutdown the proxy."""
        self.api.__class__.shutdown = True
        LogRecord(
            "Proxy: shutdown started",
            level="info",
            sources=[self.plugin_id, "shutdown"],
        )()
        SendDataDirectlyToClient(
            NetworkData(
                [NetworkDataLine("Shutting down proxy")],
                owner_id=f"{self.plugin_id}:_api_proxy_shutdown",
            )
        )()
        self.api("plugins.core.events:event.raise")(f"ev_{self.plugin_id}_shutdown")
        LogRecord(
            "Proxy: shutdown complete",
            level="info",
            sources=[self.plugin_id, "shutdown"],
        )()

    @AddParser(description="shutdown the proxy")
    def _command_shutdown(self):
        """Shutdown the proxy."""
        signal.raise_signal(signal.SIGINT)

    @AddCommand(format=False)
    @AddParser(description="restart the proxy")
    @AddArgument(
        "-s",
        "--seconds",
        type=int,
        default=10,
        help="# of seconds to wait before restart",
    )
    def _command_restart(self):
        """Restart the proxy."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        listen_port = self.api("plugins.core.settings:setting.get")(self.plugin_id, "listenport")
        self.api(f"{self.plugin_id}:proxy.restart")(args["seconds"])
        return True, [f"Restarting bastproxy on port: {listen_port} in {args['seconds']} seconds"]

    @RegisterToEvent(event_name="ev_plugins.core.clients_client_logged_in")
    def _eventcb_client_logged_in(self):
        """Check for mud settings."""
        if not self.api("plugins.core.events:event.current.record.get")():
            return
        tmsg = []
        divider = "@R------------------------------------------------@w"
        if not self.mud_connection or not self.mud_connection.connected:
            if not self.api("plugins.core.settings:setting.get")(self.plugin_id, "mudhost"):
                tmsg.extend(
                    (
                        divider,
                        "Please set the mudhost.",
                        f"{self.api('plugins.core.commands:command.format')(self.plugin_id, 'set')} mudhost 'host'",
                    )
                )
            if self.api("plugins.core.settings:setting.get")(self.plugin_id, "mudport") == 0:
                tmsg.extend(
                    (
                        divider,
                        "Please set the mudport.",
                        f"{self.api('plugins.core.commands:command.format')(self.plugin_id, 'set')} mudport 'port'",
                    )
                )
            tmsg.extend(
                (
                    divider,
                    f"Connect to the mud with {self.api('plugins.core.commands:command.format')(self.plugin_id, 'connect')}",
                )
            )
        else:
            tmsg.extend(
                (
                    divider,
                    f"{self.api(f'{self.plugin_id}:preamble.color.get')(error=True)}{self.api(f'{self.plugin_id}:preamble.get')()}: @GThe proxy is already connected to the mud@w",
                )
            )
        if self.api(f"{self.plugin_id}:ssc.proxypw.get")(quiet=True) == "defaultpass":
            tmsg.extend(
                (
                    divider,
                    "The proxy password is still the default password.",
                    "Please set the proxy password!",
                    f"{self.api('plugins.core.commands:command.format')(self.plugin_id, 'proxypw')} 'This is a password'",
                )
            )
        if self.api(f"{self.plugin_id}:ssc.proxypwview.get")(quiet=True) == "defaultviewpass":
            tmsg.extend(
                (
                    divider,
                    "The proxy view password is still the default password.",
                    "Please set the proxy view password!",
                    f"{self.api('plugins.core.commands:command.format')(self.plugin_id, 'proxypwview')} 'This is a view password'",
                )
            )
        if tmsg[-1] != divider:
            tmsg.append(divider)
        if tmsg[0] != divider:
            tmsg.insert(0, divider)

        if tmsg:
            new_message = NetworkData(tmsg, owner_id=f"{self.plugin_id}:_eventcb_client_logged_in")
            SendDataDirectlyToClient(new_message)()

    @AddAPI("proxy.restart", description="restart the proxy")
    def _api_proxy_restart(self, restart_in=None):
        """Restart the proxy after 10 seconds."""
        restart_in = restart_in or 10
        listen_port = self.api("plugins.core.settings:setting.get")(self.plugin_id, "listenport")

        SendDataDirectlyToClient(
            NetworkData(
                [f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds"],
                owner_id=f"{self.plugin_id}:_api_proxy_restart",
            )
        )()
        LogRecord(
            f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds",
            level="warning",
            sources=[self.plugin_id],
        )()

        self.api("plugins.core.timers:timer.add")(
            "restart", self.timer_restart, restart_in, onetime=True
        )

    def timer_restart(self):
        """A function to restart the proxy after a timer."""
        self.api("plugins.core.pluginm:plugin.state.save.all")()

        self.api(f"{self.plugin_id}:proxy.shutdown")()

        time.sleep(5)

        os.execv(sys.executable, [Path(sys.executable).name, *sys.argv])

    @RegisterToEvent(event_name="ev_{plugin_id}_var_cmdseperator_modified")
    def _eventcb_command_seperator_change(self):
        """Update the command regex."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            newsep = event_record["newvalue"]

            self.api.__class__.command_split_regex = r"(?<=[^{}]){}(?=[^{}])".format(
                "\\" + newsep,
                "\\" + newsep,
                "\\" + newsep,
            )

    @AddParser(description="output proxy resource usage")
    @AddArgument(
        "-ni",
        "--networkinterfaces",
        help="show network interfaces in output",
        action="store_false",
        default=True,
    )
    @AddArgument(
        "-of",
        "--openfiles",
        help="show open files in output",
        action="store_false",
        default=True,
    )
    @AddArgument("-p", "--ports", help="show network ports", action="store_false", default=True)
    def _command_resource(self):
        """Output proxy resource usage."""
        args = self.api("plugins.core.commands:command.current.args.get")()

        cpu_percent = psutil.cpu_percent()
        virtual_memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count()
        load_average = os.getloadavg()
        net_if_addrs = psutil.net_if_addrs()
        column_width = 19
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        net_connections = process.net_connections(kind="inet")
        open_files = process.open_files()

        uname = platform.uname()

        msg = [
            *self.api("plugins.core.commands:output.header.format")("OS Info"),
            f"{'OS':<{column_width}} : {uname.system}",
            f"{'Hostname':<{column_width}} : {uname.node}",
            f"{'Platform':<{column_width}} : {platform.platform()}",
            *self.api("plugins.core.commands:output.header.format")("Python Info"),
            f"{'Python Version':<{column_width}} : {platform.python_version()}",
            f"{'Python Path':<{column_width}} :",
            *[f"     {i}" for i in sys.path],
            *self.api("plugins.core.commands:output.header.format")("CPU Info"),
            f"{'CPU Percent':<{column_width}} : {cpu_percent}",
            f"{'CPU Count':<{column_width}} : {cpu_count}",
            *self.api("plugins.core.commands:output.header.format")("Load Info"),
            f"{'1 Minute':<{column_width}} : {load_average[0]}",
            f"{'5 Minute':<{column_width}} : {load_average[1]}",
            f"{'15 Minute':<{column_width}} : {load_average[2]}",
            *self.api("plugins.core.commands:output.header.format")("Memory Info"),
            f"{'Total':<{column_width}} : {humanize.naturalsize(virtual_memory.total, binary=True)}",
            f"{'Available':<{column_width}} : {humanize.naturalsize(virtual_memory.available, binary=True)}",
            f"{'Used':<{column_width}} : {humanize.naturalsize(virtual_memory.used, binary=True)}",
            f"{'Used Percent':<{column_width}} : {virtual_memory.percent}%",
            *self.api("plugins.core.commands:output.header.format")("Process Info"),
            f"{'CPU Percentage':<{column_width}} : {process.cpu_percent()}",
            f"{'Memory Percentage':<{column_width}} : {process.memory_percent():.2}%",
            f"{'Memory RSS':<{column_width}} : {humanize.naturalsize(mem_info.rss, binary=True)}",
            f"{'Memory VMS':<{column_width}} : {humanize.naturalsize(mem_info.vms, binary=True)}",
            *self.api("plugins.core.commands:output.header.format")("Network Info"),
        ]

        if args["networkinterfaces"]:
            nic_addresses = []
            for nic in net_if_addrs:
                nic_addresses.extend(
                    {"nic": nic, "address": addr.address, "type": addr.family.name}
                    for addr in net_if_addrs[nic]
                )

            nic_addresses_columns = [
                {"name": "NIC", "key": "nic", "width": 10},
                {"name": "Address", "key": "address", "width": 40},
                {"name": "Type", "key": "type", "width": 10},
            ]

            msg.extend(
                [
                    *self.api("plugins.core.utils:table.format")(
                        "Network Addresses", nic_addresses, nic_addresses_columns
                    ),
                ]
            )

        if args["ports"]:
            connected_port_columns = [
                {"name": "Local Address", "key": "local_address", "width": 20},
                {"name": "Local Port", "key": "local_port", "width": 11},
                {"name": "Remote Address", "key": "remote_address", "width": 20},
                {"name": "Remote Port", "key": "remote_port", "width": 12},
                {"name": "Status", "key": "status", "width": 7},
            ]
            listening_port_columns = [
                {"name": "Local Address", "key": "local_address", "width": 20},
                {"name": "Local Port", "key": "local_port", "width": 11},
                {"name": "Status", "key": "status", "width": 7},
            ]

            listening_ports_dicts = []
            connected_ports_dicts = []
            for conn in net_connections:
                if conn.status == "LISTEN":
                    listening_ports_dicts.append(
                        {
                            "local_address": conn.laddr.ip,
                            "local_port": conn.laddr.port,
                            "status": conn.status,
                        }
                    )
                elif is_connected_address(conn.raddr):
                    connected_ports_dicts.append(
                        {
                            "local_address": conn.laddr.ip,
                            "local_port": conn.laddr.port,
                            "remote_address": conn.raddr.ip,
                            "remote_port": conn.raddr.port,
                            "status": conn.status,
                        }
                    )

            msg.extend(
                [
                    "",
                    *self.api("plugins.core.utils:table.format")(
                        "Listening Ports", listening_ports_dicts, listening_port_columns
                    ),
                    "",
                    *self.api("plugins.core.utils:table.format")(
                        "Connected Ports", connected_ports_dicts, connected_port_columns
                    ),
                ]
            )

        if args["openfiles"]:
            open_files_columns = [
                {"name": "File", "key": "path", "width": 60},
                {"name": "Mode", "key": "mode", "width": 5},
            ]

            open_files_dicts = [
                {"path": file.path, "mode": file.mode}
                for file in open_files  # pyright: ignore[reportAttributeAccessIssue]
            ]

            msg.extend(
                [
                    "",
                    *self.api("plugins.core.utils:table.format")(
                        "Open Files", open_files_dicts, open_files_columns
                    ),
                ]
            )

        return True, msg
