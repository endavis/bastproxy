# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/changelog.py
#
# File Description: Holds a class that monitors attributes
#
# By: Bast
"""
Holds a class that monitors attributes
"""
# Standard Library
import datetime
from uuid import uuid4
import traceback
import pprint

# 3rd Party

# Project

# class ChangeManager:
#     def __init__(self):
#         # TODO: add a way to limit the number of changes stored per object
#         self._cm_changes = {}
#         #self._cm_tracked_items = {}

#     def add_change(self, change: 'ChangeLogEntry'):
#         if change.tracked_item_uuid not in self._cm_changes:
#             self._cm_changes[change.tracked_item_uuid] = []
#         self._cm_changes[change.tracked_item_uuid].append(change)

#     def get_changes(self, uuid):
#         return sorted(self._cm_changes[uuid])

#     def get_all_changes(self, uuid):
#         new_list = []
#         if uuid in self._cm_changes:
#             new_list.extend(self._cm_changes[uuid])
#         for uuid in self._cm_changes:
#             new_list.extend(
#                 change
#                 for change in self._cm_changes[uuid]
#                 if change.extra.get('related_uuid') == uuid
#             )
#         new_list.sort()
#         return new_list

    # def add_tracked_item(self, item):
    #     self._cm_tracked_items[item._tracking_uuid] = item

    # def get_tracked_item(self, uuid):
    #     return self._cm_tracked_items.get(uuid, None)

# CHANGEMANAGER = ChangeManager()

def fix_header(header_name):
    return header_name.replace('_', ' ').title()

class ChangeLogEntry:
    def __init__(self, change_type, tracked_item_uuid, **kwargs):
        """
        change_type: one of 'attribute', 'list', 'dict'
        name: the name of the attribute, list, or dict
        kwargs: any other info about the change
        """
#        print(f"ChangeLogEntry: {change_type=} {tracked_item_uuid=} {kwargs=}")
        self.uuid = uuid4().hex
        self.type = change_type
        self.tracked_item_uuid = tracked_item_uuid
        self.action = kwargs.pop('action', 'unknown')
#       print(f"ChangeLogEntry: {self.action=}")
        self.method = kwargs.pop('method', '')
        self.location = kwargs.pop('location', '')
        self.extra = kwargs
        self.header_column_width = 17
        self.created_time = datetime.datetime.now(datetime.timezone.utc)
        self.stack = self.get_stack()
        for item in self.extra:
            if not isinstance(self.extra[item], str):
                self.extra[item] = repr(self.extra[item])
        # if self.action == 'unknown':
        #     print('S ACTION =============== unknown')
        #     for item in self.stack:
        #         print(f"### {item=}")
        #     print('E ACTION =============== unknown')

    def get_stack(self):
        stack = traceback.format_stack(limit=15)
        new_stack = []
        # don't need the last 2 lines
        for line in stack:
            new_stack.extend(line.splitlines() if line else [])
        return new_stack[:-2]

    def __repr__(self) -> str:
        return f"ChangeLogEntry: {self.created_time} {self.type} {self.tracked_item_uuid} {self.action} {self.method} '{self.location}' {self.extra}"

    def __eq__(self, value: object) -> bool:
        return self.uuid == value.uuid if isinstance(value, ChangeLogEntry) else False

    def __lt__(self, value: object) -> bool:
        return self.created_time < value.created_time if hasattr(value, 'created_time') else False # type: ignore

    def copy(self, new_type, new_tracked_item_uuid):
        extra = self.extra.copy()
        extra['action'] = self.action
        extra['method'] = self.method
        extra['location'] = self.location
        new_log = ChangeLogEntry(new_type, new_tracked_item_uuid, **extra)
        new_log.created_time = self.created_time
        new_log.stack = self.stack
        return new_log

    def format_detailed(self, show_stack: bool = False,
                        data_lines_to_show: int = 10):
        """
        format the change record
        """
        # args = self.api('plugins.core.commands:get.current.command.args')()
        # if 'show_data' in args:
        #     show_data = args['show_data']
        # if 'show_stack' in args:
        #     show_stack = args['show_stack']
        # if 'data_lines_to_show' in args:
        #     data_lines_to_show = int(args['data_lines_to_show'])
        item_order = ['created', 'type', 'location', 'action', 'sub_command', 'method',
                            'passed_index', 'locked', 'value', 'data_pre_change',
                            'data_post_change']

        tmsg =  [
            f"{'Change UUID':<{self.header_column_width}} : {self.uuid}",
            f"{'Object UUID':<{self.header_column_width}} : {self.tracked_item_uuid}"]

        for item in item_order:
            tmsg.extend(self.format_data(item, data_lines_to_show))

        if self.extra:
            for item in self.extra:
                if item in item_order:
                    continue
            tmsg.extend(self.format_data(item, data_lines_to_show))

        if show_stack and self.stack:
            tmsg.append(f"{'Stack':<{self.header_column_width}} :")
            tmsg.extend([f"{'':<{self.header_column_width}} {line}" for line in self.stack if line.strip()])

        return tmsg

    def format_data(self, name, data_lines_to_show):
        data = getattr(self, name) if hasattr(self, name) else self.extra[name] if name in self.extra else '-#@$%##$'

        if data == '-#@$%##$':
            return []

        header = fix_header(name)
        try:
            testdata = eval(data)
        except Exception as e:
            testdata = data

        if testdata in [None, 'None', '']:
            return []

        testdata_string = pprint.pformat(testdata, width=80).splitlines()

        if len(testdata_string) == 1:
            return [f"{header:<{self.header_column_width}} : {testdata}"]

        tmsg = [f"{header:<{self.header_column_width}} : {testdata_string[0]}"]
        tmsg.extend(f"{'':<{self.header_column_width}} : {line}" for line in testdata_string[1:data_lines_to_show])
        if len(testdata_string) > data_lines_to_show:
            tmsg.append(f"{'':<{self.header_column_width}} : ...")
        return tmsg
