"""The web client bundle served from the clientdir setting (#846)."""

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.core.web.libs import _client
from bastproxy.plugins.core.web.libs._client import CLIENT_TYPES, read_client_file
from bastproxy.plugins.core.web.libs._http import CLIENT_CSP, CSP
from bastproxy.plugins.core.web.libs._store import CLIENT_SEGMENT, RouteTable
from bastproxy.plugins.core.web.plugin._web import WebPlugin

from .conftest import http_get
from .test_providers import add as add_provider
from .test_routes import Env, noop  # reason: reuse the fixture
from .test_routes import env as env
from .test_web_plugin import stub as stub  # reason: reuse the fixture

needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="creating symlinks needs privileges on Windows"
)


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(b"<html>index</html>")
    (root / "assets" / "app.js").write_bytes(b"console.log(1)")
    (tmp_path / "secret.js").write_bytes(b"secret")
    return root


# ---- the resolver ----


def test_empty_rest_serves_the_index(bundle: Path) -> None:
    assert read_client_file(bundle, "") == (b"<html>index</html>", CLIENT_TYPES[".html"])


@pytest.mark.parametrize("suffix", sorted(CLIENT_TYPES))
def test_each_type_has_its_content_type(bundle: Path, suffix: str) -> None:
    (bundle / f"f{suffix}").write_bytes(b"x")
    assert read_client_file(bundle, f"f{suffix}") == (b"x", CLIENT_TYPES[suffix])


def test_the_content_types_are_exact() -> None:
    assert CLIENT_TYPES == {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".woff2": "font/woff2",
    }


def test_a_nested_file_is_served(bundle: Path) -> None:
    assert read_client_file(bundle, "assets/app.js") == (
        b"console.log(1)",
        "text/javascript; charset=utf-8",
    )


@pytest.mark.parametrize(
    "rest",
    [
        "..",
        "../x.js",
        "a/../../x.js",
        "../secret.js",
        ".",
        ".hidden.js",
        "/etc/passwd.js",
        "a//b.js",
        "a\\b.js",
        "%2e%2e/x.js",
        "assets/",
        "assets",
        "x.txt",
        "x.map",
        "x",
        "missing.js",
    ],
)
def test_a_bad_name_is_refused(bundle: Path, rest: str) -> None:
    (bundle / "x.txt").write_bytes(b"t")
    (bundle / "x.map").write_bytes(b"m")
    (bundle / ".hidden.js").write_bytes(b"h")
    assert read_client_file(bundle, rest) is None


def test_an_oversized_file_is_refused_and_logged(
    bundle: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(_client, "MAX_CLIENT_FILE", 4)
    (bundle / "big.js").write_bytes(b"12345")
    (bundle / "ok.js").write_bytes(b"1234")
    with caplog.at_level(logging.WARNING):
        assert read_client_file(bundle, "big.js") is None
    assert "big.js" in caplog.text
    assert read_client_file(bundle, "ok.js") is not None


def test_a_missing_or_non_directory_base_gives_none(tmp_path: Path) -> None:
    assert read_client_file(tmp_path / "nope", "") is None
    plain = tmp_path / "file"
    plain.write_bytes(b"x")
    assert read_client_file(plain, "") is None


@needs_symlinks
def test_a_symlink_that_leaves_the_directory_is_refused(bundle: Path, tmp_path: Path) -> None:
    (bundle / "link.js").symlink_to(tmp_path / "secret.js")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.js").write_bytes(b"o")
    (bundle / "dirlink").symlink_to(outside, target_is_directory=True)
    assert read_client_file(bundle, "link.js") is None
    assert read_client_file(bundle, "dirlink/o.js") is None


@needs_symlinks
def test_a_symlink_inside_the_directory_is_served(bundle: Path) -> None:
    (bundle / "alias.js").symlink_to(bundle / "assets" / "app.js")
    assert read_client_file(bundle, "alias.js") == (
        b"console.log(1)",
        "text/javascript; charset=utf-8",
    )


# ---- over HTTP ----


async def test_a_session_gets_the_bundle_with_the_client_policy(env: Env, bundle: Path) -> None:
    env.app._client_dir = lambda: bundle
    sid = await env.login()
    status, headers, body = await env.get("/webclient/", sid)
    assert status == 200
    assert body == b"<html>index</html>"
    assert headers["content-security-policy"] == CLIENT_CSP
    assert CLIENT_CSP != CSP
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    status, _, body = await env.get("/webclient/assets/app.js", sid)
    assert (status, body) == (200, b"console.log(1)")


async def test_no_session_is_401_with_the_default_policy(env: Env, bundle: Path) -> None:
    env.app._client_dir = lambda: bundle
    status, headers, body = await env.get("/webclient/")
    assert status == 401
    assert headers["content-security-policy"] == CSP
    assert b"index" not in body


async def test_an_unset_or_missing_dir_is_404_with_and_without_a_session(
    env: Env, tmp_path: Path
) -> None:
    sid = await env.login()
    for directory in (None, tmp_path / "missing"):
        env.app._client_dir = lambda directory=directory: directory  # type: ignore[misc]
        assert (await env.get("/webclient/", sid))[0] == 404
        assert (await env.get("/webclient/"))[0] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/webclient/..",
        "/webclient/../secret.js",
        "/webclient/%2e%2e/secret.js",
        "/webclient/%252e%252e/secret.js",
        "/webclient//etc/passwd",
        "/webclient/assets",
        "/webclient/assets/",
        "/webclient/nothing.js",
    ],
)
async def test_raw_traversal_is_404_with_the_default_policy(
    env: Env, bundle: Path, path: str
) -> None:
    env.app._client_dir = lambda: bundle
    sid = await env.login()
    status, headers, body = await env.get(path, sid)
    assert status == 404
    assert headers["content-security-policy"] == CSP
    assert b"secret" not in body


async def test_a_bare_prefix_is_404(env: Env, bundle: Path) -> None:
    env.app._client_dir = lambda: bundle
    sid = await env.login()
    assert (await env.get("/webclient", sid))[0] == 404


async def test_a_post_is_405(env: Env, bundle: Path) -> None:
    env.app._client_dir = lambda: bundle
    raw = b"POST /webclient/ HTTP/1.1\r\nHost: x\r\n\r\n"
    status, headers, _ = await http_get(env.port, raw)
    assert status == 405
    assert headers["content-security-policy"] == CSP


async def test_other_pages_keep_the_default_policy(env: Env, bundle: Path) -> None:
    env.app._client_dir = lambda: bundle
    token = env.app.pages.add("owner", "Title", b"<p>hi</p>")
    env.add(noop)
    sid = await env.login()
    paths = ["/", "/test/web/page", "/static/table.js", f"/p/{token}"]
    for path in paths:
        status, headers, _ = await env.get(path, sid)
        assert status == 200, path
        assert headers["content-security-policy"] == CSP, path


# ---- the reserved segment ----


def test_the_segment_is_webclient() -> None:
    assert CLIENT_SEGMENT == "webclient"


def test_a_route_under_the_segment_is_refused() -> None:
    with pytest.raises(ValueError, match="reserved"):
        RouteTable().add("plugins.webclient.x", "a", noop, "t")


def test_a_provider_under_the_segment_is_refused() -> None:
    with pytest.raises(ValueError, match="reserved"):
        add_provider(RouteTable(), owner="plugins.webclient")


def test_the_route_api_returns_none_for_the_segment(stub: Any) -> None:
    result = WebPlugin._api_web_route_add(stub, "plugins.webclient.x", "a", noop, "t")
    assert result is None


# ---- the plugin ----


def test_client_dir_is_none_when_empty(stub: Any) -> None:
    assert stub._client_dir() is None


def test_client_dir_is_relative_to_the_data_directory(stub: Any) -> None:
    stub.settings["clientdir"] = "web/dist"
    assert stub._client_dir() == Path(stub.api.BASEDATAPATH) / "web/dist"


def test_client_dir_keeps_an_absolute_path(stub: Any, tmp_path: Path) -> None:
    absolute = tmp_path / "elsewhere"
    stub.settings["clientdir"] = str(absolute)
    assert stub._client_dir() == absolute


async def test_build_app_passes_the_client_dir(stub: Any, tmp_path: Path) -> None:
    stub.settings["clientdir"] = str(tmp_path)
    stub.api = _AppApi(stub.api)
    app = stub._build_app()
    assert app._client_dir() == tmp_path


class _AppApi:
    """Wrap the stub api so the colour converter lookup works in _build_app."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __call__(self, name: str) -> Any:
        return self._inner(name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
