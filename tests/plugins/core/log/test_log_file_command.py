"""Tests for the #bp.core.log.file command and its argument parsing (#185)."""

import argparse
from unittest.mock import MagicMock

from bastproxy.plugins.core.log.plugin._log import LogPlugin


def test_command_file_argument_parser_spec() -> None:
    """_command_file should declare logtype with nargs='*' and default=[]."""
    cmd_data = getattr(LogPlugin._command_file, "command_data", None)
    assert cmd_data is not None

    parser = argparse.ArgumentParser()
    for arg in cmd_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])

    # No argument gives empty list
    args_empty = parser.parse_args([])
    assert args_empty.logtype == []

    # Single argument gives list with one element
    args_single = parser.parse_args(["mudproxy"])
    assert args_single.logtype == ["mudproxy"]

    # Multiple arguments give list of elements
    args_multi = parser.parse_args(["mudproxy", "core.events"])
    assert args_multi.logtype == ["mudproxy", "core.events"]


def test_command_file_no_args_lists_file_handlers() -> None:
    """Running _command_file with empty args lists current file log types."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.log"
    stub.logtype_col_length = 20
    file_dict = {"mudproxy": "info", "network": "debug"}
    stub.handlers = {"file": file_dict}

    def api(name: str):
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"logtype": []}
        return MagicMock()

    stub.api = api

    success, msg = LogPlugin._command_file(stub)
    assert success is True
    assert "Current types going to file" in msg[0]
    # Should not toggle single characters 'l', 'i', 's', 't'
    assert "l" not in file_dict
    assert "i" not in file_dict
    assert "s" not in file_dict
    assert "t" not in file_dict


def test_command_file_toggles_single_logtype() -> None:
    """Running _command_file with a logtype toggles it and doesn't split characters."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.log"
    stub.logtype_col_length = 20
    file_dict: dict[str, str] = {}
    file_mock = MagicMock()
    file_mock.__getitem__.side_effect = file_dict.__getitem__
    file_mock.__setitem__.side_effect = file_dict.__setitem__
    file_mock.__contains__.side_effect = file_dict.__contains__
    stub.handlers = {"file": file_mock}

    set_to_file = MagicMock()

    def api(name: str):
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"logtype": ["mudproxy"]}
        if name == "plugins.core.log:set.log.to.file":
            return set_to_file
        return MagicMock()

    stub.api = api

    # First toggle: not in handlers -> default info -> toggles to debug
    success, msg = LogPlugin._command_file(stub)
    assert success is True
    assert msg == ["setting mudproxy to log to file at level 'debug'"]
    set_to_file.assert_called_once_with("mudproxy", level="debug")

    # Ensure individual characters were never added
    for char in "mudproxy":
        assert char not in file_dict
    assert file_dict["mudproxy"] == "info"  # initial set before set_to_file
