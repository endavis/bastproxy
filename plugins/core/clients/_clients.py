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
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord
from libs.api import API
from libs.commands import AddParser, AddArgument
from libs.event import RegisterToEvent
from libs.api import AddAPI

class BanRecord:
    def __init__(self, plugin_id, ip_addr, how_long=600):
        self.api = API(owner_id=f"{plugin_id}:Ban:{ip_addr}")
        self.plugin_id = plugin_id
        self.ip_addr = ip_addr
        self.how_long = how_long
        self.timer = None

        if self.how_long > 0:
            LogRecord(f"{self.ip_addr} has been banned for {self.how_long} seconds",
                      level='error', sources=[self.plugin_id])()
            self.timer = self.api('plugins.core.timers:add.timer')(f'{self.plugin_id}_banremove_{self.ip_addr}', self.remove,
                                                            self.how_long, unique=True, onetime=True, plugin_id=self.plugin_id)
        else:
            LogRecord(f"{self.ip_addr} has been banned with no expiration",
                      level='error', sources=[self.plugin_id])()

    def expires(self):
        if self.timer:
            return self.timer.next_fire_datetime.strftime(self.api.time_format)
        else:
            return 'Permanent'

    def remove(self):
        self.api(f"{self.plugin_id}:client.banned.remove")(self.ip_addr)


class ClientPlugin(BasePlugin):
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

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

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
        if client_uuid in self.clients:
            addr = self.clients[client_uuid].addr
            ban_record = BanRecord(self.plugin_id, addr, how_long=how_long)
            self.banned[addr] = ban_record
            self.clients[client_uuid].connected = False

    @AddAPI('client.banned.add.by.ip', description='add a banned ip')
    def _api_client_banned_add_by_ip(self, ip_address, how_long=600):
        """
        add a banned ip
        """
        if ip_address not in self.banned:
            ban_record = BanRecord(self.plugin_id, ip_address, how_long=how_long)
            self.banned[ip_address] = ban_record

    @AddAPI('client.banned.check', description='check if a client is banned')
    def _api_checkbanned(self, clientip):
        """
        check if a client is banned

        required
          clientip - the client ip to check
        """
        return clientip in self.banned

    @AddAPI('client.banned.remove', description='remove a banned ip')
    def _api_client_banned_remove(self, addr):
        """
        remove a banned ip
        """
        if addr in self.banned:
            del self.banned[addr]

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

        if self.banned:
            bannedformat = '%-20s %s'
            tmsg.extend(['',
                    (
                        bannedformat % ('Banned IPs', 'Until')
                    ),
                '@B' + 70 * '-'])
            for banned_ip in self.banned:
                banned_time = self.banned[banned_ip].expires()

                tmsg.append(bannedformat % (banned_ip, banned_time))

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
            if ip in self.banned:
                removed.append(ip)
                self.banned[ip].remove()
            else:
                added.append(ip)
                self.api(f"{self.plugin_id}:client.banned.add.by.ip")(ip, how_long=-1)

        tmsg = []
        if removed:
            tmsg.extend((f"Removed {len(removed)} IPs from the ban list", ', '.join(removed)))
        if added:
            tmsg.extend((f"Added {len(added)} IPs to the ban list", ', '.join(added)))

        if not tmsg:
            tmsg = ['No changes made']

        return True, tmsg
