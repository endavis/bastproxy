# Project: bastproxy
# Filename: plugins/core/mudcmds/plugin/_mudcmds.py
#
# File Description: a command queue plugin
#
# By: Bast

# Standard Library
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger, log_to

# 3rd Party
# Project
from bastproxy.libs.records import NetworkData, SendDataDirectlyToMud
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent


@dataclass(slots=True)
class MudCmdType:
    """A registered mud command type."""

    cmd: str
    regex: str
    cregex: re.Pattern[str]
    ctype: str
    owner: str
    beforef: Callable[[], None] | None = None
    afterf: Callable[[], None] | None = None


@dataclass(slots=True)
class QueuedCommand:
    """A command waiting in the queue or currently running."""

    cmd: str
    ctype: str
    plugin: str


class MUDCmdsPlugin(BasePlugin):
    """a plugin to handle sending a command to the mud."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.queue: list[QueuedCommand] = []
        self.cmds: dict[str, MudCmdType] = {}
        self.current_command: QueuedCommand | None = None
        self.timing_uid = None

        self.reload_dependents_f = True

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self.api(f"{self.plugin_id}:type.remove.for.plugin")(event_record["plugin_id"])

    @AddAPI(
        "type.remove.for.plugin",
        description="remove all mud commands related to a plugin",
    )
    def _api_type_remove_for_plugin(self, plugin_id):
        """Remove all commands related to a plugin.

        @Yplugin_id@w   = The plugin name.

        this function returns no values
        """
        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "_api_type_remove_for_plugin - removing mudcmds data for plugin %s",
            plugin_id,
        )
        for i in list(self.cmds):  # copy keys since we are deleting things
            if self.cmds[i].owner == plugin_id:
                self.api(f"{self.plugin_id}:type.remove")(i)

    @AddAPI("type.remove", description="remove a command type")
    def _api_type_remove(self, cmdtype):
        """Remove a command."""
        if cmdtype in self.cmds:
            del self.cmds[cmdtype]
        else:
            get_logger(self.plugin_id).debug("_api_type_remove - %s not found", cmdtype)

    @AddAPI("command.start", description="tell the plugin a command has started")
    def _api_command_start(self, cmdtype):
        """Tell the plugin a command has started."""
        if self.current_command and cmdtype != self.current_command.ctype:
            get_logger(self.plugin_id).error(
                "_api_command_start - got command start for %s and it's not the current cmd: %s",
                cmdtype,
                self.current_command.ctype,
            )
            return
        self.timing_uid = self.api("libs.timing:timing.start")(f"cmd_{cmdtype}")

    @AddAPI("type.add", description="add a command type")
    def _api_type_add(self, cmdtype, cmd, regex, **kwargs):
        """Add a command type.

        Optional keyword arguments:
            owner: the plugin id that owns the type. Defaults to the calling
                plugin, found with libs.api:caller.owner.get.
            beforef: function to call before the command is sent
            afterf: function to call after the command completes
        """
        owner = kwargs.get("owner") or self.api("libs.api:caller.owner.get")(
            ignore_owner_list=[self.plugin_id]
        )
        beforef = kwargs.get("beforef")
        afterf = kwargs.get("afterf")
        if cmdtype not in self.cmds:
            self.cmds[cmdtype] = MudCmdType(
                cmd=cmd,
                regex=regex,
                cregex=re.compile(regex),
                ctype=cmdtype,
                owner=owner,
                beforef=beforef,
                afterf=afterf,
            )

            self.api("plugins.core.events:event.add")(
                f"cmd_{cmdtype}_send",
                self.cmds[cmdtype].owner,
                description=[f"event for the command {self.cmds[cmdtype].ctype} being sent"],
                arg_descriptions={"None": None},
            )
            self.api("plugins.core.events:event.add")(
                f"cmd_{cmdtype}_completed",
                self.cmds[cmdtype].owner,
                description=[f"event for the command {self.cmds[cmdtype].ctype} completing"],
                arg_descriptions={"None": None},
            )

    def _finish_timing(self):
        """Finish the timer started for the current command, if any."""
        if self.timing_uid:
            self.api("libs.timing:timing.finish")(self.timing_uid)
            self.timing_uid = None

    def sendnext(self):
        """Send the next command."""
        get_logger(self.plugin_id).debug("sendnext - checking queue")
        if not self.queue or self.current_command:
            return

        cmdt = self.queue.pop(0)
        cmd = cmdt.cmd
        cmdtype = cmdt.ctype
        get_logger(self.plugin_id).debug("sendnext - sending cmd: %s (%s)", cmd, cmdtype)

        if cmdtype in self.cmds and (beforef := self.cmds[cmdtype].beforef):
            beforef()

        self.current_command = cmdt
        self.api("plugins.core.events:event.raise")(f"cmd_{self.current_command.ctype}_send")
        SendDataDirectlyToMud(NetworkData(cmd), show_in_history=False)()

    def checkinqueue(self, cmd):
        """Check for a command in the queue."""
        return any(i.cmd == cmd for i in self.queue)

    @AddAPI("command.finish", description="tell the plugin a command has finished")
    def _api_command_finish(self, cmdtype):
        """Tell the plugin that a command has finished."""
        get_logger(self.plugin_id).debug("_api_command_finish - got command finish for %s", cmdtype)
        if not self.current_command:
            return
        if cmdtype == self.current_command.ctype:
            if cmdtype in self.cmds and (afterf := self.cmds[cmdtype].afterf):
                get_logger(self.plugin_id).debug(
                    "_api_command_finish - running afterf for %s", cmdtype
                )
                afterf()

            self._finish_timing()
            self.api("plugins.core.events:event.raise")(
                f"cmd_{self.current_command.ctype}_completed"
            )
            self.current_command = None
            self.sendnext()

    @AddAPI("command.queue", description="add a command to the plugin")
    def _api_command_queue(self, cmdtype, arguments=""):
        """Add a command to the queue."""
        plugin = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        cmd = self.cmds[cmdtype].cmd
        if arguments:
            cmd = f"{cmd} {arguments!s}"
        if self.checkinqueue(cmd) or (
            self.current_command is not None and self.current_command.cmd == cmd
        ):
            return
        get_logger(self.plugin_id).debug("_api_command_queue - adding %s to queue", cmd)
        self.queue.append(QueuedCommand(cmd=cmd, ctype=cmdtype, plugin=plugin))
        if not self.current_command:
            self.sendnext()

    def resetqueue(self, _=None):
        """Reset the queue."""
        self.queue = []

    @AddParser(description="drop the last command")
    def _command_fixqueue(self):
        """Finish the last command."""
        if self.current_command:
            self._finish_timing()
            self.current_command = None
            self.sendnext()

        return CommandResult(True, ["finished the currentcmd"])
