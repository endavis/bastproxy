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


class EventDataRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown', data: dict | None = None):
        """
        initialize the class
        """
        BaseDictRecord.__init__(self, owner_id, data)
        self.event_name = event_name

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.__class__.__name__:<20} {self.uuid} {self.event_name}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].append(('Event Name', 'event_name'))
        return attributes
