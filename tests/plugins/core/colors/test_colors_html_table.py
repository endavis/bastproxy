"""The xterm colour table, html output and width difference (#534)."""

from unittest.mock import MagicMock

from bastproxy.plugins.core.colors.libs._colors import COLORTABLE
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin


def to_html(text: str) -> str:
    result: str = ColorsPlugin._api_colorcode_to_html(MagicMock(), text)
    return result


def length_difference(text: str) -> int:
    result: int = ColorsPlugin._api_color_length_difference_get(MagicMock(), text)
    return result


def test_colortable_covers_exactly_0_to_255() -> None:
    assert {key for key in COLORTABLE if isinstance(key, int)} == set(range(256))


def test_colortable_cube_and_greyscale_ends() -> None:
    assert COLORTABLE[16] == (0, 0, 0)
    assert COLORTABLE[231] == (255, 255, 255)
    assert COLORTABLE[232] == (8, 8, 8)
    assert COLORTABLE[255] == (238, 238, 238)


def test_html_basic_color() -> None:
    assert to_html("@rred") == "<span style='color:#cd0000'>red</span>"


def test_html_xterm_foreground() -> None:
    assert to_html("@x075t") == "<span style='color:#5fafff'>t</span>"


def test_html_xterm_background() -> None:
    assert to_html("@z010t") == "<span style='background-color:#00ff00'>t</span>"


def test_html_foreground_and_background_share_a_span() -> None:
    assert to_html("@r@z010t") == "<span style='color:#cd0000;background-color:#00ff00'>t</span>"


def test_html_escape_and_default_colors_get_no_span() -> None:
    assert to_html("@@") == "@"
    assert to_html("@wn") == "n"
    assert to_html("@Dn") == "n"
    assert to_html("plain") == "plain"


def test_html_mixed_example_from_the_plan() -> None:
    assert to_html("@rred@x075xt@z010bg@wn") == (
        "<span style='color:#cd0000'>red</span>"
        "<span style='color:#5fafff'>xt</span>"
        "<span style='color:#5fafff;background-color:#00ff00'>bg</span>"
        "n"
    )


def test_html_w_clears_the_background() -> None:
    """@w is the general reset, so text after it has no background (#534)."""
    assert to_html("@z010bg@w plain") == "<span style='background-color:#00ff00'>bg</span> plain"


def test_html_colors_reset_on_each_line() -> None:
    assert to_html("@rone\ntwo") == "<span style='color:#cd0000'>one</span>\ntwo"


def test_length_difference() -> None:
    assert length_difference("@Rab@w") == 4
    assert length_difference("mail@@host") == 1
    assert length_difference("plain") == 0
