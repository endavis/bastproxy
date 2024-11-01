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

    def get_all_related_records(self, record_uuid, recfilter=None):
        if recfilter is None:
            recfilter = ['LogRecprd']
        record = self.get_record(record_uuid)
        related_records = record.related_records()
        for related_record in related_records:
                record = self.get_record(related_record.uuid)
                if record.__class__.__name__ not in filter:
                    related_records.extend(self.get_all_related_records(related_record.uuid, recfilter))
        related_records = list(set(related_records))
        return related_records

    def get_children(self, record_uuid):
        record = self.get_record(record_uuid)
        return [rec.uuid for rec in self.record_instances.values() if rec.parent and rec.parent.uuid == record.uuid and rec.__class__.__name__ != 'LogRecord']

    def get_all_children(self, record_uuid):
        children = self.get_children(record_uuid)
        return {child: self.get_all_children(child) for child in children}

    def format_all_children(self, record_uuid):
        children = self.get_all_children(record_uuid)
        return [f"{'       ' * 0}{self.get_record(record_uuid).one_line_summary()}",
                *self.format_all_children_helper(children, 0)]

    def format_all_children_helper(self, children, indent = 0, emptybars = 0, output = None):
        output = output or []
        all_children = list(children.keys())
        for child in children:
            all_children.pop(all_children.index(child))
            output.append(f"{'    ' * emptybars}{' |  ' * (indent - emptybars)} |-> {self.get_record(child).one_line_summary()}")
            if not all_children:
                emptybars += 1
            self.format_all_children_helper(children[child], indent + 1, emptybars, output)
        return output

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
