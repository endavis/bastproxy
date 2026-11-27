"""Dispatch, headers and the listener (#424)."""

import asyncio
import os
import re
import ssl
from pathlib import Path

import pytest

from bastproxy.plugins.core.web.libs._http import CSP, MAX_CONNECTIONS
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import PageStore
from bastproxy.plugins.core.web.libs._tls import CertManager

from .conftest import MakeCert, Running, get_request, http_get, needs_openssl

EXPECTED_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=\"/static/table.js\")", re.IGNORECASE)


def test_csp_is_exactly_the_settled_policy() -> None:
    assert CSP == EXPECTED_CSP


async def test_a_page_is_served_escaped_and_coloured(running: Running) -> None:
    token = running.add_page(["@rhello <b>&", "<script>alert(1)</script>"])
    status, headers, body = await running.get(f"/p/{token}")
    text = body.decode()
    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert "<span style='color:#cd0000'>hello &lt;b&gt;&amp;</span>" in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "<script" not in text


async def test_unknown_token_is_404(running: Running) -> None:
    status, _, _ = await running.get("/p/unknown")
    assert status == 404


async def test_expired_token_is_404(running: Running) -> None:
    now = [0.0]
    running.pages._clock = lambda: now[0]
    token = running.add_page("x")
    assert (await running.get(f"/p/{token}"))[0] == 200
    now[0] = running.pages.ttl + 1
    assert (await running.get(f"/p/{token}"))[0] == 404


@pytest.mark.parametrize("path", ["/p/", "/login/x", "/a/b"])
async def test_everything_else_is_404(running: Running, path: str) -> None:
    status, _, _ = await running.get(path)
    assert status == 404


async def test_post_is_405_with_allow(running: Running) -> None:
    token = running.add_page("x")
    raw = f"POST /p/{token} HTTP/1.1\r\nContent-Length: 0\r\n\r\n".encode()
    status, headers, _ = await http_get(running.port, raw)
    assert status == 405
    assert headers["allow"] == "GET"


async def test_every_response_has_the_security_headers_and_no_inline_script(
    running: Running,
) -> None:
    token = running.add_page("<script>x</script>")
    requests = [
        get_request(f"/p/{token}"),
        get_request("/p/unknown"),
        get_request("/"),
        b"POST / HTTP/1.1\r\n\r\n",
        b"junk\r\n\r\n",
    ]
    for raw in requests:
        _, headers, body = await http_get(running.port, raw)
        assert headers["content-security-policy"] == EXPECTED_CSP
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["connection"] == "close"
        assert not INLINE_SCRIPT.search(body.decode())


async def test_connection_cap_closes_the_extra_connection(running: Running) -> None:
    held = [
        await asyncio.open_connection("127.0.0.1", running.port) for _ in range(MAX_CONNECTIONS)
    ]
    try:
        for _ in range(50):
            if len(running.server._writers) >= MAX_CONNECTIONS:
                break
            await asyncio.sleep(0.02)
        reader, writer = await asyncio.open_connection("127.0.0.1", running.port)
        assert await asyncio.wait_for(reader.read(), 2) == b""
        writer.close()
    finally:
        for _, writer in held:
            writer.close()


async def test_close_stops_the_listener(running: Running) -> None:
    running.server.close()
    await running.server.wait_closed()
    assert not running.server.running
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", running.port)


async def test_close_aborts_open_connections(running: Running) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", running.port)
    for _ in range(50):
        if running.server._writers:
            break
        await asyncio.sleep(0.02)
    running.server.close()
    assert await asyncio.wait_for(reader.read(), 2) == b""
    writer.close()


@needs_openssl
async def test_tls_serves_a_page(make_cert: MakeCert) -> None:
    certfile, keyfile = make_cert("bastproxy.test")
    cert = CertManager(certfile, keyfile)
    cert.load()
    pages = PageStore()
    token = pages.add("o", "t", b"<p>secure</p>")
    server = WebServer()
    port = await server.start("127.0.0.1", 0, WebApp(pages), cert)
    try:
        assert server.tls
        client = ssl.create_default_context(cafile=str(certfile))
        client.check_hostname = False
        client.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        status, headers, body = await http_get(port, get_request(f"/p/{token}"), client)
        assert (status, body) == (200, b"<p>secure</p>")
        assert headers["content-security-policy"] == EXPECTED_CSP
    finally:
        server.close()
        await server.wait_closed()


@needs_openssl
async def test_next_connection_sees_a_replaced_certificate(
    make_cert: MakeCert, tmp_path: Path
) -> None:
    first_cert, first_key = make_cert("first.test", "one")
    second_cert, second_key = make_cert("second.test", "two")
    live_cert, live_key = tmp_path / "live.pem", tmp_path / "live.key"
    live_cert.write_bytes(first_cert.read_bytes())
    live_key.write_bytes(first_key.read_bytes())
    cert = CertManager(live_cert, live_key)
    cert.load()
    server = WebServer()
    port = await server.start("127.0.0.1", 0, WebApp(PageStore()), cert)

    async def subject_seen(ca: Path) -> str:
        client = ssl.create_default_context(cafile=str(ca))
        client.check_hostname = False
        client.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        _, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client, server_hostname="x"
        )
        cn = ""
        peer = writer.get_extra_info("peercert")
        for rdn in peer["subject"]:
            for key, value in rdn:
                if key == "commonName":
                    cn = value
        writer.close()
        await writer.wait_closed()
        return cn

    try:
        assert await subject_seen(first_cert) == "first.test"
        live_cert.write_bytes(second_cert.read_bytes())
        live_key.write_bytes(second_key.read_bytes())
        newer = live_cert.stat().st_mtime_ns + 5_000_000_000
        for path in (live_cert, live_key):
            os.utime(path, ns=(newer, newer))
        assert await subject_seen(second_cert) == "second.test"
    finally:
        server.close()
        await server.wait_closed()


@needs_openssl
async def test_a_failed_tls_handshake_does_not_stop_the_server(make_cert: MakeCert) -> None:
    certfile, keyfile = make_cert("bastproxy.test")
    cert = CertManager(certfile, keyfile)
    cert.load()
    server = WebServer()
    port = await server.start("127.0.0.1", 0, WebApp(PageStore()), cert)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET / HTTP/1.1\r\n\r\n")  # plain text to a TLS listener
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 5) == b""
        writer.close()
        assert server.running
    finally:
        server.close()
        await server.wait_closed()


async def test_the_server_port_is_set_on_start_and_reset_on_close() -> None:
    server = WebServer()
    assert server.port == 0
    bound = await server.start("127.0.0.1", 0, WebApp(PageStore()), None)
    assert bound != 0
    assert server.port == bound
    server.close()
    await server.wait_closed()
    assert server.port == 0
