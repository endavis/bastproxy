# Project: bastproxy
# Filename: libs/records/events.py
#
# File Description: The events the processing records raise
#
# By: Bast
"""The events the processing records raise.

The records only name their events here. The events plugin registers them once, when it
initializes, so creating a record makes no API call. Adding an event only sets metadata and
``event.get`` creates an event on first use, so the order in which plugins load does not
matter.
"""

# Standard Library
from typing import NamedTuple

__all__ = [
    "RECORD_EVENTS",
    "TO_CLIENT_DATA_MODIFY",
    "TO_CLIENT_DATA_READ",
    "TO_MUD_DATA_MODIFY",
    "TO_MUD_DATA_READ",
    "RecordEventSpec",
]

TO_CLIENT_DATA_MODIFY = "ev_to_client_data_modify"
TO_CLIENT_DATA_READ = "ev_to_client_data_read"
TO_MUD_DATA_MODIFY = "ev_to_mud_data_modify"
TO_MUD_DATA_READ = "ev_to_mud_data_read"


class RecordEventSpec(NamedTuple):
    """The arguments of one event registration."""

    name: str
    created_by: str
    description: list[str]
    arg_descriptions: dict[str, str]


RECORD_EVENTS: tuple[RecordEventSpec, ...] = (
    RecordEventSpec(
        TO_CLIENT_DATA_MODIFY,
        "bastproxy.libs.records.rtypes.clientdata",
        ["An event to modify data before it is sent to the client"],
        {"line": "The line to modify, a NetworkDataLine object"},
    ),
    RecordEventSpec(
        TO_CLIENT_DATA_READ,
        "bastproxy.libs.records.rtypes.clientdata",
        ["An event to see data that was sent to the client"],
        {"line": "The line to modify, a NetworkDataLine object"},
    ),
    RecordEventSpec(
        TO_MUD_DATA_MODIFY,
        "bastproxy.libs.records.rtypes.muddata",
        ["An event to modify data before it is sent to the mud"],
        {
            "line": "The line to modify, a NetworkDataLine instance",
            "showinhistory": "If the data should be shown in the history",
            "client_id": "The client id it came from",
        },
    ),
    RecordEventSpec(
        TO_MUD_DATA_READ,
        "bastproxy.libs.records.rtypes.muddata",
        ["An event to see data that was sent to the mud"],
        {"line": "The line to modify, a NetworkDataLine instance"},
    ),
)
