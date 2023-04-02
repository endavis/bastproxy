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

class RecordManager(object):
    def __init__(self):
        """
        Keep the last 1000 records of each type
        """
        self.max_records = 1000
        self.records = {}
        self.api = BASEAPI(owner_id=__name__)
        self.api.MANAGERS['records'] = self

    def add(self, record):
        queuename = record.__class__.__name__
        if queuename not in self.records:
            self.records[queuename] = deque(maxlen=self.max_records)
        self.records[queuename].append(record)

RMANAGER = RecordManager()
