# Project: bastproxy
# Filename: plugins/client/loop/plugin/_loop.py
#
# File Description: a plugin that runs a line a number of times
#
# By: Bast
"""Run a line a number of times, with ``%1`` as the counter (ADR-0017, issue #711)."""

# Standard Library
import logging
import re
from typing import Any

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser, CommandResult

COUNTER_RE = re.compile(r"%(%?)1")

# the most passes one loop may run
MAX_COUNT = 50

# the most passes across one outermost loop and every loop nested in it
MAX_TOTAL = 200

COUNT_MESSAGE = f"Count must be a whole number from 1 to {MAX_COUNT}"


def substitute_counter(template: str, counter: int) -> str:
    """Substitute ``%1`` with the counter in a single pass.

    ``%%1`` becomes the literal ``%1``. Nothing else is touched, so ``%{name}``
    and ``%2`` stay as typed, and the counter is never substituted again.
    """

    def _replace(match: re.Match[str]) -> str:
        if match.group(1):
            return "%1"
        return str(counter)

    return COUNTER_RE.sub(_replace, template)


class LoopPlugin(BasePlugin):
    """a plugin that runs a line a number of times."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self._depth = 0
        self._total = 0
        self._stopped = False

    @staticmethod
    def _refusal(count: Any) -> str:
        """Return why a count is refused, or an empty string when it is fine."""
        text = str(count).strip() if isinstance(count, (str, int)) else ""
        if isinstance(count, bool) or not text.isascii() or not text.isdecimal():
            return COUNT_MESSAGE
        if not 1 <= int(text) <= MAX_COUNT:
            return COUNT_MESSAGE
        return ""

    def _run(self, template: str, count: Any) -> tuple[int, str]:
        """Run the template count times. Return the passes done and a refusal message."""
        if not isinstance(template, str) or not template.strip():
            return 0, "Please provide a line to run"
        message = self._refusal(count)
        if message:
            return 0, message
        number = int(str(count).strip())
        if self._total + number > MAX_TOTAL:
            self._stopped = True
            return 0, f"nested loops reached the limit of {MAX_TOTAL} runs"
        done = 0
        self._depth += 1
        try:
            for counter in range(1, number + 1):
                if self._stopped:
                    return done, f"nested loops reached the limit of {MAX_TOTAL} runs"
                self._total += 1
                self.api("plugins.core.commands:command.line.run")(
                    substitute_counter(template, counter), show_in_history=False
                )
                done += 1
            if self._stopped:
                return done, f"nested loops reached the limit of {MAX_TOTAL} runs"
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._total = 0
                self._stopped = False
        return done, ""

    @AddAPI("loop.run", description="run a line a number of times through the input path")
    def _api_loop_run(self, template: str, count: int) -> bool:
        """Run a line a number of times through the input path.

        @Ytemplate@w    = the line to run, %1 is replaced by the counter
        @Ycount@w       = how many times, 1 to 50

        Each pass goes through the separator split, proxy commands, aliases and
        variables. This function returns True when every pass ran. It returns
        False, logging a warning, when it refused or stopped early.
        """
        done, message = self._run(template, count)
        if message:
            log_to([self.plugin_id], logging.WARNING, "_api_loop_run: %s", message)
            return False
        return done > 0

    @AddCommand(literal_args=True)
    @AddParser(description="run a line a number of times, with %1 as the counter")
    @AddArgument("count", help="how many times, 1 to 50")
    @AddArgument("template", help="the line to run, %%1 is the counter", nargs="*")
    def _command_run(self) -> CommandResult:
        """Run a line a number of times."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        template = " ".join(args["template"])
        # a typed line is split on the command separator before this command runs,
        # so a doubled separator is how a user types one; send it single so the
        # input path splits each pass
        separator = self.api.command_separator
        if separator:
            template = template.replace(separator * 2, separator)
        done, message = self._run(template, args["count"])
        if message and done == 0:
            return CommandResult(False, [message])
        escape = self.api("plugins.core.colors:colorcode.escape")
        if message:
            return CommandResult(
                False, [f"ran {done} of {int(str(args['count']).strip())} times: {message}"]
            )
        return CommandResult(True, [f'"{escape(template)}" ran {done} times'])
