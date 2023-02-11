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
import time
import datetime

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin

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
        self.vclients = {}
        self.banned = {}

        # new api format
        self.api('libs.api:add')('get:client', self._api_get_client)
        self.api('libs.api:add')('get:all:clients', self._api_get_all_clients)
        self.api('libs.api:add')('client:banned:add', self.api_addbanned)
        self.api('libs.api:add')('client:banned:check', self.api_checkbanned)
        self.api('libs.api:add')('client:count', self.api_numconnected)
        self.api('libs.api:add')('client:add', self._api_addclient)
        self.api('libs.api:add')('client:view:add', self._api_addviewclient)
        self.api('libs.api:add')('client:remove', self._api_removeclient)
        self.api('libs.api:add')('client:is:logged:in', self._api_is_client_logged_in)
        self.api('libs.api:add')('client:logged:in', self._api_client_logged_in)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.commands:command:add')('show',
                                              self.cmd_show,
                                              shelp='list clients that are connected')

        self.api('plugins.core.events:register:to:event')('ev_net.proxy_proxy_shutdown',
                                                  self.shutdown)

    def api_numconnected(self):
        """
        return the # of clients connected
        """
        return len(self.clients)

    def _api_get_client(self, client_uuid):
        """
        get a connection
        """
        if client_uuid in self.clients:
            return self.clients[client_uuid]
        if client_uuid in self.vclients:
            return self.vclients[client_uuid]
        return None

    def api_addbanned(self, client_uuid):
        """
        add a banned ip
        """
        if client_uuid in self.clients:
            addr = self.clients[client_uuid].addr
            self.api('libs.io:send:error')(f"{addr} has been banned for 10 minutes")
            self.banned[addr] = time.localtime()

    def _api_is_client_logged_in(self, client_uuid):
        """
        check if a client is logged in
        """
        if client_uuid in self.clients and self.clients[client_uuid].state['logged in']:
            return True

        return False

    def _api_client_logged_in(self, client_uuid):
        """
        set a client as logged in
        """
        if client_uuid in self.clients:
            self.clients[client_uuid].state['logged in'] = True

    def api_checkbanned(self, clientip):
        """
        check if a client is banned

        required
          clientip - the client ip to check
        """
        if clientip in self.banned:
            difference = time.mktime(time.localtime()) - time.mktime(self.banned[clientip])
            delta = datetime.timedelta(seconds=difference)
            if delta.total_seconds() > 600:
                del self.banned[clientip]
                return False
            return True

        return False

    def _api_addclient(self, client_connection):
        """
        add a client from the connected event
        """
        self.clients[client_connection.uuid] = client_connection
        self.api('libs.io:send:msg')(f"Client {client_connection.uuid} logged in from {client_connection.addr}:{client_connection.port}",
                                     level='info')
        self.api('plugins.core.events:raise:event')('ev_core.clients_client_connected',
                                    {'client_uuid':client_connection.uuid})


    def _api_addviewclient(self, client_connection):
        """
        add a view client from the connected event
        """
        self.vclients[client_connection.uuid] = client_connection
        self.api('libs.io:send:msg')(f"View Client {client_connection.uuid} logged from {client_connection.addr}:{client_connection.port}",
                                     level='info')
        self.api('plugins.core.events:raise:event')('ev_core.clients_client_connected_view',
                                    {'client_uuid':client_connection.uuid})

    def _api_removeclient(self, client_connection):
        """
        remove a client
        """
        removed = False
        if client_connection.uuid in self.clients:
            del self.clients[client_connection.uuid]
            removed = True
        if client_connection.uuid in self.vclients:
            del self.vclients[client_connection.uuid]
            removed = True

        if removed:
            self.api('plugins_core.events:raise:event')('ev_core.clients_client_disconnected',
                    {'client_uuid':client_connection.uuid})

    def shutdown(self, args=None): # pylint: disable=unused-argument
        """
        close all clients
        """
        for client in self.clients:
            client.handle_close()
        for client in self.vclients:
            client.handle_close()

    def _api_get_all_clients(self):
        """
        return a dictionary of clients
        two keys: view, active
        """
        clients = []
        clients.extend(self.clients.values())
        clients.extend(self.vclients.values())
        return clients

    def cmd_show(self, args): # pylint: disable=unused-argument
        """
        show all clients
        """
        clientformat = '%-6s %-17s %-7s %-17s %-s'
        tmsg = ['']
        tmsg.append(clientformat % ('Type', 'Host', 'Port',
                                    'Client', 'Connected'))
        tmsg.append('@B' + 60 * '-')
        for i in self.clients:
            client = self.clients[i]
            ttime = self.api('plugins.core.utils:convert:timedelta:to:string')(
                client.connected_time,
                time.localtime())

            tmsg.append(clientformat % ('Active', client.addr, client.port,
                                        'Terminal Type', ttime))
            # options = i.options_info()
            # if options:
            #     tmsg.append('Option Info')
            #     for j in options:
            #         tmsg.append(j)

        for i in self.vclients:
            client = self.vclients[i]
            ttime = self.api('plugins.core.utils:convert:timedelta:to:string')(
                client.connected_time,
                time.localtime())
            tmsg.append(clientformat % ('View', client.addr, client.port,
                                        'Unknown', ttime))

        return True, tmsg
