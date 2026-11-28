# Project: bastproxy
# Filename: plugins/core/web/libs/_http.py
#
# File Description: HTTP requests and responses for the web plugin
#
# By: Bast
"""A minimal HTTP/1.1 request reader and response writer (no body is ever read)."""

# Standard Library
import asyncio
import html
import re
import urllib.parse
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._table import TableQuery

# keep module identity across a reload of the plugin (other objects hold these classes)
CANRELOAD = False

MAX_HEAD = 8192
READ_TIMEOUT = 10
HANDLER_TIMEOUT = 30
MAX_CONNECTIONS = 32
MAX_QUERY_FIELDS = 50

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
# the policy for the web client bundle: the page above plus its own fetches and fonts
CLIENT_CSP = CSP + "; connect-src 'self'; font-src 'self'"
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", CSP),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
)

_METHOD_RE = re.compile(r"^[A-Z]{1,16}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class HttpError(Exception):
    """A request that must be answered with an error status."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


@dataclass(frozen=True)
class Request:
    """One parsed GET-style request, read only."""

    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    subpath: str = ""
    table: "TableQuery | None" = None


@dataclass
class Response:
    """One response; the security headers are added when it is serialized."""

    status: int
    content_type: str
    body: bytes
    headers: list[tuple[str, str]] = field(default_factory=list)
    csp: str = CSP


def _parse_cookies(value: str) -> dict[str, str]:
    """Parse a Cookie header, returning nothing for a malformed one."""
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(value)
    except CookieError:
        return {}
    return {name: morsel.value for name, morsel in jar.items()}


def parse_head(head: bytes) -> Request:
    """Parse a request head (up to and including the blank line).

    Raises HttpError(400) for a bad request line, version, header or percent-encoding.
    """
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise HttpError(HTTPStatus.BAD_REQUEST)
    method, target, version = parts
    if (
        not _METHOD_RE.match(method)
        or version not in ("HTTP/1.0", "HTTP/1.1")
        or not target.startswith("/")
    ):
        raise HttpError(HTTPStatus.BAD_REQUEST)

    cookies: dict[str, str] = {}
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep or not name or name != name.strip():
            raise HttpError(HTTPStatus.BAD_REQUEST)
        lowered = name.lower()
        if lowered == "cookie":
            cookies.update(_parse_cookies(value.strip()))
        # a repeated header is joined with a comma, so a doubled Origin never matches
        previous = headers.get(lowered)
        headers[lowered] = value.strip() if previous is None else f"{previous}, {value.strip()}"

    raw_path, _, raw_query = target.partition("?")
    try:
        path = urllib.parse.unquote(raw_path, errors="strict")
        parsed = urllib.parse.parse_qs(
            raw_query, keep_blank_values=True, errors="strict", max_num_fields=MAX_QUERY_FIELDS
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HttpError(HTTPStatus.BAD_REQUEST) from exc
    if _CONTROL_RE.search(path):
        raise HttpError(HTTPStatus.BAD_REQUEST)
    query = {key: values[0] for key, values in parsed.items()}
    return Request(method=method, path=path, query=query, cookies=cookies, headers=headers)


async def read_head(reader: asyncio.StreamReader) -> bytes:
    """Read one request head, up to and including the blank line.

    Raises HttpError(431) for a head over MAX_HEAD, HttpError(400) for a truncated one, and
    TimeoutError when the client is too slow (the caller closes the connection).
    """
    try:
        async with asyncio.timeout(READ_TIMEOUT):
            head = await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as exc:
        raise HttpError(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE) from exc
    except asyncio.IncompleteReadError as exc:
        raise HttpError(HTTPStatus.BAD_REQUEST) from exc
    return head


async def read_request(reader: asyncio.StreamReader) -> Request:
    """Read and parse one request head; the body is never read.

    Raises what ``read_head`` and ``parse_head`` raise.
    """
    return parse_head(await read_head(reader))


def serialize(response: Response) -> bytes:
    """Build the bytes of a response with the security headers, length and close."""
    phrase = HTTPStatus(response.status).phrase
    headers = [
        ("Content-Type", response.content_type),
        ("Content-Length", str(len(response.body))),
        ("Connection", "close"),
        ("Content-Security-Policy", response.csp),
        *SECURITY_HEADERS[1:],
        *response.headers,
    ]
    head = f"HTTP/1.1 {response.status} {phrase}\r\n"
    head += "".join(f"{name}: {value}\r\n" for name, value in headers)
    return head.encode("latin-1") + b"\r\n" + response.body


def text_response(status: int, document: str) -> Response:
    """Wrap an html document in a response."""
    return Response(status, "text/html; charset=utf-8", document.encode("utf-8"))


def message_response(
    status: int, text: str = "", extra: list[tuple[str, str]] | None = None
) -> Response:
    """A small html page that carries the status phrase and an optional message."""
    phrase = html.escape(HTTPStatus(status).phrase)
    body = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{status} {phrase}</title></head>"
    )
    body += f"<body><h1>{status} {phrase}</h1><p>{html.escape(text)}</p></body></html>"
    response = text_response(status, body)
    response.headers.extend(extra or [])
    return response


def redirect(location: str, headers: list[tuple[str, str]] | None = None) -> Response:
    """A 303 response to a location, with extra headers such as Set-Cookie."""
    response = Response(HTTPStatus.SEE_OTHER, "text/html; charset=utf-8", b"")
    response.headers.append(("Location", location))
    response.headers.extend(headers or [])
    return response
