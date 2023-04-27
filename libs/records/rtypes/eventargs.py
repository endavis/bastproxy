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

# 3rd Party

# Project
from libs.records.rtypes.base import BaseDictRecord


class EventArgsRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown', data: dict | None = None):
        """
        initialize the class
        """
        BaseDictRecord.__init__(self, owner_id, data, add_related_event_record=False)
        if 'notes' not in self.data:
            self.data['notes'] = {}
        self.event_name = event_name
        self.items_to_format_in_details.extend([('Event Name', 'event_name')])

