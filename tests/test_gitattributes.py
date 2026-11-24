"""Guard the repo-root ``.gitattributes`` that keeps working files LF (#1288).

Without it, ``core.autocrlf=true`` on Windows checks files out CRLF and
``doit format_check`` fails against ruff's ``line-ending = "lf"``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GITATTRIBUTES = REPO_ROOT / ".gitattributes"


def _star_attributes() -> dict[str, str]:
    """Return the attributes of the ``*`` rule as a name -> value mapping."""
    attrs: dict[str, str] = {}
    for raw in GITATTRIBUTES.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *tokens = line.split()
        if pattern != "*":
            continue
        for token in tokens:
            name, _, value = token.partition("=")
            attrs[name] = value
    return attrs


def test_gitattributes_exists_at_repo_root() -> None:
    assert GITATTRIBUTES.is_file()


def test_star_rule_normalizes_text_to_lf() -> None:
    attrs = _star_attributes()
    assert "text" in attrs
    assert attrs["text"] == "auto"
    assert attrs["eol"] == "lf"


def test_eol_matches_ruff_line_ending() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    ruff_ending: str = data["tool"]["ruff"]["format"]["line-ending"]
    assert _star_attributes()["eol"] == ruff_ending
