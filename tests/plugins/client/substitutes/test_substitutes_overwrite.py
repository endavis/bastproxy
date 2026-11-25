# Project: bastproxy
# Filename: tests/plugins/client/substitutes/test_substitutes_overwrite.py
#
# File Description: Tests for the -o flag of the substitutes add command
#
# By: Bast
"""The substitutes `add` command refuses an existing name without -o (#786)."""

from pathlib import Path

from .test_substitutes import _plugin


def test_add_existing_name_needs_overwrite(tmp_path: Path) -> None:
    """Without -o an existing substitution is refused and unchanged; with -o it is replaced."""
    base = {"name": "a", "pattern": "x", "replacement": ["one"], "regex": False}
    assert _plugin(tmp_path, base)._command_add().success is True
    again = _plugin(tmp_path, {**base, "replacement": ["two"]})
    result = again._command_add()
    assert result.success is False
    assert result.message == ["substitution a exists, use -o to replace it"]
    assert again.substitutes["a"]["replacement"] == "one"
    forced = _plugin(tmp_path, {**base, "replacement": ["two"], "overwrite": True})
    assert forced._command_add().success is True
    assert forced.substitutes["a"]["replacement"] == "two"
