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
import time
import traceback

# 3rd Party

# Project
from libs.net.networkdata import NetworkData
from libs.api import API

class ChangeRecord(object):
    """
    a change event for a record
    flag: one of 'Modify', 'Set Flag'
    action: a description of what was changed
    actor: the item that changed the message (likely a plugin)
    extra: any extra info about this change
    data: the new data

    will automatically add the time and last 5 stack frames
    """
    def __init__(self, flag, action, actor=None, extra=None, data=None):
        self.uuid = uuid4()
        self.time_taken = time.time()
        self.flag = flag
        self.action = action
        self.actor = actor
        self.extra = extra
        self.data = data
        # Extract the last 5 stack frames
        self.stack = traceback.extract_stack(limit=5)

    def format(self):
        """
        format the change record
        """
        if self.flag == 'Modify':
            return f"{self.actor} changed {self.action}"
        if self.flag == 'Set Flag':
            return f"{self.actor} set {self.action} to {self.data}"

class ChangeManager(object):
    """
    a class to manage changes to records

    each record instance will have one of these
    """
    def __init__(self):
        self.changes = deque(maxlen=1000)

    def add(self, change):
        self.changes.append(change)

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
        API.MANAGERS['records'] = self

    def add(self, record):
        self.records[record.__class__.__name__].append(record)

RMANAGER = RecordManager()

class BaseRecord(UserList):
    def __init__(self, message, internal=True):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message]
        super().__init__(message)
        # Add an API
        self.api = API()
        # create a unique id for this message
        self.uuid = uuid4()
        # True if this was created internally
        self.internal = internal
        self.changes = ChangeManager()
        RMANAGER.add(self)

    def replace(self, data, actor=None, extra=None):
        """
        replace the data in the message
        """
        if not isinstance(data, list):
            data = [data]
        if data != self.data:
            self.data = data
            self.addchange('Modify', 'replace', actor, extra=extra)

    def color(self, color, actor=None):
        """
        color the message

        actor is the item that ran the color function

        """
        new_message = []
        if not self.api('libs.api:has')('plugins.core.colors:colorcode:to:ansicode'):
            return
        if color:
            for line in self.data:
                if '@x' in line:
                    line_list = line.split('@x')
                    new_line_list = []
                    for item in line_list:
                        new_line_list.append(f"{color}{item}")
                    line = f"@x{color}".join(new_line_list)
                line = f"{color}{line}@x"
                new_message.append(self.api('plugins.core.colors:colorcode:to:ansicode')(line))
            if new_message != self.data:
                self.data = new_message
                self.addchange('Modify', 'color', actor)

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
                LogRecord(f"clean - {self.uuid} Message.clean: line is not a string: {line}",
                          level='error', sources=[__name__])
        if new_message != self.data:
            self.data = new_message
            self.addchange('Modify', 'clean', actor)

    def addchange(self, flag, action, actor, extra=None, savedata=True):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        change = {}
        change['flag'] = flag
        change['action'] = action
        change['actor'] = actor
        change['extra'] = extra
        change['time'] = time.localtime()

        data = None
        if savedata:
            data = self.data

        change = ChangeRecord(flag, action, actor, extra, data)

        self.changes.add(change)

    def check_for_change(self, flag, action):
        """
        check if there is a change with the given flag and action
        """
        for change in self.changes:
            if change['flag'] == flag:
                if change['action'] == action:
                    return True
        return False

class LogRecord(BaseRecord):
    """
    a simple message record for logging, this may end up sent to a client
    """
    def __init__(self, message, level='info', sources=None, **kwargs):
        """
        initialize the class
        """
        super().__init__(message, internal=True)
        # The type of message
        self.level = level
        # The sources of the message for logging purposes, a list
        self.sources = sources
        if not self.sources:
            self.sources = []
        self.kwargs = kwargs
        self.wasemitted = {}
        self.wasemitted['console'] = False
        self.wasemitted['file'] = False
        self.wasemitted['client'] = False

    def color(self, actor=None):
        """
        color the message

        actor is the item that ran the color function
        """
        if not self.api('libs.api:has')('plugins.core.log:get:level:color'):
            return
        color = self.api('plugins.core.log:get:level:color')(self.level)
        super().color(color, actor)

    def add_source(self, source):
        """
        add a source to the message
        """
        if source not in self.sources:
            self.sources.append(source)

    def format(self, actor=None):
        self.clean(actor)
        self.color(actor)

    def send(self, actor=None):
        """
        send the message to the logger
        """
        #print(f"Sending {self.data} to logger")
        self.format(actor)
        for i in self.sources:
            if i:
                logger = logging.getLogger(i)
                loggingfunc = getattr(logger, self.level)
                loggingfunc(self, **self.kwargs)

    def __str__(self):
        """
        return the message as a string
        """
        return '\n'.join(self.data)

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
                 internal=True, prelogin=False, error=False, color_for_all_lines=None):
        """
        initialize the class
        """
        super().__init__(message, internal)
        # flag to include preamble when sending to client
        self.preamble = preamble
        # flag to send to client before login
        self.prelogin = prelogin
        # flag for this is an error message
        self.error = error
        # This is so that events can set this and it will not be sent to the client
        self.send_to_clients = True
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients = clients
        # This will set the color for all lines in the message
        self.color_for_all_lines = color_for_all_lines
        self.message_type = message_type
        if not self.clients:
            self.clients = []
        # clients to exclude, a list of client uuids
        self.exclude_clients = exclude_clients
        if not self.exclude_clients:
            self.exclude_clients = []

    def set_send_to_clients(self, flag, actor=None, extra=None):
        """
        set the send to clients flag
        """
        if flag != self.send_to_clients:
            self.send_to_clients = flag
            self.addchange('Set Flag', 'send_to_clients', actor=actor, extra=f"set to {flag}, {extra}", savedata=False)

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
            # then we can check to make sure the client is logged in or the prelogin flag is set
            if not self.clients or client_uuid in self.clients:
                if self.api('plugins.core.clients:client:is:logged:in')(client_uuid) or self.prelogin:
                    # All checks passed, we can send to this client
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
            if new_message != self.data:
                self.data = new_message
                self.addchange('Modify', 'preamble', actor, 'add a preamble to all items')

    def convert_to_bytes(self, actor=None):
        """
        convert the message to bytes
        """
        byte_message = []
        for i in self.data:
            if isinstance(i, str):
                i = i.encode('utf-8')
            byte_message.append(i)
        if byte_message != self.data:
            self.data = byte_message
            self.addchange('Modify', 'to_bytes', actor, 'convert all items to byte strings')

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
            if self.data != converted_message:
                self.data = converted_message
                self.addchange('Modify', 'convert_colors', actor, 'convert color codes to ansi codes on each item')

    def color(self, actor=None):
        """
        add the color to the beginning of all lines in the message
        """
        # add color only if internal and 'IO'
        if self.internal and self.message_type == 'IO':
            super().color(self.color_for_all_lines, actor)

    def add_line_endings(self, actor=None):
        """
        add line endings to the message
        """
        # add line endings only if internal and 'IO'
        if self.internal and self.message_type == 'IO':
            new_message = []
            for item in self.data:
                new_message.append(f"{item}\n\r")
            if new_message != self.data:
                self.data = new_message
                self.addchange('Modify', 'add_line_endings', actor, 'add line endings to each item')

    def format(self, actor=None):
        """
        format the message
        """
        # format only if internal and 'IO'
        self.clean(actor=actor)
        self.color(actor=actor)
        self.add_preamble(actor=actor)
        self.convert_colors(actor=actor)
        self.add_line_endings(actor=actor)
        self.convert_to_bytes(actor=actor)

    def send(self, actor=None):
        """
        send the message
        """
        if not self.internal:
            self.api('plugins.core.events:raise:event')('before_client_send', args={'ToClientRecord': self})
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
                    if self.message_type == 'IO':
                        message = NetworkData(self.message_type, message=b''.join(self), client_uuid=client_uuid)
                        loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
                    else:
                        for i in self:
                            message = NetworkData(self.message_type, message=i, client_uuid=client_uuid)
                            loop.call_soon_threadsafe(client.msg_queue.put_nowait, message)
                else:
                    LogRecord(f"## NOTE: Client {client_uuid} cannot receive message {str(self.uuid)}",
                              level='debug', sources=[__name__]).send()

            if not self.internal:
                self.api('plugins.core.events:raise:event')('after_client_send', args={'ToClientRecord': self})


