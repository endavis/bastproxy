"""Every ``_command_*`` function under bastproxy/plugins returns a CommandResult (#426)."""

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy" / "plugins"


def _command_functions(tree: ast.AST) -> Iterator[ast.FunctionDef]:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name.startswith("_command_")
            and node.decorator_list
            and not _is_static(node)
        ):
            yield node


def _is_static(fn: ast.FunctionDef) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)


def _terminates(stmt: ast.stmt) -> bool:
    """True if control cannot fall off the end of ``stmt``."""
    if isinstance(stmt, (ast.Return, ast.Raise)):
        return True
    if isinstance(stmt, ast.If):
        return bool(stmt.orelse) and _terminates(stmt.body[-1]) and _terminates(stmt.orelse[-1])
    if isinstance(stmt, ast.Try):
        if stmt.finalbody and _terminates(stmt.finalbody[-1]):
            return True
        main = _terminates((stmt.orelse or stmt.body)[-1])
        return main and all(_terminates(h.body[-1]) for h in stmt.handlers)
    return False


def _direct_returns(fn: ast.FunctionDef) -> Iterator[ast.Return]:
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, ast.Return):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_command_result_call(value: ast.expr | None) -> bool:
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "CommandResult"
    )


def _violations(source: str, name: str = "x.py") -> list[str]:
    found: list[str] = []
    for fn in _command_functions(ast.parse(source)):
        for ret in _direct_returns(fn):
            if not _is_command_result_call(ret.value):
                found.append(f"{name}:{ret.lineno} {fn.name} does not return CommandResult(...)")
        if not _terminates(fn.body[-1]):
            found.append(f"{name}:{fn.lineno} {fn.name} can fall off the end and return None")
    return found


def test_all_commands_return_command_result() -> None:
    problems: list[str] = []
    scanned = 0
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        scanned += source.count("def _command_")
        problems.extend(_violations(source, str(path.relative_to(SRC))))
    assert scanned > 0
    assert not problems, "\n".join(problems)


def test_guard_flags_bad_commands() -> None:
    tuple_return = "@d\ndef _command_a(self):\n    return True, []\n"
    bare = "@d\ndef _command_a(self):\n    pass\n"
    good = "@d\ndef _command_a(self):\n    return CommandResult(True)\n"
    raises = "@d\ndef _command_a(self):\n    raise ValueError\n"
    assert _violations(tuple_return)
    assert _violations(bare)
    assert not _violations(good)
    assert not _violations(raises)
