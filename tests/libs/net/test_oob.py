"""Tests for the bounded GMCP and MSDP codecs (#59)."""

import json
import threading
from typing import Any

import pytest
from telnetlib3.mud import msdp_encode
from telnetlib3.telopt import (
    MSDP_ARRAY_CLOSE,
    MSDP_ARRAY_OPEN,
    MSDP_TABLE_CLOSE,
    MSDP_TABLE_OPEN,
    MSDP_VAL,
    MSDP_VAR,
)

from bastproxy.libs.net import oob
from bastproxy.libs.net.oob import OobDecodeError

JOIN_TIMEOUT = 5


def run_bounded(payload: bytes) -> Any:
    """Decode MSDP in a thread; fail the test if it has not finished after JOIN_TIMEOUT."""
    outcome: list[Any] = []

    def work() -> None:
        try:
            outcome.append(oob.decode_msdp(payload))
        except OobDecodeError as exc:
            outcome.append(exc)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(JOIN_TIMEOUT)
    assert not thread.is_alive(), "decode_msdp did not finish in time"
    return outcome[0]


# GMCP ---------------------------------------------------------------------


def test_gmcp_bare_package() -> None:
    assert oob.decode_gmcp(b"Core.KeepAlive") == ("Core.KeepAlive", None)


def test_gmcp_package_with_json() -> None:
    assert oob.decode_gmcp(b'Char.Vitals {"hp": 5, "tags": [1, 2]}') == (
        "Char.Vitals",
        {"hp": 5, "tags": [1, 2]},
    )


def test_gmcp_empty_body() -> None:
    assert oob.decode_gmcp(b"Room.Info   ") == ("Room.Info", None)


@pytest.mark.parametrize("body", [b"Char.Vitals {not json", b"Char.Vitals {"])
def test_gmcp_bad_json_names_the_package(body: bytes) -> None:
    with pytest.raises(OobDecodeError) as info:
        oob.decode_gmcp(body)
    assert info.value.name == "Char.Vitals"


def test_gmcp_deep_nesting_is_rejected() -> None:
    body = b"[" * 100_000 + b"]" * 100_000
    with pytest.raises(OobDecodeError):
        oob.decode_gmcp(b"Char.Deep " + body)


@pytest.mark.parametrize("name", [b"", b"9Bad", b"Bad Name x", b"Bad/Name", b"A" * 65])
def test_gmcp_invalid_package_is_rejected(name: bytes) -> None:
    with pytest.raises(OobDecodeError):
        oob.decode_gmcp(name + b" {}")


def test_gmcp_oversize_payload_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "OOB_MAX_PAYLOAD", 32)
    assert oob.decode_gmcp(b"A.B " + b"1" * 28)[0] == "A.B"
    with pytest.raises(OobDecodeError):
        oob.decode_gmcp(b"A.B " + b"1" * 29)


def test_gmcp_uses_the_given_encoding() -> None:
    payload = 'Char.Name "é"'.encode("latin-1")
    assert oob.decode_gmcp(payload, "latin-1") == ("Char.Name", "é")


# MSDP ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "variables",
    [
        {"HEALTH": "100"},
        {"ROOM": ["a", "b", "c"]},
        {"ROOM": {"VNUM": "1", "NAME": "Hall", "EXITS": {"n": "2"}}},
        {"A": "1", "B": ["x", {"k": "v"}], "C": {"l": ["1", "2"]}},
        {"EMPTY": "", "LIST": []},
    ],
)
def test_msdp_round_trips_telnetlib3_encoding(variables: dict[str, Any]) -> None:
    assert run_bounded(msdp_encode(variables)) == variables


def test_msdp_decodes_utf8_strings() -> None:
    assert run_bounded(msdp_encode({"NAME": "héllo"})) == {"NAME": "héllo"}


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"garbage",
        MSDP_VAR + b"ROOM",
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_TABLE_OPEN,
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_TABLE_OPEN + MSDP_VAR + b"A",
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_ARRAY_OPEN + MSDP_VAL + b"x",
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_TABLE_CLOSE,
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_TABLE_OPEN + MSDP_VAL + b"x" + MSDP_TABLE_CLOSE,
        MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_ARRAY_OPEN + MSDP_VAR + b"x" + MSDP_ARRAY_CLOSE,
        MSDP_VAR + MSDP_VAL + b"x",
        MSDP_VAR + b"bad name" + MSDP_VAL + b"x",
        MSDP_VAL + MSDP_VAL + MSDP_VAL,
        MSDP_ARRAY_CLOSE * 50,
        MSDP_TABLE_OPEN * 50,
    ],
)
def test_msdp_malformed_input_raises_promptly(payload: bytes) -> None:
    assert isinstance(run_bounded(payload), OobDecodeError)


def test_msdp_depth_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def nested(depth: int) -> bytes:
        body = b"x"
        for _ in range(depth):
            body = MSDP_ARRAY_OPEN + MSDP_VAL + body + MSDP_ARRAY_CLOSE
        return MSDP_VAR + b"A" + MSDP_VAL + body

    assert isinstance(run_bounded(nested(oob.MSDP_MAX_DEPTH)), dict)
    assert isinstance(run_bounded(nested(oob.MSDP_MAX_DEPTH + 1)), OobDecodeError)
    monkeypatch.setattr(oob, "MSDP_MAX_DEPTH", 2)
    assert isinstance(run_bounded(nested(2)), dict)
    assert isinstance(run_bounded(nested(3)), OobDecodeError)


def test_msdp_node_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def items(count: int) -> bytes:
        return (
            MSDP_VAR
            + b"A"
            + MSDP_VAL
            + MSDP_ARRAY_OPEN
            + (MSDP_VAL + b"x") * count
            + MSDP_ARRAY_CLOSE
        )

    # the array itself is one node
    assert isinstance(run_bounded(items(oob.MSDP_MAX_NODES - 1)), dict)
    assert isinstance(run_bounded(items(oob.MSDP_MAX_NODES)), OobDecodeError)
    monkeypatch.setattr(oob, "MSDP_MAX_NODES", 3)
    assert isinstance(run_bounded(items(2)), dict)
    assert isinstance(run_bounded(items(3)), OobDecodeError)


def test_msdp_oversize_payload_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "OOB_MAX_PAYLOAD", 10)
    assert isinstance(run_bounded(MSDP_VAR + b"A" + MSDP_VAL + b"1" * 20), OobDecodeError)


def test_msdp_error_names_the_variable() -> None:
    result = run_bounded(MSDP_VAR + b"ROOM" + MSDP_VAL + MSDP_TABLE_OPEN)
    assert result.name == "ROOM"


def test_msdp_large_valid_payload_decodes_quickly() -> None:
    variables = {"LIST": [str(n) for n in range(oob.MSDP_MAX_NODES - 1)]}
    assert run_bounded(msdp_encode(variables)) == variables


# names ---------------------------------------------------------------------


def test_valid_names() -> None:
    assert oob.valid_package("Char.Vitals")
    assert not oob.valid_package("Char Vitals")
    assert oob.valid_variable("ROOM_NAME")
    assert not oob.valid_variable("ROOM.NAME")
    assert not oob.valid_variable("")


# supports --------------------------------------------------------------------


def test_parse_supports_versions_and_case() -> None:
    parsed = oob.parse_supports(["Char 1", "char 3", "Room", "Comm.Channel 2"])
    assert parsed == {"char": 3, "room": 1, "comm.channel": 2}


def test_parse_supports_skips_invalid_entries() -> None:
    parsed = oob.parse_supports(["Char 1", 5, "bad entry here", "x" * 100, "Room 1000", "9a", ""])
    assert parsed == {"char": 1}


def test_parse_supports_ignores_non_lists() -> None:
    assert oob.parse_supports("Char 1") == {}
    assert oob.parse_supports(None) == {}


def test_parse_supports_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "CLIENT_MAX_MODULES", 2)
    parsed = oob.parse_supports(["A 1", "B 1", "C 1", "A 4"])
    assert parsed == {"a": 4, "b": 1}


def test_supports_payload_is_sorted() -> None:
    assert oob.supports_payload({"room": 1, "char": 2}) == ["char 2", "room 1"]


@pytest.mark.parametrize(
    ("package", "modules", "expected"),
    [
        ("Char.Vitals", ["char"], True),
        ("Char", ["char"], True),
        ("char.vitals", ["char"], True),
        ("Character.X", ["char"], False),
        ("Char.Vitals", ["room", "char.vitals"], True),
        ("Char", ["char.vitals"], False),
        ("Room.Info", [], False),
    ],
)
def test_package_wanted(package: str, modules: list[str], expected: bool) -> None:
    assert oob.package_wanted(package, modules) is expected


# merge -----------------------------------------------------------------------


def test_merge_gmcp_shallow_merges_dicts() -> None:
    assert oob.merge_gmcp({"a": 1, "b": {"x": 1}}, {"b": {"y": 2}}) == {"a": 1, "b": {"y": 2}}


def test_merge_gmcp_replaces_non_dicts() -> None:
    assert oob.merge_gmcp([1], [2]) == [2]
    assert oob.merge_gmcp({"a": 1}, "text") == "text"


def test_merge_gmcp_replaces_when_the_merge_is_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oob, "OOB_MAX_PAYLOAD", 30)
    old = {"a": "x" * 20}
    new = {"b": "y" * 20}
    assert len(json.dumps({**old, **new})) > 30
    assert oob.merge_gmcp(old, new) == new
