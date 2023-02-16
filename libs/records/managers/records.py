# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/managers/records.py
#
# File Description: a manager that handles records of all types
#
# By: Bast
"""
This module holds a manager that handles records of all types
"""
# Standard Library
from collections import deque

# 3rd Party

# Project
from libs.api import API as BASEAPI

API = BASEAPI()

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
