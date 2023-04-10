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
from libs.records.rtypes.change import ChangeRecord
from libs.records.managers.changes import ChangeManager
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
        self.changes = ChangeManager()
        RMANAGER.add(self)
        #self.addchange('Create', 'init', None)

    def addchange(self, flag: str, action: str, actor:str , extra: dict | None = None):
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
        change = ChangeRecord(flag, action, actor, extra)

        self.changes.add(change)

    def check_for_change(self, flag: str, action: str):
        """
        check if there is a change with the given flag and action
        """
        for change in self.changes:
            if change['flag'] == flag:
                if change['action'] == action:
                    return True
        return False

class BaseDataRecord(BaseRecord, UserList):
    def __init__(self, message: list[str] | str, internal: bool=True, owner_id: str=''):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message]
        UserList.__init__(self, message)
        BaseRecord.__init__(self, owner_id)
        self.internal = internal

    def replace(self, data, actor='', extra=''):
        """
        replace the data in the message
        """
        if not isinstance(data, list):
            data = [data]
        if data != self.data:
            self.data = data
            self.addchange('Modify', 'replace', actor, extra=extra)

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
        if new_message != self.data:
            self.data = new_message
            self.addchange('Modify', 'color_lines', actor, 'convert color codes to ansi codes on each item')

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
        if new_message != self.data:
            self.data = new_message
            self.addchange('Modify', 'clean', actor)

    def addchange(self, flag: str, action: str, actor: str, extra: str = '', savedata: bool = True):
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
        data = None
        if savedata:
            data = self.data[:]

        change = ChangeRecord(flag, action, actor, extra, data)

        self.changes.add(change)
