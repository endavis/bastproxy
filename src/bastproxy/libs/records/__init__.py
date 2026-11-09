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
    SendDataDirectlyToMud - send data to the mud
    ProcessDataToMud - process data to send to the mud
    EventDataRecord - data to send to event callbacks (a BaseDictRecord on pydatatracker).

The public manager is RMANAGER, which manages records or all types

There are also some private classes that are used to manage records
    BaseRecord - the base class for the processing records
    TrackedUpdate - the display view of one update to a record
"""

__all__ = [
    "RMANAGER",
    "BaseDictRecord",
    "BaseRecord",
    "NetworkData",
    "NetworkDataLine",
    "ProcessDataToClient",
    "ProcessDataToMud",
    "SendDataDirectlyToClient",
    "SendDataDirectlyToMud",
]

from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord  # import to resolve circular import
from bastproxy.libs.records.rtypes.clientdata import (
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.libs.records.rtypes.dictrecord import BaseDictRecord
from bastproxy.libs.records.rtypes.muddata import (
    ProcessDataToMud,
    SendDataDirectlyToMud,
)
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
