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

# 3rd Party

# Project
from libs.api import API as BASEAPI
from libs.stack import SimpleStack

class RecordManager(object):
    def __init__(self):
        """
        Keep the last 1000 records of each type
        track the active record
        """
        self.max_records: int = 1000
        self.records: dict[str, list] = {}
        self.api = BASEAPI(owner_id=__name__)
        self.record_instances = {}
        self.active_record_stack = SimpleStack()

    def start(self, record):
        self.active_record_stack.push(record)

    def end(self, record):
        if record != self.active_record_stack.peek():
            from libs.records import LogRecord
            LogRecord(f"RecordManger end: Record {record} is not the same as the active record {self.active_record_stack.peek()}", level='warning')
            self.active_record_stack.remove(record)
        else:
            self.active_record_stack.pop()

    def get_latest_record(self):
        return self.active_record_stack.peek()

    def add(self, record):
        queuename = record.__class__.__name__
        if queuename not in self.records:
            self.records[queuename] = []
        if record.uuid in self.record_instances:
            from libs.records import LogRecord
            LogRecord(f"Record UUID collision {record.uuid} already exists in the record manager", level='error')()
        self.records[queuename].append(record)
        self.record_instances[record.uuid] = record

        # check if we need to pop an item off the front
        if len(self.records[queuename]) > self.max_records:
            poppeditem = self.records[queuename].pop(0)
            del self.record_instances[poppeditem.uuid]

    def get_types(self):
        return [(key, len(self.records[key])) for key in self.records.keys()]

    def get_records(self, recordtype, count=10):
        records = self.records.get(recordtype, [])
        return records[-count:]

    def get_record(self, recordid):
        return self.record_instances.get(recordid, None)

RMANAGER = RecordManager()
