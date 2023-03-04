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
    def __init__(self, plugin_id=None):
        """
        initialize the class
        """
        # Add an API
        self.api = API()
        # create a unique id for this message
        self.uuid = uuid4()
        # True if this was created internally
        self.plugin_id = plugin_id
        self.created =  datetime.datetime.now(datetime.timezone.utc)
        self.changes = ChangeManager()
        RMANAGER.add(self)
        #self.addchange('Create', 'init', None)

    def addchange(self, flag, action, actor, extra=None):
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
        change = {}
        change['flag'] = flag
        change['action'] = action
        change['actor'] = actor
        change['extra'] = extra
        change['time'] =  datetime.datetime.now(datetime.timezone.utc)

        change = ChangeRecord(flag, action, actor, extra)

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

class BaseDataRecord(BaseRecord, UserList):
    def __init__(self, message, internal=True, plugin_id=None):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message]
        UserList.__init__(self, message)
        BaseRecord.__init__(self, plugin_id)
        self.internal = internal

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
                from libs.records.rtypes.log import LogRecord
                LogRecord(f"clean - {self.uuid} Message.clean: line is not a string: {line}",
                          level='error', sources=[__name__])
        if new_message != self.data:
            self.data = new_message
            self.addchange('Modify', 'clean', actor)

    def addchange(self, flag, action, actor, extra=None, savedata=True):
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
        change = {}
        change['flag'] = flag
        change['action'] = action
        change['actor'] = actor
        change['extra'] = extra
        change['time'] =  datetime.datetime.now(datetime.timezone.utc)

        data = None
        if savedata:
            data = self.data[:]

        change = ChangeRecord(flag, action, actor, extra, data)

        self.changes.add(change)
