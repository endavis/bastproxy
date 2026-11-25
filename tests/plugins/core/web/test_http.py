"""Request parsing and response serialization (#424)."""

import asyncio

import pytest

from bastproxy.plugins.core.web.libs import _http
from bastproxy.plugins.core.web.libs._http import (
    CSP,
    HttpError,
    Response,
    parse_head,
    read_request,
    serialize,
)

from .conftest import Running, get_request, http_get


def test_valid_get_is_parsed() -> None:
    head = b"GET /p/abc%20d?x=1&y=&x=2 HTTP/1.1\r\nHost: h\r\nCookie: a=1; b=2\r\n\r\n"
    request = parse_head(head)
    assert request.method == "GET"
    assert request.path == "/p/abc d"
    assert request.query == {"x": "1", "y": ""}
    assert request.cookies == {"a": "1", "b": "2"}


@pytest.mark.parametrize(
    "head",
    [
        b"GET /\r\n\r\n",
        b"GET / HTTP/2.0\r\n\r\n",
        b"GET / HTTP/1.1 extra\r\n\r\n",
        b"get / HTTP/1.1\r\n\r\n",
        b"GET index HTTP/1.1\r\n\r\n",
        b"GET /%ff HTTP/1.1\r\n\r\n",
        b"GET /%00 HTTP/1.1\r\n\r\n",
        b"GET /?a=%ff HTTP/1.1\r\n\r\n",
        b"GET / HTTP/1.1\r\nno colon here\r\n\r\n",
    ],
)
def test_bad_requests_are_400(head: bytes) -> None:
    with pytest.raises(HttpError) as excinfo:
        parse_head(head)
    assert excinfo.value.status == 400


def test_too_many_query_fields_is_400() -> None:
    query = "&".join(f"k{i}=1" for i in range(_http.MAX_QUERY_FIELDS + 1))
    with pytest.raises(HttpError):
        parse_head(f"GET /?{query} HTTP/1.1\r\n\r\n".encode())


def test_malformed_cookie_is_ignored() -> None:
    request = parse_head(b"GET / HTTP/1.1\r\nCookie: a b=\x01\r\n\r\n")
    assert request.cookies == {}


def test_serialize_adds_the_security_headers() -> None:
    raw = serialize(Response(200, "text/plain", b"hi", [("Allow", "GET")]))
    head, _, body = raw.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 200 OK\r\n")
    assert body == b"hi"
    text = head.decode()
    for line in (
        f"Content-Security-Policy: {CSP}",
        "Referrer-Policy: no-referrer",
        "Cache-Control: no-store",
        "X-Content-Type-Options: nosniff",
        "Connection: close",
        "Content-Length: 2",
        "Allow: GET",
    ):
        assert line in text


async def test_read_request_over_a_reader() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"GET /x HTTP/1.1\r\n\r\n")
    assert (await read_request(reader)).path == "/x"


async def test_truncated_head_is_400() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"GET /x HTT")
    reader.feed_eof()
    with pytest.raises(HttpError) as excinfo:
        await read_request(reader)
    assert excinfo.value.status == 400


async def test_silent_client_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "READ_TIMEOUT", 0.1)
    with pytest.raises(TimeoutError):
        await read_request(asyncio.StreamReader())


async def test_oversized_head_is_431(running: Running) -> None:
    raw = b"GET / HTTP/1.1\r\nX-Pad: " + b"a" * (_http.MAX_HEAD + 100) + b"\r\n\r\n"
    status, _, _ = await http_get(running.port, raw)
    assert status == 431


async def test_bad_request_line_is_400_over_the_wire(running: Running) -> None:
    status, _, _ = await http_get(running.port, b"nonsense\r\n\r\n")
    assert status == 400


async def test_idle_connection_is_closed_after_the_timeout(
    running: Running, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_http, "READ_TIMEOUT", 0.1)
    reader, writer = await asyncio.open_connection("127.0.0.1", running.port)
    assert await asyncio.wait_for(reader.read(), 2) == b""
    writer.close()
    # the server still answers the next client
    status, _, _ = await http_get(running.port, get_request("/nothing"))
    assert status == 404
