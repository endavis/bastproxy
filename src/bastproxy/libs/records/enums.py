# Project: bastproxy
# Filename: libs/records/enums.py
#
# File Description: Holds the enums the records use for fixed string values
#
# By: Bast
"""Holds the enums the records use for fixed string values.

Each is a ``StrEnum`` whose members equal their old string values, so logs, debug output and
callers that pass plain strings keep working. Build one from a string to validate it: an unknown
value raises ``ValueError``.

This module imports only the standard library, so any records module can import it.
"""

# Standard Library
from enum import StrEnum

__all__ = [
    "Direction",
    "LineType",
    "Originated",
    "UpdateFlag",
]


class Direction(StrEnum):
    """Which way a telnet negotiation or protocol message travelled."""

    SENT = "sent"
    RECEIVED = "received"


class Originated(StrEnum):
    """Where a network data line came from."""

    MUD = "mud"
    CLIENT = "client"
    INTERNAL = "internal"


class LineType(StrEnum):
    """What a network data line holds."""

    IO = "IO"
    COMMAND_TELNET = "COMMAND-TELNET"


class UpdateFlag(StrEnum):
    """The flag of a record update."""

    MODIFY = "Modify"
    SET_FLAG = "Set Flag"
    INFO = "Info"
