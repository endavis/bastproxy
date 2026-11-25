"""Shared fixtures for the web plugin tests."""

import asyncio
import shutil
import ssl
import subprocess
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.web.libs._render import render_page
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import PageStore

needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="needs the openssl CLI to make a test certificate"
)

MakeCert = Callable[..., tuple[Path, Path]]


def to_html(text: str) -> str:
    """The real colour converter, as the web plugin gets it from the colors API."""
    result: str = ColorsPlugin._api_colorcode_to_html(MagicMock(), text)
    return result


@pytest.fixture
def make_cert(tmp_path: Path) -> MakeCert:
    """Return a function that writes a self-signed certificate and key, valid for 2 days."""

    def make(cn: str, name: str = "cert") -> tuple[Path, Path]:
        certfile = tmp_path / f"{name}.pem"
        keyfile = tmp_path / f"{name}.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-subj",
                f"/CN={cn}",
                "-addext",
                f"subjectAltName=DNS:{cn}",
                "-keyout",
                str(keyfile),
                "-out",
                str(certfile),
            ],
            check=True,
            capture_output=True,
        )
        return certfile, keyfile

    return make


async def http_get(
    port: int,
    raw: bytes,
    ssl_ctx: ssl.SSLContext | None = None,
    host: str = "127.0.0.1",
) -> tuple[int, dict[str, str], bytes]:
    """Send raw bytes and return (status, lower-cased headers, body)."""
    reader, writer = await asyncio.open_connection(
        host, port, ssl=ssl_ctx, server_hostname=host if ssl_ctx else None
    )
    writer.write(raw)
    await writer.drain()
    data = await reader.read()
    writer.close()
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split(" ")[1])
    headers = {
        key.lower(): value.strip() for key, _, value in (line.partition(":") for line in lines[1:])
    }
    return status, headers, body


def get_request(path: str) -> bytes:
    """A minimal GET request for a path."""
    return f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode("latin-1")


class Running:
    """A started plain-http server with its page store."""

    def __init__(self, server: WebServer, pages: PageStore, port: int) -> None:
        self.server = server
        self.pages = pages
        self.port = port

    def add_page(self, lines: list[str] | str, title: str = "t") -> str:
        document = render_page(title, lines, to_html)
        return self.pages.add("plugins.test", title, document.encode("utf-8"))

    async def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        return await http_get(self.port, get_request(path))


@pytest.fixture
async def running() -> AsyncIterator[Running]:
    """A plain-http server on 127.0.0.1 with a free port."""
    pages = PageStore()
    server = WebServer()
    port = await server.start("127.0.0.1", 0, WebApp(pages), None)
    yield Running(server, pages, port)
    server.close()
    await server.wait_closed()
