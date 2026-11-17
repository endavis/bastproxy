"""The README's Core Plugins list matches the plugins in ``plugins/core`` (#520).

Every core plugin package needs a ``- **name**: purpose`` line, no line may name a plugin that
does not exist, and each purpose must match the plugin's ``PLUGIN_PURPOSE``.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CORE_DIR = ROOT / "src" / "bastproxy" / "plugins" / "core"

HEADING = "### Core Plugins"
ENTRY = re.compile(r"^- \*\*(?P<name>[\w]+)\*\*: (?P<purpose>.+)$")
PURPOSE = re.compile(r"""^PLUGIN_PURPOSE\s*=\s*(["'])(?P<text>.*?)\1""", re.MULTILINE)
TRAILING_PAREN = re.compile(r"\s*\([^()]*\)$")


def _core_plugin_names() -> set[str]:
    return {
        path.name
        for path in CORE_DIR.iterdir()
        if path.is_dir() and path.name != "__pycache__" and (path / "__init__.py").is_file()
    }


def _plugin_purpose(name: str) -> str:
    source = (CORE_DIR / name / "__init__.py").read_text(encoding="utf-8")
    match = PURPOSE.search(source)
    assert match is not None, f"{name} has no literal PLUGIN_PURPOSE"
    return match.group("text")


def _readme_entries(text: str) -> dict[str, str]:
    """Return ``{name: purpose}`` for the entries in the Core Plugins section."""
    entries: dict[str, str] = {}
    in_section = False
    for line in text.splitlines():
        if line.strip() == HEADING:
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        match = ENTRY.match(line) if in_section else None
        if match:
            entries[match.group("name")] = match.group("purpose")
    return entries


def _missing_and_stale(entries: dict[str, str], plugins: set[str]) -> tuple[set[str], set[str]]:
    return plugins - set(entries), set(entries) - plugins


def _normalize(purpose: str) -> str:
    return TRAILING_PAREN.sub("", purpose.strip()).strip().lower()


def test_discovers_core_plugins() -> None:
    assert len(_core_plugin_names()) >= 10


def test_every_core_plugin_is_listed() -> None:
    entries = _readme_entries(README.read_text(encoding="utf-8"))
    missing, _ = _missing_and_stale(entries, _core_plugin_names())
    assert not missing, f"README Core Plugins is missing: {sorted(missing)}"


def test_no_stale_readme_entries() -> None:
    entries = _readme_entries(README.read_text(encoding="utf-8"))
    assert entries, "README Core Plugins section has no entries"
    _, stale = _missing_and_stale(entries, _core_plugin_names())
    assert not stale, f"README lists plugins that do not exist: {sorted(stale)}"


def test_purposes_match_plugin_purpose() -> None:
    entries = _readme_entries(README.read_text(encoding="utf-8"))
    mismatched = {
        name: (purpose, _plugin_purpose(name))
        for name, purpose in entries.items()
        if name in _core_plugin_names() and _normalize(purpose) != _normalize(_plugin_purpose(name))
    }
    assert not mismatched, f"README purpose differs from PLUGIN_PURPOSE: {mismatched}"


def test_helpers_report_missing_and_stale() -> None:
    text = f"{HEADING}\n\n- **alpha**: First\n- **gone**: Old\n\n## Next\n\n- **beta**: Not here\n"
    entries = _readme_entries(text)
    assert entries == {"alpha": "First", "gone": "Old"}
    missing, stale = _missing_and_stale(entries, {"alpha", "beta"})
    assert missing == {"beta"}
    assert stale == {"gone"}
