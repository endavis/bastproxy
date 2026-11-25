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
import dataclasses
import functools
import html
import importlib.resources
import inspect
import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from bastproxy.libs.logger import get_logger

from . import _http
from ._http import (
    HttpError,
    Request,
    Response,
    message_response,
    read_request,
    redirect,
    serialize,
    text_response,
)
from ._render import render_index, render_page, render_table, render_table_page
from ._store import LoginTokens, PageStore, Route, RouteTable, SessionStore
from ._table import FILTER_PREFIX, TABLE_KEYS, parse_table_query
from ._tls import LOGGER_NAME, CertManager

CANRELOAD = False

TLS_HANDSHAKE_TIMEOUT = 10
CLOSE_TIMEOUT = 5
PAGE_PREFIX = "/p/"
LOGIN_PREFIX = "/login/"
SESSION_COOKIE = "bpsession"
TABLE_SCRIPT_PATH = "/static/table.js"
HANDLER_ERROR_STATUSES = (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND)


@functools.cache
def _table_script() -> bytes:
    """The one static script, read once from the package."""
    resource = importlib.resources.files("bastproxy.plugins.core.web") / "static" / "table.js"
    return resource.read_bytes()


class WebApp:
    """Turns a request into a response."""

    def __init__(
        self,
        pages: PageStore,
        *,
        routes: RouteTable | None = None,
        logins: LoginTokens | None = None,
        sessions: SessionStore | None = None,
        to_html: Callable[[str], str] = html.escape,
        login_command: Callable[[], str] = lambda: "the login command",
        secure_cookie: Callable[[], bool] = lambda: False,
        session_seconds: Callable[[], float] = lambda: 12 * 3600,
    ) -> None:
        self.pages = pages
        self.routes = routes if routes is not None else RouteTable()
        self.logins = logins if logins is not None else LoginTokens()
        self.sessions = sessions if sessions is not None else SessionStore()
        self._to_html = to_html
        self._login_command = login_command
        self._secure_cookie = secure_cookie
        self._session_seconds = session_seconds

    async def dispatch(self, request: Request) -> Response:
        """Answer one request.

        The order is: a method other than GET (405), a page token link, a login link, the
        index, a plugin route (the last two need a session, else 401), anything else (404).
        """
        if request.method != "GET":
            return message_response(HTTPStatus.METHOD_NOT_ALLOWED, extra=[("Allow", "GET")])
        path = request.path
        if path.startswith(PAGE_PREFIX):
            page = self.pages.get(path[len(PAGE_PREFIX) :])
            if page is not None:
                return Response(HTTPStatus.OK, "text/html; charset=utf-8", page.body)
        elif path.startswith(LOGIN_PREFIX):
            return self._login(path[len(LOGIN_PREFIX) :])
        elif path == TABLE_SCRIPT_PATH:
            return Response(HTTPStatus.OK, "text/javascript; charset=utf-8", _table_script())
        elif path == "/":
            if not self._has_session(request):
                return self._unauthorized()
            return text_response(HTTPStatus.OK, render_index(self.routes.by_owner()))
        elif (route := self.routes.match(path)) is not None:
            if not self._has_session(request):
                return self._unauthorized()
            return await self._call_handler(route, request)
        return message_response(HTTPStatus.NOT_FOUND)

    def _has_session(self, request: Request) -> bool:
        return self.sessions.is_valid(request.cookies.get(SESSION_COOKIE))

    def _unauthorized(self) -> Response:
        text = f"Not logged in. Run {self._login_command()} in your MUD client and open the link."
        return message_response(HTTPStatus.UNAUTHORIZED, text)

    def _login(self, token: str) -> Response:
        """Turn a login token into a session and a cookie, then go to the index."""
        if not self.logins.consume(token):
            return message_response(HTTPStatus.NOT_FOUND)
        lifetime = int(self._session_seconds())
        sid = self.sessions.create(lifetime)
        cookie = f"{SESSION_COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={lifetime}"
        if self._secure_cookie():
            cookie += "; Secure"
        return redirect("/", [("Set-Cookie", cookie)])

    async def _call_handler(self, route: Route, request: Request) -> Response:
        """Run a plugin handler (sync or async) under the timeout and build the response."""
        table = None
        if route.columns is not None:
            try:
                table = parse_table_query(request.query, route.columns)
            except HttpError as exc:
                return message_response(exc.status)
        routed = dataclasses.replace(request, subpath=route.subpath, table=table)
        try:
            async with asyncio.timeout(_http.HANDLER_TIMEOUT):
                result = route.handler(routed)
                if inspect.isawaitable(result):
                    result = await result
        except TimeoutError:
            get_logger(LOGGER_NAME).error("handler of %s timed out", route.path)
            return message_response(HTTPStatus.GATEWAY_TIMEOUT)
        except Exception:
            get_logger(LOGGER_NAME).error("handler of %s failed", route.path, exc_info=True)
            return message_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        try:
            return self._convert(result, route, routed)
        except Exception:
            get_logger(LOGGER_NAME).error(
                "handler of %s returned an unusable response", route.path, exc_info=True
            )
            return message_response(HTTPStatus.INTERNAL_SERVER_ERROR)

    def _convert(self, result: Any, route: Route, request: Request) -> Response:
        """Turn a handler's dict into a response; anything else is a 500."""
        if isinstance(result, dict):
            kind = result.get("kind")
            if kind == "html":
                document = render_page(str(result["title"]), result["lines"], self._to_html)
                return text_response(HTTPStatus.OK, document)
            if kind == "table" and route.columns is not None and request.table is not None:
                table = render_table(
                    route.columns,
                    result["rows"],
                    query=request.table,
                    total=int(result["total"]),
                    base_path=route.path,
                    to_html=self._to_html,
                    extra={
                        key: value
                        for key, value in request.query.items()
                        if key not in TABLE_KEYS and not key.startswith(FILTER_PREFIX)
                    },
                )
                document = render_table_page(
                    str(result["title"]), result.get("lines", ""), table, self._to_html
                )
                return text_response(HTTPStatus.OK, document)
            if kind == "svg" and isinstance(result.get("svg"), str):
                return Response(
                    HTTPStatus.OK, "image/svg+xml; charset=utf-8", result["svg"].encode("utf-8")
                )
            if kind == "error" and result.get("status") in HANDLER_ERROR_STATUSES:
                return message_response(int(result["status"]), str(result.get("message", "")))
            if kind == "json":
                body = json.dumps(result["data"], default=str).encode("utf-8")
                return Response(HTTPStatus.OK, "application/json", body)
        get_logger(LOGGER_NAME).error("a handler returned %s, not a response dict", type(result))
        return message_response(HTTPStatus.INTERNAL_SERVER_ERROR)


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
