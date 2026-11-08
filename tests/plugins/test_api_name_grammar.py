"""Every registered API name follows the ADR-0004 naming grammar (#160).

The scan is static: it parses ``src/bastproxy`` and does not start the proxy. Each
registration is keyed by ``(owner, name)``, so ``libs.api:data.get`` and the BasePlugin
``data.get`` stay apart.

ADR-0004 is the source of the rules. Names that do not conform yet sit in
``LEGACY_NAMES``. That allowlist can only shrink: a rename PR removes its own rows, and
the tests fail when a listed name now conforms, is no longer registered, or is not an
ADR-0004 appendix row that needs a rename.

The parser checks the shape (rules 1, 2, 6 and 7 of the ADR). Rules 3 and 5 (the
resource is the right singular noun, the qualifier never names the object) are left to
review, so a few names that need a rename already parse. They are tagged ``review``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"
ADR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "decisions"
    / "0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md"
)
ADR_RELATIVE = "docs/decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md"

# ADR-0004 rule 2: the closed action list. Adding a word means amending the ADR.
ACTIONS: frozenset[str] = frozenset(
    {
        "add", "remove", "get", "set", "update", "list", "count",
        "toggle", "start", "finish", "reset", "clear", "clean",
        "load", "unload", "reload", "initialize", "save",
        "register", "unregister", "raise", "send", "run", "queue",
        "format", "to", "strip", "escape", "dump", "center", "cap", "dedent",
        "verify", "match",
        "select", "modify", "shutdown", "restart",
        "is", "has", "exists",
    }
)  # fmt: skip
_BANNED = frozenset({"can", "does", "check"})
_PLACEHOLDER = "placeholder"
_SEGMENT = re.compile(r"[a-z][a-z0-9]*$")

# (path under src/bastproxy, function name) -> reason it is not scanned
_EXCLUDED_FUNCTIONS: dict[tuple[str, str], str] = {
    ("libs/api/_api.py", "test"): (
        "manual demo run only under __main__; it registers its own a.test:* names"
    ),
}

# Appendix owner label -> owner key used by the scan
_APPENDIX_OWNERS: dict[str, str] = {
    "every plugin (BasePlugin)": "plugins._baseplugin",
    "sqldb database object (dynamic)": "plugins.core.sqldb",
    "ssc object (dynamic)": "plugins.core.ssc",
    "plugins.core.cmdq → plugins.core.mudcmds": "plugins.core.cmdq",
}

Site = tuple[str, int]
Key = tuple[str, str]


def split_api_name(name: str) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """Split ``name`` into (resource, action, qualifier), or raise ``ValueError``."""
    cleaned = re.sub(r"\{[^}]*\}", _PLACEHOLDER, name)
    segments = cleaned.split(".")
    for segment in segments:
        if not _SEGMENT.match(segment):
            raise ValueError(f"segment {segment!r} is not a lowercase word")
    for segment in segments:
        if segment in _BANNED:
            raise ValueError(f"{segment!r} is not allowed (rule 7)")
    index = next((i for i, s in enumerate(segments) if s in ACTIONS), None)
    if index is None:
        raise ValueError("no action word from the closed action list")
    if index == 0:
        raise ValueError("empty resource: the name starts with an action word")
    resource = tuple(segments[:index])
    action = segments[index]
    qualifier = tuple(segments[index + 1 :])
    if "all" in resource:
        raise ValueError("'all' is not used as a resource (rule 6)")
    if action in {"is", "has"} and not qualifier:
        raise ValueError(f"{action!r} needs at least one word after it (rule 7)")
    if action == "exists" and qualifier:
        raise ValueError("'exists' must be the last segment (rule 7)")
    return resource, action, qualifier


def api_name_error(name: str) -> str | None:
    """Return why ``name`` breaks the grammar, or None when it conforms."""
    try:
        split_api_name(name)
    except ValueError as exc:
        return str(exc)
    return None


# ---------------------------------------------------------------------------
# Scan of src/bastproxy
# ---------------------------------------------------------------------------


def _owner_of(rel: Path) -> str | None:
    """Return the API owner for a file path relative to ``src/bastproxy``."""
    parts = rel.with_suffix("").parts
    if parts and parts[0] == "plugins":
        if len(parts) > 1 and parts[1] == "_baseplugin":
            return "plugins._baseplugin"
        if len(parts) < 4:
            return None
        return f"plugins.{parts[1]}.{parts[2]}"
    parts = parts[:-1] if parts and parts[-1] == "__init__" else parts
    return ".".join(parts) if parts else None


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_api_callable(func: ast.expr) -> bool:
    return (isinstance(func, ast.Attribute) and func.attr == "api") or (
        isinstance(func, ast.Name) and func.id == "api"
    )


def _first_arg(node: ast.Call, keyword: str) -> ast.expr | None:
    if node.args:
        return node.args[0]
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _resolve_owner(node: ast.expr, file_owner: str | None) -> str | None:
    value = _const_str(node)
    if value is not None:
        return value
    if isinstance(node, ast.Name) and node.id == "APILOCATION":
        return "libs.api"
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "plugin_id"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return file_owner
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, rel: Path, file_owner: str | None) -> None:
        self.rel = rel.as_posix()
        self.owner = file_owner
        self.registered: list[tuple[Key, Site]] = []
        self.unresolved: list[Site] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if (self.rel, node.name) in _EXCLUDED_FUNCTIONS:
            return
        self.generic_visit(node)

    def _register(self, owner: str | None, name: str | None, line: int) -> None:
        if owner is None or name is None:
            self.unresolved.append((self.rel, line))
            return
        self.registered.append(((owner, name), (self.rel, line)))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        # @AddAPI("name", ...)
        if isinstance(func, ast.Name) and func.id == "AddAPI":
            self._register(self.owner, _const_str(_first_arg(node, "api")), node.lineno)
        # self.add(APILOCATION, "name", ...) inside libs/api/_api.py
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "add"
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and self.rel == "libs/api/_api.py"
        ) or (
            isinstance(func, ast.Call)
            and _is_api_callable(func.func)
            and func.args
            and _const_str(func.args[0]) == "libs.api:api.add"
        ):
            self._add_call(node)
        self.generic_visit(node)

    def _add_call(self, node: ast.Call) -> None:
        if len(node.args) < 2:
            self.unresolved.append((self.rel, node.lineno))
            return
        self._register(
            _resolve_owner(node.args[0], self.owner), _const_str(node.args[1]), node.lineno
        )


def collect_registrations() -> tuple[dict[Key, list[Site]], list[Site]]:
    """Return every registration keyed by (owner, name), plus unresolved sites."""
    found: dict[Key, list[Site]] = {}
    unresolved: list[Site] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        scanner = _Scanner(rel, _owner_of(rel))
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for key, site in scanner.registered:
            found.setdefault(key, []).append(site)
        unresolved += scanner.unresolved
    return found, unresolved


# ---------------------------------------------------------------------------
# ADR-0004 appendix
# ---------------------------------------------------------------------------

_ROW = re.compile(r"^\| (.+?) \| (\S+) \| (\S+) \| (format|boolean|misnamed|unchanged) \|$")


def appendix_rows() -> list[tuple[Key, str, str]]:
    """Return ((owner, current), new, reason) for each appendix row."""
    rows: list[tuple[Key, str, str]] = []
    for line in ADR.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        owner, current, new, reason = match.groups()
        rows.append(((_APPENDIX_OWNERS.get(owner, owner), current), new, reason))
    return rows


# ---------------------------------------------------------------------------
# Allowlist: names that need a rename and have not had it yet. It only shrinks.
# "shape": the parser rejects the name.
# "review": the name already parses, but breaks rule 3 or 5 (wrong resource noun,
#           or a noun in the qualifier), which the ADR leaves to review.
# ---------------------------------------------------------------------------
LEGACY_NAMES: dict[Key, str] = {
    # libs.timing
    ("libs.timing", "finish"): "shape",
    ("libs.timing", "start"): "shape",
    ("libs.timing", "toggle"): "shape",
    # plugins.core.clients
    ("plugins.core.clients", "client.banned.check"): "shape",
    ("plugins.core.clients", "client.logged.in"): "shape",
    ("plugins.core.clients", "client.logged.in.view.only"): "shape",
    ("plugins.core.clients", "get.all.clients"): "shape",
    ("plugins.core.clients", "get.client"): "shape",
    ("plugins.core.clients", "get.clients.formatted"): "shape",
    ("plugins.core.clients", "send.to.client"): "shape",
    # plugins.core.cmdq
    ("plugins.core.cmdq", "finish"): "shape",
    ("plugins.core.cmdq", "queue.add.command"): "shape",
    ("plugins.core.cmdq", "remove.mud.commands.for.plugin"): "shape",
    ("plugins.core.cmdq", "start"): "shape",
    # plugins.core.colors
    ("plugins.core.colors", "color.length.difference"): "shape",
    # plugins.core.commands
    # plugins.core.errors
    ("plugins.core.errors", "add"): "shape",
    ("plugins.core.errors", "clear.all.errors"): "shape",
    ("plugins.core.errors", "get"): "shape",
    # plugins.core.fuzzy
    ("plugins.core.fuzzy", "get.best.match"): "shape",
    ("plugins.core.fuzzy", "get.top.matches"): "shape",
    # plugins.core.log
    ("plugins.core.log", "can.log.to.client"): "shape",
    ("plugins.core.log", "can.log.to.console"): "shape",
    ("plugins.core.log", "can.log.to.file"): "shape",
    ("plugins.core.log", "clean.types"): "shape",
    ("plugins.core.log", "get.level.color"): "shape",
    ("plugins.core.log", "set.log.to.client"): "shape",
    ("plugins.core.log", "set.log.to.console"): "shape",
    ("plugins.core.log", "set.log.to.file"): "shape",
    # plugins.core.proxy
    ("plugins.core.proxy", "get.mud.connection"): "shape",
    ("plugins.core.proxy", "is.mud.connected"): "shape",
    ("plugins.core.proxy", "restart"): "shape",
    ("plugins.core.proxy", "shutdown"): "shape",
    # plugins.core.sqldb
    ("plugins.core.sqldb", "baseclass"): "shape",
    ("plugins.core.sqldb", "{database_name}.get.single.row"): "review",  # rules 3/5, left to review
    # plugins.core.ssc
    ("plugins.core.ssc", "ssc.{name}"): "shape",
    # plugins.core.timers
    ("plugins.core.timers", "add.timer"): "shape",
    ("plugins.core.timers", "get.timer.next.fire"): "shape",
    ("plugins.core.timers", "has.timer"): "shape",
    ("plugins.core.timers", "remove.data.for.plugin"): "shape",
    ("plugins.core.timers", "remove.timer"): "shape",
    ("plugins.core.timers", "toggle.timer"): "shape",
    # plugins.core.triggers
    ("plugins.core.triggers", "remove.data.for.owner"): "shape",
    # plugins.core.utils
    ("plugins.core.utils", "cap.line"): "shape",
    ("plugins.core.utils", "center.colored.string"): "shape",
    ("plugins.core.utils", "check.list.for.match"): "shape",
    ("plugins.core.utils", "convert.data.to.output.table"): "review",  # rules 3/5, left to review
    ("plugins.core.utils", "convert.seconds.to.dhms"): "review",  # rules 3/5, left to review
    ("plugins.core.utils", "convert.timedelta.to.string"): "review",  # rules 3/5, left to review
    ("plugins.core.utils", "convert.timelength.to.secs"): "review",  # rules 3/5, left to review
    ("plugins.core.utils", "convert.to.readable.number"): "review",  # rules 3/5, left to review
    ("plugins.core.utils", "dedent.list.of.strings"): "shape",
    ("plugins.core.utils", "dump.object.as.string"): "shape",
    ("plugins.core.utils", "format.list.into.columns"): "shape",
    ("plugins.core.utils", "format.time"): "shape",
    ("plugins.core.utils", "get.keys.from.dict"): "shape",
    ("plugins.core.utils", "verify.value"): "shape",
    # plugins.core.watch
    ("plugins.core.watch", "remove.all.data.for.plugin"): "shape",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "timer.add",
        "plugin.info.get",
        "colorcode.to.html",
        "client.banned.add.by.ip",
        "client.is.logged.in",
        "plugin.exists",
        "event.has.handler",
        "trigger.toggle.enable",
        "plugin.state.save.all",
        "{database_name}.select",
        "ssc.{name}.get",
    ],
)
def test_conforming_names_parse(name: str) -> None:
    assert api_name_error(name) is None


def test_split_separates_resource_action_qualifier() -> None:
    assert split_api_name("api.list.in.toplevel") == (("api",), "list", ("in", "toplevel"))


@pytest.mark.parametrize(
    ("name", "fragment"),
    [
        ("add", "empty resource"),
        ("get.plugin.info", "empty resource"),
        ("has.event", "empty resource"),
        ("stackdump", "no action"),
        ("ssc.{name}", "no action"),
        ("client.logged.in", "no action"),
        ("can.log.to.console", "'can'"),
        ("does.plugin.exist", "'does'"),
        ("client.banned.check", "'check'"),
        ("plugin.is", "'is' needs"),
        ("timer.has", "'has' needs"),
        ("timer.exists.now", "'exists' must be the last"),
        ("is.character.active:set", "not a lowercase word"),
        ("Timer.add", "not a lowercase word"),
        ("all.plugin.list", "'all' is not used as a resource"),
    ],
)
def test_non_conforming_names_fail(name: str, fragment: str) -> None:
    error = api_name_error(name)
    assert error is not None
    assert fragment in error


def test_appendix_has_rows() -> None:
    rows = appendix_rows()
    assert len(rows) >= 100
    assert {reason for _, _, reason in rows} <= {"format", "boolean", "misnamed", "unchanged"}


def test_appendix_new_names_conform() -> None:
    bad = {
        f"{owner}:{new}": error
        for (owner, _), new, _ in appendix_rows()
        if (error := api_name_error(new)) is not None
    }
    assert not bad, f"ADR-0004 appendix new names that break the grammar: {bad}"


def test_appendix_unchanged_names_conform() -> None:
    bad = {
        f"{owner}:{current}": error
        for (owner, current), _, reason in appendix_rows()
        if reason == "unchanged" and (error := api_name_error(current)) is not None
    }
    assert not bad, f"'unchanged' appendix names that break the grammar: {bad}"


def test_legacy_names_are_appendix_renames() -> None:
    renames = {key for key, _, reason in appendix_rows() if reason != "unchanged"}
    extra = sorted(set(LEGACY_NAMES) - renames)
    assert not extra, (
        f"LEGACY_NAMES entries that are not ADR-0004 appendix rows needing a rename: {extra}"
    )


def test_legacy_reasons_are_valid() -> None:
    assert set(LEGACY_NAMES.values()) <= {"shape", "review"}


def test_shape_entries_still_fail_the_grammar() -> None:
    now_ok = sorted(
        f"{owner}:{name}"
        for (owner, name), reason in LEGACY_NAMES.items()
        if reason == "shape" and api_name_error(name) is None
    )
    assert not now_ok, f"now conforms, remove it from LEGACY_NAMES: {now_ok}"


def test_review_entries_parse() -> None:
    rejected = sorted(
        f"{owner}:{name}"
        for (owner, name), reason in LEGACY_NAMES.items()
        if reason == "review" and api_name_error(name) is not None
    )
    assert not rejected, f"the parser now rejects it, retag as shape: {rejected}"


def test_legacy_names_are_still_registered() -> None:
    found, _ = collect_registrations()
    gone = sorted(f"{owner}:{name}" for owner, name in set(LEGACY_NAMES) - set(found))
    assert not gone, f"no longer registered, remove it from LEGACY_NAMES: {gone}"


def test_every_registration_outside_the_allowlist_conforms() -> None:
    found, _ = collect_registrations()
    lines: list[str] = []
    for (owner, name), sites in sorted(found.items()):
        if (owner, name) in LEGACY_NAMES:
            continue
        error = api_name_error(name)
        if error is not None:
            where = ", ".join(f"{f}:{ln}" for f, ln in sites)
            lines.append(f"{owner}:{name} - {error} - {where}")
    report = "\n".join(lines)
    assert not lines, f"API names that break the ADR-0004 grammar ({ADR_RELATIVE}):\n{report}"


def test_no_unresolved_registrations() -> None:
    _, unresolved = collect_registrations()
    assert not unresolved, f"registrations with an unresolvable owner or name: {unresolved}"


def test_scan_is_not_vacuous() -> None:
    found, _ = collect_registrations()
    assert len(found) >= 150
    for key in [
        ("libs.asynch", "task.add"),
        ("plugins.core.pluginm", "plugin.state.save.all"),
        ("libs.api", "api.add"),
        ("plugins._baseplugin", "data.get"),
        ("plugins.core.sqldb", "{database_name}.select"),
    ]:
        assert key in found
    assert not [owner for owner, _ in found if owner.startswith("a.")]
