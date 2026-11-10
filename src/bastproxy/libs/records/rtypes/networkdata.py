# Project: bastproxy
# Filename: libs/records/rtypes/networkdata.py
#
# File Description: Holds the records for network data
#
# By: Bast
"""Holds the data line record."""

# Standard Library
from typing import Any

# 3rd Party
from pydatatracker import TrackedAttr, TrackedList

# Project
from bastproxy.libs.api import API
from bastproxy.libs.logger import get_logger
from bastproxy.libs.records.enums import LineType, Originated
from bastproxy.libs.records.tracking import (
    TrackedRecordMixin,
    current_capture_stacks,
    current_max_changes,
)

logger = get_logger(__name__)

_LINE_FIELDS = (
    "line",
    "send",
    "is_prompt",
    "had_line_endings",
    "prelogin",
    "preamble",
    "color",
    "line_modified",
    "was_sent",
    "originated",
    "line_type",
    "split_from",
)
# The fields a lock freezes. was_sent stays writable because the network layer sets it after
# the line is locked. originated, line_type and split_from are tracked so the lock freezes them
# too (#264).
_LOCKED_FIELDS = tuple(name for name in _LINE_FIELDS if name != "was_sent")
# Fields the detail view does not list as monitored rows: line_modified has its own row, and
# originated and line_type already show through get_attributes_to_format.
_UNMONITORED_ROWS = ("line_modified", "originated", "line_type", "split_from")


class NetworkDataLine(TrackedRecordMixin, TrackedAttr):
    """A record to hold a line of data that will be sent to the clients.

    or the mud.
    """

    _tracking_fields = _LINE_FIELDS
    # One API for every line, so no API is built per line.
    api = API(owner_id="NetworkDataLine")

    def __init__(
        self,
        line: str | bytes | bytearray,
        originated: Originated | str = Originated.INTERNAL,
        line_type: LineType | str = LineType.IO,
        had_line_endings: bool = True,
        preamble: bool = True,
        prelogin: bool = False,
        color: str = "",
    ):
        """Initialize a network data line.

        Args:
            line: The line content as string or bytes.
            originated: Source of the line, an ``Originated`` or its string
                (default: ``Originated.INTERNAL``).
            line_type: Type of line, a ``LineType`` or its string (default: ``LineType.IO``).
            had_line_endings: Whether line had line endings (default: True).
            preamble: Whether to include preamble (default: True).
            prelogin: Whether this is a prelogin line (default: False).
            color: Color code for the line (default: "").

        Raises:
            ValueError: If ``originated`` or ``line_type`` is not a member of its enum.

        """
        # Coerce first so a bad value never registers a half-built record.
        originated = Originated(originated)
        line_type = LineType(line_type)
        TrackedAttr.__init__(
            self,
            tracking_max_changes=current_max_changes(),
            tracking_capture_stack=current_capture_stacks(),
        )
        self._init_record()
        self._line_locked = False
        if originated is not Originated.INTERNAL and (
            (isinstance(line, str) and ("\n" in line or "\r" in line))
            or (isinstance(line, (bytes, bytearray)) and (b"\n" in line or b"\r" in line))
        ):
            logger.error(
                "NetworkDataLine: %s %s is multi line with \\n and/or \\r",
                self.uuid,
                line,
                stack_info=True,
            )
        self.line_type: LineType = line_type
        self.originated: Originated = originated
        if (isinstance(line, (bytes, bytearray))) and not self.is_command_telnet:
            line = line.decode("utf-8")
        self.line: str | bytes | bytearray = line
        self._original_line: str | bytes | bytearray = line
        self.send: bool = True
        self.line_modified: bool = False
        self.is_prompt: bool = False
        self.had_line_endings: bool = had_line_endings
        self.was_sent: bool = False
        self.color = color
        self.split_from: NetworkDataLine | None = None

        # preamble defaults to True because a large percentage
        # of the data that is internal will need it
        # it is not used if the data is not internal
        self.preamble = preamble

        # prelogin defaults to False because a large percentage
        # of the data that is internal will not need it
        # because not much data is sent to a client before login
        self.prelogin = prelogin

    @property
    def original_line(self) -> str | bytes | bytearray:
        """The line as it was created, which never changes."""
        return self._original_line

    @original_line.setter
    def original_line(self, value: Any) -> None:
        """Refuse the write: the original line is locked."""
        msg = f"NetworkDataLine.original_line is locked and cannot be modified (got {value!r})."
        raise RuntimeError(msg)

    def add_parent(self, parent: Any, reset: bool = True) -> None:
        """Add a parent to this record.

        Only a ``NetworkData`` or a ``NetworkDataLine`` (subclasses included) is kept. Any other
        parent is ignored, silently on purpose: ``_init_record`` offers the executing processing
        record on almost every line created during execution, so a log would spam.
        """
        if reset:
            self.parents = []
        if parent in self.parents:
            return
        if isinstance(parent, (NetworkData, NetworkDataLine)):
            self.parents.append(parent)

    def _monitored_fields(self) -> list[str]:
        """Return the monitored fields to show; the others have their own rows."""
        return [name for name in _LINE_FIELDS if name not in _UNMONITORED_ROWS]

    def _original_value(self, name: str) -> Any:
        """Return the value a monitored field had when it was first set."""
        return self.tracking_get_original_value(name)

    def _tracking_attribute_change(
        self, method: str, attribute_name: str, original_value: Any, new_value: Any
    ) -> None:
        """Record the change, then set line_modified when the line changed."""
        super()._tracking_attribute_change(method, attribute_name, original_value, new_value)
        if (
            attribute_name == "line"
            and "line_modified" in self.__dict__
            and not self.line_modified
            and original_value != new_value
        ):
            self.line_modified = True

    @property
    def noansi(self):
        """Get the line with ANSI codes stripped.

        Returns:
            The line without ANSI escape sequences.

        """
        if self.is_command_telnet:
            return self.line
        return self.api("plugins.core.colors:ansicode.strip")(self.line)

    @property
    def colorcoded(self):
        """Get the line with ANSI codes converted to color codes.

        Returns:
            The line with color codes.

        """
        if self.is_command_telnet:
            return self.line
        return self.api("plugins.core.colors:ansicode.to.colorcode")(self.line)

    def lock(self, attribute_name: str = "") -> None:
        """Lock the line so its fields refuse writes with ``RuntimeError``.

        A whole-object lock would also refuse the later ``was_sent = True``, so this locks
        each field except ``was_sent``. A second call does nothing.
        """
        if attribute_name:
            super().lock(attribute_name)
            return
        if self._line_locked:
            return
        for name in _LOCKED_FIELDS:
            super().lock(name)
        self._line_locked = True

    def escapecolor(self):
        """Get the line with color codes escaped for display.

        Returns:
            The line with escaped color codes.

        """
        if self.is_command_telnet:
            return self.line
        return self.api("plugins.core.colors:colorcode.escape")(self.line)

    @property
    def is_command_telnet(self):
        """A shortcut property to determine if this message is a Telnet Opcode."""
        return self.line_type == LineType.COMMAND_TELNET

    @property
    def is_io(self):
        """A shortcut property to determine if this message is normal I/O."""
        return self.line_type == LineType.IO

    @property
    def internal(self):
        """A shortcut property to determine if this message is internal."""
        return self.originated == Originated.INTERNAL

    @property
    def fromclient(self):
        """A shortcut property to determine if this message is from a client."""
        return self.originated == Originated.CLIENT

    @property
    def frommud(self):
        """A shortcut property to determine if this message is from the mud."""
        return self.originated == Originated.MUD

    def add_line_endings(self, actor=""):
        """Add line endings to the message."""
        if self.is_io and self.had_line_endings:
            self.line = f"{self.line}\r\n"

    def copy_attributes(self, new_line):
        """Copy the attributes from the current line to a new line."""
        new_line.line_type = self.line_type
        new_line.originated = self.originated
        new_line._original_line = self.original_line
        new_line.preamble = self.preamble
        new_line.had_line_endings = self.had_line_endings
        new_line.prelogin = self.prelogin
        new_line.color = self.color
        new_line.split_from = self

    def color_line(self):
        """Color the message and convert all colors to ansicodes.

        color is the color for all lines

        actor is the item that ran the color function
        """
        if not self.is_io:
            return

        if not self.api("libs.api:api.exists")("plugins.core.colors:colorcode.to.ansicode"):
            return

        if self.color and isinstance(self.line, str):
            if "@w" in self.line:
                line_list = self.line.split("@w")
                new_line_list = []
                for item in line_list:
                    if item:
                        new_line_list.append(f"{self.color}{item}")
                    else:
                        new_line_list.append(item)
                self.line = f"@w{self.color}".join(new_line_list)
            if self.line:
                self.line = f"{self.color}{self.line}@w"
        self.line = self.api("plugins.core.colors:colorcode.to.ansicode")(self.line)

    def fix_double_command_seperator(self):
        """Fix double command seperators.

        take out double command seperators and replaces them with a single one before
        sending the data to the mud
        """
        if isinstance(self.line, str):
            current_line = self.line.replace("||", "|")
            if current_line != self.line:
                self.line = current_line

    def format(self, preamble: bool = False, color: str = "") -> None:
        """Format the message. A locked line is already formatted, so this does nothing."""
        if self._line_locked:
            return
        if self.is_io:
            if self.internal:  # generated from the proxy
                if self.preamble:
                    self.add_preamble()
            else:  # generated from a client
                self.fix_double_command_seperator()

            self.color_line()
            self.add_line_endings()

    def get_attributes_to_format(self):
        """Get the attributes to format for display.

        Returns:
            A list of attribute tuples for formatting.

        """
        attributes = super().get_attributes_to_format()
        attributes[0].append(("Line Modified", "line_modified"))
        attributes[0].append(("Originated", "originated"))
        attributes[0].append(("Type", "line_type"))
        return attributes

    def one_line_summary(self):
        """Get a one-line summary of the network data.

        Returns:
            A formatted summary string.

        """
        return f"{self.__class__.__name__:<20} {self.uuid} {self.originated} {self.line!r}"

    def __str__(self):
        """Return a string representation of the line.

        Returns:
            The line content as a string.

        """
        return self.line

    def __repr__(self):
        """Return a detailed representation of the network data line.

        Returns:
            The one-line summary.

        """
        return self.one_line_summary()

    def add_preamble(self, error: bool = False):
        """Add the preamble to the line only if it is from internal and is an IO message."""
        if self.internal and self.is_io:
            preamblecolor = self.api("plugins.core.proxy:preamble.color.get")(error=error)
            preambletext = self.api("plugins.core.proxy:preamble.get")()
            self.line = f"{preamblecolor}{preambletext}@w: {self.line}"


class NetworkData(TrackedRecordMixin, TrackedList):
    """this is a base record of a list of NetworkDataLine records."""

    def __init__(
        self,
        message: (
            NetworkDataLine | str | bytes | list[NetworkDataLine] | list[str] | list[bytes] | None
        ) = None,
        owner_id: str = "",
    ):
        """Initialize the class."""
        if message is None:
            message = []
        if not isinstance(message, list):
            message = [message]  # type: ignore[list-item]

        TrackedList.__init__(
            self,
            message,  # type: ignore[arg-type]
            tracking_max_changes=current_max_changes(),
            tracking_capture_stack=current_capture_stacks(),
        )
        self._init_record(owner_id)
        self.api = API(owner_id=self.owner_id)

    def _tracking_convert_item(self, value: Any, _location: Any = "") -> NetworkDataLine:
        """Turn a stored value into a ``NetworkDataLine`` that has this list as its parent.

        Every way of storing an item goes through here: construction, ``append``,
        ``insert``, ``extend``, ``+=`` and ``__setitem__``, slices included.

        Raises:
            TypeError: If the value is not a line, str, bytes or bytearray.

        """
        if isinstance(value, (str, bytes, bytearray)):
            value = NetworkDataLine(value)
        elif not isinstance(value, NetworkDataLine):
            msg = f"item must be a NetworkDataLine object or a string, not {type(value)} {value!r}"
            raise TypeError(msg)
        value.parent = self
        value.add_parent(self)
        return value

    def _tracking_remove_child_tracked_item(self, trackable_item: Any) -> None:
        """Detach a line that this list no longer holds anywhere.

        pydatatracker calls this once for each removed item that is no longer stored at
        any index, on every removal path. The line stops listing this list as a parent.
        Identity is used because ``==`` on records compares uuids.
        """
        was_child = trackable_item._tracking_uuid in self._tracking_child_tracked_items
        super()._tracking_remove_child_tracked_item(trackable_item)
        if was_child and isinstance(trackable_item, NetworkDataLine):
            trackable_item.parents = [p for p in trackable_item.parents if p is not self]
            if trackable_item.parent is self:
                trackable_item.parent = None

    @property
    def locked(self) -> bool:
        """Whether the list refuses changes."""
        return bool(self._tracking_locked)

    def _monitored_fields(self) -> list[str]:
        """A list has no monitored fields."""
        return []

    def _original_value(self, name: str) -> Any:
        """A list has no monitored fields, so there is no original value."""
        return None

    def get_first_line(self):
        """Get the first non-empty line from the network data.

        Returns:
            The first valid line or "No data found" if empty.

        """
        return (
            "No data found"
            if len(self) == 0
            else next(
                (
                    networkline.original_line
                    for networkline in self
                    if networkline.original_line not in ["#BP", b"#BP", "", b"", "''", b"''"]
                ),
                "",
            )
        )

    def one_line_summary(self):
        """Get a one line summary of the record."""
        return f"{self.__class__.__name__:<20} {self.uuid} {len(self)} {self.get_first_line()!r}"
