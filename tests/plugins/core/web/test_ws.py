"""The client socket helpers: origins, upgrade, messages and the handler registry (#842)."""

from typing import Any

import pytest

from bastproxy.plugins.core.web.libs._http import parse_head, read_request
from bastproxy.plugins.core.web.libs._store import RESERVED_SEGMENTS
from bastproxy.plugins.core.web.libs._ws import (
    SocketHub,
    envelope,
    error_message,
    is_upgrade,
    origin_of,
    parse_message,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:9998", "http://127.0.0.1:9998"),
        ("HTTPS://Example.NET:443", "https://example.net"),
        ("http://example.net:80", "http://example.net"),
        ("https://example.net:9998", "https://example.net:9998"),
        ("http://[::1]:9998", "http://[::1]:9998"),
        ("null", None),
        ("", None),
        ("ftp://example.net", None),
        ("https://example.net/path", None),
        ("https://user@example.net", None),
        ("https://example.net:notaport", None),
    ],
)
def test_origin_of(value: str, expected: str | None) -> None:
    assert origin_of(value) == expected


def test_origin_of_can_strip_a_path() -> None:
    assert origin_of("https://Example.net:443/base/", strip_path=True) == "https://example.net"


def test_is_upgrade() -> None:
    upgrade = parse_head(b"GET /ws HTTP/1.1\r\nUpgrade: WebSocket\r\n\r\n")
    plain = parse_head(b"GET /ws HTTP/1.1\r\nHost: x\r\n\r\n")
    assert is_upgrade(upgrade)
    assert not is_upgrade(plain)


def test_parse_head_keeps_lower_cased_headers_and_joins_repeats() -> None:
    request = parse_head(b"GET / HTTP/1.1\r\nOrigin: a\r\nORIGIN: b\r\nHost: h\r\n\r\n")
    assert request.headers == {"origin": "a, b", "host": "h"}


async def test_read_request_still_parses_a_head() -> None:
    import asyncio

    reader = asyncio.StreamReader()
    reader.feed_data(b"GET /x HTTP/1.1\r\nHost: h\r\n\r\n")
    request = await read_request(reader)
    assert request.path == "/x"
    assert request.headers["host"] == "h"


def test_ws_is_a_reserved_segment() -> None:
    assert "ws" in RESERVED_SEGMENTS


def test_envelope() -> None:
    assert envelope("x", a=1) == {"v": 1, "type": "x", "a": 1}


def test_parse_message_accepts_an_object() -> None:
    message, error = parse_message('{"v": 1, "type": "ping", "n": 2}')
    assert error is None
    assert message == {"v": 1, "type": "ping", "n": 2}


@pytest.mark.parametrize(
    ("text", "code", "for_type"),
    [
        ("not json", "bad_json", None),
        ("[1]", "bad_message", None),
        ('"x"', "bad_message", None),
        ('{"v": 1}', "bad_message", None),
        ('{"v": 1, "type": 5}', "bad_message", None),
        ('{"v": 1, "type": ""}', "bad_message", None),
        ('{"type": "ping"}', "version", "ping"),
        ('{"v": 2, "type": "ping"}', "version", "ping"),
        ('{"v": "1", "type": "ping"}', "version", "ping"),
        ('{"v": true, "type": "ping"}', "version", "ping"),
        ('{"v": 1.0, "type": "ping"}', "version", "ping"),
    ],
)
def test_parse_message_errors(text: str, code: str, for_type: str | None) -> None:
    message, error = parse_message(text)
    assert message is None
    assert error is not None
    assert error["type"] == "error"
    assert error["code"] == code
    assert error.get("for") == for_type


def test_hub_register_and_unregister() -> None:
    hub = SocketHub()

    def handler(conn: object, message: dict[str, object]) -> None:
        return None

    hub.register("a", handler)
    assert hub.handlers["a"] is handler
    with pytest.raises(ValueError, match="cannot register"):
        hub.register("a", handler)
    with pytest.raises(ValueError, match="cannot register"):
        hub.register("", handler)
    hub.unregister("a")
    hub.unregister("a")
    assert "a" not in hub.handlers
    assert hub.count() == 0
    assert hub.close_all(1001, "x") == 0


def test_error_message_takes_extra_fields() -> None:
    message = error_message("unknown_topic", "no", "subscribe", topic="a.b")
    assert message == {
        "v": 1,
        "type": "error",
        "code": "unknown_topic",
        "message": "no",
        "for": "subscribe",
        "topic": "a.b",
    }
    assert "for" not in error_message("x", "y", topic="t")


def test_hub_connections_is_a_copy() -> None:
    hub = SocketHub()
    connection: Any = object()
    hub.add(connection)
    found = hub.connections()
    assert found == [connection]
    found.clear()
    assert hub.count() == 1


def test_hub_listeners_hear_open_and_close_and_can_be_removed() -> None:
    hub = SocketHub()
    seen: list[tuple[str, Any]] = []

    def opened(conn: Any) -> None:
        seen.append(("open", conn))

    def closed(conn: Any) -> None:
        seen.append(("close", conn))

    hub.add_listener(opened, closed)
    hub.opened("a")  # type: ignore[arg-type]
    hub.closed("a")  # type: ignore[arg-type]
    assert seen == [("open", "a"), ("close", "a")]
    hub.remove_listener(opened, closed)
    hub.remove_listener(opened, closed)
    hub.opened("b")  # type: ignore[arg-type]
    assert len(seen) == 2


def test_a_raising_listener_is_logged_and_the_others_still_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hub = SocketHub()
    seen: list[Any] = []

    def boom(conn: Any) -> None:
        raise RuntimeError("listener broke")

    hub.add_listener(boom, boom)
    hub.add_listener(seen.append, seen.append)
    hub.opened("a")  # type: ignore[arg-type]
    assert seen == ["a"]
    assert any("socket listener failed" in r.getMessage() for r in caplog.records)
