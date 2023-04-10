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
from libs.records.rtypes.update import UpdateRecord

class EventArgsRecord(BaseRecord, UserDict):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown', data: dict | None = None):
        """
        initialize the class
        """
        if data:
            if not isinstance(data, dict):
                raise TypeError(f"data must be a dict not {type(data)}")
        else:
            data = {}
        if 'notes' not in data:
             data['notes'] = {}
        UserDict.__init__(self, data)
        BaseRecord.__init__(self, owner_id)
        self.event_name = event_name

    def addupdate(self, flag: str, action: str, actor: str, extra: dict | None = None, saveargs: bool = True):
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
        data = self.copy() if saveargs else None
        change = UpdateRecord(flag, action, actor, extra, data)

        self.updates.add(change)
