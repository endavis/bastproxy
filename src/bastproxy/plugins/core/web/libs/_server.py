# Project: bastproxy
# Filename: plugins/core/web/libs/_server.py
#
# File Description: request dispatch and the asyncio connection handler
#
# By: Bast
"""The web application (request dispatch) and the listener."""

# Standard Library
import asyncio
import contextlib
from http import HTTPStatus

from bastproxy.libs.logger import get_logger

from . import _http
from ._http import HttpError, Request, Response, message_response, read_request, serialize
from ._store import PageStore
from ._tls import LOGGER_NAME, CertManager

CANRELOAD = False

TLS_HANDSHAKE_TIMEOUT = 10
CLOSE_TIMEOUT = 5
PAGE_PREFIX = "/p/"


class WebApp:
    """Turns a request into a response."""

    def __init__(self, pages: PageStore) -> None:
        self.pages = pages

    async def dispatch(self, request: Request) -> Response:
        """Answer one request.

        The order is: a method other than GET (405), a page token link, anything else (404).
        """
        if request.method != "GET":
            return message_response(HTTPStatus.METHOD_NOT_ALLOWED, extra=[("Allow", "GET")])
        if request.path.startswith(PAGE_PREFIX):
            page = self.pages.get(request.path[len(PAGE_PREFIX) :])
            if page is not None:
                return Response(HTTPStatus.OK, "text/html; charset=utf-8", page.body)
        return message_response(HTTPStatus.NOT_FOUND)


class WebServer:
    """The asyncio listener: connection cap, optional TLS per connection, and dispatch."""

    def __init__(self) -> None:
        self.tls = False
        self.address = ""
        self._server: asyncio.Server | None = None
        self._closed: asyncio.Server | None = None
        self._cert: CertManager | None = None
        self._app: WebApp | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    @property
    def running(self) -> bool:
        """True while the listener is accepting connections."""
        return self._server is not None and self._server.is_serving()

    async def start(self, host: str, port: int, app: WebApp, cert: CertManager | None) -> int:
        """Start listening and return the bound port (a port of 0 picks a free one)."""
        self._app = app
        self._cert = cert
        self._server = await asyncio.start_server(
            self._on_connection, host, port, limit=_http.MAX_HEAD
        )
        self.tls = cert is not None
        bound: int = self._server.sockets[0].getsockname()[1]
        self.address = f"{host}:{bound}"
        return bound

    def close(self) -> None:
        """Stop listening at once and abort the connections still open."""
        if self._server is not None:
            self._server.close()
            self._closed = self._server
            self._server = None
        for writer in list(self._writers):
            writer.transport.abort()
        self._writers.clear()
        self.tls = False
        self.address = ""

    async def wait_closed(self) -> None:
        """Wait until the listener closed by ``close`` is fully shut down."""
        if self._closed is not None:
            server, self._closed = self._closed, None
            await server.wait_closed()

    async def _on_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if len(self._writers) >= _http.MAX_CONNECTIONS:
            writer.transport.abort()
            return
        self._writers.add(writer)
        try:
            if self._cert is not None:
                await writer.start_tls(
                    self._cert.current(), ssl_handshake_timeout=TLS_HANDSHAKE_TIMEOUT
                )
            response = await self._answer(reader)
            writer.write(serialize(response))
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            # a handshake failure, a timeout, or a client that went away
            pass
        except Exception:
            get_logger(LOGGER_NAME).error("web request failed", exc_info=True)
        finally:
            self._writers.discard(writer)
            writer.close()
            with contextlib.suppress(OSError):
                async with asyncio.timeout(CLOSE_TIMEOUT):
                    await writer.wait_closed()

    async def _answer(self, reader: asyncio.StreamReader) -> Response:
        if self._app is None:
            return message_response(HTTPStatus.SERVICE_UNAVAILABLE)
        try:
            request = await read_request(reader)
        except HttpError as exc:
            return message_response(exc.status)
        return await self._app.dispatch(request)
