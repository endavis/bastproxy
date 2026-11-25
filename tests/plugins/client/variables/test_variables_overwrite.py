# Project: bastproxy
# Filename: tests/plugins/client/variables/test_variables_overwrite.py
#
# File Description: Tests for the -o flag of the variables add command
#
# By: Bast
"""The variables `add` command refuses an existing name without -o (#786)."""

from pathlib import Path

from bastproxy.plugins.client.variables.plugin._variables import VariablesPlugin

from .test_variables import _cmd_stub


def test_add_existing_name_needs_overwrite(tmp_path: Path) -> None:
    """Without -o an existing variable is refused and unchanged; with -o it is replaced."""
    stub = _cmd_stub(tmp_path, {"name": "t", "value": ["one"]})
    assert VariablesPlugin._command_add(stub).success is True
    stub = _cmd_stub(tmp_path, {"name": "t", "value": ["two"]})
    result = VariablesPlugin._command_add(stub)
    assert result.success is False
    assert result.message == ["variable t exists, use -o to replace it"]
    assert stub.variables["t"] == "one"
    stub = _cmd_stub(tmp_path, {"name": "t", "value": ["two"], "overwrite": True})
    assert VariablesPlugin._command_add(stub).success is True
    assert stub.variables["t"] == "two"
