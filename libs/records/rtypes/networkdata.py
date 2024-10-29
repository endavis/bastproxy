# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/dataline.py
#
# File Description: Holds the records for network data
#
# By: Bast
"""
Holds the data line record
"""
# Standard Library
from collections import UserList
import re

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.log import LogRecord

class NetworkDataLine(BaseRecord):
    """
    A record to hold a line of data that will be sent to the clients
    or the mud
    """
    def __init__(self, line: str | bytes | bytearray, originated: str = 'internal', line_type: str = 'IO'):
        BaseRecord.__init__(self, f"{self.__class__.__name__}:{repr(line)}")
        self._attributes_to_monitor.append('line')
        self._attributes_to_monitor.append('send')
        if (isinstance(line, str) and ('\n' in line or '\r' in line)) or \
               (isinstance(line, (bytes, bytearray)) and (b'\n' in line or b'\r' in line)):
            LogRecord(f"LogRecord: {self.uuid} {line} is multi line with \\n and/or \\r",
                                level='error', stack_info=True, sources=[__name__])()
        self.line_type = line_type # IO, COMMAND-TELNET
        self.originated = originated # mud, client, internal
        if (isinstance(line, (bytes, bytearray))) and not self.is_command_telnet:
            line = line.decode('utf-8')
        self.line: str | bytes | bytearray = line
        self.original_line: str | bytes | bytearray = line
        self.send: bool = True
        self.line_modified: bool = False
        self.is_prompt: bool = False
        if self.is_io:
            self.noansi: str = self.api('plugins.core.colors:ansicode.strip')(line)
            self.color: str = self.api('plugins.core.colors:ansicode.to.colorcode')(line)
        else:
            self.noansi: str = ''
            self.color: str = ''

    def _onchange_line(self, orig_value, new_value):
        """
        set the line_modified flag if the line changes
        """
        if orig_value != new_value:
            self.line_modified = True

    @property
    def is_command_telnet(self):
        """
        A shortcut property to determine if this message is a Telnet Opcode.
        """
        return self.line_type == "COMMAND-TELNET"

    @property
    def is_io(self):
        """
        A shortcut property to determine if this message is normal I/O.
        """
        return self.line_type == "IO"

    @property
    def internal(self):
        """
        A shortcut property to determine if this message is internal
        """
        return self.originated == 'internal'

    @property
    def fromclient(self):
        """
        A shortcut property to determine if this message is from a client
        """
        return self.originated == 'client'

    @property
    def frommud(self):
        """
        A shortcut property to determine if this message is from the mud
        """
        return self.originated == 'mud'

    def add_line_endings(self, actor=''):
        """
        add line endings to the message
        """
        if self.is_io:
            self.line = f"{self.line}\n\r"

    def color_line(self, color: str = ''):
        """
        color the message and convert all colors to ansicodes

        color is the color for all lines

        actor is the item that ran the color function
        """
        if not self.is_io:
            return

        if not self.api('libs.api:has')('plugins.core.colors:colorcode.to.ansicode'):
            return

        if color and isinstance(self.line, str):
            if '@w' in self.line:
                line_list = self.line.split('@w')
                new_line_list = []
                for item in line_list:
                    if item:
                        new_line_list.append(f"{color}{item}")
                    else:
                        new_line_list.append(item)
                self.line = f"@w{color}".join(new_line_list)
            if self.line:
                self.line = f"{color}{self.line}@w"
        self.line = self.api('plugins.core.colors:colorcode.to.ansicode')(self.line)

    def fix_double_command_seperator(self):
        """
        fix double command seperators

        take out double command seperators and replaces them with a single one before
        sending the data to the mud
        """
        if isinstance(self.line, str):
            current_line = self.line.replace('||', '|')
            if current_line != self.line:
                self.line = current_line

    def format(self, preamble: bool = False, color: str = '') -> None:
        """
        format the message
        """
        if self.is_io:
            if self.internal: # generated from the proxy
                if preamble:
                    self.add_preamble()
            else: # generated from a client
                self.fix_double_command_seperator()

            self.color_line(color)
            self.add_line_endings()

    def strip(self):
        """
        strip the line of carriage returns and line feeds
        """
        return self.line.strip()

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        for item in self._attributes_to_monitor:
            orig_value = self._am_get_original_value(item)
            if orig_value == getattr(self, item):
                attributes[0].append((f"{item}", item))
            else:
                attributes[0].append((item, f"changed from '{self._am_get_original_value(item)}' to '{getattr(self, item)}'"))
        attributes[0].append(('Line Modified', 'line_modified'))
        attributes[0].append(('Originated', 'originated'))
        attributes[0].append(('Type', 'line_type'))
        return attributes

    def one_line_summary(self):
        return repr(self.line)

    def __str__(self):
        return self.line

    def __repr__(self):
        return f'{self.__class__.__name__}({self.uuid} {self.originated} {repr(self.original_line.strip())})'

    def add_preamble(self, error: bool = False):
        """
        add the preamble to the line only if it is from internal and is an IO message
        """
        if self.internal and self.is_io:
            preamblecolor = self.api('plugins.core.proxy:preamble.color.get')(error=error)
            preambletext = self.api('plugins.core.proxy:preamble.get')()
            self.line = f"{preamblecolor}{preambletext}@w: {self.line}"

class NetworkData(UserList, BaseRecord):
    """
    this is a base record of a list of NetworkDataLine records
    """
    def __init__(self, message: NetworkDataLine | str | bytes | list[NetworkDataLine] | list[str] | list[bytes],
                 owner_id: str='', track_record=True):
        """
        initialize the class
        """
        if not isinstance(message, list):
            message = [message] # type: ignore

        new_message = []
        for item in message: # type: ignore
            if not (isinstance(item, (NetworkDataLine, str, bytes))):
                raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)}")
            if isinstance(item, (str, bytes)):
                item = NetworkDataLine(item)
            new_message.append(item)

        UserList.__init__(self, new_message)
        BaseRecord.__init__(self, owner_id, track_record=track_record)
        for item in new_message:
            self.add_related_record(item)
        self.owner_id = owner_id
        # This is a flag to prevent the message from being sent  more than once
        self.sending = False
        self.addupdate('Modify', 'original input', extra={'list':f"{new_message}"})

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        first_str = ''
        for networkdataitem in self:
            if networkdataitem.line:
                first_str = networkdataitem.original_line

        return first_str or 'No data found'

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[2].append(('Data', 'data'))

        return attributes

    def __setitem__(self, index, item: NetworkDataLine | str | bytes | bytearray):
        """
        set the item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
        self.add_related_record(item)
        super().__setitem__(index, item)
        self.addupdate('Modify', f'set item at position {index}', extra={'item':f"{repr(item)}"})

    def insert(self, index, item: NetworkDataLine | str | bytes | bytearray):
        """
        insert an item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
        self.add_related_record(item)
        super().insert(index, item)
        self.addupdate('Modify', f'inserted item into position {index}', extra={'item':f"{repr(item)}"})

    def append(self, item: NetworkDataLine | str | bytes | bytearray):
        """
        append an item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
        self.add_related_record(item)
        super().append(item)
        self.addupdate('Modify', f'Appended item into position {len(self) - 1}', extra={'item':f"{repr(item)}"})

    def extend(self, items: list[NetworkDataLine | str | bytes | bytearray]):
        """
        extend the list
        """
        new_list = []
        for item in items:
            if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
                raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
            if isinstance(item, (str, bytes, bytearray)):
                item = NetworkDataLine(item)
            self.add_related_record(item)
            new_list.append(item)
        super().extend(new_list)
        self.addupdate('Modify', 'extended list', extra={'new_list':f"{new_list}"})
