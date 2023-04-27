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
from collections import UserDict

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.update import UpdateRecord

class CmdArgsRecord(BaseRecord, UserDict):
    def __init__(self, owner_id: str = '', data: dict | None = None, arg_string: str = ''):
        """
        initialize the class
        """
        if data:
            if not isinstance(data, dict):
                raise TypeError(f"data must be a dict not {type(data)}")
        else:
            data = {}
        #data['arg_string'] = arg_string
        UserDict.__init__(self, data)
        BaseRecord.__init__(self, owner_id)
        self.arg_string: str = arg_string
        self.items_to_format_in_details.extend([('Arg String', 'arg_string')])
        self.addupdate('Info', 'Init', self.__class__.__name__, savedata=True)
        # if event_record := self.api('plugins.core.events:get.current.event.record')():
        #     event_record.add_related_record(self)

    def addupdate(self, flag: str, action: str, actor: str, extra: dict | None = None, savedata: bool = True):
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
        data = self.copy() if savedata else None
        change = UpdateRecord(self, flag, action, actor, extra, data)

        self.updates.add(change)
