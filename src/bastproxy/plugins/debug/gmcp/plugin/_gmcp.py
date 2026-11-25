# Project: bastproxy
# Filename: plugins/debug/gmcp/plugin/_gmcp.py
#
# File Description: a plugin to inspect and send GMCP
#
# By: Bast
"""Commands to show the cached GMCP values and to send a GMCP message to the mud (#784)."""

# Standard Library
import io
import json
import shlex
from typing import Any

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import (
    AddArgument,
    AddCommand,
    AddParser,
    CommandResult,
)

_ABSENT = object()


def _split_payload(arg_string: str) -> tuple[str, str]:
    """Split an argument string into the package (first shell token) and the rest.

    The rest keeps its inner whitespace, so JSON reaches ``json.loads`` as typed.
    A string with no valid first token gives ``("", "")``.
    """
    lexer = shlex.shlex(io.StringIO(arg_string), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        package = lexer.get_token()
    except ValueError:
        return "", ""
    if not package:
        return "", ""
    position = lexer.instream.tell()  # type: ignore[attr-defined]  # a StringIO, see above
    return package, arg_string[position:].strip()


def _parse_payload(remainder: str, words: list[str]) -> tuple[bool, Any]:
    """Parse the JSON to send; return ``(ok, value)``, where value is the error text if not ok.

    An empty remainder is no data. The remainder is tried as typed, then as the
    words the argument parser kept (the single-quoted form, whose quotes shlex removed).
    """
    if not remainder:
        return True, None
    try:
        return True, json.loads(remainder)
    except ValueError as exc:
        first_error = exc
    try:
        return True, json.loads(" ".join(words))
    except ValueError:
        return False, str(first_error)


def _format_json(value: Any) -> list[str]:
    """One line per line of indented, sorted JSON."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).splitlines()


class GMCPPlugin(BasePlugin):
    """a plugin to inspect and send GMCP."""

    @AddParser(description="show the cached GMCP modules, or the value of one")
    @AddArgument(
        "module",
        help="a module or dotted path, such as Char.Vitals or Char.Vitals.hp",
        default="",
        nargs="?",
    )
    def _command_cache(self) -> CommandResult:
        """List the cached GMCP modules, or show one value."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        escape = self.api("plugins.core.colors:colorcode.escape")
        module = args["module"]
        if not module:
            cache = self.api("libs.net.protocols:gmcp.cache.get")()
            if not cache:
                return CommandResult(True, ["No GMCP modules are cached"])
            lines = [f"Cached GMCP modules: {len(cache)}"]
            lines.extend(f"    {escape(name)}" for name in sorted(cache))
            return CommandResult(True, lines)
        value = self.api("libs.net.protocols:gmcp.value.get")(module, _ABSENT)
        if value is _ABSENT:
            return CommandResult(False, [f"No cached GMCP value for {escape(module)}"])
        return CommandResult(True, [escape(line) for line in _format_json(value)])

    @AddCommand(literal_args=True, show_in_history=False)
    @AddParser(
        description="send a GMCP message to the mud; the JSON is optional "
        "(single-quote it if it starts with -)"
    )
    @AddArgument("module", help="the GMCP package, quote it if it has a space")
    @AddArgument("data", help="the JSON data to send", nargs="*")
    def _command_send(self) -> CommandResult:
        """Send a GMCP message to the mud."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        escape = self.api("plugins.core.colors:colorcode.escape")
        package, remainder = _split_payload(getattr(args, "arg_string", ""))
        package = package or args["module"]
        ok, payload = _parse_payload(remainder, list(args["data"]))
        if not ok:
            return CommandResult(False, [f"The data is not valid JSON: {escape(str(payload))}"])
        if self.api("libs.net.protocols:gmcp.send")(package, payload):
            return CommandResult(True, [f"Sent GMCP {escape(package)}"])
        return CommandResult(
            False, [f"Could not send GMCP {escape(package)}, see the log for the reason"]
        )
