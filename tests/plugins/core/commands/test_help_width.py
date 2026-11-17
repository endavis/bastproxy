"""Command help wraps to the requesting client's line length (#509)."""

from unittest.mock import MagicMock

from bastproxy.libs import argp
from bastproxy.plugins.core.colors.libs._tokenizer import strip_colorcodes
from bastproxy.plugins.core.colors.libs._tokenizer import tokenize as _tokenize
from bastproxy.plugins.core.commands.plugin._commands import _help_formatter

LONG = " ".join(["word"] * 40)


def _widest(width: int) -> int:
    stub = MagicMock()
    stub.api = lambda name: {"plugins.core.proxy:line.length.get": lambda: width}[name]
    parser = argp.ArgumentParser(description=LONG, prog="p")
    parser.formatter_class = lambda prog: _help_formatter(stub.api, prog)
    return max(len(ln) for ln in parser.format_help().splitlines() if "word" in ln)


def test_help_wraps_to_client_width() -> None:
    assert _widest(45) <= 45


def test_help_uses_linelen_without_naws() -> None:
    # line.length.get returns linelen for a client with no NAWS width
    assert _widest(110) > 73
    assert _widest(110) <= 110


def test_width_read_each_time_help_is_formatted() -> None:
    widths = iter([40, 100])
    stub = MagicMock()
    stub.api = lambda _n: lambda: next(widths)
    parser = argp.ArgumentParser(description=LONG, prog="p")
    parser.formatter_class = lambda prog: _help_formatter(stub.api, prog)
    first = max(len(ln) for ln in parser.format_help().splitlines() if "word" in ln)
    second = max(len(ln) for ln in parser.format_help().splitlines() if "word" in ln)
    assert first <= 40 < second <= 100


def test_help_formatter_passes_tokenizer_to_wrap() -> None:
    stub = MagicMock()
    stub.api = lambda _n: lambda: 40
    text = "@Gone two three four five six seven eight nine ten@w"

    def tokenize(value: str) -> list[tuple[str, str]]:
        return [(t.raw, t.visible) for t in _tokenize(value)]

    formatter = _help_formatter(stub.api, "p", tokenize=tokenize)
    lines = formatter._split_lines(text, 40)
    assert [strip_colorcodes(ln) for ln in lines] == [
        "one two three four five six seven eight",
        "nine ten",
    ]
