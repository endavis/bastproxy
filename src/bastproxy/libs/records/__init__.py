# Project: bastproxy
# Filename: libs/records/__init__.py
#
# File Description: a "package" to manage records
#
# By: Bast
"""Record types and the record manager.

Exported (``__all__``):
    ProcessDataToClient - process data from the mud before it goes to the clients
    SendDataDirectlyToClient - send data to the clients
    ProcessDataToMud - process data from a client before it goes to the mud
    SendDataDirectlyToMud - send data to the mud
    NetworkData - a list of lines, the message the records above carry
    NetworkDataLine - one line of a NetworkData
    BaseRecord - the base class of the processing records
    BaseDictRecord - the base class of the dict records, such as the events plugin's
        EventDataRecord
    RMANAGER - the record manager, which keeps root trees of records
    Originated - an enum of where a line came from (mud, client, internal)
    LineType - an enum of what a line holds (IO, COMMAND-TELNET)
    UpdateFlag - an enum of the flag of a record update (Modify, Set Flag, Info)

TrackedUpdate, the display view of one update, is in ``bastproxy.libs.records.tracking``.
"""

__all__ = [
    "RMANAGER",
    "BaseDictRecord",
    "BaseRecord",
    "LineType",
    "NetworkData",
    "NetworkDataLine",
    "Originated",
    "ProcessDataToClient",
    "ProcessDataToMud",
    "SendDataDirectlyToClient",
    "SendDataDirectlyToMud",
    "UpdateFlag",
]

from bastproxy.libs.records.enums import LineType, Originated, UpdateFlag
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
