# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/clients/_clients.py
#
# File Description: a plugin to hold information about clients
#
# By: Bast

# Standard Library
import datetime

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from libs.records import LogRecord
from libs.api import API
from libs.commands import AddParser, AddArgument
from libs.event import RegisterToEvent
from libs.api import AddAPI
from libs.net.client import ClientConnection

class BanRecord:
    def __init__(self, plugin_id:str , ip_addr: str, how_long: int = 600, copy: bool = False):
        self.api = API(owner_id=f"{plugin_id}:Ban:{ip_addr}")
        self.plugin_id: str = plugin_id
        self.ip_addr: str = ip_addr
        self.how_long: int = how_long
        self.timer = None

        if not copy and self.how_long > 0:
            self.timer = self.api('plugins.core.timers:add.timer')(f'{self.plugin_id}_banremove_{self.ip_addr}', self.remove,
                                                            self.how_long, unique=True, onetime=True, plugin_id=self.plugin_id)

    @property
    def expires(self) -> str:
        if self.timer:
            return self.timer.next_fire_datetime.strftime(self.api.time_format)
        else:
            return 'Permanent'

    def remove(self):
        self.api(f"{self.plugin_id}:client.banned.remove")(self.ip_addr)

    def copy(self, newclass):
        newrecord = newclass(self.plugin_id, self.ip_addr, self.how_long, copy=True)
        newrecord.timer = self.timer
        return newrecord

class ClientPlugin(BasePlugin):
    """
    a plugin to show connection information
    """
    @RegisterPluginHook('__init__')
    def _phook_init_plugin(self):
        """
        initialize the plugin
        """
        self.attributes_to_save_on_reload = ['clients', 'banned']

        self.clients: dict[str, ClientConnection] = {}
        self.banned: dict[str, BanRecord] = {}

    @RegisterPluginHook('initialize')
    def _phook_initialize(self):
        """
        initialize the plugin
        """

        self.api('plugins.core.settings:add')(self.plugin_id, 'permbanips', [], list,
                        'A list of IPs that are permanently banned',
                        readonly=True)

        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_logged_in", self.plugin_id,
                                                  description=['An event that is raised when a client logs in'],
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_logged_in_view_only", self.plugin_id,
                                                  description=['An event that is raised when a client logs in as a view client'],
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_connected", self.plugin_id,
                                                  description=['An event that is raised when a client connects'],
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})
        self.api('plugins.core.events:add.event')(f"ev_{self.plugin_id}_client_disconnected", self.plugin_id,
                                                  description=['An event that is raised when a client disconnects'],
                                                  arg_descriptions={'client_uuid':'the uuid of the client'})

        # This will only occur if the plugin is reloaded
        # copy the banned ips to the newly loaded class to free up the original objects and class
        if self.banned:
            LogRecord(f"Loading {len(self.banned)} banned IPs", level='debug', sources=[self.plugin_id])()
            for item in self.banned:
                self.banned[item] = self.banned[item].copy(BanRecord)

    @AddAPI('client.count', description='return the # of clients connected')
    def _api_client_count(self):
        """
        return the # of clients connected
        """
        return len(self.clients)

    @AddAPI('get.client', description='get a client by uuid')
    def _api_get_client(self, client_uuid):
        """
        get a client by uuid
        """
        return self.clients[client_uuid] if client_uuid in self.clients else None

    @AddAPI('client.banned.add', description='add a banned client')
    def _api_client_banned_add(self, client_uuid, how_long=600):
        """
        add a banned client
        """
        self.clients[client_uuid].connected = False
        return self.api(f"{self.plugin_id}:client.banned.add.by.ip")(self.clients[client_uuid].addr, how_long)

    @AddAPI('client.banned.add.by.ip', description='add a banned ip')
    def _api_client_banned_add_by_ip(self, ip_address, how_long=600):
        """
        add a banned ip
        """
        if how_long == -1:
            permbanips = self.api('plugins.core.settings:get')(self.plugin_id, 'permbanips')
            if ip_address not in permbanips:
                permbanips.append(ip_address)
                self.api('plugins.core.settings:change')(self.plugin_id, 'permbanips', permbanips)
                LogRecord(f"{ip_address} has been banned with no expiration",
                        level='error', sources=[self.plugin_id])()
                return True
        elif ip_address not in self.banned:
            ban_record = BanRecord(self.plugin_id, ip_address, how_long=how_long)
            self.banned[ip_address] = ban_record
            LogRecord(f"{ip_address} has been banned for {how_long} seconds",
                        level='error', sources=[self.plugin_id])()
            return True

        return False

    @AddAPI('client.banned.check', description='check if a client is banned')
    def _api_checkbanned(self, clientip):
        """
        check if a client is banned

        required
          clientip - the client ip to check
        """
        permbanips = self.api('plugins.core.settings:get')(self.plugin_id, 'permbanips')
        return clientip in self.banned or clientip in permbanips

    @AddAPI('client.banned.remove', description='remove a banned ip')
    def _api_client_banned_remove(self, addr):
        """
        remove a banned ip
        """
        if addr in self.banned:
            del self.banned[addr]
            LogRecord(f"{addr} is no longer banned",
                        level='error', sources=[self.plugin_id])()
            return True
        permbanips = self.api('plugins.core.settings:get')(self.plugin_id, 'permbanips')
        if addr in permbanips:
            permbanips.remove(addr)
            self.api('plugins.core.settings:change')(self.plugin_id, 'permbanips', permbanips)
            LogRecord(f"{addr} is no longer banned",
                        level='error', sources=[self.plugin_id])()
            return True

        return False

    @AddAPI('client.is.view.client', description='check if a client is a view client')
    def _api_is_client_view_client(self, client_uuid):
        """
        check if a client is a view client
        """
        if client_uuid in self.clients:
            return self.clients[client_uuid].view_only

        return False

    @AddAPI('client.is.logged.in', description='check if a client is logged in')
    def _api_client_is_logged_in(self, client_uuid):
        """
        check if a client is logged in
        """
        return bool(
            client_uuid in self.clients
            and self.clients[client_uuid].state['logged in']
        )

    @AddAPI('client.logged.in', description='set a client as logged in')
    def _api_client_logged_in(self, client_uuid):
        """
        set a client as logged in
        """
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state['logged in'] = True
            LogRecord(f"Client {client_connection.uuid} logged in from {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id])()

            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_logged_in",
                                        {'client_uuid':client_connection.uuid})

    @AddAPI('client.logged.in.view.only', description='set a client as logged in for view only')
    def _api_client_logged_in_view_only(self, client_uuid):
        """
        set a client as logged in for view only
        """
        if client_uuid in self.clients:
            client_connection = self.clients[client_uuid]
            client_connection.state['logged in'] = True
            client_connection.view_only = True

            LogRecord(f"View Client {client_connection.uuid} logged in from {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id])()

            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_logged_in_view_only",
                                        {'client_uuid':client_connection.uuid})

    @AddAPI('client.add', description='add a connected client')
    def _api_client_add(self, client_connection):
        """
        add a connected client
        """
        if client_connection.uuid in self.clients:
            LogRecord(f"Client {client_connection.uuid} already exists", level='warning', sources=[self.plugin_id])()
        self.clients[client_connection.uuid] = client_connection
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_connected",
                                                    {'client_uuid' : client_connection.uuid})

    @AddAPI('client.remove', description='remove a connected client')
    def _api_client_remove(self, client_connection):
        """
        remove a connected client
        """
        if client_connection.uuid in self.clients:
            del self.clients[client_connection.uuid]
            self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_client_disconnected",
                                                        {'client_uuid' : client_connection.uuid})
            LogRecord(f"Client {client_connection.uuid} disconnected {client_connection.addr}:{client_connection.port}",
                      level='warning', sources=[self.plugin_id])()

    @AddAPI('get.all.clients', description='get all clients')
    def _api_get_all_clients(self, uuid_only=False):
        """
        return a dictionary of clients
        two keys: view, active
        """
        return self.clients.keys() if uuid_only else self.clients.values()

    @AddParser(description='list clients that are connected')
    def _command_show(self):
        """
        show all clients
        """
        tmsg = []

        color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        # TODO: add telnet options
        clients = [
            {'state': 'Active', 'address': item.addr, 'port': item.port,
             'term_type': 'Term Type', 'connected': item.connected_length,
             'view_only': item.view_only} for item in self.clients.values()
        ]

        clients_columns = [
            {'name': 'State', 'key': 'state', 'width': 6},
            {'name': 'Client IP', 'key': 'address', 'width': 17},
            {'name': 'Port', 'key': 'port', 'width': 7},
            {'name': 'Term Type', 'key': 'term_type', 'width': 17},
            {'name': 'Connected', 'key': 'connected', 'width': 12},
            {'name': 'View Only', 'key': 'view_only', 'width': 8},
        ]

        tmsg.extend(self.api('plugins.core.utils:convert.data.to.output.table')('Clients', clients, clients_columns, color=color))

        banned_clients = [
            {'address': item, 'until': self.banned[item].expires}
            for item in self.banned
        ]
        permbanips = self.api('plugins.core.settings:get')(self.plugin_id, 'permbanips')
        banned_clients.extend(
            {'address': item, 'until': 'Permanent'} for item in permbanips
        )

        if banned_clients:
            banned_clients_columns = [
                {'name': 'Address', 'key': 'address', 'width': 30},
                {'name': 'Until', 'key': 'until', 'width': 20},
            ]

            tmsg.append('')
            tmsg.extend(self.api('plugins.core.utils:convert.data.to.output.table')('Banned IPs', banned_clients, banned_clients_columns, color=color))

        return True, tmsg

    @AddParser(description='add or remove a banned ip')
    @AddArgument('ips',
                        help='a list of ips to ban or remove (this is a toggle)',
                        default=None,
                        nargs='*')
    def _command_ban(self):
        """
        ban or remove an IP

        required
          ips - a list of IPs to ban or remove (this is a toggle)

        if the ip is already banned, it will be unbanned
        otherwise, it will be banned
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['ips']:
            return True, ['No IPs specified']

        removed = []
        added = []

        for ip in args['ips']:
            if self.api(f"{self.plugin_id}:client.banned.check")(ip):
                if self.api(f"{self.plugin_id}:client.banned.remove")(ip):
                    removed.append(ip)
            elif self.api(f"{self.plugin_id}:client.banned.add.by.ip")(ip, how_long=-1):
                added.append(ip)

        found_ips = set(removed + added)
        not_found = set(args['ips']) - found_ips

        tmsg = []
        if removed:
            tmsg.extend((f"Removed {len(removed)} IPs from the ban list", ', '.join(removed)))
        if added:
            tmsg.extend((f"Added {len(added)} IPs to the ban list", ', '.join(added)))
        if not_found:
            tmsg.extend((f"{len(not_found)} IPs were not acted on", ', '.join(not_found)))

        if not tmsg:
            tmsg = ['No changes made']

        return True, tmsg
