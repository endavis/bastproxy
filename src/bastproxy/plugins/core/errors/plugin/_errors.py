# Project: bastproxy
# Filename: plugins/core/errors/_errors.py
#
# File Description: a plugin to handle errors
#
# By: Bast

# Standard Library

# 3rd Party

# Project
import logging

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent


class ErrorPlugin(BasePlugin):
    """a plugin to handle errors."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.errors = []

    @RegisterToEvent(event_name="ev_bastproxy_proxy_ready")
    def _eventcb_proxy_ready(self):
        """Show all errors that happened during startup."""
        if errors := self.api("plugins.core.errors:error.list")():
            msg = ["The following errors happened during startup:", "Proxy Errors"]
            for i in errors:
                msg.extend(("", f"Time  : {i['timestamp']}", f"Error : {i['msg']}"))
            log_to([self.plugin_id, "mudproxy"], logging.ERROR, "%s", "\n".join(msg))

    @AddAPI("error.add", description="add an error")
    def _api_error_add(self, timestamp, error):
        """Add an error.

        this function adds an error to the list
        """
        self.errors.append({"timestamp": timestamp, "msg": error})

    @AddAPI("error.list", description="list all errors")
    def _api_error_list(self):
        """Get errors.

        this function has no arguments

        this function returns the list of errors
        """
        return self.errors

    @AddAPI("error.clear", description="clear all errors")
    def _api_error_clear(self):
        """Clear errors.

        this function has no arguments

        this function returns no values
        """
        self.errors = []

    @AddParser(description="show errors")
    @AddArgument("number", help="list the last <number> errors", default="-1", nargs="?")
    def _command_show(self):
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
            if args and number > 0:
                for i in errors[-number:]:
                    msg.extend(("", f"Time  : {i['timestamp']}", f"Error : {i['msg']}"))
            else:
                for i in errors:
                    msg.extend(("", f"Time   : {i['timestamp']}", f"Error  : {i['msg']}"))
        else:
            msg.append("There are no errors")
        return CommandResult(True, msg)

    @AddParser(description="clear errors")
    def _command_clear(self):
        """Clear errors."""
        self.api("plugins.core.errors:error.clear")()

        return CommandResult(True, ["Errors cleared"])
