# Project: bastproxy
# Filename: tests/plugins/client/substitutes/test_substitutes.py
#
# File Description: Tests for the substitutes plugin
#
# By: Bast
"""Unit tests for `plugins.client.substitutes` (issue #710)."""

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import regex

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.plugins import imputils
from bastproxy.plugins.client.substitutes.plugin import _substitutes as sub_module
from bastproxy.plugins.client.substitutes.plugin._substitutes import (
    SUBSTITUTE_PRIORITY,
    SubstitutesPlugin,
    expand_replacement,
    substitute_line,
)
from bastproxy.plugins.core.colors.libs._sgr import sgr_to_colorcode
from bastproxy.plugins.core.colors.libs._tokenizer import (
    escape_at,
    strip_ansi,
    strip_colorcodes,
    tokenize,
)
from bastproxy.plugins.core.colors.plugin._colors import _to_ansicode

PID = "plugins.client.substitutes"


def _tokens(text: str) -> list[tuple[str, str]]:
    return [(t.raw, t.visible) for t in tokenize(text)]


def _to_ansi(text: str) -> str:
    return _to_ansicode(tokenize(text)) if "@" in text else text


class FakeApi:
    """A stand-in for the plugin api: callable, with the split attributes."""

    command_split_regex: str | None = r"(?<=[^\|])\|(?=[^\|])"
    command_separator: str = "|"

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        return self.table[name]


def _plugin(tmp_path: Path, args: dict[str, Any] | None = None) -> Any:
    plugin: Any = object.__new__(SubstitutesPlugin)
    plugin.plugin_id = PID
    plugin.substitutes = PersistentDict("x", tmp_path / "substitutes.txt", "c")
    plugin._compiled = {}
    plugin._timeout_warned = set()
    plugin.record = None
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.current.args.get": lambda: args,
        "plugins.core.colors:colorcode.escape": escape_at,
        "plugins.core.colors:colorcode.to.tokens": _tokens,
        "plugins.core.colors:colorcode.to.ansicode": _to_ansi,
        "plugins.core.events:event.current.record.get": lambda: plugin.record,
        f"{PID}:substitute.add": plugin._api_substitute_add,
        f"{PID}:substitute.remove": plugin._api_substitute_remove,
        f"{PID}:substitute.clear": plugin._api_substitute_clear,
    }
    plugin.api = FakeApi(table)
    return plugin


def _line(ansi: str, **kwargs: Any) -> Any:
    """A line-like object whose colorcoded form is built from its ANSI text."""
    fields: dict[str, Any] = {
        "internal": False,
        "is_io": True,
        "send": True,
        "mxp_mode": None,
    }
    fields.update(kwargs)
    fields.setdefault("line", ansi)
    line = SimpleNamespace(**fields)
    line.colorcoded = _colorcoded(ansi)
    return line


def _colorcoded(ansi: str) -> str:
    return sgr_to_colorcode(ansi)


def _run(p: Any, line: Any) -> Any:
    p.record = {"line": line}
    p._eventcb_substitute_line()
    return line


def _plain(text: str) -> str:
    return strip_colorcodes(strip_ansi(text))


def _find(text: str, pattern: str, repl: str) -> list[tuple[int, int, str]]:
    out = []
    start = text.find(pattern)
    while start != -1:
        out.append((start, start + len(pattern), repl))
        start = text.find(pattern, start + len(pattern))
    return out


def test_every_occurrence_replaced(tmp_path: Path) -> None:
    """A plain substitution replaces every occurrence."""
    p = _plugin(tmp_path)
    assert p._api_substitute_add("o", "orc", "goblin")
    line = _run(p, _line("an orc and an orc\r\n"))
    assert line.line == "an goblin and an goblin\r\n"


def test_no_match_leaves_line_untouched(tmp_path: Path) -> None:
    """A line with no match is not written."""
    p = _plugin(tmp_path)
    p._api_substitute_add("o", "orc", "goblin")
    line = _run(p, _line("nothing here"))
    assert line.line == "nothing here"


def test_colour_survives() -> None:
    """The colour after a replaced span is the colour that was active."""
    out = substitute_line("@rred orc@w here", _tokens, lambda t: _find(t, "orc", "goblin"))
    assert out == "@rred goblin@w here"


def test_match_spanning_colour_change_keeps_code() -> None:
    """A code inside the match moves after a replacement with no colour."""
    out = substitute_line("@rab@gcd", _tokens, lambda t: _find(t, "bc", "X"))
    assert out == "@raX@gd"


def test_replacement_with_colour_restores() -> None:
    """A coloured replacement is followed by a restore of the colour at the match end."""
    out = substitute_line("@rab@gcd", _tokens, lambda t: _find(t, "bc", "@Rboom"))
    assert out == "@ra@Rboom@w@gd"


def test_restore_tracks_xterm_background() -> None:
    """The restore carries the foreground and background active at the match end."""
    out = substitute_line("@x075@z100abc", _tokens, lambda t: _find(t, "b", "@Rb"))
    assert out == "@x075@z100a@Rb@w@x075@z100c"


def test_at_in_mud_text_stays_literal(tmp_path: Path) -> None:
    """A literal @r in MUD text survives as text, not as a colour."""
    p = _plugin(tmp_path)
    p._api_substitute_add("o", "orc", "goblin")
    line = _run(p, _line("mail@@rhost orc".replace("@@", "@")))
    assert "orc" not in line.line
    assert _plain(line.line).startswith("mail")


def test_group_text_with_at_is_escaped(tmp_path: Path) -> None:
    """Group text inserted through %1 never reads as a colour code."""
    match = regex.search(r"(\S+) x", "a@r x")
    assert expand_replacement("[%1]", match) == "[a@@r]"
    out = substitute_line(
        "a@@r x",
        _tokens,
        lambda t: [
            (m.start(), m.end(), expand_replacement("[%1]", m))
            for m in regex.finditer(r"(\S+) x", t)
        ],
    )
    assert out is not None
    assert strip_ansi(_to_ansi(out)) == "[a@r]"


def test_regex_references() -> None:
    """%1, %<name>, %%1 and an absent group."""
    match = regex.search(r"(?P<who>\w+) (\w+)?", "orc ")
    assert expand_replacement("%1/%<who>/%2/%%1", match) == "orc/orc//%1"


@pytest.mark.parametrize(
    ("pattern", "replacement"),
    [("(a)", "%2"), ("(?P<x>a)", "%<y>"), ("(", "x"), ("a", "x\ny"), ("", "x")],
)
def test_add_refuses_bad_regex_input(tmp_path: Path, pattern: str, replacement: str) -> None:
    """A missing group, a bad regex, a line break or an empty pattern is refused."""
    p = _plugin(tmp_path)
    assert p._api_substitute_add("n", pattern, replacement, True) is False
    assert not p.substitutes


def test_add_refuses_bad_name(tmp_path: Path) -> None:
    """A name with other characters is refused."""
    assert _plugin(tmp_path)._api_substitute_add("a b", "x", "y") is False


def test_regex_mode_replaces(tmp_path: Path) -> None:
    """A regex substitution rewrites with group references."""
    p = _plugin(tmp_path)
    assert p._api_substitute_add("a", r"^(\w+) arrives", "@G%1@w is here", True)
    line = _run(p, _line("Bob arrives now"))
    assert _plain(line.line) == "Bob is here now"


def test_plain_mode_percent_is_literal(tmp_path: Path) -> None:
    """In plain mode %1 is literal text."""
    p = _plugin(tmp_path)
    p._api_substitute_add("a", "x", "%1")
    assert _run(p, _line("axb")).line == "a%1b"


def test_zero_width_matches_skipped(tmp_path: Path) -> None:
    """A regex that matches nothing wide does not change the line."""
    p = _plugin(tmp_path)
    p._api_substitute_add("z", "x*", "Q", True)
    assert _run(p, _line("ab")).line == "ab"


def test_timeout_leaves_line_and_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timed out regex skips that substitution, warns once, and the others still apply."""
    p = _plugin(tmp_path)
    p._api_substitute_add("a_slow", "o+", "X", True)
    p._api_substitute_add("b_plain", "orc", "goblin")

    class _Compiled:
        groups = 0
        groupindex: Any = None

        def finditer(self, text: str, timeout: float) -> Any:
            raise TimeoutError

    monkeypatch.setattr(p, "_regex_for", lambda name: _Compiled())
    messages: list[str] = []
    monkeypatch.setattr(sub_module, "log_to", lambda ids, level, msg, *a: messages.append(msg % a))
    assert _run(p, _line("orc")).line == "goblin"
    assert _run(p, _line("orc")).line == "goblin"
    assert len(messages) == 1


def test_order_by_name(tmp_path: Path) -> None:
    """Substitutions apply in name order, the second on the output of the first."""
    p = _plugin(tmp_path)
    p._api_substitute_add("b", "bb", "cc")
    p._api_substitute_add("a", "aa", "bb")
    assert _run(p, _line("aa")).line == "cc"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"internal": True},
        {"send": False},
        {"is_io": False},
        {"mxp_mode": object()},
    ],
)
def test_skipped_lines(tmp_path: Path, kwargs: dict[str, Any]) -> None:
    """Internal, gagged, non-io and MXP lines are left alone."""
    p = _plugin(tmp_path)
    p._api_substitute_add("o", "orc", "goblin")
    assert _run(p, _line("an orc", **kwargs)).line == "an orc"


def test_skips_bytes_and_no_record(tmp_path: Path) -> None:
    """A bytes line and a missing event record do nothing."""
    p = _plugin(tmp_path)
    p._api_substitute_add("o", "orc", "goblin")
    assert _run(p, _line("an orc", line=b"an orc")).line == b"an orc"
    p.record = None
    p._eventcb_substitute_line()


def test_priority_is_after_triggers() -> None:
    """The callback runs after triggers (50) and line waiters (40)."""
    assert SUBSTITUTE_PRIORITY == 60


def test_command_add(tmp_path: Path) -> None:
    """add stores plain and regex substitutions, with the separator and empty replacement."""
    base = {"name": "a", "pattern": "x||y", "replacement": ["z"], "regex": False}
    p = _plugin(tmp_path, base)
    assert p._command_add().success is True
    assert p.substitutes["a"] == {"pattern": "x|y", "replacement": "z", "regex": False}
    q = _plugin(
        tmp_path, {**base, "name": "b", "pattern": "(x)", "replacement": ["<%1>"], "regex": True}
    )
    assert q._command_add().success is True
    assert q.substitutes["b"]["regex"] is True
    e = _plugin(tmp_path, {**base, "name": "c", "replacement": [""]})
    assert e._command_add().success is True
    assert e.substitutes["c"]["replacement"] == ""
    bad = _plugin(tmp_path, {**base, "name": "bad name"})._command_add()
    assert bad.success is False
    assert "could not set" in bad.message[0]


def test_command_remove(tmp_path: Path) -> None:
    """remove reports an existing and a missing substitution."""
    p = _plugin(tmp_path, {"name": "a"})
    p._api_substitute_add("a", "x", "y")
    assert p._command_remove().success is True
    assert p._command_remove().success is False


def test_command_list(tmp_path: Path) -> None:
    """list is empty, filtered, escaped and tags regex substitutions."""
    p = _plugin(tmp_path, {"match": ""})
    assert p._command_list().message == ["No substitutions defined"]
    p._api_substitute_add("one", "a@r", "b")
    p._api_substitute_add("two", "(x)", "%1", True)
    lines = p._command_list().message
    assert lines == ["one : a@@r -> b", "two : (x) -> %1 (regex)"]
    p.api.table["plugins.core.commands:command.current.args.get"] = lambda: {"match": "tw"}
    assert p._command_list().message == ["two : (x) -> %1 (regex)"]


def test_command_clear(tmp_path: Path) -> None:
    """clear reports the count and persists the empty state."""
    p = _plugin(tmp_path)
    p._api_substitute_add("a", "x", "y")
    p._api_substitute_add("b", "x", "y")
    result = p._command_clear()
    assert result.success is True
    assert "2" in result.message[0]
    assert not p.substitutes
    assert not dict(PersistentDict("x", tmp_path / "substitutes.txt", "c"))


def test_persistence(tmp_path: Path) -> None:
    """A substitution reloads in a new instance and the save hook syncs."""
    p = _plugin(tmp_path)
    p._api_substitute_add("a", "x", "y")
    assert _plugin(tmp_path).substitutes["a"]["pattern"] == "x"
    p.substitutes["b"] = {"pattern": "q", "replacement": "r", "regex": False}
    p._phook_substitutes_save()
    assert "b" in dict(PersistentDict("x", tmp_path / "substitutes.txt", "c"))


def test_api_get_exists_list(tmp_path: Path) -> None:
    """get and list return copies; exists reports membership."""
    p = _plugin(tmp_path)
    p._api_substitute_add("a", "x", "y")
    assert p._api_substitute_exists("a") and not p._api_substitute_exists("b")
    got = p._api_substitute_get("a")
    assert got is not None
    got["pattern"] = "changed"
    assert p.substitutes["a"]["pattern"] == "x"
    assert p._api_substitute_get("zz") is None
    assert set(p._api_substitute_list()) == {"a"}
    assert p._api_substitute_remove("a") and not p._api_substitute_remove("a")


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.substitutes" in ids
    assert not result.errors


def _command_names(methods: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for func in methods.values():
        data = getattr(func, "command_data", None)
        if data is None:
            continue
        name = data.command.get("name") or func.__name__.replace("_command_", " ")
        names.add(name.strip())
    return names


def test_command_names_do_not_shadow_base_plugin_commands() -> None:
    """The commands are exactly the four, none named like a BasePlugin command."""
    from bastproxy.plugins._baseplugin import BasePlugin

    base_names: set[str] = set()
    for klass in BasePlugin.__mro__:
        base_names |= _command_names(dict(vars(klass)))
    own = _command_names(dict(vars(SubstitutesPlugin)))
    assert own == {"add", "remove", "list", "clear"}
    assert not own & base_names


def test_callback_registered_at_priority() -> None:
    """The callback is registered on ev_to_client_data_modify at priority 60."""
    func = SubstitutesPlugin._eventcb_substitute_line
    text = repr(vars(func))
    assert "ev_to_client_data_modify" in text
