# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/proxy.py
#
# File Description: a plugin to handle settings and information about the proxy
#
# By: Bast
"""
This plugin will show information about connections to the proxy
"""
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
from libs.records import ToClientRecord, LogRecord, ToMudRecord, EventArgsRecord
import libs.argp as argp

#these 5 are required
NAME = 'Proxy Interface'
SNAME = 'proxy'
PURPOSE = 'control the proxy'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True


class Plugin(BasePlugin):
    """
    a plugin to show connection information
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.api('dependency:add')('core.ssc')

        self.proxypw = None
        self.proxyvpw = None
        self.mudpw = None
        self.mud_connection = None

        # new api format
        self.api('libs.api:add')(self.plugin_id, 'proxy:restart', self.api_restart)
        self.api('libs.api:add')(self.plugin_id, 'proxy:shutdown', self.api_shutdown)
        self.api('libs.api:add')(self.plugin_id, 'preamble:get', self.api_preamble)
        self.api('libs.api:add')(self.plugin_id, 'preamble:color:get', self.api_preamble_color)
        self.api('libs.api:add')(self.plugin_id, 'get:mud:connection', self.api_get_mud_connection)

        self.api('setting:add')('mudhost', '', str,
                                'the hostname/ip of the mud')
        self.api('setting:add')('mudport', 0, int,
                                'the port of the mud')
        self.api('setting:add')('listenport', 9999, int,
                                'the port for the proxy to listen on')
        self.api('setting:add')('username', '', str,
                                'username')
        self.api('setting:add')('linelen', 79, int,
                                'the line length for data, does not affect data that comes from the mud or clients')
        self.api('setting:add')('preamble', '#BP', str,
                                'the preamble from any proxy output')
        self.api('setting:add')('preamblecolor', '@C', str,
                                'the preamble color')
        self.api('setting:add')('preambleerrorcolor', '@R', str,
                                'the preamble color for an error line')
        self.api('setting:add')('cmdseperator', '|', str,
                                'the seperator for sending multiple commands')

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:add:event')(f"ev_{self.plugin_id}_shutdown", self.plugin_id,
                                                  description='event when the proxy is shutting down',
                                                  arg_descriptions={'None': None})

        self.api('plugins.core.commands:command:add')('info',
                                              self.cmd_info,
                                              shelp='list proxy info')

        self.api('plugins.core.commands:command:add')('disconnect',
                                              self.cmd_disconnect,
                                              shelp='disconnect from the mud')

        self.api('plugins.core.commands:command:add')('connect',
                                              self.cmd_connect,
                                              shelp='connect to the mud')

        parser = argp.ArgumentParser(add_help=False,
                                    description='restart the proxy')
        parser.add_argument('-s',
                            '--seconds',
                            type=int,
                            default=10,
                            help='# of seconds to wait before restart')
        self.api('plugins.core.commands:command:add')('restart',
                                              self.cmd_restart,
                                              shelp='restart the proxy',
                                              format=False,
                                              parser=parser)

        self.api('plugins.core.commands:command:add')('shutdown',
                                              self.cmd_shutdown,
                                              shelp='shutdown the proxy')

        self.api('plugins.core.events:register:to:event')('ev_plugins.core.clients_client_logged_in', self.evc_client_logged_in)
        self.api('plugins.core.events:register:to:event')('ev_libs.net.mud_mudconnect', self.evc_sendusernameandpw)
        self.api('plugins.core.events:register:to:event')(
            f"ev_{self.plugin_id}_var_listenport_modified",
            self.evc_listen_port_change
        )
        self.api('plugins.core.events:register:to:event')(
            f"ev_{self.plugin_id}_var_cmdseperator_modified",
            self.evc_command_seperator_change,
        )

        ssc = self.api('plugins.core.ssc:baseclass:get')()
        self.proxypw = ssc('proxypw', self.plugin_id, desc='Proxy Password',
                           default='defaultpass')
        self.proxyvpw = ssc('proxypwview', self.plugin_id, desc='Proxy View Password',
                            default='defaultviewpass')
        self.mudpw = ssc('mudpw', self.plugin_id, desc='Mud Password')

    def api_get_mud_connection(self) -> MudConnection:
        """
        get the mud connection
        """
        if not self.mud_connection:
            self.mud_connection = MudConnection(self.api('setting:get')('mudhost'),
                                                self.api('setting:get')('mudport'))

        return self.mud_connection

    def api_preamble(self):
        """
        get the preamble
        """
        return self.api('setting:get')('preamble')

    def api_preamble_color(self, error=False):
        """
        get the preamble
        """
        if error:
            return self.api('setting:get')('preambleerrorcolor')
        else:
            return self.api('setting:get')('preamblecolor')

    def evc_sendusernameandpw(self):
        """
        if username and password are set, then send them when the proxy
        connects to the mud
        """
        if self.api('setting:get')('username') != '':
            ToMudRecord(self.api('setting:get')('username'), internal=True, show_in_history=False)
            pasw = self.api(f"{self.plugin_id}:ssc:mudpw")()
            if pasw != '':
                ToMudRecord([pasw, '\n'], internal=True, show_in_history=False)

    def cmd_info(self, _):
        """
        show info about the proxy
        """
        template = '%-15s : %s'
        mud = self.api('plugins.core.managers:get')('mud')
        started = 'Unknown'
        if self.api.proxy_start_time:
            started = self.api.proxy_start_time.strftime(self.api.time_format)

        uptime = self.api('plugins.core.utils:convert:timedelta:to:string')(
            self.api.proxy_start_time,
            datetime.datetime.now(datetime.timezone.utc))

        tmsg = [
            '',
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
                                'plugins.core.utils:convert:timedelta:to:string'
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

        clients = self.api('plugins.core.clients:get:all:clients')()

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
        _, nmsg = self.api('plugins.core.commands:command:run')('plugins.core.clients', 'show', '')

        del nmsg[0]
        tmsg.extend(nmsg)
        return True, tmsg

    def cmd_disconnect(self, args=None): # pylint: disable=unused-argument
        """
        disconnect from the mud
        """
        mud = self.api('plugins.core.managers:get')('mud')
        if mud.connected:
            mud.handle_close()

            return True, ['Attempted to close the connection to the mud']
        else:
            return True, ['The proxy is not connected to the mud']

    def cmd_connect(self, args=None): # pylint: disable=unused-argument
        """
        disconnect from the mud
        """
        mud = self.api('plugins.core.managers:get')('mud')
        if mud.connected:
            return True, ['The proxy is currently connected to the mud']

        mud.connectmud(self.api('setting:get')('mudhost'),
                       self.api('setting:get')('mudport'))

        return True, ['Connecting to the mud']

    def api_shutdown(self):
        """
        shutdown the proxy
        """
        self.api.__class__.shutdown = True
        LogRecord('Proxy: shutdown started', level='info', sources=[self.plugin_id, 'shutdown']).send()
        ToClientRecord('Shutting down proxy').send(f'{self.plugin_id}:api_shutdown')
        self.api('plugins.core.events:raise:event')(f"ev_{self.plugin_id}_shutdown")
        LogRecord('Proxy: shutdown complete', level='info', sources=[self.plugin_id, 'shutdown']).send()

    def cmd_shutdown(self, args=None): # pylint: disable=unused-argument,no-self-use
        """
        shutdown the proxy
        """
        signal.raise_signal( signal.SIGINT )

    def cmd_restart(self, args): # pylint: disable=unused-argument
        """
        restart the proxy
        """
        seconds = args['seconds'] or None
        self.api(f"{self.plugin_id}:proxy:restart")(seconds)

    def evc_client_logged_in(self):
        """
        check for mud settings
        """
        if not (
            event_record := self.api(
                'plugins.core.events:get:current:event:record'
            )()
        ):
            return
        cmdprefix = self.api('plugins.core.commands:get:command:prefix')()
        tmsg = []
        divider = '@R------------------------------------------------@w'
        if not self.mud_connection or not self.mud_connection.connected:
            if not self.api('setting:get')('mudhost'):
                tmsg.extend(
                    (
                        divider,
                        'Please set the mudhost.',
                        f"{cmdprefix}.{self.plugin_id}.set mudhost 'host'",
                    )
                )
            if self.api('setting:get')('mudport') == 0:
                tmsg.extend(
                    (
                        divider,
                        'Please set the mudport.',
                        f"{cmdprefix}.{self.plugin_id}.set mudport 'port'",
                    )
                )
            tmsg.extend(
                (
                    divider,
                    f"Conect to the mud with {cmdprefix}.{self.plugin_id}.connect",
                )
            )
        else:
            tmsg.extend(
                (
                    divider,
                    f"{self.api(f'{self.plugin_id}:preamble:color:get')(error=True)}{self.api(f'{self.plugin_id}:preamble:get')()}: @GThe proxy is already connected to the mud@w",
                )
            )
        if self.api(f"{self.plugin_id}:ssc:proxypw")(quiet=True) == 'defaultpass':
            tmsg.extend(
                (
                    divider,
                    'The proxy password is still the default password.',
                    'Please set the proxy password!',
                    f"{cmdprefix}.{self.plugin_id}.proxypw 'This is a password'",
                )
            )
        if self.api(f"{self.plugin_id}:ssc:proxypwview")(quiet=True) == 'defaultviewpass':
            tmsg.extend(
                (
                    divider,
                    'The proxy view password is still the default password.',
                    'Please set the proxy view password!',
                    f"{cmdprefix}.{self.plugin_id}.proxypwview 'This is a view password'",
                )
            )
        if tmsg[-1] != divider:
            tmsg.append(divider)
        if tmsg[0] != divider:
            tmsg.insert(0, divider)


        if tmsg:
            ToClientRecord(tmsg, clients=[event_record['client_uuid']]).send(
                f'{__name__}:client_connected'
            )

    # restart the proxy
    def api_restart(self, restart_in=None):
        """
        restart the proxy after 10 seconds
        """
        restart_in = restart_in or 10
        listen_port = self.api('setting:get')('listenport')

        ToClientRecord(
            f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds"
        ).send(f'{self.plugin_id}:api_restart')
        LogRecord(f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds", level='warning', sources=[self.plugin_id]).send()

        self.api('plugins.core.timers:add:timer')('restart', self.timer_restart, restart_in, onetime=True)

    def timer_restart(self):
        """
        a function to restart the proxy after a timer
        """
        self.api('plugins.core.pluginm:save:all:plugins:state')()

        self.api(f"{self.plugin_id}:proxy:shutdown")()

        time.sleep(5)

        os.execv(sys.executable, [os.path.basename(sys.executable)] + sys.argv)

    def evc_listen_port_change(self):
        """
        restart when the listen port changes
        """
        if not self.api.startup and not self.initializing_f:
            self.api(f"{self.plugin_id}:proxy:restart")()

    def evc_command_seperator_change(self):
        """
        update the command regex

        """
        if event_record := self.api('plugins.core.events:get:current:event:record')():
            newsep = event_record['newvalue']

            self.api.__class__.command_split_regex = r"(?<=[^%s])%s(?=[^%s])" % ('\\' + newsep, '\\' + newsep, '\\' + newsep)
