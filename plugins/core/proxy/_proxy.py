# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/proxy/_proxy.py
#
# File Description: a plugin to handle settings and information about the proxy
#
# By: Bast

# Standard Library
import time
import os
import sys
import platform
import datetime
import signal

# 3rd Party
try:
    import psutil
except ImportError:
    print('Please install required libraries. psutil is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)
try:
    import humanize
except ImportError:
    print('Please install required libraries. humanize is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
from libs.net.mud import MudConnection
from plugins._baseplugin import BasePlugin
from libs.records import ToClientRecord, LogRecord, ToMudRecord
from libs.commands import AddCommand, AddParser, AddArgument
from libs.event import RegisterToEvent
from libs.api import AddAPI

class ProxyPlugin(BasePlugin):
    """
    a plugin to show connection information
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.api(f"{self.plugin_id}:dependency.add")('core.ssc')

        self.proxypw = None
        self.proxyvpw = None
        self.mudpw = None
        self.mud_connection = None

    def initialize(self):
        """
        initialize the plugin
        """
        super().initialize()

        restartproxymessage = "@RPlease restart the proxy for the changes to take effect.@w"

        # Network Settings
        self.api('plugins.core.settings:add')(self.plugin_id, 'listenport', 9999, int,
                                'the port for the proxy to listen on',
                                aftersetmessage=restartproxymessage)
        self.api('plugins.core.settings:add')(self.plugin_id, 'ipv4', True, bool,
                                'add an IPv4 listener',
                                aftersetmessage=restartproxymessage)
        self.api('plugins.core.settings:add')(self.plugin_id, 'ipv4address', 'localhost', str,
                                'the IPv4 hostname to bind to',
                                aftersetmessage=restartproxymessage)
        self.api('plugins.core.settings:add')(self.plugin_id, 'ipv6', False, bool,
                                'add an IPv6 listener',
                                aftersetmessage=restartproxymessage)
        self.api('plugins.core.settings:add')(self.plugin_id, 'ipv6address', 'ip6-localhost', str,
                                'the IPv6 hostname to bind to',
                                aftersetmessage=restartproxymessage)

        # Mud Settings
        self.api('plugins.core.settings:add')(self.plugin_id, 'mudhost', '', str,
                                'the hostname/ip of the mud')
        self.api('plugins.core.settings:add')(self.plugin_id, 'mudport', 0, int,
                                'the port of the mud')
        self.api('plugins.core.settings:add')(self.plugin_id, 'username', '', str,
                                'the mud username')

        # Output and Command Settings
        self.api('plugins.core.settings:add')(self.plugin_id, 'linelen', 80, int,
                                'the line length for internal output data, does not affect data that comes from the mud or clients')
        self.api('plugins.core.settings:add')(self.plugin_id, 'preamble', '#BP', str,
                                'the preamble for any proxy output')
        self.api('plugins.core.settings:add')(self.plugin_id, 'preamblecolor', '@C', 'color',
                                'the preamble color')
        self.api('plugins.core.settings:add')(self.plugin_id, 'preambleerrorcolor', '@R', 'color',
                                'the preamble color for an error line')
        self.api('plugins.core.settings:add')(self.plugin_id, 'cmdseperator', '|', str,
                                'the seperator for sending multiple commands')

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_shutdown", self.plugin_id,
                                                  description=['event when the proxy is shutting down'],
                                                  arg_descriptions={'None': None})

        ssc = self.api('plugins.core.ssc:baseclass.get')()
        self.proxypw = ssc('proxypw', self.plugin_id, self.plugin_info.data_directory, desc='Proxy password',
                           default='defaultpass')
        self.proxyvpw = ssc('proxypwview', self.plugin_id, self.plugin_info.data_directory, desc='Proxy View password',
                            default='defaultviewpass')
        self.mudpw = ssc('mudpw', self.plugin_id, self.plugin_info.data_directory, desc='Mud password')

    @AddAPI('get.mud.connection', description='get the mud connection')
    def _api_get_mud_connection(self) -> MudConnection:
        """
        get the mud connection
        """
        if not self.mud_connection:
            self.mud_connection = MudConnection(self.api('plugins.core.settings:get')(self.plugin_id, 'mudhost'),
                                                self.api('plugins.core.settings:get')(self.plugin_id, 'mudport'))

        return self.mud_connection

    @AddAPI('preamble.get', description='get the preamble')
    def _api_preamble_get(self):
        """
        get the preamble
        """
        return self.api('plugins.core.settings:get')(self.plugin_id, 'preamble')

    @AddAPI('preamble.color.get', description='get the preamble color')
    def _api_preamble_color_get(self, error=False):
        """
        get the preamble color
        """
        if error:
            return self.api('plugins.core.settings:get')(self.plugin_id, 'preambleerrorcolor')
        else:
            return self.api('plugins.core.settings:get')(self.plugin_id, 'preamblecolor')

    @RegisterToEvent(event_name='ev_libs.net.mud_mudconnect')
    def _eventcb_sendusernameandpw(self):
        """
        if username and password are set, then send them when the proxy
        connects to the mud
        """
        if self.api('plugins.core.settings:get')(self.plugin_id, 'username') != '':
            ToMudRecord(self.api('plugins.core.settings:get')(self.plugin_id, 'username'), internal=True, show_in_history=False)()
            pasw = self.api(f"{self.plugin_id}:ssc.mudpw")()
            if pasw != '':
                ToMudRecord([pasw, '\n'], internal=True, show_in_history=False)()

    @AddParser(description='list proxy info')
    def _command_info(self):
        """
        show info about the proxy
        """
        template = '%-15s : %s'
        mud = self.api('plugins.core.managers:get')('mud')
        started = 'Unknown'
        if self.api.proxy_start_time:
            started = self.api.proxy_start_time.strftime(self.api.time_format)

        uptime = self.api('plugins.core.utils:convert.timedelta.to.string')(
            self.api.proxy_start_time,
            datetime.datetime.now(datetime.timezone.utc))

        tmsg = [
            *(
                '@B-------------------  Proxy ------------------@w',
                template % ('Started', started),
                template % ('Uptime', uptime),
                template % ('Python Version', platform.python_version()),
                '',
                '@B-------------------   Mud  ------------------@w',
            ),
        ]
        if mud and mud.connected:
            if mud.connected_time:
                tmsg.extend(
                    (
                        template
                        % (
                            'Connected',
                            mud.connected_time.strftime(self.api.time_format),
                        ),
                        template
                        % (
                            'Uptime',
                            self.api(
                                'plugins.core.utils:convert.timedelta.to.string'
                            )(
                                mud.connected_time,
                                datetime.datetime.now(datetime.timezone.utc),
                            ),
                        ),
                        template % ('Host', mud.host),
                        template % ('Port', mud.port),
                        template % ('Options', ''),
                    )
                )
                options = mud.options_info()
                tmsg.extend(f"     {i}" for i in options)
        else:
            tmsg.append(template % ('Mud', 'disconnected'))

        clients = self.api('plugins.core.clients:get.all.clients')()

        # client.view_only
        aclients = [client for client in clients if not client.view_only]
        vclients = [client for client in clients if client.view_only]

        tmsg.extend(
            (
                '',
                '@B-----------------   Clients  ----------------@w',
                template % ('Clients', len(aclients)),
                template % ('View Clients', len(vclients)),
                '@B---------------------------------------------@w',
            )
        )
        _, nmsg = self.api('plugins.core.commands:run')('plugins.core.clients', 'show', '')

        del nmsg[0]
        tmsg.extend(nmsg)
        return True, tmsg

    @AddParser(description='disconnect from the mud')
    def _command_disconnect(self):
        """
        disconnect from the mud
        """
        mud = self.api('plugins.core.managers:get')('mud')
        if mud.connected:
            mud.handle_close()

            return True, ['Attempted to close the connection to the mud']
        else:
            return True, ['The proxy is not connected to the mud']

    @AddParser(description='connect to the mud')
    def _command_connect(self):
        """
        disconnect from the mud
        """
        mud = self.api('plugins.core.managers:get')('mud')
        if mud.connected:
            return True, ['The proxy is currently connected to the mud']

        mud.connectmud(self.api('plugins.core.settings:get')(self.plugin_id, 'mudhost'),
                       self.api('plugins.core.settings:get')(self.plugin_id, 'mudport'))

        return True, ['Connecting to the mud']

    @AddAPI('shutdown', description='shutdown the proxy')
    def _api_shutdown(self):
        """
        shutdown the proxy
        """
        self.api.__class__.shutdown = True
        LogRecord('Proxy: shutdown started', level='info', sources=[self.plugin_id, 'shutdown'])()
        ToClientRecord('Shutting down proxy')(f'{self.plugin_id}:_api_shutdown')
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_shutdown")
        LogRecord('Proxy: shutdown complete', level='info', sources=[self.plugin_id, 'shutdown'])()

    @AddParser(description='shutdown the proxy')
    def _command_shutdown(self):
        """
        shutdown the proxy
        """
        signal.raise_signal( signal.SIGINT )

    @AddCommand(format=False)
    @AddParser(description='restart the proxy')
    @AddArgument('-s',
                    '--seconds',
                    type=int,
                    default=10,
                    help='# of seconds to wait before restart')
    def _command_restart(self):
        """
        restart the proxy
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        listen_port = self.api('plugins.core.settings:get')(self.plugin_id, 'listenport')
        self.api(f"{self.plugin_id}:restart")(args['seconds'])
        return True, [f"Restarting bastproxy on port: {listen_port} in {args['seconds']} seconds"]

    @RegisterToEvent(event_name='ev_plugins.core.clients_client_logged_in')
    def _eventcb_client_logged_in(self):
        """
        check for mud settings
        """
        if not (
            event_record := self.api(
                'plugins.core.events:get.current.event.record'
            )()
        ):
            return
        tmsg = []
        divider = '@R------------------------------------------------@w'
        if not self.mud_connection or not self.mud_connection.connected:
            if not self.api('plugins.core.settings:get')(self.plugin_id, 'mudhost'):
                tmsg.extend(
                    (
                        divider,
                        'Please set the mudhost.',
                        f"{self.api('plugins.core.commands:get.command.format')(self.plugin_id, 'set')} mudhost 'host'",
                    )
                )
            if self.api('plugins.core.settings:get')(self.plugin_id, 'mudport') == 0:
                tmsg.extend(
                    (
                        divider,
                        'Please set the mudport.',
                        f"{self.api('plugins.core.commands:get.command.format')(self.plugin_id, 'set')} mudport 'port'",
                    )
                )
            tmsg.extend(
                (
                    divider,
                    f"Connect to the mud with {self.api('plugins.core.commands:get.command.format')(self.plugin_id, 'connect')}",
                )
            )
        else:
            tmsg.extend(
                (
                    divider,
                    f"{self.api(f'{self.plugin_id}:preamble.color.get')(error=True)}{self.api(f'{self.plugin_id}:preamble.get')()}: @GThe proxy is already connected to the mud@w",
                )
            )
        if self.api(f"{self.plugin_id}:ssc.proxypw")(quiet=True) == 'defaultpass':
            tmsg.extend(
                (
                    divider,
                    'The proxy password is still the default password.',
                    'Please set the proxy password!',
                    f"{self.api('plugins.core.commands:get.command.format')(self.plugin_id, 'proxypw')} 'This is a password'",
                )
            )
        if self.api(f"{self.plugin_id}:ssc.proxypwview")(quiet=True) == 'defaultviewpass':
            tmsg.extend(
                (
                    divider,
                    'The proxy view password is still the default password.',
                    'Please set the proxy view password!',
                    f"{self.api('plugins.core.commands:get.command.format')(self.plugin_id, 'proxypwview')} 'This is a view password'",
                )
            )
        if tmsg[-1] != divider:
            tmsg.append(divider)
        if tmsg[0] != divider:
            tmsg.insert(0, divider)


        if tmsg:
            ToClientRecord(tmsg, clients=[event_record['client_uuid']])(
                f'{self.plugin_id}:client_connected'
            )

    @AddAPI('restart', description='restart the proxy')
    def _api_restart(self, restart_in=None):
        """
        restart the proxy after 10 seconds
        """
        restart_in = restart_in or 10
        listen_port = self.api('plugins.core.settings:get')(self.plugin_id, 'listenport')

        ToClientRecord(
            f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds"
        )(f'{self.plugin_id}:_api_restart')
        LogRecord(f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds", level='warning', sources=[self.plugin_id])()

        self.api('plugins.core.timers:add.timer')('restart', self.timer_restart, restart_in, onetime=True)

    def timer_restart(self):
        """
        a function to restart the proxy after a timer
        """
        self.api('plugins.core.pluginm:save.all.plugins.state')()

        self.api(f"{self.plugin_id}:shutdown")()

        time.sleep(5)

        os.execv(sys.executable, [os.path.basename(sys.executable)] + sys.argv)

    @RegisterToEvent(event_name="ev_{plugin_id}_var_cmdseperator_modified")
    def _eventcb_command_seperator_change(self):
        """
        update the command regex
        """
        if event_record := self.api('plugins.core.events:get.current.event.record')():
            newsep = event_record['newvalue']

            self.api.__class__.command_split_regex = r"(?<=[^%s])%s(?=[^%s])" % ('\\' + newsep, '\\' + newsep, '\\' + newsep)

    @AddParser(description='output proxy resource usage')
    def _command_resource(self):
        """
        output proxy resource usage
        """
        cpu_percent = psutil.cpu_percent()
        virtual_memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count()
        load_average = os.getloadavg()
        net_connections = psutil.net_connections(kind='inet')
        net_if_addrs = psutil.net_if_addrs()
        proxy_port = self.api('plugins.core.settings:get')(self.plugin_id, 'listenport')
        line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        output_header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        output_subheader_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')
        column_width = 19

        msg = [
            *self.api('plugins.core.commands:format.output.header')('CPU Info'),
            f'{"CPU Percent":<{column_width}} : {cpu_percent}',
            f'{"CPU Count":<{column_width}} : {cpu_count}',
            *self.api('plugins.core.commands:format.output.header')('Load Info'),
            f'{"1 Minute":<{column_width}} : {load_average[0]}',
            f'{"5 Minute":<{column_width}} : {load_average[1]}',
            f'{"15 Minute":<{column_width}} : {load_average[2]}',
            *self.api('plugins.core.commands:format.output.header')('Memory Info'),
            f'{"Total":<{column_width}} : {humanize.naturalsize(virtual_memory.total, binary=True)}',
            f'{"Available":<{column_width}} : {humanize.naturalsize(virtual_memory.available, binary=True)}',
            f'{"Used":<{column_width}} : {humanize.naturalsize(virtual_memory.used, binary=True)}',
            f'{"Used Percent":<{column_width}} : {virtual_memory.percent}%',
            *self.api('plugins.core.commands:format.output.header')('Network Info'),
        ]

        nic_addesses_columns = [
            {'name': 'NIC', 'key': 'nic', 'width': 10},
            {'name': 'Address', 'key': 'address', 'width': 40},
            {'name': 'Type', 'key': 'type', 'width': 10},
        ]

        nic_addresses = []
        for nic in net_if_addrs:
            nic_addresses.extend(
                {'nic': nic, 'address': addr.address, 'type': addr.family.name}
                for addr in net_if_addrs[nic]
            )

        connected_port_columns = [
            {'name': 'Local Address', 'key': 'local_address', 'width': 20},
            {'name': 'Local Port', 'key': 'local_port', 'width': 11},
            {'name': 'Remote Address', 'key': 'remote_address', 'width': 20},
            {'name': 'Remote Port', 'key': 'remote_port', 'width': 12},
            {'name': 'Status', 'key': 'status', 'width': 7},
        ]
        listening_port_columns = [
            {'name': 'Local Address', 'key': 'local_address', 'width': 20},
            {'name': 'Local Port', 'key': 'local_port', 'width': 11},
            {'name': 'Status', 'key': 'status', 'width': 7},
        ]

        listening_ports_dicts = []
        connected_ports_dicts = []
        for conn in net_connections:
            if conn.laddr[1] == proxy_port:
                if conn.status == 'LISTEN':
                    listening_ports_dicts.append({'local_address': conn.laddr.ip,
                                                  'local_port': conn.laddr.port,
                                                  'status': conn.status})
                else:
                    connected_ports_dicts.append({'local_address': conn.laddr.ip,
                                                  'local_port': conn.laddr.port,
                                                  'remote_address': conn.raddr.ip,
                                                  'remote_port': conn.raddr.port,
                                                  'status': conn.status})

        msg.extend(
            [
                *self.api('plugins.core.utils:convert.data.to.output.table')('Network Addresses', nic_addresses, nic_addesses_columns),
                '',
                *self.api('plugins.core.utils:convert.data.to.output.table')('Listening Ports', listening_ports_dicts, listening_port_columns),
                '',
                *self.api('plugins.core.utils:convert.data.to.output.table')('Connected Ports', connected_ports_dicts, connected_port_columns),
            ]
        )

        return True, msg
