"""Tests for the plugins.core.utils value converters and value.verify (#428)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.utils.plugin._utils import (
    UtilsPlugin,
    to_bool,
    to_int,
    to_list,
    to_str,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        (" YES ", True),
        ("On", True),
        ("1", True),
        ("false", False),
        ("No", False),
        (" off", False),
        ("0", False),
        (True, True),
        (False, False),
        (1, True),
        (0, False),
    ],
)
def test_to_bool_accepts(value: Any, expected: bool) -> None:
    assert to_bool(value) is expected


@pytest.mark.parametrize("value", ["maybe", "n", "0.0", "", "2", 2, None])
def test_to_bool_rejects(value: Any) -> None:
    with pytest.raises(ValueError, match="bool"):
        to_bool(value)


def test_to_int() -> None:
    assert to_int(" 7 ") == 7
    assert to_int(5) == 5
    for bad in ("5x", True, 5.5, None):
        with pytest.raises(ValueError):
            to_int(bad)


def test_to_str_and_to_list() -> None:
    assert to_str(5) == "5"
    assert to_list((1, 2)) == [1, 2]
    source = [1]
    assert to_list(source) == source
    assert to_list(source) is not source
    with pytest.raises(ValueError):
        to_list("abc")


def _stub() -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.utils"
    stub.verify_color = lambda v: UtilsPlugin.verify_color(stub, v)
    stub.verify_miltime = lambda v: UtilsPlugin.verify_miltime(stub, v)
    stub.verify_timelength = lambda v: UtilsPlugin.verify_timelength(stub, v)

    def api(name: str) -> Any:
        if name == "plugins.core.colors:colorcode.is.valid":
            return lambda v: v in ("@R", "@x100")
        if name == "plugins.core.utils:timelength.to.seconds":
            return lambda v: 3600 if v == "1h" else 0
        raise AssertionError(name)

    stub.api = api
    return stub


def _verify(value: Any, vtype: Any) -> Any:
    return UtilsPlugin._api_value_verify(_stub(), value, vtype)


def test_verify_uses_converters() -> None:
    assert _verify("on", bool) is True
    assert _verify("5", int) == 5
    assert _verify(5, str) == "5"
    assert _verify((1,), list) == [1]


def test_verify_color() -> None:
    assert _verify("@R", "color") == "@R"
    with pytest.raises(ValueError):
        _verify("nope", "color")


def test_verify_miltime() -> None:
    assert _verify("0830", "miltime") == "0830"
    with pytest.raises(ValueError):
        _verify("2599", "miltime")


def test_verify_timelength() -> None:
    assert _verify("30", "timelength") == 30
    assert _verify("1h", "timelength") == 3600


def test_verify_custom_callable_and_unknown_type() -> None:
    assert _verify("3", float) == 3.0
    with pytest.raises(ValueError, match="unknown setting type"):
        _verify("x", "nonsense")
