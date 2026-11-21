# Project: bastproxy
# Filename: plugins/core/errors/_errors.py
#
# File Description: a plugin to handle errors
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from typing import Any

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import (
    NOT_COLLECTED_ATTR,
    add_error,
    clear_errors,
    get_errors,
    get_logger,
)
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent


def format_errors(errors: list[dict[str, Any]]) -> list[str]:
    """Format error entries, one block each, for the show command and the startup summary."""
    msg: list[str] = []
    for i in errors:
        msg.extend(
            (
                "",
                f"Time   : {i['timestamp']}",
                f"Level  : {i['level']}",
                f"Source : {i['source']}",
                f"Error  : {i['msg']}",
            )
        )
    return msg


class ErrorPlugin(BasePlugin):
    """a plugin to show the errors collected from the logging system."""

    @RegisterToEvent(event_name="ev_bastproxy_proxy_ready")
    def _eventcb_proxy_ready(self) -> None:
        """Show all errors that happened during startup."""
        if errors := self.api("plugins.core.errors:error.list")():
            msg = ["The following errors happened during startup:", "Proxy Errors"]
            msg.extend(format_errors(errors))
            # not collected again: the summary is logged at ERROR
            get_logger(self.plugin_id).error(
                "%s",
                "\n".join(msg),
                extra={"log_sources": (self.plugin_id, "mudproxy"), NOT_COLLECTED_ATTR: True},
            )

    @AddAPI("error.add", description="add an error")
    def _api_error_add(self, timestamp: str, error: str) -> None:
        """Add an error.

        this function adds an error to the list
        """
        add_error(timestamp, error)

    @AddAPI("error.list", description="list all errors")
    def _api_error_list(self) -> list[dict[str, Any]]:
        """Get errors.

        this function has no arguments

        this function returns a copy of the list of errors, each with timestamp, level,
        source and msg
        """
        return get_errors()

    @AddAPI("error.clear", description="clear all errors")
    def _api_error_clear(self) -> None:
        """Clear errors.

        this function has no arguments

        this function returns no values
        """
        clear_errors()

    @AddParser(description="show errors")
    @AddArgument("number", help="list the last <number> errors", default="-1", nargs="?")
    def _command_show(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        show the error queue
        @CUsage@w: show.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        msg = []
        try:
            number = int(args["number"])
        except ValueError:
            msg.append("Please specify a number")
            return CommandResult(False, msg)

        if errors := self.api("plugins.core.errors:error.list")():
            if number > 0:
                errors = errors[-number:]
            msg.extend(format_errors(errors))
        else:
            msg.append("There are no errors")
        return CommandResult(True, msg)

    @AddParser(description="clear errors")
    def _command_clear(self) -> CommandResult:
        """Clear errors."""
        self.api("plugins.core.errors:error.clear")()

        return CommandResult(True, ["Errors cleared"])
