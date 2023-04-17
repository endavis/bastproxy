# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/clients.py
#
# File Description: a plugin to hold information about clients
#
# By: Bast
"""
This plugin will show information about connections to the proxy
"""
# Standard Library
import datetime

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord

#these 5 are required
NAME = 'Clients'
SNAME = 'clients'
PURPOSE = 'manage clients'
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

        self.can_reload_f = False

        self.clients = {}
        self.banned = {}

        # new api format
        self.api('libs.api:add')(self.plugin_id, 'get.client', self._api_get_client)
        self.api('libs.api:add')(self.plugin_id, 'get.all.clients', self._api_get_all_clients)
        self.api('libs.api:add')(self.plugin_id, 'client.banned.add', self.api_addbanned)
        self.api('libs.api:add')(self.plugin_id, 'client.banned.check', self.api_checkbanned)
        self.api('libs.api:add')(self.plugin_id, 'client.count', self.api_numconnected)
        self.api('libs.api:add')(self.plugin_id, 'client.add', self._api_addclient)
        self.api('libs.api:add')(self.plugin_id, 'client.remove', self._api_removeclient)
        self.api('libs.api:add')(self.plugin_id, 'client.is.logged.in', self._api_is_client_logged_in)
        self.api('libs.api:add')(self.plugin_id, 'client.is.view.client', self._api_is_client_view_client)
        self.api('libs.api:add')(self.plugin_id, 'client.logged.in', self._api_client_logged_in)
        self.api('libs.api:add')(self.plugin_id, 'client.logged.in.view.only', self._api_client_logged_in_view_only)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_logged_in", self.plugin_id,
                                                  description='An event that is raised when a client logs in',
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_logged_in_view_only", self.plugin_id,
                                                  description='An event that is raised when a client logs in as a view client',
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_connected", self.plugin_id,
                                                  description='An event that is raised when a client connects',
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_disconnected", self.plugin_id,
                                                  description='An event that is raised when a client disconnects',
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})

        self.api('plugins.core.commands:command.add')('show',
                                              self.cmd_show,
                                              shelp='list clients that are connected')

        self.api('plugins.core.events:register.to.event')('ev_plugin.core.proxy_proxy_shutdown',
                                                  self.evc_shutdown)

    def api_numconnected(self):
        """
        return the # of clients connected
        """
        return len(self.clients)

    def _api_get_client(self, client_uuid):
        """
        get a connection
        """
        return self.clients[client_uuid] if client_uuid in self.clients else None

    def api_addbanned(self, client_uuid):
        """
        add a banned ip
        """
        if client_uuid in self.clients:
            addr = self.clients[client_uuid].addr
            LogRecord(f"{addr} has been banned for 10 minutes",
                      level='error', sources=[self.plugin_id]).send()
            self.banned[addr] =  datetime.datetime.now(datetime.timezone.utc)
            self.clients[client_uuid].state['connected'] = False

    def _api_is_client_view_client(self, client_uuid):
        """
        check if a client is a view client
        """
        if client_uuid in self.clients:
            return self.clients[client_uuid].view_only

        return False

    def _api_is_client_logged_in(self, client_uuid):
        """
        check if a client is logged in
        """
        return bool(
            client_uuid in self.clients
            and self.clients[client_uuid].state['logged in']
        )

    def _api_client_logged_in(self, client_uuid):
        """
        set a client as logged in
        """
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state['logged in'] = True
            LogRecord(f"Client {client_connection.uuid} logged in from {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id]).send()

            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_logged_in",
                                        {'client_uuid':client_connection.uuid})

    def _api_client_logged_in_view_only(self, client_uuid):
        """
        set a client as logged in for view only
        """
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state['logged in'] = True
            client_connection.view_only = True

            LogRecord(f"View Client {client_connection.uuid} logged in from {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id]).send()

            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_logged_in_view_only",
                                        {'client_uuid':client_connection.uuid})

    def api_checkbanned(self, clientip):
        """
        check if a client is banned

        required
          clientip - the client ip to check
        """
        if clientip in self.banned:
            difference =  datetime.datetime.now(datetime.timezone.utc) - self.banned[clientip]
            if difference.total_seconds() > 600:
                del self.banned[clientip]
                return False
            return True

        return False

    def _api_addclient(self, client_connection):
        """
        add a connected client
        """
        if client_connection.uuid in self.clients:
            LogRecord(f"Client {client_connection.uuid} already exists", level='warning', sources=[self.plugin_id]).send()
        self.clients[client_connection.uuid] = client_connection
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_connected",
                                                    {'client_uuid' : client_connection.uuid})

    def _api_removeclient(self, client_connection):
        """
        remove a connected client
        """
        if client_connection.uuid in self.clients:
            del self.clients[client_connection.uuid]
            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_disconnected",
                                                        {'client_uuid' : client_connection.uuid})
            LogRecord(f"Client {client_connection.uuid} disconnected {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id]).send()

    def evc_shutdown(self):
        """
        close all clients

        #TODO: need to fix this for asyncio
        """
        pass

    def _api_get_all_clients(self, uuid_only=False):
        """
        return a dictionary of clients
        two keys: view, active
        """
        return self.clients.keys() if uuid_only else self.clients.values()

    def cmd_show(self, args):    # pylint: disable=unused-argument
        """
        show all clients
        """
        clientformat = '%-6s %-17s %-7s %-17s %-12s %-s'
        tmsg = [
            '',
            (
                clientformat
                % ('Type', 'Host', 'Port', 'Client', 'Connected', 'View Only')
            ),
            '@B' + 70 * '-',
        ]
        for i in self.clients:
            client = self.clients[i]
            ttime = self.api('plugins.core.utils:convert.timedelta.to.string')(
                client.connected_time,
                datetime.datetime.now(datetime.timezone.utc))

            tmsg.append(clientformat % ('Active', client.addr, client.port,
                                        'Terminal Type', ttime, client.view_only))
            # options = i.options_info()
            # if options:
            #     tmsg.append('Option Info')
            #     for j in options:
            #         tmsg.append(j)


        return True, tmsg
