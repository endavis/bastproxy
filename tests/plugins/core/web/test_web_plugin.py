"""The web plugin: settings, start rules, links, status, reload and unload (#424)."""

import asyncio
import logging
import ssl
from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.core.web.libs._call import Calls
from bastproxy.plugins.core.web.libs._server import WebServer
from bastproxy.plugins.core.web.libs._store import (
    LoginTokens,
    PageStore,
    ProviderListeners,
    RouteTable,
    SessionStore,
)
from bastproxy.plugins.core.web.libs._subscribe import Subscriptions
from bastproxy.plugins.core.web.plugin._web import WebPlugin

from .conftest import MakeCert, get_request, http_get, needs_openssl, to_html

HELPERS = (
    "_setting",
    "_path",
    "_client_dir",
    "_base_url",
    "_with_served_port",
    "_restart",
    "_schedule_restart",
    "_build_app",
    "_secure_cookie",
    "_sync_provider_events",
    "_provider_event_fired",
    "_refuse",
    "_escape",
    "_remove_routes",
)


class _Api:
    """The api object: callable by name, with the data directory attribute."""

    def __init__(self, stub: "_Stub", base: Path) -> None:
        self.BASEHOMEPATH = base
        self.BASEDATAPATH = base / "data"
        self._stub = stub

    def __call__(self, name: str) -> Any:
        stub = self._stub

        def call(*args: Any, **kwargs: Any) -> Any:
            stub.calls.append((name, args, kwargs))
            if name == "plugins.core.settings:setting.get":
                return stub.settings[args[1]]
            if name == "plugins.core.settings:setting.add":
                stub.added[args[1]] = args[2]
                return None
            if name == "plugins.core.colors:colorcode.to.html":
                return to_html(args[0])
            if name == "plugins.core.colors:colorcode.escape":
                return str(args[0]).replace("@", "@@")
            if name == "plugins.core.events:event.current.record.get":
                return {"plugin_id": stub.unloaded}
            if name == "plugins.core.events:event.current.name.get":
                return stub.current_event
            if name == "libs.api:caller.owner.get":
                return stub.caller
            if name == "libs.plugins.loader:plugin.id.is.valid":
                return str(args[0]).startswith("plugins.")
            if name == "plugins.core.commands:command.format":
                return f"#bp.{args[0].replace('plugins.', '')}.{args[1]}"
            if name == "libs.asynch:task.add":
                return asyncio.get_running_loop().create_task(args[0])
            return None

        return call


class _Stub:
    """Plugin stand-in with real containers and a recording api."""

    plugin_id = "plugins.core.web"

    def __init__(self, base: Path) -> None:
        self.settings: dict[str, Any] = {
            "enabled": True,
            "port": 0,
            "bindaddress": "127.0.0.1",
            "certfile": "",
            "keyfile": "",
            "publicurl": "",
            "sessionhours": 12,
            "clientdir": "",
        }
        self.caller = "plugins.test.caller"
        self.unloaded = ""
        self.current_event = ""
        self.added: dict[str, Any] = {}
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.pages = PageStore()
        self.routes = RouteTable()
        self.provider_listeners = ProviderListeners()
        self.logins = LoginTokens()
        self.sessions = SessionStore()
        self.server = WebServer()
        self.subscriptions = Subscriptions(
            self.server.sockets, lambda: self.routes, self.provider_listeners
        )
        self.command_calls = Calls(self.server.sockets, lambda *_a: {}, lambda text: [])
        self.cert: Any = None
        self._generation = 0
        self._restart_sequence = 0
        self._lock = asyncio.Lock()
        self.api = _Api(self, base)

    @property
    def port(self) -> int:
        return int(self.server.address.rsplit(":", 1)[1])


for _name in HELPERS:
    setattr(_Stub, _name, getattr(WebPlugin, _name))
_Stub._describe_cert = staticmethod(WebPlugin._describe_cert)  # type: ignore[attr-defined]


@pytest.fixture
async def stub(tmp_path: Path) -> Any:
    plugin = _Stub(tmp_path)
    yield plugin
    plugin.server.close()
    await plugin.server.wait_closed()


def status_text(plugin: Any) -> str:
    result = WebPlugin._command_status(plugin)
    assert result.success
    return "\n".join(result.message)


def test_settings_and_defaults(stub: Any) -> None:
    WebPlugin._phook_initialize(stub)
    assert stub.added == {
        "enabled": False,
        "port": 9998,
        "bindaddress": "127.0.0.1",
        "certfile": "",
        "keyfile": "",
        "publicurl": "",
        "sessionhours": 12,
        "clientdir": "",
    }


async def test_disabled_does_not_start_and_page_add_is_empty(stub: Any) -> None:
    stub.settings["enabled"] = False
    await stub._restart(0)
    assert not stub.server.running
    assert WebPlugin._api_web_page_add(stub, "plugins.x", "t", ["a"]) == ""
    assert "stopped" in status_text(stub)


async def test_default_bind_is_plain_http_on_loopback(stub: Any) -> None:
    await stub._restart(0)
    assert stub.server.running
    assert not stub.server.tls
    assert stub.server.address.startswith("127.0.0.1:")
    url = WebPlugin._api_web_page_add(stub, "plugins.x", "Title", ["@rhello"])
    assert url.startswith(f"http://127.0.0.1:{stub.settings['port']}/p/")
    token = url.rsplit("/", 1)[1]
    status, _, body = await http_get(stub.port, get_request(f"/p/{token}"))
    assert status == 200
    assert b"<span style='color:#cd0000'>hello</span>" in body
    assert len(token) >= 43


async def test_non_loopback_without_a_certificate_does_not_start(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    stub.settings["bindaddress"] = (
        "0.0.0.0"  # reason: the rule under test refuses a non-loopback bind
    )
    with caplog.at_level(logging.ERROR):
        await stub._restart(0)
    assert not stub.server.running
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors
    assert "loopback" in errors[0]
    assert "certfile" in errors[0]


async def test_only_one_of_certfile_and_keyfile_does_not_start(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    stub.settings["certfile"] = "c.pem"
    with caplog.at_level(logging.ERROR):
        await stub._restart(0)
    assert not stub.server.running
    assert any("both" in r.getMessage() for r in caplog.records)


async def test_a_missing_certificate_does_not_start(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    stub.settings["certfile"] = "no.pem"
    stub.settings["keyfile"] = "no.key"
    with caplog.at_level(logging.ERROR):
        await stub._restart(0)
    assert not stub.server.running
    assert any("certificate" in r.getMessage() for r in caplog.records)


async def test_a_port_in_use_is_logged_not_raised(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    await stub._restart(0)
    other: Any = _Stub(stub.api.BASEHOMEPATH)
    other.settings["port"] = stub.port
    with caplog.at_level(logging.ERROR):
        await other._restart(0)
    assert not other.server.running
    assert any("cannot listen" in r.getMessage() for r in caplog.records)


async def test_setup_b_loopback_plain_http_with_an_https_publicurl(stub: Any) -> None:
    stub.settings["publicurl"] = "https://x.ts.net/"
    await stub._restart(0)
    assert stub.server.running
    assert not stub.server.tls
    url = WebPlugin._api_web_page_add(stub, "plugins.x", "t", "text")
    assert url.startswith("https://x.ts.net/p/")
    status, _, _ = await http_get(stub.port, get_request("/p/" + url.rsplit("/", 1)[1]))
    assert status == 200
    assert f"{'Public url':<14}: https://x.ts.net/" in status_text(stub).splitlines()


async def test_ipv6_loopback_link_is_bracketed(stub: Any) -> None:
    stub.settings["bindaddress"] = "::1"
    stub.settings["port"] = 9998
    assert stub._base_url() == "http://[::1]:9998"


async def test_status_in_plain_mode(stub: Any) -> None:
    await stub._restart(0)
    WebPlugin._api_web_page_add(stub, "plugins.x", "t", "a")
    WebPlugin._api_web_page_add(stub, "plugins.x", "t", "b")
    text = status_text(stub)
    assert "running, plain http, on 127.0.0.1:" in text
    assert "Pages held    : 2" in text
    assert "Certificate" not in text


async def test_status_when_enabled_but_not_running(stub: Any) -> None:
    stub.settings["bindaddress"] = (
        "0.0.0.0"  # reason: the rule under test refuses a non-loopback bind
    )
    await stub._restart(0)
    assert "enabled but not running" in status_text(stub)


def _use_cert(stub: Any, make_cert: MakeCert, cn: str) -> tuple[Path, Path]:
    certfile, keyfile = make_cert(cn)
    stub.settings["certfile"] = certfile.name
    stub.settings["keyfile"] = keyfile.name
    return certfile, keyfile


@needs_openssl
async def test_tls_mode_serves_links_and_status_shows_the_certificate(
    stub: Any, make_cert: MakeCert
) -> None:
    certfile, _ = _use_cert(stub, make_cert, "bastproxy.test")
    await stub._restart(0)
    assert stub.server.running
    assert stub.server.tls
    url = WebPlugin._api_web_page_add(stub, "plugins.x", "t", "secure")
    assert url.startswith("https://127.0.0.1:")
    client = ssl.create_default_context(cafile=str(certfile))
    client.check_hostname = False
    client.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    status, _, body = await http_get(stub.port, get_request("/p/" + url.rsplit("/", 1)[1]), client)
    assert status == 200
    assert b"secure" in body
    text = status_text(stub)
    assert "running, TLS, on" in text
    assert "bastproxy.test" in text
    assert "expires" in text
    assert "Last reload" in text


@needs_openssl
async def test_reload_command(stub: Any, make_cert: MakeCert) -> None:
    result = WebPlugin._command_reload(stub)
    assert "not active" in result.message[0]
    _, keyfile = _use_cert(stub, make_cert, "bastproxy.test")
    await stub._restart(0)
    assert WebPlugin._command_reload(stub).message == ["certificate reloaded"]
    keyfile.write_text("not a key")
    result = WebPlugin._command_reload(stub)
    assert result.message[0].startswith("reload failed")
    assert "Last error" in status_text(stub)


async def test_restart_picks_up_a_changed_setting(stub: Any) -> None:
    await stub._restart(0)
    first = stub.server.address
    stub.settings["enabled"] = False
    await stub._restart(0)
    assert not stub.server.running
    stub.settings["enabled"] = True
    await stub._restart(0)
    assert stub.server.running
    assert stub.server.address.startswith("127.0.0.1:")
    assert first.startswith("127.0.0.1:")


async def test_schedule_restart_runs_in_a_queued_task(stub: Any) -> None:
    stub._schedule_restart()
    task_calls = [c for c in stub.calls if c[0] == "libs.asynch:task.add"]
    assert len(task_calls) == 1
    await asyncio.sleep(0.1)
    assert stub.server.running


async def test_restarts_queued_together_start_the_listener_once(stub: Any) -> None:
    starts: list[str] = []
    real_start = stub.server.start

    async def counting_start(*args: Any, **kwargs: Any) -> None:
        starts.append(str(stub.settings["bindaddress"]))
        await real_start(*args, **kwargs)

    stub.server.start = counting_start
    for _ in range(6):
        stub._schedule_restart()
    stub.settings["bindaddress"] = "127.0.0.2"
    await asyncio.sleep(0.2)
    assert starts == ["127.0.0.2"]
    assert stub.server.running
    assert stub.server.address.startswith("127.0.0.2:")


async def test_a_restart_scheduled_after_one_finished_still_restarts(stub: Any) -> None:
    stub._schedule_restart()
    await asyncio.sleep(0.1)
    first = stub.server.address
    stub.settings["enabled"] = False
    stub._schedule_restart()
    await asyncio.sleep(0.1)
    assert first
    assert not stub.server.running


async def test_unload_stops_a_pending_scheduled_restart(stub: Any) -> None:
    stub._schedule_restart()
    WebPlugin._phook_close_server(stub)
    await asyncio.sleep(0.1)
    assert not stub.server.running


async def test_unload_closes_the_listener(stub: Any) -> None:
    await stub._restart(0)
    port = stub.port
    WebPlugin._phook_close_server(stub)
    assert not stub.server.running
    assert stub._generation == 1
    await asyncio.sleep(0.05)
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", port)


async def test_a_queued_restart_exits_after_the_generation_bump(stub: Any) -> None:
    pending = stub._restart(stub._generation)
    WebPlugin._phook_close_server(stub)
    await pending
    assert not stub.server.running


@pytest.mark.parametrize("name", ["certfile", "keyfile", "clientdir"])
def test_path_setting_is_relative_to_the_home_directory(stub: Any, name: str) -> None:
    stub.settings[name] = "certs/value"
    result = stub._path(name)
    assert result == Path(stub.api.BASEHOMEPATH) / "certs/value"
    assert not result.is_relative_to(Path(stub.api.BASEDATAPATH))


@pytest.mark.parametrize("name", ["certfile", "keyfile", "clientdir"])
def test_absolute_path_setting_is_kept(stub: Any, name: str, tmp_path: Path) -> None:
    absolute = tmp_path / "elsewhere" / "x.pem"
    stub.settings[name] = str(absolute)
    assert stub._path(name) == absolute


def _ipv6_loopback_available() -> bool:
    import socket

    if not socket.has_ipv6:
        return False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False
    return True


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


needs_ipv6 = pytest.mark.skipif(
    not _ipv6_loopback_available(), reason="IPv6 loopback is not available"
)


@needs_ipv6
async def test_a_list_listens_on_both_families_on_one_port(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    stub.settings["bindaddress"] = "127.0.0.1,::1"
    # with a port of 0 asyncio picks a separate port per address, so use one fixed free port
    stub.settings["port"] = _free_port()
    with caplog.at_level(logging.INFO):
        await stub._restart(0)
    assert stub.server.running
    port = stub.port
    assert stub.server.address == f"127.0.0.1:{port}, [::1]:{port}"
    url = WebPlugin._api_web_page_add(stub, "plugins.x", "t", "text")
    token = url.rsplit("/", 1)[1]
    for host in ("127.0.0.1", "::1"):
        status, _, _ = await http_get(port, get_request(f"/p/{token}"), host=host)
        assert status == 200
    assert any(
        f"127.0.0.1:{port}, [::1]:{port}" in r.getMessage() and "listening" in r.getMessage()
        for r in caplog.records
    )
    assert f"on 127.0.0.1:{port}, [::1]:{port}" in status_text(stub)


async def test_a_single_address_is_unchanged(stub: Any) -> None:
    await stub._restart(0)
    assert stub.server.address == f"127.0.0.1:{stub.port}"
    assert "," not in stub.server.address


@needs_ipv6
async def test_a_single_ipv6_address_is_bracketed(stub: Any) -> None:
    stub.settings["bindaddress"] = "::1"
    await stub._restart(0)
    assert stub.server.address == f"[::1]:{stub.port}"


async def test_plain_http_with_a_mixed_list_is_refused(
    stub: Any, caplog: pytest.LogCaptureFixture
) -> None:
    stub.settings["bindaddress"] = (
        "127.0.0.1,0.0.0.0"  # reason: the rule under test refuses a non-loopback entry
    )
    with caplog.at_level(logging.ERROR):
        await stub._restart(0)
    assert not stub.server.running
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors
    assert "127.0.0.1, 0.0.0.0" in errors[0]
    assert "certfile" in errors[0]


async def test_base_url_uses_the_first_address(stub: Any) -> None:
    stub.settings["port"] = 9998
    stub.settings["bindaddress"] = "::1, 127.0.0.1"
    assert stub._base_url() == "http://[::1]:9998"
    stub.settings["bindaddress"] = "127.0.0.1,::1"
    assert stub._base_url() == "http://127.0.0.1:9998"


@pytest.mark.parametrize(
    ("public", "tls", "port", "expected"),
    [
        ("https://bastproxy.example.net", True, 9998, "https://bastproxy.example.net:9998"),
        ("https://h.example/sub/", True, 9998, "https://h.example:9998/sub"),
        ("https://h.example:8443", True, 9998, "https://h.example:8443"),
        ("https://h.example", False, 9998, "https://h.example"),
        ("https://h.example", True, 443, "https://h.example"),
        ("http://h.example", True, 80, "http://h.example"),
        ("https://[2001:db8::1]", True, 9998, "https://[2001:db8::1]:9998"),
        ("https://[2001:db8::1]:8443/x", True, 9998, "https://[2001:db8::1]:8443/x"),
    ],
)
def test_publicurl_gets_the_tls_port_only_when_it_names_none(
    stub: Any, public: str, tls: bool, port: int, expected: str
) -> None:
    stub.settings["publicurl"] = public
    stub.server.tls = tls
    stub.server.port = port
    assert stub._base_url() == expected


def test_the_allowed_origin_is_the_effective_base_url(stub: Any) -> None:
    stub.settings["publicurl"] = "https://bastproxy.example.net"
    stub.server.tls = True
    stub.server.port = 9998
    app = stub._build_app()
    assert list(app._allowed_origins()) == ["https://bastproxy.example.net:9998"]


def test_status_shows_the_effective_url(stub: Any) -> None:
    stub.settings["publicurl"] = "https://bastproxy.example.net"
    stub.server.tls = True
    stub.server.port = 9998
    lines = status_text(stub).splitlines()
    assert f"{'Public url':<14}: https://bastproxy.example.net" in lines
    assert f"{'Effective url':<14}: https://bastproxy.example.net:9998" in lines
