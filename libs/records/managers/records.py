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
import typing

# 3rd Party

# Project
from libs.api import API as BASEAPI
from libs.stack import SimpleStack

if typing.TYPE_CHECKING:
    from libs.records.rtypes.update import UpdateRecord

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
        # don't show these records in detailed output
        self.default_filter = ['LogRecord']

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

    def get_children(self, record_uuid, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        record = self.get_record(record_uuid)
        return [rec.uuid for rec in self.record_instances.values() if rec.parent and rec.parent.uuid == record.uuid and rec.__class__.__name__ not in rfilter]

    def get_all_children_dict(self, record_uuid, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_children(record_uuid)
        return {child: self.get_all_children_dict(child, rfilter) for child in children if self.get_record(child).__class__.__name__ not in rfilter}

    def get_all_children_list(self, record_uuid, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record_uuid, record_filter)
        return self.api('plugins.core.utils:get.keys.from.dict')(children)

    def flatten_keys(self, d, parent_key='', sep='.'):
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self.flatten_keys(v, new_key, sep=sep))
            else:
                items.append(new_key)
        return items

    def format_all_children(self, record_uuid, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record_uuid, rfilter)
        return [f"{'       ' * 0}{self.get_record(record_uuid).one_line_summary()}",
                *self.format_all_children_helper(children, record_filter=rfilter)]

    def format_all_children_helper(self, children, indent = 0, emptybar = None, output = None, record_filter=None):
        if not emptybar:
            emptybar = {}
        emptybar[indent] = False
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        output = output or []
        all_children = list(children.keys())
        pre_string = ''.join('    ' if emptybar[i] else ' |  ' for i in range(indent))
        for child in children:
            all_children.pop(all_children.index(child))
            output.append(f"{pre_string} |-> {self.get_record(child).one_line_summary()}")
            if not all_children:
                emptybar[indent] = True
            self.format_all_children_helper(children[child], indent + 1, emptybar, output, rfilter)
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
