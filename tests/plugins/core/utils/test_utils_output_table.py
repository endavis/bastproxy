"""Tests for plugins.core.utils:table.format (#93)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin

LINELEN = 60
SUB_COLOR = "@C"


def make_utils_stub() -> MagicMock:
    """Build a stub utils plugin wired to the real colors and line.cap code."""
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, setting: LINELEN if setting == "linelen" else SUB_COLOR
        if name == "plugins.core.proxy:line.length.get":
            return lambda: LINELEN
        if name == "plugins.core.colors:colorcode.strip":
            return lambda text: ColorsPlugin._api_colorcode_strip(colors, text)
        if name == "plugins.core.colors:colorcode.to.tokens":
            return lambda text: ColorsPlugin._api_colorcode_to_tokens(colors, text)
        if name == "plugins.core.commands:header.format":
            return lambda text, color, line_length: [f"HEADER {text} {color} {line_length}"]
        if name == "plugins.core.utils:line.cap":
            return lambda *a, **k: UtilsPlugin._api_line_cap(stub, *a, **k)
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
    cap = stub.api("plugins.core.utils:line.cap")
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
    result = UtilsPlugin._api_table_format(stub, "T", data, columns)

    assert result == expected


def test_colored_cells_are_aligned() -> None:
    """Color codes do not count toward width, so columns still line up."""
    stub = make_utils_stub()
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Vers", "key": "v"}]
    data = [{"n": "@x075alpha", "v": "@x0751"}, {"n": "beta", "v": "2"}]

    result = UtilsPlugin._api_table_format(stub, "T", data, columns)

    strip = stub.api("plugins.core.colors:colorcode.strip")
    rows = [strip(line) for line in result[1:]]
    assert rows[0].index("|", 3) == rows[2].index("|", 3) == rows[3].index("|", 3)
    assert columns[0]["width"] == 5
    assert columns[1]["width"] == 4


def _bar_positions(line: str) -> list[int]:
    return [i for i, ch in enumerate(line) if ch == "|"]


def _render(
    data: list[dict[str, Any]], columns: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    stub = make_utils_stub()
    result = UtilsPlugin._api_table_format(stub, "T", data, columns)
    strip = stub.api("plugins.core.colors:colorcode.strip")
    return result, [strip(line) for line in result[1:]]


def _assert_aligned(plain: list[str]) -> None:
    """Every line is as wide as the line length and the borders line up."""
    assert {len(line) for line in plain} == {LINELEN}
    rows = [line for line in plain if not line.startswith("+")]
    assert len({tuple(_bar_positions(row)[1:-1]) for row in rows}) == 1


def test_one_long_cell_wraps_inside_its_column() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Info", "key": "i"}]
    data = [{"n": "alpha", "i": "one two three four five six seven eight nine ten eleven"}]

    result, plain = _render(data, columns)

    _assert_aligned(plain)
    assert result[0] == f"HEADER T {SUB_COLOR} {LINELEN}"
    body = plain[2:-1]
    assert len(body) > 1
    assert body[0].startswith("| alpha")
    assert body[1].startswith("|       |")  # continuation row: blank padded name cell


def test_several_long_cells_row_height_is_the_tallest() -> None:
    columns: list[dict[str, Any]] = [
        {"name": "A", "key": "a"},
        {"name": "B", "key": "b"},
        {"name": "C", "key": "c"},
    ]
    data = [
        {
            "a": "aaa bbb ccc ddd eee fff ggg",
            "b": "short",
            "c": "one two three four five six seven eight nine ten",
        },
        {"a": "x", "b": "y", "c": "z"},
    ]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    body = plain[2:-1]
    assert body[-1].split("|")[1].strip() == "x"
    assert len(body) == 4  # the tallest cell (C, 3 lines) sets the row height, plus row 2
    assert any("ten" in line for line in body)


def test_cell_without_spaces_is_split() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Val", "key": "v"}]
    data = [{"n": "alpha", "v": "x" * 90}]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    assert "".join(line.split("|")[2].strip() for line in plain[2:-1]) == "x" * 90


def test_colored_cells_survive_wrapping() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Info", "key": "i"}]
    data = [{"n": "@x075alpha", "i": "@Rone two three four five six seven eight nine ten eleven@w"}]

    result, plain = _render(data, columns)

    _assert_aligned(plain)
    assert sum(line.count("@R") for line in result) >= 2  # carried onto continuation lines


def test_fitting_headers_do_not_wrap() -> None:
    columns: list[dict[str, Any]] = [
        {"name": "A Long Header Name", "key": "a"},
        {"name": "Another Header", "key": "b"},
    ]
    data = [{"a": "word " * 12, "b": "word " * 12}]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    assert "A Long Header Name" in plain[0]
    assert "Another Header" in plain[0]


def test_headers_wrap_when_nothing_else_makes_the_table_fit() -> None:
    columns: list[dict[str, Any]] = [
        {"name": "Term Type", "key": "a"},
        {"name": "View Only", "key": "b"},
        {"name": "Connected For", "key": "c"},
        {"name": "Client Address", "key": "d"},
        {"name": "Idle Time", "key": "e"},
    ]
    data = [dict.fromkeys("abcde", "x")]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    rule = next(i for i, line in enumerate(plain) if line.startswith("+"))
    assert rule > 1  # the header row is several lines tall
    header = " ".join(plain[:rule])
    for word in ("Term", "Type", "View", "Only", "Connected", "Address"):
        assert word in header
    assert not any(line.startswith("+") for line in plain[:rule])


def test_header_words_split_when_even_header_words_cannot_fit() -> None:
    columns: list[dict[str, Any]] = [
        {"name": "Alphabetical", "key": "a"},
        {"name": "Bibliography", "key": "b"},
        {"name": "Cartography", "key": "c"},
        {"name": "Demography", "key": "d"},
        {"name": "Etymology", "key": "e"},
    ]
    data = [dict.fromkeys("abcde", "x")]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    assert "Alphabetical" not in "\n".join(plain)


def test_table_grows_only_when_one_column_per_cell_cannot_fit() -> None:
    columns = [{"name": "H", "key": str(i)} for i in range(30)]
    data = [{str(i): "x" for i in range(30)}]

    _, plain = _render(data, columns)

    width = 30 + 3 * 29 + 4
    assert width > LINELEN
    assert {len(line) for line in plain} == {width}


def test_split_word_in_a_table_breaks_after_punctuation() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}, {"name": "Plugin", "key": "p"}]
    data = [{"n": "alpha", "p": "plugins.core.clients.thing.more.and.more.and.more.stuff.here"}]

    _, plain = _render(data, columns)

    _assert_aligned(plain)
    body = plain[2:-1]
    assert body[0].split("|")[2].strip().endswith(".")


def test_line_cap_default_width_comes_from_line_length_api() -> None:
    stub = make_utils_stub()
    stub_api = stub.api
    stub.api = lambda name: (
        (lambda: 30) if name == "plugins.core.proxy:line.length.get" else stub_api(name)
    )
    assert len(UtilsPlugin._api_line_cap(stub, "x")) == 30
