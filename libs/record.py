# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/message.py
#
# File Description: a message class for sending through libs.io
#
# By: Bast
"""
This plugin has a classes for various record types
    ToClientRecord - data to send to the client

At this time, this is not used to send to the mud
"""
# Standard Library
from collections import UserList, deque
from uuid import uuid4
import asyncio
import logging

# 3rd Party

# Project
from libs.net.networkdata import NetworkData
from libs.api import API

class RecordManager(object):
    def __init__(self):
        """
        Keep the last 1000 records of each type
        """
        self.max_records = 1000
        self.records = {}
        self.records['LogRecord'] = deque(maxlen=self.max_records)
        self.records['ToMudRecord'] = deque(maxlen=self.max_records)
        self.records['ToClientRecord'] = deque(maxlen=self.max_records)

    def add(self, record):
        self.records[record.__class__.__name__].append(record)

class BaseRecord(UserList):
    def __init__(self, message, internal=True):
        """
        initialize the class
        """
        super().__init__(message)
        # Add an API
        self.api = API()
        # create a unique id for this message
        self.uuid = uuid4()
        self.logger = logging.getLogger(self.__class__.__name__ + '.' + str(self.uuid))
        # True if this was created internally
        self.internal = internal
        self.snapshots = []
        RManager.add(self)

    def clean(self, actor=None):
        """
        clean the message

        actor is the item that ran the clean function

        converts it to a string
        splits it on a newline
        removes newlines and carriage returns from the end of the line
        """
        new_message = []
        for line in self.data:
            if isinstance(line, bytes):
                line = line.decode('utf-8')
            if isinstance(line, str):
                if '\n' in line:
                    tlist = line.split('\n')
                    for tline in tlist:
                        new_message.append(tline.rstrip('\r').rstrip('\n'))
                else:
                    new_message.append(line.rstrip('\r').rstrip('\n'))
            else:
                #self.api('libs.io:send:error')(Message(['Error: Message.clean: line is not a string'], internal=True))
                self.api('libs.io:send:error')(f"Error: {self.uuid} Message.clean: line is not a string: {line}")
        self.data = new_message
        self.snapshot('Modify', 'clean', actor)

    def snapshot(self, flag, action, actor):
        """
        add a snapshot of the message
            flag: one of 'Modify'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
        a message should be snapshotted at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        snapshot = {}
        snapshot['flag'] = flag
        snapshot['action'] = action
        snapshot['actor'] = actor
        snapshot['message'] = self.data
        self.snapshots.append(snapshot)

    def check_for_snapshot(self, flag, action):
        """
        check if there is a snapshot with the given flag and action
        """
        for snapshot in self.snapshots:
            if snapshot['flag'] == flag:
                if snapshot['action'] == action:
                    return True
        return False


class ToClientRecord(BaseRecord):
    """
    a record to a client, this can originate with the mud or internally
    data from the mud will immediately be transformed into this type of record
    will not neccesarily end up going to the client

    Valid message_types:
        'IO' - a regular string to send to the client
        'TELNET-COMMAND' - a telnet command to the client

    when it goes on the client queue, it will be converted to a NetworkData object
    """
    def __init__(self, message, message_type='IO', clients=None, exclude_clients=None, preamble=True,
                 internal=True, prelogin=False, error=False):
        """
        initialize the class
        """
        if type(message) == str or type(message) == bytes:
            message = [message]
        super().__init__(message, internal)
        # flag to include preamble when sending to client
        self.preamble = preamble
        # flag to send to client before login
        self.prelogin = prelogin
        # flag for this is an error message
        self.error = error
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients = clients
        self.message_type = message_type
        if not self.clients:
            self.clients = []
        # clients to exclude, a list of client uuids
        self.exclude_clients = exclude_clients
        if not self.exclude_clients:
            self.exclude_clients = []

    def add_client(self, client_uuid):
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
            # If the client is in the list of clients to send to or send to all is true,
            # then we can send the message to this client
            if not self.clients or client_uuid in self.clients:
                if self.api('plugins.core.clients:client:is:logged:in')(client_uuid) or self.prelogin:
                    return True
        return False

    def add_preamble(self, actor=None):
        """
        add the preamble to the message only if it is from internal and is an IO message
        """
        if self.preamble and self.internal and self.message_type == 'IO':
            preamblecolor = self.api('plugins.core.proxy:preamble:color:get')(error=self.error)
            preambletext = self.api('plugins.core.proxy:preamble:get')()
            new_message = []
            for item in self.data:
                    new_message.append(f"{preamblecolor}{preambletext}@w {item}")
            self.data = new_message
            self.snapshot('Modify', 'preamble', actor)

    def convert_to_bytes(self, actor=None):
        """
        convert the message to bytes
        """
        byte_message = []
        for i in self.data:
            if type(i) == str:
                i = i.encode('utf-8')
            byte_message.append(i)
        self.data = byte_message
        self.snapshot('Modify', 'to_bytes', actor)

    def clean(self, actor=None):
        """
        clean the message
        """
        # clean only if internal and 'IO'
        if self.internal and self.message_type == 'IO':
            super().clean(actor)

    def convert_colors(self, actor=None):
        """
        convert the message colors
        """
        # convert colors only if internal and 'IO'
        if self.internal and self.message_type == 'IO':
            converted_message = []
            for i in self.data:
                if self.api('libs.api:has')('plugins.core.colors:colorcode:to:ansicode'):
                    converted_message.append(self.api('plugins.core.colors:colorcode:to:ansicode')(i))
            self.data = converted_message
            self.snapshot('Modify', 'convert_colors', actor)

    def add_line_endings(self, actor=None):
        """
        add line endings to the message
        """
        # add line endings only if internal and 'IO'
        if self.internal and self.message_type == 'IO':
            new_message = []
            for item in self.data:
                new_message.append(f"{item}\n\r")
            self.data = new_message
            self.snapshot('Modify', 'add_line_endings', actor)

    def send(self, actor=None):
        """
        send the message
        """
        self.clean(actor=actor)
        self.add_preamble(actor=actor)
        self.convert_colors(actor=actor)
        self.add_line_endings(actor=actor)
        self.convert_to_bytes(actor=actor)
        loop = asyncio.get_event_loop()
        if self.clients:
            clients = self.clients
        else:
            clients = self.api('plugins.core.clients:get:all:clients')(uuid_only=True)
        for client_uuid in clients:
            if self.can_send_to_client(client_uuid):
                client = self.api('plugins.core.clients:get:client')(client_uuid)
                if self.message_type == 'IO':
                    message = NetworkData(self.message_type, message=b''.join(self), client_uuid=client_uuid)
                    loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
                else:
                    for i in self:
                        message = NetworkData(self.message_type, message=i, client_uuid=client_uuid)
                        loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
            else:
                self.logger.debug(f"## NOTE: Client {client_uuid} cannot receive this message")

RManager = RecordManager()