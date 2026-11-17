"""wrap_cell and table.format take their widths from the colors tokenizer (#534)."""

from typing import Any

from bastproxy.plugins.core.utils.plugin._utils import UtilsPlugin, wrap_cell
from tests.plugins.core.utils.test_utils_output_table import LINELEN, make_utils_stub

_STUB = make_utils_stub()
_TOKENIZE = _STUB.api("plugins.core.colors:colorcode.to.tokens")
_STRIP = _STUB.api("plugins.core.colors:colorcode.strip")


def test_true_colour_sgr_counts_as_zero_width() -> None:
    assert wrap_cell("\x1b[38;2;1;2;3mabc", 3, _TOKENIZE) == ["\x1b[38;2;1;2;3mabc"]
    lines = wrap_cell("\x1b[38;2;1;2;3mabc def", 3, _TOKENIZE)
    assert [_STRIP(line) for line in lines] == ["abc", "def"]


def test_tilde_escape_is_one_column() -> None:
    assert wrap_cell("a@-b", 3, _TOKENIZE) == ["a@-b"]
    assert wrap_cell("a@-bc", 3, _TOKENIZE) == ["a@-b", "c"]


def test_table_cell_with_escaped_at_is_not_wider_than_it_looks() -> None:
    columns: list[dict[str, Any]] = [{"name": "Name", "key": "n"}]
    lines = UtilsPlugin._api_table_format(_STUB, "T", [{"n": "mail@@host"}], columns)
    assert columns[0]["width"] == 9
    assert all(len(_STRIP(line)) == LINELEN for line in lines[1:])
    assert any("mail@host" in _STRIP(line) for line in lines)
