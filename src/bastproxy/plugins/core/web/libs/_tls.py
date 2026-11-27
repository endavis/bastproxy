# Project: bastproxy
# Filename: plugins/core/web/libs/_tls.py
#
# File Description: the TLS rule, certificate reload and certificate details
#
# By: Bast
"""Certificate handling for the web plugin, standard library only."""

# Standard Library
import datetime
import ipaddress
import os
import ssl
from pathlib import Path
from typing import Any

from bastproxy.libs.logger import get_logger

CANRELOAD = False

LOGGER_NAME = "plugins.core.web"
# the expired code of OpenSSL's X509_V_ERR_CERT_HAS_EXPIRED
VERIFY_CODE_EXPIRED = 10
_MAX_HANDSHAKE_ROUNDS = 20


def is_loopback(addr: str) -> bool:
    """Return True for ``localhost`` or an IP literal that is a loopback address.

    Any other hostname counts as not loopback.
    """
    if addr.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def parse_bind_addresses(value: str) -> list[str]:
    """Split a comma-separated bind address setting into stripped entries."""
    return [part.strip() for part in value.split(",")]


def all_loopback(addrs: list[str]) -> bool:
    """Return True when every address is a loopback address."""
    return all(is_loopback(addr) for addr in addrs)


def validate_bind_address(value: Any) -> str:
    """Setting validator: IP literals or ``localhost``, comma-separated; "" when valid."""
    if not isinstance(value, str) or not value:
        return "the bind address cannot be empty"
    seen: set[str] = set()
    for entry in parse_bind_addresses(value):
        if not entry:
            return "the bind address list cannot have an empty entry"
        if entry.lower() == "localhost":
            key = "localhost"
        else:
            try:
                key = str(ipaddress.ip_address(entry))
            except ValueError:
                return "the bind address must be an IP address or localhost"
        if key in seen:
            return f"the bind address {entry} is listed more than once"
        seen.add(key)
    return ""


class CertManager:
    """Keeps one SSLContext and rebuilds it when the certificate or key file changes."""

    def __init__(self, certfile: Path, keyfile: Path) -> None:
        self.certfile = certfile
        self.keyfile = keyfile
        self.last_reload: datetime.datetime | None = None
        self.last_error = ""
        self._context: ssl.SSLContext | None = None
        self._stamp: tuple[int, int] | None = None

    def _stat(self) -> tuple[int, int]:
        return (os.stat(self.certfile).st_mtime_ns, os.stat(self.keyfile).st_mtime_ns)

    def _build(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.certfile), str(self.keyfile))
        return context

    def load(self) -> None:
        """Load the certificate; raises OSError or ssl.SSLError on failure."""
        stamp = self._stat()
        self._context = self._build()
        self._stamp = stamp
        self.last_reload = datetime.datetime.now(datetime.UTC)
        self.last_error = ""

    def reload(self) -> bool:
        """Rebuild the context now. On failure keep the old context and log an ERROR."""
        try:
            stamp = self._stat()
        except OSError as exc:
            return self._failed(exc)
        # remember the stamp even on failure, so a bad pair is not retried on every connection
        self._stamp = stamp
        try:
            context = self._build()
        except (OSError, ssl.SSLError) as exc:
            return self._failed(exc)
        self._context = context
        self.last_reload = datetime.datetime.now(datetime.UTC)
        self.last_error = ""
        return True

    def _failed(self, exc: Exception) -> bool:
        self.last_error = f"{type(exc).__name__}: {exc}"
        get_logger(LOGGER_NAME).error(
            "certificate reload failed, keeping the previous certificate: %s", self.last_error
        )
        return False

    def current(self) -> ssl.SSLContext:
        """Return the context to use for a new connection, reloading when a file changed."""
        if self._context is None:
            raise RuntimeError("the certificate is not loaded")
        try:
            changed = self._stat() != self._stamp
        except OSError:
            changed = True
        if changed:
            self.reload()
        return self._context


def _handshake(certfile: Path, keyfile: Path) -> dict[str, Any]:
    """Run a TLS handshake in memory and return the certificate the client verified."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(certfile), str(keyfile))
    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = False
    client_ctx.load_verify_locations(cafile=str(certfile))
    client_ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN

    to_server, to_client = ssl.MemoryBIO(), ssl.MemoryBIO()
    from_server, from_client = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_ctx.wrap_bio(to_client, from_client)
    server = server_ctx.wrap_bio(to_server, from_server, server_side=True)
    done = {"client": False, "server": False}
    for _ in range(_MAX_HANDSHAKE_ROUNDS):
        for name, side in (("client", client), ("server", server)):
            if done[name]:
                continue
            try:
                side.do_handshake()
                done[name] = True
            except ssl.SSLWantReadError:
                pass
        if data := from_client.read():
            to_server.write(data)
        if data := from_server.read():
            to_client.write(data)
        if all(done.values()):
            break
    cert = client.getpeercert()
    if not cert:
        raise ssl.SSLError("no certificate was returned by the handshake")
    return dict(cert)


def cert_details(certfile: Path, keyfile: Path) -> dict[str, Any]:
    """Describe the certificate: ``state`` (ok, expired, unavailable), ``subject``,
    ``san``, ``not_after`` and the files' ``mtime``.
    """
    details: dict[str, Any] = {
        "state": "unavailable",
        "subject": "",
        "san": [],
        "not_after": "",
        "mtime": None,
    }
    try:
        details["mtime"] = datetime.datetime.fromtimestamp(os.stat(certfile).st_mtime, datetime.UTC)
        cert = _handshake(certfile, keyfile)
    except ssl.SSLCertVerificationError as exc:
        if exc.verify_code == VERIFY_CODE_EXPIRED:
            details["state"] = "expired"
        return details
    except (OSError, ssl.SSLError, ValueError):
        return details
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                details["subject"] = value
    details["san"] = [value for _kind, value in cert.get("subjectAltName", ())]
    details["not_after"] = cert.get("notAfter", "")
    details["state"] = "ok"
    return details
