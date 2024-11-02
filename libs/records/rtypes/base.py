# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/__init__.py
#
# File Description: Holds the base record type
#
# By: Bast
"""
Holds the base record type
"""
# Standard Library
import datetime
import traceback
import pprint
from collections import UserList, UserDict
from uuid import uuid4
from typing import TYPE_CHECKING

# 3rd Party

# Project
from libs.api import API
from libs.records.rtypes.update import UpdateRecord
from libs.records.managers.updates import UpdateManager
from libs.records.managers.records import RMANAGER
from libs.tracking.utils.attributes import AttributeMonitor

if TYPE_CHECKING:
    from libs.records.rtypes.networkdata import NetworkDataLine

class BaseRecord(AttributeMonitor):
    def __init__(self, owner_id: str = '', track_record=True):
        """
        initialize the class
        """
        AttributeMonitor.__init__(self)
        self._attributes_to_monitor.append('parent')
        # create a unique id for this message
        self.uuid = uuid4().hex
        self.owner_id = owner_id or f"{self.__class__.__name__}:{self.uuid}"
        # Add an API
        self.api = API(owner_id=self.owner_id)
        self.created = datetime.datetime.now(datetime.timezone.utc)
        self.updates = UpdateManager()
        self.execute_time_taken = -1
        self.track_record = track_record
        self.column_width = 15
        stack = traceback.format_stack(limit=10)
        self.stack_at_creation = self.fix_stack(stack)
        if self.api('libs.api:has')('plugins.core.events:get.event.stack'):
            self.event_stack = self.api('plugins.core.events:get.event.stack')()
        else:
            self.event_stack = ['No event stack available']

        current_active_record = RMANAGER.get_latest_record()
        self.parent = current_active_record or None
        RMANAGER.add(self)

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        return self.uuid == other.uuid if isinstance(other, BaseRecord) else False

    def __repr__(self):
        return f"{self.__class__.__name__}:{self.uuid})"

    def _onchange__all(self, name, original_value, new_value):
        """
        Track changes to attributes, works in conjunction with the AttributeMonitor class
        """
        self.addupdate('Modify', f"{name} attribute changed", extra={'original':original_value, 'new':new_value})

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        if self.execute_time_taken > 0:
            return f"{self.__class__.__name__:<20} {self.uuid} {self.owner_id} {self.execute_time_taken:.2f}ms"
        else:
            return f"{self.__class__.__name__:<20} {self.uuid} {self.owner_id}"

    def addupdate(self, flag: str, action: str, actor: str = '', extra: dict | None = None):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag', 'Info'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
            extra: any extra info about this change
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        change = UpdateRecord(self, flag, action, actor, extra)

        self.updates.add(change)

    def get_all_updates(self, update_filter=None) -> list[UpdateRecord]:
        """
        get all updates for this record
        """
        updates = []
        update_filter = update_filter or []
        for record_uuid in RMANAGER.get_all_children_list(self.uuid, record_filter=update_filter):
            record = RMANAGER.get_record(record_uuid)
            updates.extend(update for update in record.updates if update.parent.__class__.__name__ not in update_filter)
        updates.extend(self.updates)

        updates.sort(key=lambda x: x.time_taken)
        return updates

    def get_update(self, uuid):
        """
        get the last update for this record
        """
        if record := self.updates.get_update(uuid):
            return record

        for child_record_uuid in RMANAGER.get_all_children_list(self.uuid):
            child_record = RMANAGER.get_record(child_record_uuid)
            if child_record.updates.get_update(uuid):
                return record

    def fix_stack(self, stack):
        """
        turn the stack into a list of lines
        """
        new_stack = []
        for line in stack:
            new_stack.extend([nline for nline in line.splitlines() if nline])
        return new_stack

    def get_attributes_to_format(self):
        """
        attributes to format in the details
        0 will be the top section
        1 is the middle section
        3 is the bottom section
        """
        default_attributes = {0:[('UUID', 'uuid'), ('Owner ID', 'owner_id'),
                      ('Creation Time', 'created'), ('Parent', 'parent'),
                      ('Exec Time (ms)', 'execute_time_taken')],
                1:[],
                2:[]}

        for item in self._attributes_to_monitor:
            orig_value = self._am_get_original_value(item)
            if orig_value == getattr(self, item):
                default_attributes[0].append((f"{item}", item))
            else:
                default_attributes[0].append((item, f"changed from '{repr(self._am_get_original_value(item))}' to '{repr(getattr(self, item))}'"))

        return default_attributes

    def get_formatted_details(self, full_children_records=False,
                              include_updates=True, update_filter=None,
                              include_children_records=True) -> list[str]:
        """
        get a formatted detail string
        """
        column_width = 15
        msg = [
                f"{'Type':<{column_width}} : {self.__class__.__name__}",
              ]

        attributes = self.get_attributes_to_format()
        for level in attributes:
            for item_string, item_attr in attributes[level]:
                if isinstance(item_attr, str):
                    attr = getattr(self, item_attr) if hasattr(self, item_attr) else item_attr
                else:
                    attr = item_attr
                if isinstance(attr, (list, dict)):
                    msg.append(f"{item_string:<{self.column_width}} : ")
                    msg.extend(f"{'':<15} : {line}" for line in pprint.pformat(attr, width=120).splitlines())
                else:
                    msg.append(f"{item_string:<{self.column_width}} : {attr}")

        msg.extend(
            [
                "Event Stack at Creation :",
                *[f"    {event}" for event in self.event_stack],
                "Call Stack at Creation :",
                *[f"    {line}" for line in self.stack_at_creation if line],
            ]
        )
        if include_children_records:
            if full_children_records:
                children_records = RMANAGER.get_all_children_dict(self.uuid, record_filter=update_filter)
                msg.extend(["Children Records :",
                            '---------------------------------------'])
                for record in children_records:
                    msg.extend(f"     {line}" for line in record.get_formatted_details(full_children_records=False,
                                                            include_updates=False,
                                                            update_filter=update_filter,
                                                            include_children_records=False))
                    msg.append('---------------------------------------')
            else:
                msg.extend(["Children Records :",
                    *RMANAGER.format_all_children(self.uuid, record_filter=update_filter),
                ])
        if include_updates:
            msg.extend(["Updates :",
                        '-------------------------',
            ])
            for update in self.get_all_updates(update_filter):
                msg.extend([f"   {line}" for line in update.format_detailed()])
                msg.append('-------------------------')
        return msg

    def check_for_change(self, flag: str, action: str):
        """
        check if there is a change with the given flag and action
        """
        return any(
            update['flag'] == flag and update['action'] == action
            for update in self.updates
        )

    # def __str__(self):
    #     return f"{self.__class__.__name__}:{self.uuid})"

    def _exec_(self, actor):
        """
        override this in the derived classes if needed
        """
        raise NotImplementedError

    def __call__(self, actor='Unknown'):
        """
        Enable tracking of the class execution
        """
        if self.track_record:
            tracking_uuid = self.api('libs.timing:start')(f'{self.__class__.__name__}:{self.uuid}.__call__')
            RMANAGER.start(self)
            self._exec_(actor)
            RMANAGER.end(self)
            self.execute_time_taken = self.api('libs.timing:finish')(tracking_uuid)
        else:
            self._exec_(actor)

class TrackedUserList(BaseRecord, UserList):
    """
    this is a Userlist whose updates are tracked
    """
    def __init__(self, data: list | None = None,
                 owner_id: str=''):
        """
        initialize the class
        """
        if data is None:
            data = []
        UserList.__init__(self, data)
        BaseRecord.__init__(self, owner_id, track_record=False)
        self.addupdate('Modify', 'original input', extra={'data':f"{repr(data)}"})

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.__class__.__name__:<20} {self.uuid} {repr(self[0]) if len(self) > 1 else "No data found"}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[2].append(('Data', 'data'))

        return attributes

    def __setitem__(self, index, item):
        """
        set the item
        """
        super().__setitem__(index, item)
        self.addupdate('Modify', f'set item at position {index}', extra={'item':f"{repr(item)}"})

    def insert(self, index, item):
        """
        insert an item
        """
        super().insert(index, item)
        self.addupdate('Modify', f'inserted item into position {index}', extra={'item':f"{repr(item)}"})

    def append(self, item):
        """
        append an item
        """
        super().append(item)
        self.addupdate('Modify', f'Appended item into position {len(self) - 1}', extra={'item':f"{repr(item)}"})

    def extend(self, items: list):
        """
        extend the list
        """
        super().extend(items)
        self.addupdate('Modify', 'extended list', extra={'new_list':f"{[repr(item) for item in items]}"})

class BaseListRecord(UserList, BaseRecord):
    def __init__(self, message: list[str | bytes] | list[str] | list[bytes] | str | bytes,
                 message_type: str = 'IO', internal: bool=True, owner_id: str='', track_record=True):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message]
        UserList.__init__(self, message)
        BaseRecord.__init__(self, owner_id, track_record=track_record)
        # This is a flag to determine if this message is internal or not
        self.internal = internal
        # This is the message id, see the derived classes for more info
        self.message_type: str = message_type
        # This is a flag to prevent the message from being sent to the client more than once
        self.sending = False
        # copy the original data
        self.original_data = message[:]
        self.addupdate('Info', 'Init', f"{self.__class__.__name__}:init", savedata=True)

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        if len(self.original_data) == 1 and not self.original_data[0].strip():
            first_str = self.original_data[0]
        else:
            first_str = ''
            index = 0
            while not first_str and index < len(self.original_data):
                first_str = self.original_data[index]
                index += 1

        return f"{self.__class__.__name__:<20} {self.uuid} {repr(first_str)}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].extend([('Internal', 'internal'),
                                    ('Message Type', 'message_type')])
        attributes[2].append(('Data', 'data'))
        if self.original_data != self.data:
            attributes[2].append(('Original Data', 'original_data'))

        return attributes

    @property
    def is_command_telnet(self):
        """
        A shortcut property to determine if this message is a Telnet Opcode.
        """
        return self.message_type == "COMMAND-TELNET"

    @property
    def is_io(self):
        """
        A shortcut property to determine if this message is normal I/O.
        """
        return self.message_type == "IO"

    def add_line_endings(self, actor=''):
        """
        add line endings to the message
        """
        new_message = [f"{item}\n\r" for item in self.data]
        self.replace(new_message, f"{actor}:add_line_endings", extra={'msg':'add line endings to each item'})

    def replace(self, data, actor='', extra: dict | None = None):
        """
        replace the data in the message
        """
        if not isinstance(data, list):
            data = [data]
        if data != self.data:
            self.data = data
            self.addupdate('Modify', 'replace', actor, extra=extra, savedata=True)

    def color_lines(self, color: str, actor=''):
        """
        color the message and convert all colors to ansicodes

        color is the color for all lines

        actor is the item that ran the color function
        """
        new_message: list[str] = []
        if not self.api('libs.api:has')('plugins.core.colors:colorcode.to.ansicode'):
            return
        for line in self.data:
            if color:
                if '@w' in line:
                    line_list = line.split('@w')
                    new_line_list = []
                    for item in line_list:
                        if item:
                            new_line_list.append(f"{color}{item}")
                        else:
                            new_line_list.append(item)
                    line = f"@w{color}".join(new_line_list)
                if line:
                    line = f"{color}{line}@w"
            new_message.append(self.api('plugins.core.colors:colorcode.to.ansicode')(line))

        self.replace(new_message, actor=f"{actor}:color_lines", extra={'msg':'convert color codes to ansi codes on each item'})

    def clean(self, actor: str = ''):
        """
        clean the message

        actor is the item that ran the clean function

        converts it to a string
        splits it on a newline
        removes newlines and carriage returns from the end of the line
        """
        new_message: list[str] = []
        for line in self.data:
            if isinstance(line, bytes):
                line = line.decode('utf-8')
            if isinstance(line, str):
                new_message.extend(line.splitlines() if line else [''])
            else:
                from libs.records.rtypes.log import LogRecord
                LogRecord(f"clean - {self.uuid} Message.clean: line is not a string: {line}",
                          level='error', sources=[__name__])()
        self.replace(new_message, actor=f"{actor}:clean", extra={'msg':'clean each item'})

    def addupdate(self, flag: str, action: str, actor: str = '', extra: dict | None = None, savedata: bool = True):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag', 'Info'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
            extra:  a dict of any extra info about this change
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        data = self.data[:] if savedata else None
        change = UpdateRecord(self, flag, action, actor, extra, data)

        self.updates.add(change)

class BaseDictRecord(UserDict, BaseRecord):
    def __init__(self, owner_id: str = '', data: dict | None = None, track_record=True):
        """
        initialize the class
        """
        if data:
            if not isinstance(data, dict):
                raise TypeError(f"data must be a dict not {type(data)}")
        else:
            data = {}
        UserDict.__init__(self, data)
        BaseRecord.__init__(self, owner_id, track_record=track_record)
        self.original_data = data.copy()
        self.addupdate('Info', 'Init', f"{self.__class__.__name__}:init", savedata=True)

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.__class__.__name__:<20} {self.uuid} {self.original_data[list(self.original_data.keys())[0]].strip()}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[2].append(('Data', 'data'))
        if self.original_data != self.data:
            attributes[2].append(('Original Data', 'original_data'))

        return attributes

    def addupdate(self, flag: str, action: str, actor: str = '', extra: dict | None = None, savedata: bool = True):
        """
        add a change event for this record
            flag: one of 'Modify', 'Set Flag', 'Info'
            action: a description of what was changed
            actor: the item that changed the message (likely a plugin)
            extra: any extra info about this change
        a message should create a change event at the following times:
            when it is created
            after modification
            when it ends up at it's destination
        """
        data = self.copy() if savedata else None
        change = UpdateRecord(self, flag, action, actor, extra, data)

        self.updates.add(change)
