"""Every argument a record passes to an event is declared in that event's spec (#530)."""

import pytest

from bastproxy.libs.records.events import RECORD_EVENTS
from bastproxy.libs.records.rtypes.clientdata import ProcessDataToClient
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud, SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

from .conftest import FakeConnection, StandIns

_SPECS = {spec.name: spec for spec in RECORD_EVENTS}


def _check_events(stand_ins: StandIns, expected: int) -> None:
    assert len(stand_ins.events) == expected
    for call in stand_ins.events:
        declared = set(_SPECS[call.name].arg_descriptions)
        passed = {*call.kwargs.get("event_args", {}), call.kwargs["key_name"]}
        assert passed <= declared, f"{call.name} gets undeclared {passed - declared}"


def test_send_directly_to_mud_event_args_declared(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    message = NetworkData([NetworkDataLine("say a", originated="client")])
    SendDataDirectlyToMud(message, client_id="c1")()
    _check_events(plugin_stand_ins, 1)


@pytest.mark.usefixtures("split_regex")
def test_process_to_mud_event_args_declared(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.connection = FakeConnection()
    message = NetworkData([NetworkDataLine("say a", originated="client")])
    ProcessDataToMud(message, client_id="c1")()
    _check_events(plugin_stand_ins, 2)


def test_process_to_client_event_args_declared(plugin_stand_ins: StandIns) -> None:
    plugin_stand_ins.logged_in = {"u1"}
    plugin_stand_ins.clients = ["u1"]
    message = NetworkData([NetworkDataLine("from mud", originated="mud")])
    ProcessDataToClient(message)()
    _check_events(plugin_stand_ins, 2)
