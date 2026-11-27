"""The loopback rule, certificate reload and certificate details (#424)."""

import logging
import os
import ssl
from pathlib import Path

import pytest

from bastproxy.plugins.core.web.libs import _tls
from bastproxy.plugins.core.web.libs._tls import (
    CertManager,
    all_loopback,
    cert_details,
    is_loopback,
    parse_bind_addresses,
    validate_bind_address,
)

from .conftest import MakeCert, needs_openssl


@pytest.mark.parametrize("addr", ["127.0.0.1", "127.1.2.3", "::1", "localhost", "LOCALHOST"])
def test_loopback(addr: str) -> None:
    assert is_loopback(addr) is True


@pytest.mark.parametrize(
    "addr", ["0.0.0.0", "192.168.1.5", "example.net", "::", ""]
)  # reason: the test needs the wildcard address as an example of a non-loopback value
def test_not_loopback(addr: str) -> None:
    assert is_loopback(addr) is False


@pytest.mark.parametrize("value", ["127.0.0.1", "::1", "localhost", "192.168.1.5"])
def test_valid_bind_addresses(value: str) -> None:
    assert validate_bind_address(value) == ""


@pytest.mark.parametrize("value", ["", "example.net", "999.1.1.1", 5, None])
def test_invalid_bind_addresses(value: object) -> None:
    assert validate_bind_address(value) != ""


@needs_openssl
def test_load_and_current(make_cert: MakeCert) -> None:
    certfile, keyfile = make_cert("a.test")
    manager = CertManager(certfile, keyfile)
    manager.load()
    assert manager.last_reload is not None
    assert manager.current() is manager.current()


@needs_openssl
def test_current_rebuilds_when_a_file_changed(make_cert: MakeCert, tmp_path: Path) -> None:
    first = make_cert("first.test", "one")
    second = make_cert("second.test", "two")
    live_cert, live_key = tmp_path / "live.pem", tmp_path / "live.key"
    live_cert.write_bytes(first[0].read_bytes())
    live_key.write_bytes(first[1].read_bytes())
    manager = CertManager(live_cert, live_key)
    manager.load()
    before = manager.current()
    live_cert.write_bytes(second[0].read_bytes())
    live_key.write_bytes(second[1].read_bytes())
    newer = live_cert.stat().st_mtime_ns + 5_000_000_000
    os.utime(live_cert, ns=(newer, newer))
    os.utime(live_key, ns=(newer, newer))
    assert manager.current() is not before


@needs_openssl
def test_forced_reload_with_a_broken_key_keeps_the_old_context(
    make_cert: MakeCert, caplog: pytest.LogCaptureFixture
) -> None:
    certfile, keyfile = make_cert("a.test")
    manager = CertManager(certfile, keyfile)
    manager.load()
    before = manager.current()
    keyfile.write_text("not a key")
    with caplog.at_level(logging.ERROR):
        assert manager.reload() is False
    assert manager.current() is before
    assert manager.last_error
    assert any(r.levelno == logging.ERROR for r in caplog.records)


@needs_openssl
def test_a_bad_pair_is_not_retried_on_every_connection(
    make_cert: MakeCert, caplog: pytest.LogCaptureFixture
) -> None:
    certfile, keyfile = make_cert("a.test")
    manager = CertManager(certfile, keyfile)
    manager.load()
    keyfile.write_text("not a key")
    with caplog.at_level(logging.ERROR):
        manager.current()
        manager.current()
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1


def test_load_raises_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        CertManager(tmp_path / "no.pem", tmp_path / "no.key").load()


def test_current_before_load_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        CertManager(tmp_path / "a", tmp_path / "b").current()


@needs_openssl
def test_cert_details_for_a_valid_certificate(make_cert: MakeCert) -> None:
    certfile, keyfile = make_cert("bastproxy.test")
    details = cert_details(certfile, keyfile)
    assert details["state"] == "ok"
    assert details["subject"] == "bastproxy.test"
    assert details["san"] == ["bastproxy.test"]
    assert "GMT" in details["not_after"]
    assert details["mtime"] is not None


def test_cert_details_for_an_expired_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    certfile = tmp_path / "c.pem"
    certfile.write_text("x")

    def expired(_cert: Path, _key: Path) -> dict[str, object]:
        error = ssl.SSLCertVerificationError("certificate has expired")
        error.verify_code = 10
        raise error

    monkeypatch.setattr(_tls, "_handshake", expired)
    details = cert_details(certfile, tmp_path / "k.key")
    assert details["state"] == "expired"
    assert details["mtime"] is not None


def test_cert_details_unavailable_for_a_broken_file(tmp_path: Path) -> None:
    certfile = tmp_path / "c.pem"
    certfile.write_text("not a certificate")
    details = cert_details(certfile, certfile)
    assert details["state"] == "unavailable"
    assert details["mtime"] is not None


def test_cert_details_unavailable_for_a_missing_file(tmp_path: Path) -> None:
    details = cert_details(tmp_path / "no.pem", tmp_path / "no.key")
    assert details["state"] == "unavailable"
    assert details["mtime"] is None


@pytest.mark.parametrize(
    "value", ["127.0.0.1,::1", " 127.0.0.1 , ::1 ", "localhost,::1", "0.0.0.0,::"]
)  # reason: the wildcard addresses are the dual-stack example
def test_valid_bind_address_lists(value: str) -> None:
    assert validate_bind_address(value) == ""


@pytest.mark.parametrize(
    "value",
    ["127.0.0.1,", ",127.0.0.1", "127.0.0.1,,::1", "127.0.0.1,bad", "127.0.0.1,127.0.0.1"],
)
def test_invalid_bind_address_lists(value: str) -> None:
    assert validate_bind_address(value) != ""


def test_duplicate_is_compared_by_normalized_address() -> None:
    assert "more than once" in validate_bind_address("::1,0:0:0:0:0:0:0:1")
    assert "more than once" in validate_bind_address("localhost,LOCALHOST")


def test_parse_bind_addresses_strips() -> None:
    assert parse_bind_addresses(" 127.0.0.1 , ::1") == ["127.0.0.1", "::1"]


def test_all_loopback() -> None:
    assert all_loopback(["127.0.0.1", "::1", "localhost"])
    assert not all_loopback(["127.0.0.1", "0.0.0.0"])  # reason: a mixed list is not loopback
