# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/eventargs.py
#
# File Description: Holds the record type for event arguments
#
# By: Bast
"""
Holds the log record type
"""
# Standard Library
import datetime
from collections import UserDict

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.change import ChangeRecord

class EventArgsRecord(BaseRecord, UserDict):
    def __init__(self, plugin_id=None, event_name=None, data=None):
        """
        initialize the class
        """
        if data:
            if not isinstance(data, dict):
                raise TypeError(f"data must be a dict not {type(data)}")
        else:
            data = {}
        UserDict.__init__(self, data)
        BaseRecord.__init__(self, plugin_id)
        self.event_name = event_name

    def addchange(self, flag, action, actor, extra=None, saveargs=True):
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
        if saveargs:
            data = self.copy()

        change = ChangeRecord(flag, action, actor, extra, data)

        self.changes.add(change)