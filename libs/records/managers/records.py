# Project: bastproxy
# Filename: libs/records/managers/records.py
#
# File Description: a manager that handles records of all types
#
# By: Bast
"""This module holds a manager that handles records of all types."""

import contextlib

# Standard Library
from typing import TYPE_CHECKING

# 3rd Party
# Project
from libs.api import API as BASEAPI
from libs.queue import SimpleQueue
from libs.stack import SimpleStack

if TYPE_CHECKING:
    pass


class RecordManager:
    def __init__(self):
        """Keep the last max_records of each type
        track the active record.
        """
        self.max_records: int = 5000
        self.records: dict[str, SimpleQueue] = {}
        self.api = BASEAPI(owner_id=__name__)
        self.record_instances = {}
        self.active_record_stack = SimpleStack()
        # don't show these records in detailed output
        self.default_filter = ["LogRecord"]

    def start(self, record):
        self.active_record_stack.push(record)

    def end(self, record):
        if record != self.active_record_stack.peek():
            from libs.records import LogRecord

            LogRecord(
                f"RecordManger end: Record {record} is not the same as the active record {self.active_record_stack.peek()}",
                level="warning",
            )
            self.active_record_stack.remove(record)
        else:
            self.active_record_stack.pop()

    def get_latest_record(self):
        return self.active_record_stack.peek()

    def get_children(self, record, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        return list(
            {
                rec
                for rec in self.record_instances.values()
                for parent in rec.parents
                if parent.uuid == record.uuid and rec.__class__.__name__ not in rfilter
            }
        )

    def get_all_children_dict(self, record, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_children(record, record_filter)
        children.sort()
        return {
            child: self.get_all_children_dict(child, rfilter)
            for child in children
            if child.__class__.__name__ not in rfilter
        }

    def get_all_children_list(self, record, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record, record_filter)
        return self.api("plugins.core.utils:get.keys.from.dict")(children)

    def format_all_children(self, record, record_filter=None):
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record, rfilter)
        return [
            f"{'       ' * 0}{record.one_line_summary()}",
            *self.format_all_children_helper(children, record_filter=rfilter),
        ]

    def format_all_children_helper(
        self, children, indent=0, emptybar=None, output=None, record_filter=None
    ):
        if not emptybar:
            emptybar = {}
        emptybar[indent] = False
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        output = output or []
        all_children = list(children.keys())
        pre_string = "".join("    " if emptybar[i] else " |  " for i in range(indent))
        for child in children:
            all_children.pop(all_children.index(child))
            output.append(f"{pre_string} |-> {child.one_line_summary()}")
            if not all_children:
                emptybar[indent] = True
            self.format_all_children_helper(
                children[child], indent + 1, emptybar, output, rfilter
            )
        return output

    def add(self, record):
        queuename = record.__class__.__name__
        if queuename not in self.records:
            self.records[queuename] = SimpleQueue(self.max_records)
        if record.uuid in self.record_instances:
            from libs.records import LogRecord

            LogRecord(
                f"Record UUID collision {record.uuid} already exists in the record manager",
                level="error",
            )()
        self.records[queuename].enqueue(record)
        self.record_instances[record.uuid] = record

        if last_record := self.records[queuename].last_automatically_removed_item:
            with contextlib.suppress(KeyError):
                del self.record_instances[last_record.uuid]

    def get_types(self):
        return [(key, self.records[key].size()) for key in self.records.keys()]

    def get_records(self, recordtype, count=10):
        records = self.records.get(recordtype, None)
        return records.get_last_x(count) if records else records

    def get_record(self, recordid):
        return self.record_instances.get(recordid, None)


RMANAGER = RecordManager()
