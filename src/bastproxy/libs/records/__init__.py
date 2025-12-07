# Project: bastproxy
# Filename: libs/records/__init__.py
#
# File Description: a "package" to manage records
#
# By: Bast
"""This "package"" has classes for various record types and record managers.

The public record types ones are:
    SendDataDirectlyToClient - send data to the client
    ProcessDataToClient - process data to send to the client
    NetworkData - build data to send
    LogRecord - data to log
    SendDataDirectlyToMud - send data to the mud
    ProcessDataToMud - process data to send to the mud
    EventArgsRecord - data to send to event callbacks.

The public manager is RMANAGER, which manages records or all types

There are also some private classes that are used to manage records
    BaseRecord - the base class for all records
    ChangeRecord - a record that holds a change to a record
    ChangeManager - a manager that manages changes to records
"""

__all__ = [
    "RMANAGER",
    "BaseDictRecord",
    "BaseRecord",
    "LogRecord",
    "NetworkData",
    "NetworkDataLine",
    "ProcessDataToClient",
    "ProcessDataToMud",
    "SendDataDirectlyToClient",
    "SendDataDirectlyToMud",
]

from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.base import (  # import to resolve circular import
    BaseDictRecord,
    BaseRecord,
)
from bastproxy.libs.records.rtypes.clientdata import (
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.libs.records.rtypes.log import LogRecord
from bastproxy.libs.records.rtypes.muddata import (
    ProcessDataToMud,
    SendDataDirectlyToMud,
)
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
