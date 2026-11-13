# Project: bastproxy
# Filename: plugins/core/async/_async.py
#
# File Description: a plugin to inspect async internals
#
# By: Bast

# Standard Library
from collections.abc import Callable

# 3rd Party
# Project
from bastproxy.libs.records import NetworkData, ProcessDataToMud
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddParser, CommandResult


class lkAttrPlugin(BasePlugin):
    """a plugin to inspect records"""

    @AddParser(description="test changing a locked attribute")
    def _command_locktest(self):
        """List records of a specific type"""
        testdata = NetworkData("original line")
        refused: list[str] = []

        def attempt(description: str, write: Callable[[], object]) -> None:
            try:
                write()
            except RuntimeError as exc:
                refused.append(f"{description}: refused with RuntimeError: {exc}")
            else:
                refused.append(f"{description}: NOT refused")

        def set_line() -> None:
            testdata[0].line = "changed line"

        def set_item() -> None:
            testdata[0] = "straight assignment to index 0"

        testdata[0].lock()
        attempt("line write on a locked line", set_line)
        testdata.lock()
        attempt("append", lambda: testdata.append("appended line"))
        attempt("extend", lambda: testdata.extend(["list line 1", "list line 2"]))
        attempt("insert", lambda: testdata.insert(1, "inserted line at index 1"))
        attempt("assignment to index 0", set_item)

        tmsg = ["Created:", testdata.one_line_summary(), "Writes:", *refused]
        return CommandResult(True, tmsg)

    @AddParser(description="test splitting a command")
    def _command_splittest(self):
        """List records of a specific type"""
        testdata = NetworkData("command 1|command 2|command 3|command 4|command 5")
        testdata2 = NetworkData("command 1|command 2|command 3|command 4|command 5")

        pd1 = ProcessDataToMud(testdata)
        pd2 = ProcessDataToMud(testdata2)

        pd2.seperate_commands()

        tmsg = [
            f"pd1: {pd1.uuid}",
            *[line.line for line in pd1.message],
            f"pd2: {pd2.uuid}",
            *[line.line for line in pd2.message],
        ]

        return CommandResult(True, tmsg)
