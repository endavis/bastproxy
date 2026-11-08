"""Every literal API name called under ``src`` is registered somewhere in ``src`` (#130).

The scan is static: it parses the source and does not start the proxy. "Registered"
means some file registers the name, not that its owner is loaded at startup, so
optional, debug and test plugins count. This catches typos and names with no owner
prefix, which raise ``AttributeError`` only when the call runs.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.errors.plugin._errors import ErrorPlugin

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"

# (path under src/bastproxy, function name) -> reason it is not scanned
_EXCLUDED_FUNCTIONS: dict[tuple[str, str], str] = {
    ("libs/api/_api.py", "test"): (
        "manual demo run only under __main__; it registers its own a.test:* names"
    ),
}

Site = tuple[str, int]


def _plugin_ids() -> list[str]:
    ids: list[str] = []
    plugins = SRC / "plugins"
    for init in plugins.glob("*/*/__init__.py"):
        rel = init.relative_to(plugins).parent
        if rel.parts[0] != "_baseplugin":
            ids.append("plugins." + ".".join(rel.parts))
    return ids


def _owners_of(rel: Path) -> list[str]:
    """Return the API owner ids for a file path relative to ``src/bastproxy``."""
    parts = rel.with_suffix("").parts
    if parts and parts[0] == "plugins":
        if len(parts) > 1 and parts[1] == "_baseplugin":
            return _plugin_ids()
        if len(parts) < 4:
            return []
        return [f"plugins.{parts[1]}.{parts[2]}"]
    parts = parts[:-1] if parts[-1] == "__init__" else parts
    return [".".join(parts)] if parts else []


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


def _resolve_owner(node: ast.expr, file_owners: list[str]) -> list[str] | None:
    value = _const_str(node)
    if value is not None:
        return [value]
    if isinstance(node, ast.Name) and node.id == "APILOCATION":
        return ["libs.api"]
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "plugin_id"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return file_owners
    return None


def _template_regex(name: str) -> re.Pattern[str]:
    parts = re.split(r"\{[^}]*\}", name)
    return re.compile("[^:]+".join(re.escape(p) for p in parts) + "$")


class _Scanner(ast.NodeVisitor):
    def __init__(self, rel: Path, file_owners: list[str]) -> None:
        self.rel = rel.as_posix()
        self.owners = file_owners
        self.calls: list[tuple[str, int]] = []
        self.registered: set[str] = set()
        self.templates: list[str] = []
        self.unresolved: list[Site] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if (self.rel, node.name) in _EXCLUDED_FUNCTIONS:
            return
        self.generic_visit(node)

    def _register(self, name: str, owners: list[str]) -> None:
        for owner in owners:
            self.registered.add(f"{owner}:{name}")

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        # @AddAPI("name", ...)
        if isinstance(func, ast.Name) and func.id == "AddAPI":
            name = _const_str(_first_arg(node, "name"))
            if name is None:
                self.unresolved.append((self.rel, node.lineno))
            elif "{" in name:
                self.templates.append(name)
            else:
                self._register(name, self.owners)
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
        # api("literal")
        elif _is_api_callable(func) and node.args:
            name = _const_str(node.args[0])
            if name is not None:
                self.calls.append((name, node.lineno))
        self.generic_visit(node)

    def _add_call(self, node: ast.Call) -> None:
        if len(node.args) < 2:
            self.unresolved.append((self.rel, node.lineno))
            return
        owners = _resolve_owner(node.args[0], self.owners)
        name = _const_str(node.args[1])
        if owners is None or name is None:
            self.unresolved.append((self.rel, node.lineno))
            return
        self._register(name, owners)


def _collect() -> tuple[dict[str, list[Site]], set[str], list[re.Pattern[str]], list[Site]]:
    calls: dict[str, list[Site]] = {}
    registered: set[str] = set()
    templates: list[str] = []
    unresolved: list[Site] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        scanner = _Scanner(rel, _owners_of(rel))
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for name, line in scanner.calls:
            calls.setdefault(name, []).append((rel.as_posix(), line))
        registered |= scanner.registered
        templates += scanner.templates
        unresolved += scanner.unresolved
    return calls, registered, [_template_regex(t) for t in templates], unresolved


def _missing(
    calls: dict[str, list[Site]], registered: set[str], patterns: list[re.Pattern[str]]
) -> dict[str, list[Site]]:
    missing: dict[str, list[Site]] = {}
    for name, sites in calls.items():
        if name in registered:
            continue
        _, _, api_name = name.partition(":")
        if api_name and any(p.match(api_name) for p in patterns) and name.startswith("plugins."):
            continue
        missing[name] = sites
    return missing


def test_every_literal_api_name_is_registered() -> None:
    calls, registered, patterns, unresolved = _collect()
    assert not unresolved, f"registrations with an unresolvable owner or name: {unresolved}"
    missing = _missing(calls, registered, patterns)
    report = "\n".join(
        f"{name}: " + ", ".join(f"{f}:{ln}" for f, ln in sites) for name, sites in missing.items()
    )
    assert not missing, f"API names called but never registered:\n{report}"


def test_scan_is_not_vacuous() -> None:
    calls, registered, patterns, _ = _collect()
    assert len(calls) >= 100
    for known in (
        "libs.api:caller.owner.get",
        "libs.plugins.loader:plugin.unload",
        "plugins.core.pluginm:plugin.state.save.all",
        "libs.asynch:task.add",
        "plugins.core.errors:clear.all.errors",
    ):
        assert known in registered
    assert not _missing({"plugins.core.proxy:ssc.proxypw": [("x", 1)]}, registered, patterns)
    bad = {"plugins.core.errors:no.such": [("x", 1)], "errors.clear": [("x", 2)]}
    assert set(_missing(bad, registered, patterns)) == set(bad)


def test_errors_clear_command_uses_registered_api_name() -> None:
    names: list[str] = []

    def api(name: str) -> Any:
        names.append(name)
        return lambda *_a, **_k: None

    stub = MagicMock()
    stub.api = MagicMock(side_effect=api)
    assert ErrorPlugin._command_clear(stub) == (True, ["Errors cleared"])
    assert names == ["plugins.core.errors:clear.all.errors"]
