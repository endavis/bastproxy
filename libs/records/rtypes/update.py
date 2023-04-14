# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/change.py
#
# File Description: Holds the change record type
#
# By: Bast
"""
Holds the change record type
"""
# Standard Library
from uuid import uuid4
import datetime
import traceback

# 3rd Party

# Project

class UpdateRecord(object):
    """
    a update event for a record
    flag: one of 'Modify', 'Set Flag', 'Info'
    action: a description of what was updated
    actor: the item that send the update (likely a plugin)
    extra: any extra info about this update
    data: the new data

    will automatically add the time and last 5 stack frames
    """
    def __init__(self, flag: str, action: str, actor: str = '', extra: dict | None = None, data=None):
        self.uuid = uuid4().hex
        self.time_taken = datetime.datetime.now(datetime.timezone.utc)
        self.flag = flag
        self.action = action
        self.actor = actor
        self.extra = {}
        if extra:
            self.extra |= extra
        self.data = data
        # Extract the last 7 stack frames
        self.stack = traceback.extract_stack(limit=7)

    def __str__(self):
        return f"{self.actor} {self.flag} {self.action} {self.data} {self.extra})"

    def format(self):
        """
        format the change record
        """
        if self.flag == 'Modify':
            return f"{self.actor} updated {self.action}"
        if self.flag == 'Set Flag':
            return f"{self.actor} set {self.action} to {self.data}"
        if self.flag == 'Info':
            return f"{self.actor} {self.action}"
