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
import re
from collections import UserList

# 3rd Party
# Project
from libs.records.rtypes.base import BaseRecord, TrackedUserList
from libs.records.rtypes.log import LogRecord


class NetworkDataLine(BaseRecord):
    """
    A record to hold a line of data that will be sent to the clients
    or the mud
    """
    def __init__(self, line: str | bytes | bytearray, originated: str = 'internal', line_type: str = 'IO',
                 had_line_endings: bool = True, preamble: bool = True, prelogin: bool = False,
                 color: str = ''):
        BaseRecord.__init__(self, f"{self.__class__.__name__}:{repr(line)}")
        self._attributes_to_monitor.append('line')
        self._attributes_to_monitor.append('send')
        self._attributes_to_monitor.append('is_prompt')
        self._attributes_to_monitor.append('had_line_endings')
        self._attributes_to_monitor.append('prelogin')
        self._attributes_to_monitor.append('preamble')
        self._attributes_to_monitor.append('color')
        self._attributes_to_monitor.append('was_sent')
        if originated != 'internal' and ((isinstance(line, str) and ('\n' in line or '\r' in line)) or \
                        (isinstance(line, (bytes, bytearray)) and (b'\n' in line or b'\r' in line))):
            LogRecord(f"NetworkDataLine: {self.uuid} {line} is multi line with \\n and/or \\r",
                                level='error', stack_info=True, sources=[__name__])()
        self.line_type = line_type # IO, COMMAND-TELNET
        self.originated = originated # mud, client, internal
        if (isinstance(line, (bytes, bytearray))) and not self.is_command_telnet:
            line = line.decode('utf-8')
        self.line: str | bytes | bytearray = line
        self.original_line: str | bytes | bytearray = line
        self._am_lock_attribute('original_line')
        self.send: bool = True
        self.line_modified: bool = False
        self.is_prompt: bool = False
        self.had_line_endings: bool = had_line_endings
        self.was_sent: bool = False
        self.color = color
        self.split_from = None

        # preamble defaults to True because a large percentage
        # of the data that is internal will need it
        # it is not used if the data is not internal
        self.preamble = preamble

        # prelogin defaults to False because a large percentage
        # of the data that is internal will not need it
        # because not much data is sent to a client before login
        self.prelogin = prelogin

        self.addupdate('Modify', 'original input', extra={'data':f"{repr(line)}"})

    def add_parent(self, parent, reset=True):
        """
        add a parent to this record
        """
        if reset:
            self.parents = []
        if parent in self.parents:
            return
        if parent.__class__.__name__ in ['NetworkData', 'NetworkDataLine']:
            self.parents.append(parent)

    @property
    def noansi(self):
        if self.is_command_telnet:
            return self.line
        return self.api('plugins.core.colors:ansicode.strip')(self.line)

    @property
    def colorcoded(self):
        if self.is_command_telnet:
            return self.line
        return self.api('plugins.core.colors:ansicode.to.colorcode')(self.line)

    def lock(self):
        self._am_lock_attribute('line')
        self._am_lock_attribute('send')
        self._am_lock_attribute('is_prompt')
        self._am_lock_attribute('had_line_endings')
        self._am_lock_attribute('prelogin')
        self._am_lock_attribute('preamble')
        self._am_lock_attribute('color')
        self._am_lock_attribute('line_modified')
        self.addupdate('Modify', 'locked')

    def escapecolor(self):
        if self.is_command_telnet:
            return self.line
        return self.api('plugins.core.colors:colorcode.escape')(self.line)

    def _am_onchange_line(self, orig_value, new_value):
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
        if self.is_io and self.had_line_endings:
            self.line = f"{self.line}\n\r"

    def copy_attributes(self, new_line):
        """
        copy the attributes from the current line to a new line
        """
        new_line.line_type = self.line_type
        new_line.originated = self.originated
        new_line._am_unlock_attribute('original_line')
        new_line.original_line = self.original_line
        new_line._am_lock_attribute('original_line')
        new_line.preamble = self.preamble
        new_line.had_line_endings = self.had_line_endings
        new_line.prelogin = self.prelogin
        new_line.color = self.color
        # for item in self.parents:
        #     new_line.add_parent(item, reset=False)
        new_line.add_parent(self)
        new_line.split_from = self

    def color_line(self):
        """
        color the message and convert all colors to ansicodes

        color is the color for all lines

        actor is the item that ran the color function
        """
        if not self.is_io:
            return

        if not self.api('libs.api:has')('plugins.core.colors:colorcode.to.ansicode'):
            return

        if self.color and isinstance(self.line, str):
            if '@w' in self.line:
                line_list = self.line.split('@w')
                new_line_list = []
                for item in line_list:
                    if item:
                        new_line_list.append(f"{self.color}{item}")
                    else:
                        new_line_list.append(item)
                self.line = f"@w{self.color}".join(new_line_list)
            if self.line:
                self.line = f"{self.color}{self.line}@w"
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
                if self.preamble:
                    self.add_preamble()
            else: # generated from a client
                self.fix_double_command_seperator()

            self.color_line()
            self.add_line_endings()

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].append(('Line Modified', 'line_modified'))
        attributes[0].append(('Originated', 'originated'))
        attributes[0].append(('Type', 'line_type'))
        return attributes

    def one_line_summary(self):
        return f'{self.__class__.__name__:<20} {self.uuid} {self.originated} {repr(self.line)}'

    def __str__(self):
        return self.line

    def __repr__(self):
        return self.one_line_summary()

    def add_preamble(self, error: bool = False):
        """
        add the preamble to the line only if it is from internal and is an IO message
        """
        if self.internal and self.is_io:
            preamblecolor = self.api('plugins.core.proxy:preamble.color.get')(error=error)
            preambletext = self.api('plugins.core.proxy:preamble.get')()
            self.line = f"{preamblecolor}{preambletext}@w: {self.line}"

class NetworkData(TrackedUserList):
    """
    this is a base record of a list of NetworkDataLine records
    """
    def __init__(self, message: NetworkDataLine | str | bytes | list[NetworkDataLine] | list[str] | list[bytes] | None = None,
                 owner_id: str=''):
        """
        initialize the class
        """
        if message is None:
            message = []
        if not isinstance(message, list):
            message = [message] # type: ignore

        TrackedUserList.__init__(self, message, owner_id=owner_id) # type: ignore

        for item in self:
            old_item = item
            if not (isinstance(item, (NetworkDataLine, str, bytes))):
                raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)}")
            if isinstance(item, (str, bytes)):
                item = NetworkDataLine(item)
                self[self.index(old_item)] = item
            item.parent = self
            item.add_parent(self)

    def get_first_line(self):
        return (
            'No data found'
            if len(self) == 0
            else next(
                (
                    networkline.original_line
                    for networkline in self
                    if networkline.original_line
                    not in ['#BP', b'#BP', "", b"", "''", b"''"]
                ),
                '',
            )
        )

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f'{self.__class__.__name__:<20} {self.uuid} {len(self)} {repr(self.get_first_line())}'

    def __setitem__(self, index, item: NetworkDataLine | str | bytes | bytearray):
        """
        set the item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
            item.parent = self
            item.add_parent(self)
        super().__setitem__(index, item)

    def insert(self, index, item: NetworkDataLine | str | bytes | bytearray):
        """
        insert an item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
            item.parent = self
            item.add_parent(self)
        super().insert(index, item)

    def append(self, item: NetworkDataLine | str | bytes | bytearray):
        """
        append an item
        """
        if not (isinstance(item, (NetworkDataLine, str, bytes, bytearray))):
            raise ValueError(f"item must be a NetworkDataLine object or a string, not {type(item)} {repr(item)}")
        if isinstance(item, (str, bytes, bytearray)):
            item = NetworkDataLine(item)
            item.parent = self
            item.add_parent(self)
        super().append(item)

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
            item.parent = self
            item.add_parent(self)
            new_list.append(item)
        super().extend(new_list)
