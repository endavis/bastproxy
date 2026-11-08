"""Tests for `APIItem.detail` and `api.list.formatted` robustness (issue #200)."""

from __future__ import annotations

import subprocess
import sys
from functools import lru_cache

from bastproxy.libs.api import API


def _documented_percent() -> str:
    """Return 100% of %(name)s via %(cmdname)s at %(api_location)s.

    Returns:
        A string.

    """
    return "x"


class _Cached:
    """Holder for an lru_cache-wrapped method."""

    @lru_cache(maxsize=4)
    def cached(self, value: str) -> str:
        """Return the value."""
        return value


class TestDetailDocstring:
    """The docstring substitution handles literal percent signs."""

    def test_literal_percent_and_placeholders(self) -> None:
        """A literal % is kept and the placeholders are substituted."""
        api = API(owner_id="test_detail_owner")
        api.add("detailtest", "pct:sub", _documented_percent, description="pct")
        item = api.get("detailtest:pct:sub")
        lines = item.detail()
        text = "\n".join(lines)
        assert "100% of detailtest via pct:sub at detailtest:pct:sub." in text
        assert "%(" not in text

    def test_lru_cache_wrapped_function(self) -> None:
        """An lru_cache-wrapped function can be detailed, with source."""
        holder = _Cached()
        api = API(owner_id="test_detail_owner")
        api.add("detailtest", "cached", holder.cached, description="cached")
        item = api.get("detailtest:cached")
        lines = item.detail(show_function_code=True)
        text = "\n".join(lines)
        assert "def cached" in text
        assert "value" in text


class TestListFormattedEmptyDescription:
    """`api.list.formatted` tolerates an API with no description."""

    def test_empty_description(self) -> None:
        """No IndexError when the description list is empty."""
        api = API(owner_id="test_detail_owner")
        api.add("emptydesc", "n", lambda: 1)
        lines = api("libs.api:api.list.formatted")("emptydesc")
        assert any("emptydesc:n" in line for line in lines)


_BOOT_SCRIPT = """
from bastproxy.libs.api import API
from bastproxy.libs.plugins.loader import PluginLoader

PluginLoader().load_plugins_on_startup()
assert any("fuzzy" in name for name in API._class_api)
failures = []
for name, item in list(API._class_api.items()):
    for show_code in (False, True):
        try:
            item.detail(show_function_code=show_code)
        except Exception as exc:
            failures.append(f"{name} show_function_code={show_code}: {exc!r}")
print("\\n".join(failures))
raise SystemExit(1 if failures else 0)
"""


def test_detail_on_every_registered_api() -> None:
    """`detail` (with and without source) works on every class-level API item.

    Runs in a fresh interpreter: other tests load and unload plugins in-process,
    which leaves the plugin loader unable to boot the full set again.
    """
    result = subprocess.run(
        [sys.executable, "-c", _BOOT_SCRIPT],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
