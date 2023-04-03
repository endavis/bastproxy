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
import asyncio

# 3rd Party

# Project
from libs.net.networkdata import NetworkData
from libs.records.rtypes.log import LogRecord
from libs.records.rtypes.base import BaseDataRecord

SETUPEVENTS = False

class ToClientRecord(BaseDataRecord):
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
    def __init__(self, message: list[str] | str, message_type: str='IO', clients: list|None=None, exclude_clients: list|None=None, preamble=True,
                 internal: bool=True, prelogin: bool=False, error: bool=False, color_for_all_lines=None):
        """
        initialize the class
        """
        super().__init__(message, internal)
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
        self.clients: list[str] = clients if clients else []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients if exclude_clients else []
        # This will set the color for all lines to the specified @ color
        self.color_for_all_lines: str = color_for_all_lines if color_for_all_lines else ''
        self.message_type: str = message_type
        # This is a flag to prevent the message from being sent to the client more than once
        self.sending: bool = False
        self.setup_events()

    def setup_events(self):
        global SETUPEVENTS
        if not SETUPEVENTS:
            SETUPEVENTS = True
            self.api('plugins.core.events:add:event')('ev_client_data_modify', __name__,
                                                description='An event to modify data before it is sent to the client',
                                                arg_descriptions={'ToClientRecord': 'A libs.records.ToClientRecord object'})
            self.api('plugins.core.events:add:event')('ev_client_data_read', __name__,
                                                description='An event to see data that was sent to the client',
                                                arg_descriptions={'ToClientRecord': 'A libs.records.ToClientRecord object'})

    @property
    def is_command_telnet(self):
        """
        A shortcut property to determine if this message is a Telnet Opcode.
        """
        return self.message_type == "COMMAND-TELNET"

    @property
    def is_io(self):
        """
        A shortcut property to determine if this message is normal I/O.
        """
        return self.message_type == "IO"

    @property
    def noansi(self):
        """
        return the message without ansi codes
        """
        newmessage: list[str] = []
        for item in self.data:
            newmessage.append(self.api('plugins.core.colors:strip:ansi')(item))
        return newmessage

    @property
    def color(self):
        """
        return the message with ansi codes converted to @ color codes
        """
        newmessage: list[str] = []
        for item in self.data:
            newmessage.append(self.api('plugins.core.colors:ansicode:to:colorcode')(item))
        return newmessage

    def set_send_to_clients(self, flag, actor='', extra=''):
        """
        set the send to clients flag
        """
        if flag != self.send_to_clients:
            self.send_to_clients = flag
            self.addchange('Set Flag', 'send_to_clients', actor=actor, extra=f"set to {flag}, {extra}", savedata=False)

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
            if self.api('plugins.core.clients:client:is:view:client')(client_uuid) and self.internal:
                return False
            # If the client is in the list of clients or self.clients is empty,
            # then we can check to make sure the client is logged in or the prelogin flag is set
            if not self.clients or client_uuid in self.clients:
                if self.api('plugins.core.clients:client:is:logged:in')(client_uuid) or self.prelogin:
                    # All checks passed, we can send to this client
                    return True
        return False

    def add_preamble(self, actor=''):
        """
        add the preamble to the message only if it is from internal and is an IO message
        """
        if self.preamble:
            preamblecolor = self.api('plugins.core.proxy:preamble:color:get')(error=self.error)
            preambletext = self.api('plugins.core.proxy:preamble:get')()
            new_message = []
            for item in self.data:
                    new_message.append(f"{preamblecolor}{preambletext}@w: {item}")
            if new_message != self.data:
                self.data = new_message
                self.addchange('Modify', 'preamble', actor, 'add a preamble to all items')

    def clean(self, actor=''):
        """
        clean the message
        """
        super().clean(actor)

    def color_lines(self, actor=''):
        """
        add the color to the beginning of all lines in the message
        """
        super().color_lines(self.color_for_all_lines, actor)

    def add_line_endings(self, actor=''):
        """
        add line endings to the message
        """
        new_message = []
        for item in self.data:
            new_message.append(f"{item}\n\r")
        if new_message != self.data:
            self.data = new_message
            self.addchange('Modify', 'add_line_endings', actor, 'add line endings to each item')

    def format(self, actor=''):
        """
        format the message only if it is an internal message and is an IO message
        """
        if self.internal and self.is_io:
            self.clean(actor=actor)
            self.add_preamble(actor=actor)
            self.color_lines(actor=actor)
            self.add_line_endings(actor=actor)

    def send(self, actor=''):
        """
        send the message
        """
        if self.sending:
            LogRecord(f"LogRecord: {self.uuid} is already sending",
                                level='debug', stack_info=True, sources=[__name__]).send()
            return
        self.sending = True
        self.addchange('Info', 'Starting Send', actor)
        if not self.internal:
            self.api('plugins.core.events:raise:event')('ev_client_data_modify', args={'ToClientRecord': self})
            self.addchange('Info', 'After event ev_modify_client_data', actor)
        if self.send_to_clients:
            self.format(actor=actor)
            loop = asyncio.get_event_loop()
            if self.clients:
                clients = self.clients
            else:
                clients = self.api('plugins.core.clients:get:all:clients')(uuid_only=True)
            for client_uuid in clients:
                if self.can_send_to_client(client_uuid):
                    client = self.api('plugins.core.clients:get:client')(client_uuid)
                    if self.is_io:
                        message = NetworkData(self.message_type, message=''.join(self), client_uuid=client_uuid)
                        loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
                    else:
                        for i in self:
                            message = NetworkData(self.message_type, message=i, client_uuid=client_uuid)
                            loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
                else:
                    LogRecord(f"## NOTE: Client {client_uuid} cannot receive message {str(self.uuid)}",
                            level='debug', sources=[__name__]).send()

            if not self.internal:
                self.api('plugins.core.events:raise:event')('ev_client_data_read', args={'ToClientRecord': self})
