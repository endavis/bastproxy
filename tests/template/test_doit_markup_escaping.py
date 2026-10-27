"""Text a ``tools/doit/`` task did not write reaches Rich through ``verbatim()`` (#900, #914).

Rich reads a ``str`` passed to ``console.print`` or ``Panel`` as markup, and replaces emoji
shortcodes in it. A ``[`` followed by a lowercase letter, ``#``, ``/`` or ``@`` opens a tag. Rich
drops a tag it does not know and raises ``MarkupError`` on a closing tag with no opener. So git's
``[rejected]`` vanished from ``doit pr``'s push error, and a commit subject holding ``[/tmp]``
crashed its check that the branch is not behind ``main`` (#900).

``rich.markup.escape()`` stops the tags, but not the rest. Rich still drops a backslash before a
``[`` that opens no tag, so a Windows path lost a separator. It still turned ``:sparkles:`` in a
commit subject into an emoji (#914). ``markup=False`` also stops the tags, and also still replaces
the shortcodes. ``verbatim()`` in ``tools/doit/base.py`` returns a ``rich.text.Text``, which Rich
prints as is.

The scan cannot tell outside text from a task's own values, so it looks for the forms #900 found:
a command's ``stdout`` or ``stderr``, the variable an ``except ... as`` clause binds, and the names
the tasks give commit subjects, PR titles and ``git status`` output. It also looks for the names
they give paths, label data and ``$EDITOR`` (#920). It matches names, so a new name for such text
has to be added to ``_OUTSIDE_TEXT``. The user's own flags are outside its scope; each task's own
tests cover them (#907). No task uses ``escape()``, so none can fall back on it.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

DOIT_DIR = Path(__file__).resolve().parents[2] / "tools" / "doit"

# Rich renders the str arguments of these, as markup with emoji shortcodes replaced: Console.print,
# .log and .rule, Panel and Panel.fit. markup=False still replaces the shortcodes (#914).
_RENDERING_CALLS = frozenset({"print", "log", "rule", "Panel", "fit"})
# Keyword arguments that Panel also renders.
_RENDERED_KEYWORDS = frozenset({"title", "subtitle"})
# The names the tasks give text they did not write: command output, commit subjects and PR titles
# (#900), then paths, label data and $EDITOR (#920).
_OUTSIDE_TEXT = frozenset(
    {"stdout", "stderr", "line", "commit", "status", "pr_title", "merge_subject"}
    | {"path", "worktree", "root", "file", "full_path", "item", "bashrc", "zshrc", "editor"}
    | {"bash_completion", "zsh_completion", "name", "entry", "cmd"}
)


def _name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _renders_strings(call: ast.Call) -> bool:
    """Whether Rich renders ``call``'s ``str`` arguments itself."""
    if isinstance(call.func, ast.Name) and call.func.id == "print":
        return False  # the builtin print
    return _name(call.func) in _RENDERING_CALLS


def _carries_outside_text(node: ast.AST, caught: frozenset[str]) -> bool:
    """Whether ``node`` hands Rich outside text that has not gone through ``verbatim()``."""
    if isinstance(node, ast.Call) and _name(node.func) == "verbatim":
        return False
    if isinstance(node, ast.Name) and (node.id in _OUTSIDE_TEXT or node.id in caught):
        return True
    if isinstance(node, ast.Attribute) and node.attr in _OUTSIDE_TEXT:
        return True
    return any(_carries_outside_text(child, caught) for child in ast.iter_child_nodes(node))


def outside_text_not_verbatim(source: str) -> list[tuple[int, str]]:
    """Return ``(line, argument)`` for each argument that hands Rich outside text directly."""
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: list[tuple[int, str]] = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not _renders_strings(call):
            continue
        caught: set[str] = set()
        scope = parents.get(call)
        while scope is not None:
            if isinstance(scope, ast.ExceptHandler) and scope.name:
                caught.add(scope.name)
            scope = parents.get(scope)
        texts = [*call.args, *(k.value for k in call.keywords if k.arg in _RENDERED_KEYWORDS)]
        found.extend(
            (text.lineno, ast.unparse(text))
            for text in texts
            if _carries_outside_text(text, frozenset(caught))
        )
    return found


def escape_uses(source: str) -> list[int]:
    """Return the line of each import or attribute use of ``rich.markup.escape``."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "rich.markup":
            found.extend(node.lineno for alias in node.names if alias.name == "escape")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "escape"
            and _name(node.value) == "markup"
        ):
            found.append(node.lineno)
    return found


def _task_modules() -> list[Path]:
    paths = sorted(DOIT_DIR.glob("*.py"))
    assert paths, f"no task modules under {DOIT_DIR}"
    return paths


def test_no_task_hands_rich_outside_text_directly() -> None:
    found = [
        f"tools/doit/{path.name}:{line}: {text}"
        for path in _task_modules()
        for line, text in outside_text_not_verbatim(path.read_text(encoding="utf-8"))
    ]

    assert not found, (
        "Print text a task did not write through verbatim() from tools/doit/base.py, so Rich "
        "neither parses it as markup nor replaces emoji shortcodes in it (#900, #914):\n"
        + "\n".join(found)
    )


def test_no_task_uses_markup_escape() -> None:
    found = [
        f"tools/doit/{path.name}:{line}"
        for path in _task_modules()
        for line in escape_uses(path.read_text(encoding="utf-8"))
    ]

    assert not found, (
        "rich.markup.escape() leaves Rich to drop a backslash before a [ and to replace emoji "
        "shortcodes. Print outside text through verbatim() instead (#914):\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    "source",
    [
        """
        try:
            read()
        except OSError as e:
            console.print(f"[red]Error reading file: {e}[/red]")
        """,
        'console.print(f"[red]Stderr: {e.stderr}[/red]")',
        """
        stderr = (result.stderr or "").strip()
        console.print(f"[red]{stderr}[/red]")
        """,
        """
        for line in log.splitlines():
            console.print(f"  {line}")
        """,
        'console.print(f"  [red]{commit}[/red]")',
        "console.print(status)",
        'console.print(Panel.fit(f"Commit: {merge_subject}"))',
        'console.print(Panel("body", title=f"{pr_title}"))',
        'console.print("[red]" + stderr + "[/red]")',
        'console.print(f"[red]{escape(result.stdout)} {result.stderr}[/red]")',
        # escape() and markup=False leave the backslash and emoji problems (#914).
        'console.print(f"[red]Stderr: {escape(e.stderr)}[/red]")',
        "console.print(escape(status))",
        'console.print(stderr, style="red", markup=False)',
        'console.print(Text.from_markup(f"[red]{stderr}[/red]"))',
        # A path, a label name and a command built from them (#920).
        'console.print(f"[green]Created {path} on {branch}.[/green]")',
        'console.print(f"[dim]= no change[/dim] {name}")',
        "console.print(f\"[red]Command failed: {' '.join(cmd)}[/red]\")",
    ],
)
def test_the_scan_flags_outside_text_not_verbatim(source: str) -> None:
    assert outside_text_not_verbatim(textwrap.dedent(source))


@pytest.mark.parametrize(
    "source",
    [
        """
        try:
            read()
        except OSError as e:
            console.print(verbatim(f"Error reading file: {e}", "red"))
        """,
        'console.print(verbatim(f"Stderr: {e.stderr}", "red"))',
        'console.print(verbatim(f"git worktree add failed: {(e.stderr or "").strip()}", "red"))',
        "console.print(verbatim(status))",
        """
        console.print(
            Panel.fit(Text.assemble(verbatim("Merged", "bold green"), verbatim(merge_subject)))
        )
        """,
        'console.print(Panel("body", title=verbatim(pr_title)))',
        'print(f"[OK] {stderr}")',
        'console.print(verbatim(f"Created {path} on {branch}.", "green"))',
        'console.print(Text.assemble(verbatim("= no change", "dim"), verbatim(f" {name}")))',
        """
        for e in entries:
            console.print(f"[dim]{e}[/dim]")
        """,
        'console.print(f"[dim]{len(lines)} lines[/dim]")',
    ],
)
def test_the_scan_passes_verbatim_or_own_text(source: str) -> None:
    assert outside_text_not_verbatim(textwrap.dedent(source)) == []


@pytest.mark.parametrize(
    "source",
    [
        "from rich.markup import escape",
        "from rich.markup import escape as esc",
        "import rich.markup\nrich.markup.escape(x)",
        "from rich import markup\nmarkup.escape(x)",
    ],
)
def test_the_escape_scan_finds_each_form(source: str) -> None:
    assert escape_uses(source)


def test_the_escape_scan_ignores_re_escape() -> None:
    assert escape_uses("import re\nre.escape(x)") == []
