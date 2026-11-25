"""The one static script (#424)."""

import re
from importlib import resources

import pytest

from bastproxy.plugins.core.web.libs._http import SECURITY_HEADERS

from .test_routes import Env
from .test_routes import env as env  # reason: reuse the fixture

FORBIDDEN = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "eval",
    "Function(",
    "fetch",
    "XMLHttpRequest",
)


def script_text() -> str:
    resource = resources.files("bastproxy.plugins.core.web") / "static" / "table.js"
    return resource.read_text(encoding="utf-8")


@pytest.mark.parametrize("word", FORBIDDEN)
def test_the_script_does_not_use_forbidden_calls(word: str) -> None:
    assert word not in script_text()


def test_the_script_leaves_multi_page_tables_alone() -> None:
    text = script_text()
    assert "data-pages" in text
    assert "preventDefault" in text
    assert "textContent" in text
    assert re.search(r"createElement\(", text)


async def test_the_script_is_served_without_a_session_with_the_security_headers(env: Env) -> None:
    status, headers, body = await env.get("/static/table.js")
    assert status == 200
    assert headers["content-type"] == "text/javascript; charset=utf-8"
    for name, value in SECURITY_HEADERS:
        assert headers[name.lower()] == value
    assert body == script_text().encode("utf-8")


@pytest.mark.parametrize("path", ["/static/other.js", "/static/", "/static", "/static/table.js/x"])
async def test_any_other_static_path_is_404(env: Env, path: str) -> None:
    sid = await env.login()
    assert (await env.get(path))[0] == 404
    assert (await env.get(path, sid))[0] == 404
