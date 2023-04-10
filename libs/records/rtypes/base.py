# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/__init__.py
#
# File Description: Holds the base record type
#
# By: Bast
"""
Holds the base record type
"""
# Standard Library
from collections import UserList
from uuid import uuid4
import datetime

# 3rd Party

# Project
from libs.api import API
from libs.records.rtypes.update import UpdateRecord
from libs.records.managers.updates import UpdateManager
from libs.records.managers.records import RMANAGER

class BaseRecord:
    def __init__(self, owner_id: str = ''):
        """
        initialize the class
        """
        # create a unique id for this message
        self.uuid = uuid4().hex
        self.owner_id = owner_id if owner_id else f"{self.__class__.__name__}:{self.uuid}"
        # Add an API
        self.api = API(owner_id=self.owner_id)
        self.created =  datetime.datetime.now(datetime.timezone.utc)
        self.updates = UpdateManager()
        RMANAGER.add(self)

    def addupdate(self, flag: str, action: str, actor:str , extra: dict | None = None):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag', 'Info'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
            extra: any extra info about this change
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        change = UpdateRecord(flag, action, actor, extra)

        self.updates.add(change)

    def check_for_change(self, flag: str, action: str):
        """
        check if there is a change with the given flag and action
        """
        return any(
            update['flag'] == flag and update['action'] == action
            for update in self.updates
        )

class BaseDataRecord(BaseRecord, UserList):
    def __init__(self, message: list[str | bytes] | list[str] | list[bytes] | str | bytes, message_type: str = 'IO', internal: bool=True, owner_id: str=''):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message]
        UserList.__init__(self, message)
        BaseRecord.__init__(self, owner_id)
        # This is a flag to determine if this message is internal or not
        self.internal = internal
        # This is the message id, see the derived classes for more info
        self.message_type: str = message_type
        # This is a flag to prevent the message from being sent to the client more than once
        self.sending = False

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

    def add_line_endings(self, actor=''):
        """
        add line endings to the message
        """
        new_message = []
        for item in self.data:
            new_message.append(f"{item}\n\r")
        self.replace(new_message, f"{actor}:add_line_endings", extra={'msg':'add line endings to each item'})

    def replace(self, data, actor='', extra: dict | None = None):
        """
        replace the data in the message
        """
        if not isinstance(data, list):
            data = [data]
        if data != self.data:
            self.data = data
            self.addupdate('Modify', 'replace', actor, extra=extra)

    def color_lines(self, color: str, actor=''):
        """
        color the message and convert all colors to ansicodes

        color is the color for all lines

        actor is the item that ran the color function
        """
        new_message: list[str] = []
        if not self.api('libs.api:has')('plugins.core.colors:colorcode:to:ansicode'):
            return
        for line in self.data:
            if color:
                if '@w' in line:
                    line_list = line.split('@w')
                    new_line_list = []
                    for item in line_list:
                        if item:
                            new_line_list.append(f"{color}{item}")
                        else:
                            new_line_list.append(item)
                    line = f"@w{color}".join(new_line_list)
                if line:
                    line = f"{color}{line}@w"
            new_message.append(self.api('plugins.core.colors:colorcode:to:ansicode')(line))

        self.replace(new_message, f"{actor}:color_lines", extra={'msg':'convert color codes to ansi codes on each item'})

    def clean(self, actor: str = ''):
        """
        clean the message

        actor is the item that ran the clean function

        converts it to a string
        splits it on a newline
        removes newlines and carriage returns from the end of the line
        """
        new_message: list[str] = []
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
                from libs.records.rtypes.log import LogRecord
                LogRecord(f"clean - {self.uuid} Message.clean: line is not a string: {line}",
                          level='error', sources=[__name__])

        self.replace(new_message, f"{actor}:clean", extra={'msg':'clean each item'})

    def addupdate(self, flag: str, action: str, actor: str, extra: dict | None = None, savedata: bool = True):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag', 'Info'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
            extra:  a dict of any extra info about this change
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        data = self.data[:] if savedata else None
        change = UpdateRecord(flag, action, actor, extra, data)

        self.updates.add(change)
