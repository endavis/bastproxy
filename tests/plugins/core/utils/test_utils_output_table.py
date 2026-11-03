"""Tests for plugins.core.utils:convert.data.to.output.table (#93)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin

LINELEN = 60
SUB_COLOR = "@C"


def make_utils_stub() -> MagicMock:
    """Build a stub utils plugin wired to the real colors and cap.line code."""
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, setting: LINELEN if setting == "linelen" else SUB_COLOR
        if name == "plugins.core.colors:colorcode.strip":
            return lambda text: ColorsPlugin._api_colorcode_strip(colors, text)
        if name == "plugins.core.commands:format.header":
            return lambda text, color, line_length: [f"HEADER {text} {color} {line_length}"]
        if name == "plugins.core.utils:cap.line":
            return lambda *a, **k: UtilsPlugin._api_cap_line(stub, *a, **k)
        raise AssertionError(name)

    stub.api = api
    colors.api = lambda name: {
        "plugins.core.colors:ansicode.to.string": lambda color, data: (
            ColorsPlugin._api_ansicode_to_string(colors, color, data)
        ),
        "plugins.core.colors:ansicode.strip": lambda text: ColorsPlugin._api_ansicode_strip(
            colors, text
        ),
        "plugins.core.colors:colorcode.to.ansicode": lambda text: (
            ColorsPlugin._api_colorcode_to_ansicode(colors, text)
        ),
    }[name]
    return stub


def legacy_table(stub: MagicMock, table_name: str, data: list[dict], columns: list[dict]) -> list:
    """Reproduce the pre-#93 algorithm (len(str()) widths, str.format padding)."""
    temp = [{c["key"]: c["name"] for c in columns}, *data]
    for c in columns:
        c["width"] = max(len(str(i[c["key"]])) for i in temp)
    template = f" {SUB_COLOR}|@w ".join(
        "{" + c["key"] + ":<" + str(c["width"]) + "}" for c in columns
    )
    sub = template.format(**{c["key"]: c["name"] for c in columns})
    lines = [template.format(**i) for i in data]
    ll = LINELEN
    cap = stub.api("plugins.core.utils:cap.line")
    rule = "-" * (ll - 2)
    return [
        f"HEADER {table_name} {SUB_COLOR} {ll}",
        cap(sub, "|", color=SUB_COLOR, line_length=ll),
        cap(rule, "+", color=SUB_COLOR, line_length=ll, space=False, fullcolor=True),
        *[cap(x, "|", color=SUB_COLOR, line_length=ll) for x in lines],
        cap(rule, "+", color=SUB_COLOR, line_length=ll, space=False, fullcolor=True),
    ]


def test_uncolored_output_is_unchanged() -> None:
    """Without color codes the output is identical to the old algorithm."""
    stub = make_utils_stub()
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Vers", "key": "v"}]
    data = [{"n": "alpha", "v": 1}, {"n": "be", "v": 22}]

    expected = legacy_table(stub, "T", data, [dict(c) for c in columns])
    result = UtilsPlugin._api_convert_data_to_output_table(stub, "T", data, columns)

    assert result == expected


def test_colored_cells_are_aligned() -> None:
    """Color codes do not count toward width, so columns still line up."""
    stub = make_utils_stub()
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Vers", "key": "v"}]
    data = [{"n": "@x075alpha", "v": "@x0751"}, {"n": "beta", "v": "2"}]

    result = UtilsPlugin._api_convert_data_to_output_table(stub, "T", data, columns)

    strip = stub.api("plugins.core.colors:colorcode.strip")
    rows = [strip(line) for line in result[1:]]
    assert rows[0].index("|", 3) == rows[2].index("|", 3) == rows[3].index("|", 3)
    assert columns[0]["width"] == 5
    assert columns[1]["width"] == 4
