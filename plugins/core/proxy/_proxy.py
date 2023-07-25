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

        self.api('plugins.core.settings:add')(self.plugin_id, 'mudhost', '', str,
                                'the hostname/ip of the mud')
        self.api('plugins.core.settings:add')(self.plugin_id, 'mudport', 0, int,
                                'the port of the mud')
        self.api('plugins.core.settings:add')(self.plugin_id, 'listenport', 9999, int,
                                'the port for the proxy to listen on')
        self.api('plugins.core.settings:add')(self.plugin_id, 'username', '', str,
                                'the mud username')
        self.api('plugins.core.settings:add')(self.plugin_id, 'linelen', 80, int,
                                'the line length for internal output data, does not affect data that comes from the mud or clients')
        self.api('plugins.core.settings:add')(self.plugin_id, 'preamble', '#BP', str,
                                'the preamble from any proxy output')
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

    @RegisterToEvent(event_name="ev_{plugin_id}_var_listenport_modified")
    def _eventcb_listen_port_change(self):
        """
        restart when the listen port changes
        """
        if not self.api.startup and self.is_inititalized_f:
            self.api(f"{self.plugin_id}:restart")()

    @RegisterToEvent(event_name="ev_{plugin_id}_var_cmdseperator_modified")
    def _eventcb_command_seperator_change(self):
        """
        update the command regex

        """
        if event_record := self.api('plugins.core.events:get.current.event.record')():
            newsep = event_record['newvalue']

            self.api.__class__.command_split_regex = r"(?<=[^%s])%s(?=[^%s])" % ('\\' + newsep, '\\' + newsep, '\\' + newsep)
