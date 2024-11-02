"""
"""
import contextlib
# Standard Library
import sys
import asyncio

# Third Party

# Project
from libs.records import LogRecord
from libs.api import API as BASEAPI
from libs.net import server
from libs.asynch import TaskItem

class Listeners:
    def __init__(self):
        self.listener_tries = 1
        self.api = BASEAPI(owner_id='mudproxy')
        self.check_listener_task: TaskItem | None = None
        self.check_listener_taskname = 'Check Listeners Available'
        self.ipv4_task: TaskItem | None = None
        self.ipv4_taskname = 'Proxy Telnet Listener IPv4'
        self.ipv4_start = False
        self.ipv6_task: TaskItem | None = None
        self.ipv6_taskname = 'Proxy Telnet Listener IPv6'
        self.ipv6_start = False

    async def check_listeners_available(self):
        """
        check if any listeners started
        if not, reset listener settings to defaults and try again
        """
        await asyncio.sleep(2)

        if self.listener_tries > 2:
            LogRecord('No listeners available, defaults did not work. Please check the settings in data/plugins/plugins.core.proxy', level='error', sources=['mudproxy'])()
            sys.exit(1)

        ipv4 = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv4')
        ipv6 = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv6')
        self.ipv4_start = False
        self.ipv6_start = False

        if ipv4 and self.ipv4_task and self.ipv4_task.done:
            with contextlib.suppress(Exception):
                _ = self.ipv4_task.result
                self.ipv4_start = True
        if ipv6 and self.ipv6_task and self.ipv6_task.done:
            with contextlib.suppress(Exception):
                _ = self.ipv6_task.result
                self.ipv6_start = True

        listen_port = self.api('plugins.core.settings:get')('plugins.core.proxy', 'listenport')
        if ipv4 and not self.ipv4_start:
            ipv4_address = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv4address')
            LogRecord(f'IPv4 Listener did not start on {ipv4_address}:{listen_port}, please check errors and update settings', level='error', sources=['mudproxy'])()

        if ipv6 and not self.ipv6_start:
            ipv6_address = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv6address')
            LogRecord(f'IPv4 Listener did not start on {ipv6_address}:{listen_port}, please check errors and update settings', level='error', sources=['mudproxy'])()

        if not (ipv4 and self.ipv4_start) and not (ipv6 and self.ipv6_start):
            LogRecord('No listeners available, resetting to defaults', level='error', sources=['mudproxy'])()
            self.reset_listener_settings()
            self.listener_tries = self.listener_tries + 1
            self.check_listener_taskname = f'Check Listeners Available - Try {str(self.listener_tries)}'
            self.create_listeners()

        else:
            msg = 'Listening on '
            tlist = []
            if self.ipv4_start:
                tlist.append('IPv4')
            if self.ipv6_start:
                tlist.append('IPv6')
            msg = msg + ' and '.join(tlist) + ' port ' + str(self.api('plugins.core.settings:get')('plugins.core.proxy', 'listenport'))

            LogRecord(msg, level='info', sources=['mudproxy'])()

    def reset_listener_settings(self):
        """
        reset the listener settings to the defaults
        """
        self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv4', 'default')
        self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv6', 'default')
        self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv4address', 'default')
        self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv6address', 'default')
        self.api('plugins.core.settings:change')('plugins.core.proxy', 'listenport', 'default')

    def _create_listeners(self):
        # import the client handler here so that the server can be created
        import libs.net.client

        listen_port = self.api('plugins.core.settings:get')('plugins.core.proxy', 'listenport')

        ipv4 = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv4')
        ipv4_address = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv4address')

        ipv6 = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv6')
        ipv6_address = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv6address')

        if not ipv4 and not ipv6:
            LogRecord('No listeners enabled, adding default ipv4 listener', level='error', sources=['mudproxy'])()
            self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv4', True)
            ipv4 = True

        # add IPv4 listener
        if ipv4:
            self.ipv4_task = self.api('libs.asynch:task.add')(
                server.create_server(
                    host=ipv4_address,
                    port=listen_port,
                    shell=libs.net.client.client_telnet_handler,
                    connect_maxwait=0.5,
                    timeout=3600,
                    encoding='utf8'
                ), self.ipv4_taskname, startstring=f"{ipv4_address}:{listen_port}")

        # add IPv6 listener
        if ipv6:
            self.ipv6_task = self.api('libs.asynch:task.add')(
                server.create_server(
                    host=ipv6_address,
                    port=listen_port,
                    shell=libs.net.client.client_telnet_handler,
                    connect_maxwait=0.5,
                    timeout=3600,
                    encoding='utf8'
                ), self.ipv6_taskname, startstring=f"{ipv6_address}:{listen_port}")

    def create_listeners(self):
        """
        start the listeners
        """
        self._create_listeners()

        self.check_listener_task = self.api('libs.asynch:task.add')(
            self.check_listeners_available(),
            self.check_listener_taskname,
        )
