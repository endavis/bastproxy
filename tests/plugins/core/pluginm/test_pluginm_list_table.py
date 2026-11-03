"""Tests for the plugin list table built by the plugin manager (#93)."""

import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin
from tests.plugins.core.utils.test_utils_output_table import make_utils_stub

INFOS = {
    "plugins.core.alpha": SimpleNamespace(
        plugin_id="plugins.core.alpha",
        name="Alpha",
        author="Bast",
        version=1,
        purpose="does alpha things",
        is_required=True,
    ),
    "plugins.test.beta": SimpleNamespace(
        plugin_id="plugins.test.beta",
        name="Beta",
        author="Someone",
        version=12,
        purpose="does beta",
        is_required=False,
    ),
}


def _stub() -> MagicMock:
    utils = make_utils_stub()
    stub = MagicMock()

    def api(name: str) -> Any:
        if name == "libs.plugins.loader:get.plugin.info":
            return INFOS.__getitem__
        if name == "plugins.core.utils:convert.data.to.output.table":
            return lambda *a, **k: UtilsPlugin._api_convert_data_to_output_table(utils, *a, **k)
        raise AssertionError(name)

    stub.api = api
    return stub


def test_list_has_all_columns_and_required_legend() -> None:
    """Rows carry every column; required plugins are colored and legend added."""
    msg = PluginManager._command_helper_format_plugin_list(_stub(), list(INFOS), "Plugins")

    text = "\n".join(msg)
    for word in ("Id/Location", "Name", "Author", "Vers", "Purpose", "Alpha", "Beta", "12"):
        assert word in text
    assert "@x075plugins.core.alpha" in text
    assert "@x075Alpha" in text
    assert "plugins.test.beta" in text
    assert "@x075plugins.test.beta" not in text
    assert msg[-1] == "* @x075Required plugins appear in this color@w"


def test_no_legend_when_disabled_or_none_required() -> None:
    """The legend is omitted on request or when no plugin is required."""
    stub = _stub()
    assert "Required" not in "".join(
        PluginManager._command_helper_format_plugin_list(
            stub, list(INFOS), required_color_line=False
        )
    )
    assert "Required" not in "".join(
        PluginManager._command_helper_format_plugin_list(stub, ["plugins.test.beta"])
    )


def test_full_listing_is_one_aligned_table() -> None:
    """All packages render in one table: one title, one column header, aligned rows."""
    stub = _stub()
    packages = {
        "plugins.core": ["plugins.core.alpha"],
        "plugins.debug": [],
        "plugins.test": ["plugins.test.beta"],
    }
    stub.api = _wrap_api(stub.api, packages)
    stub._command_helper_format_plugin_list = lambda *a, **k: (
        PluginManager._command_helper_format_plugin_list(stub, *a, **k)
    )

    msg = PluginManager._build_all_plugins_message(stub)

    text = "\n".join(msg)
    print(text)
    assert text.count("Id/Location") == 1
    assert text.count("Plugins") == 1
    assert "(blank)" not in text
    assert "@x075plugins.core.alpha" in text
    assert "plugins.test.beta" in text
    assert "@x075plugins.test.beta" not in text
    assert "Required plugins appear" not in text
    rows = [line for line in msg if "plugins." in line]
    assert len(rows) == 2
    bars = [[i for i, ch in enumerate(_strip(r)) if ch == "|"] for r in rows]
    assert bars[0][1:] == bars[1][1:]
    assert msg[0].startswith("HEADER Plugins")
    assert "Id/Location" in msg[1]


def _strip(line: str) -> str:
    return re.sub(r"@x\d{3}|@[a-zA-Z]", "", line)


def _wrap_api(inner: Any, packages: dict[str, list[str]]) -> Any:
    def api(name: str) -> Any:
        if name == "libs.plugins.loader:get.packages.list":
            return lambda: list(packages)
        if name == "libs.plugins.loader:get.plugins.in.package":
            return packages.__getitem__
        return inner(name)

    return api
