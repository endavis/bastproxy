"""Tests for the telnet negotiation and protocol message records (#83)."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.records import (
    RMANAGER,
    BaseRecord,
    Direction,
    TelnetNegotiation,
    TelnetProtocolMessage,
    UpdateFlag,
)


@pytest.fixture(autouse=True)
def isolated_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test an empty record store."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    yield


def _negotiation(**kwargs: object) -> TelnetNegotiation:
    args: dict[str, object] = {
        "command": "DO",
        "option": "TTYPE",
        "direction": Direction.SENT,
        "link": "mud",
    }
    args.update(kwargs)
    return TelnetNegotiation(**args)  # type: ignore[arg-type]


def test_direction_values() -> None:
    assert Direction("sent") is Direction.SENT
    assert Direction("received") is Direction.RECEIVED
    with pytest.raises(ValueError, match="nowhere"):
        Direction("nowhere")


def test_negotiation_fields() -> None:
    rec = _negotiation(data=b"\x01", raw=b"\xff\xfa\x18\x01\xff\xf0", direction="received")
    assert rec.command == "DO"
    assert rec.option == "TTYPE"
    assert rec.direction is Direction.RECEIVED
    assert rec.link == "mud"
    assert rec.data == b"\x01"
    assert rec.raw == b"\xff\xfa\x18\x01\xff\xf0"
    assert RMANAGER.get_record(rec.uuid) is rec


def test_bad_direction_registers_nothing() -> None:
    with pytest.raises(ValueError, match="sideways"):
        _negotiation(direction="sideways")
    assert RMANAGER.record_instances == {}


def test_not_a_retention_root() -> None:
    rec = _negotiation()
    assert rec.retention_root is False
    assert RMANAGER.root_count() == 0


def test_one_info_update() -> None:
    rec = _negotiation()
    updates = rec.updates
    assert len(updates) == 1
    assert updates[0].flag == UpdateFlag.INFO


def test_summary_and_details() -> None:
    rec = _negotiation(command="WILL", option="GMCP", direction=Direction.RECEIVED, link="abc")
    summary = rec.one_line_summary()
    for part in ("abc", "received", "WILL", "GMCP"):
        assert part in summary
    details = "\n".join(
        rec.get_formatted_details(include_children_records=False, include_updates=False)
    )
    assert "Command" in details
    assert "GMCP" in details
    assert "Direction" in details


def test_protocol_message_fields() -> None:
    rec = TelnetProtocolMessage(
        protocol="GMCP",
        package="Char.Vitals",
        data={"hp": 10},
        direction="received",
        link="mud",
    )
    assert rec.protocol == "GMCP"
    assert rec.package == "Char.Vitals"
    assert rec.data == {"hp": 10}
    assert rec.direction is Direction.RECEIVED
    assert rec.retention_root is False
    assert "Char.Vitals" in rec.one_line_summary()
    assert "Protocol" in "\n".join(
        rec.get_formatted_details(include_children_records=False, include_updates=False)
    )
    with pytest.raises(ValueError, match="x"):
        TelnetProtocolMessage("GMCP", "a", {}, "x", "mud")


def test_joins_active_processing_record() -> None:
    class _Root(BaseRecord):
        pass

    root = _Root()
    RMANAGER.start(root)
    try:
        rec = _negotiation()
    finally:
        RMANAGER.end(root)
    assert rec.parent is root
    assert root in rec.parents
