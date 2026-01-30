# Project: bastproxy
# Filename: plugins/core/errors/_errors.py
#
# File Description: a plugin to handle errors
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.records import LogRecord
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser
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
        if errors := self.api("plugins.core.errors:get")():
            msg = ["The following errors happened during startup:", "Proxy Errors"]
            for i in errors:
                msg.extend(("", f"Time  : {i['timestamp']}", f"Error : {i['msg']}"))
            LogRecord(msg, level="error", sources=[self.plugin_id, "mudproxy"])()

    @AddAPI("add", description="add an error")
    def _api_add(self, timestamp, error):
        """Add an error.

        this function adds an error to the list
        """
        self.errors.append({"timestamp": timestamp, "msg": error})

    @AddAPI("get", description="get all errors")
    def _api_get(self):
        """Get errors.

        this function has no arguments

        this function returns the list of errors
        """
        return self.errors

    @AddAPI("clear.all.errors", description="clear all errors")
    def _api_clear_all_errors(self):
        """Clear errors.

        this function has no arguments

        this function returns no values
        """
        self.errors = []

    @AddParser(description="show errors")
    @AddArgument(
        "number", help="list the last <number> errors", default="-1", nargs="?"
    )
    def _command_show(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        show the error queue
        @CUsage@w: show.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()
        msg = []
        try:
            number = int(args["number"])
        except ValueError:
            msg.append("Please specify a number")
            return False, msg

        if errors := self.api("plugins.core.errors:get")():
            if args and number > 0:
                for i in errors[-number:]:
                    msg.extend(("", f"Time  : {i['timestamp']}", f"Error : {i['msg']}"))
            else:
                for i in errors:
                    msg.extend(
                        ("", f"Time   : {i['timestamp']}", f"Error  : {i['msg']}")
                    )
        else:
            msg.append("There are no errors")
        return True, msg

    @AddParser(description="clear errors")
    def _command_clear(self):
        """Clear errors."""
        self.api("errors.clear")()

        return True, ["Errors cleared"]
