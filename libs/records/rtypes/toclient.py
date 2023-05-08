# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/toclient.py
#
# File Description: Holds the client record type
#
# By: Bast
"""
Holds the client record type
"""
# Standard Library

# 3rd Party

# Project
from libs.records.rtypes.log import LogRecord
from libs.records.rtypes.base import BaseListRecord

SETUPEVENTS = False

class ToClientRecord(BaseListRecord):
    """
    a record to a client, this can originate with the mud or internally
    data from the mud will immediately be transformed into this type of record
    will not neccesarily end up going to the client

    The message format is a list of strings

    line endings will be added to each line before sending to the client

    Valid message_types:
        'IO' - a regular string to send to the client
        'TELNET-COMMAND' - a telnet command to the client
    when it goes on the client queue, it will be converted to a NetworkData object
    """
    def __init__(self, message: list[str | bytes] | list[str] | list[bytes] | str | bytes, message_type: str='IO', clients: list|None=None, exclude_clients: list|None=None, preamble=True,
                 internal: bool=True, prelogin: bool=False, error: bool=False, color_for_all_lines=None):
        """
        initialize the class
        """
        super().__init__(message, message_type, internal)
        # flag to include preamble when sending to client
        self.preamble: bool = preamble
        # flag to send to client before login
        self.prelogin: bool = prelogin
        # flag for this is an error message
        self.error: bool = error
        # This is so that events can set this and it will not be sent to the client
        self.send_to_clients: bool = True
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients: list[str] = clients or []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients or []
        # This will set the color for all lines to the specified @ color
        self.color_for_all_lines: str = color_for_all_lines or ''
        self.modify_data_event_name = 'ev_to_client_data_modify'
        self.read_data_event_name = 'ev_to_client_data_read'

        self.items_to_format_in_details.extend([('Preamble', 'preamble'),
                                                ('Prelogin', 'prelogin'),
                                                ('Error', 'error'),
                                                ('Send To Clients', 'send_to_clients'),
                                                ('Clients', 'clients'),
                                                ('Exclude Clients', 'exclude_clients'),
                                                ('Color For All Lines', 'color_for_all_lines')])

        self.setup_events()

    def setup_events(self):
        global SETUPEVENTS
        if not SETUPEVENTS:
            SETUPEVENTS = True
            self.api('plugins.core.events:add.event')(self.modify_data_event_name, __name__,
                                                description='An event to modify data before it is sent to the client',
                                                arg_descriptions={'line': 'The line to modify',
                                                                  'sendtoclient': 'A flag to determine if this line should be sent to the client'})
            self.api('plugins.core.events:add.event')(self.read_data_event_name, __name__,
                                                description='An event to see data that was sent to the client',
                                                arg_descriptions={'ToClientRecord': 'A libs.records.ToClientRecord object'})

    @property
    def noansi(self):
        """
        return the message without ansi codes
        """
        newmessage: list[str] = [
            self.api('plugins.core.colors:strip.ansi')(item) for item in self.data
        ]
        return newmessage

    @property
    def color(self):
        """
        return the message with ansi codes converted to @ color codes
        """
        newmessage: list[str] = [
            self.api('plugins.core.colors:ansicode.to.colorcode')(item)
            for item in self.data
        ]
        return newmessage

    def set_send_to_clients(self, flag, actor='', extra=''):
        """
        set the send to clients flag
        """
        if flag != self.send_to_clients:
            self.send_to_clients = flag
            self.addupdate('Set Flag', 'send_to_clients', actor=actor, extra={'msg':f"set to {flag}, {extra}"}, savedata=False)

    def add_client(self, client_uuid: str):
        """
        add a client to the list of clients to send to
        """
        if client_uuid in self.exclude_clients:
            self.exclude_clients.remove(client_uuid)
        if client_uuid not in self.clients:
            self.clients.append(client_uuid)

    def exclude_client(self, client_uuid):
        """
        add a client to the list of clients to exclude
        """
        if client_uuid in self.clients:
            self.clients.remove(client_uuid)
        if client_uuid not in self.exclude_clients:
            self.exclude_clients.append(client_uuid)

    def can_send_to_client(self, client_uuid):
        """
        returns true if this message can be sent to the client
        """
        if client_uuid:
            # Exclude takes precedence over everything else
            if client_uuid in self.exclude_clients:
                return False
            # If the client is a view client and this is an internal message, we don't send it
            # This way view clients don't see the output of commands entered by other clients
            if self.api('plugins.core.clients:client.is.view.client')(client_uuid) and self.internal:
                return False
            # If the client is in the list of clients or self.clients is empty,
            # then we can check to make sure the client is logged in or the prelogin flag is set
            if (not self.clients or client_uuid in self.clients) and (
                self.api('plugins.core.clients:client.is.logged.in')(client_uuid)
                or self.prelogin
            ):
                # All checks passed, we can send to this client
                return True
        return False

    def add_preamble(self, actor=''):
        """
        add the preamble to the message only if it is from internal and is an IO message
        """
        if self.preamble:
            preamblecolor = self.api('plugins.core.proxy:preamble.color.get')(error=self.error)
            preambletext = self.api('plugins.core.proxy:preamble.get')()
            new_message = []
            new_message = [f"{preamblecolor}{preambletext}@w: {item}" for item in self.data]
            self.replace(new_message, f"{actor}:add_preamble", extra={'msg':'add a preamble to all items'})

    def color_lines(self, actor=''):
        """
        add the color to the beginning of all lines in the message
        """
        super().color_lines(self.color_for_all_lines, actor)

    def format(self, actor=''):
        """
        format the message only if it is an internal message and is an IO message
        """
        if self.internal and self.is_io:
            self.clean(actor=actor)
            self.add_preamble(actor=actor)
            self.color_lines(actor=actor)
            self.add_line_endings(actor=actor)

    def _exec_(self, actor=''):
        """
        send the message
        """
        if self.sending:
            LogRecord(f"LogRecord: {self.uuid} is already sending",
                                level='debug', stack_info=True, sources=[__name__])()
            return
        self.sending = True
        self.addupdate('Info', f"{'Start':<8}: send", actor, savedata=False)

        # If it came from the mud, pass each line through the event system to allow plugins to modify it
        if not self.internal and self.is_io:
            self.clean(actor=actor)
            tmessage = []
            for line in self.data:
                event_args = self.api('plugins.core.events:raise.event')(self.modify_data_event_name, args={'line': line,
                                                                                                        'internal': self.internal,
                                                                                                        'sendtoclient': True})

                if event_args['line'] != line:
                    self.addupdate('Modify', f"line modified by {self.modify_data_event_name}",
                                    f"{actor}:send:{self.modify_data_event_name}",
                                    extra={'line':line, 'event_args':event_args},
                                    savedata=False)
                    self.add_related_record(event_args)

                if event_args['sendtoclient']:
                    tmessage.append(event_args['line'])
                else:
                    self.addupdate('Modify', f"line removed because sendtoclient was set to False from {self.modify_data_event_name}",
                                    f"{actor}:send:{self.modify_data_event_name}",
                                    extra={'line':line},
                                    savedata=False)
                    self.add_related_record(event_args)

            self.replace(tmessage, f"{actor}:send:{self.modify_data_event_name}")
            self.addupdate('Info', f'After event {self.modify_data_event_name}', actor)

        if self.send_to_clients:
            self.format(f"{actor}:send")

            clients = self.clients or self.api(
                'plugins.core.clients:get.all.clients'
            )(uuid_only=True)
            for client_uuid in clients:
                if self.can_send_to_client(client_uuid):
                    client = self.api('plugins.core.clients:get.client')(client_uuid)
                    client.send_to(self)
                else:
                    LogRecord(f"## NOTE: Client {client_uuid} cannot receive message {str(self.uuid)}",
                            level='debug', sources=[__name__])()

        if self.is_io:
            self.api('plugins.core.events:raise.event')(self.read_data_event_name, args={'ToClientRecord': self})

        self.addupdate('Info', f"{'Complete':<8}: send", f"{actor}:send", savedata=False)
