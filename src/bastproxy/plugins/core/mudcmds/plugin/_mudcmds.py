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
from functools import partial
from typing import Any

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger, log_to

# 3rd Party
# Project
from bastproxy.libs.records import NetworkData, SendDataDirectlyToMud
from bastproxy.libs.validators import int_range
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent


@dataclass(slots=True)
class MudCmdType:
    """A registered mud command type."""

    cmd: str
    regex: str
    ctype: str
    owner: str
    beforef: Callable[[], None] | None = None
    afterf: Callable[[], None] | None = None
    timeout: int | None = None
    hide_output: bool = False
    hide_start: str | None = None
    hide_end: str | None = None
    hide_max: int = 500


@dataclass(slots=True)
class HideWindow:
    """The state of hiding one command's output."""

    ctype: str
    cmd: str
    start: re.Pattern[str]
    end: re.Pattern[str] | None
    max_lines: int
    count: int = 0
    finished: bool = False


@dataclass(slots=True)
class QueuedCommand:
    """A command waiting in the queue or currently running."""

    cmd: str
    ctype: str
    plugin: str


class MUDCmdsPlugin(BasePlugin):
    """a plugin to handle sending a command to the mud."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        self.queue: list[QueuedCommand] = []
        self.cmds: dict[str, MudCmdType] = {}
        self.current_command: QueuedCommand | None = None
        self.timing_uid: str | None = None
        self._hide_armed: HideWindow | None = None
        self._hide_open: HideWindow | None = None
        self._prompts_seen = False

        self.reload_dependents_f = True

    @RegisterPluginHook("after_load")
    def _phook_initialize(self) -> None:
        """Add the command timeout setting."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "command_timeout",
            5,
            int,
            "seconds to wait for a command to finish before the queue finishes it and "
            "sends the next one; a command type can set its own",
            validator=int_range(1, label="command timeout"),
        )

    @property
    def _timeout_timer_name(self) -> str:
        """Name of the timer that watches the current command."""
        return f"{self.plugin_id}_command_timeout"

    def _timeout_seconds(self, cmdtype: str) -> int:
        """Seconds to wait for a command of the type: its own limit, else the setting."""
        if cmdtype in self.cmds and (own := self.cmds[cmdtype].timeout) is not None:
            return own
        seconds: int = self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "command_timeout"
        )
        return seconds

    def _start_timeout(self, cmdt: QueuedCommand) -> None:
        """Start the one-time timer that finishes the command if it never does."""
        self.api("plugins.core.timers:timer.add")(
            self._timeout_timer_name,
            partial(self._command_timed_out, cmdt),
            self._timeout_seconds(cmdt.ctype),
            onetime=True,
            plugin_id=self.plugin_id,
        )

    def _cancel_timeout(self) -> None:
        """Remove the timeout timer if it exists."""
        if self.api("plugins.core.timers:timer.exists")(self._timeout_timer_name):
            self.api("plugins.core.timers:timer.remove")(self._timeout_timer_name)

    def _command_timed_out(self, cmdt: QueuedCommand) -> None:
        """Finish a command whose end was never seen, then send the next one.

        afterf and the completed event are not run, since the output was not read.
        The cmd_<type>_timeout event lets the owning plugin clean up.
        """
        if self.current_command is not cmdt:
            return
        seconds = self._timeout_seconds(cmdt.ctype)
        get_logger(self.plugin_id).warning(
            "command %r (type %s, plugin %s) did not finish in %s seconds, "
            "finishing it and sending the next command",
            cmdt.cmd,
            cmdt.ctype,
            cmdt.plugin,
            seconds,
        )
        self._finish_timing()
        self.api("plugins.core.events:event.raise")(
            f"cmd_{cmdt.ctype}_timeout", {"cmd": cmdt.cmd, "seconds": seconds}
        )
        self._close_hide(cmdt.ctype)
        self.current_command = None
        self.sendnext()

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self.api(f"{self.plugin_id}:type.remove.for.plugin")(event_record["plugin_id"])

    @AddAPI(
        "type.remove.for.plugin",
        description="remove all mud commands related to a plugin",
    )
    def _api_type_remove_for_plugin(self, plugin_id: str) -> None:
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
    def _api_type_remove(self, cmdtype: str) -> None:
        """Remove a command type and drop its commands.

        Queued commands of the type are dropped, the rest keep their order. When the
        current command is of the type, its timing is finished and it is cleared
        without running afterf or raising its completed event, and the next command
        is sent.
        """
        if cmdtype not in self.cmds:
            get_logger(self.plugin_id).debug("_api_type_remove - %s not found", cmdtype)
            return
        del self.cmds[cmdtype]
        self._close_hide(cmdtype)
        self.queue = [queued for queued in self.queue if queued.ctype != cmdtype]
        if self.current_command and self.current_command.ctype == cmdtype:
            self._cancel_timeout()
            self._finish_timing()
            self.current_command = None
            self.sendnext()

    @AddAPI("command.start", description="tell the plugin a command has started")
    def _api_command_start(self, cmdtype: str) -> None:
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
    def _api_type_add(self, cmdtype: str, cmd: str, regex: str, **kwargs: Any) -> None:
        """Add a command type.

        Optional keyword arguments:
            owner: the plugin id that owns the type. Defaults to the calling
                plugin, found with libs.api:caller.owner.get.
            beforef: function to call before the command is sent
            afterf: function to call after the command completes
            timeout: seconds to wait for the command to finish, an int of at least 1.
                Defaults to the command_timeout setting. When the command does not
                finish in time, the queue logs a warning, finishes it without running
                afterf, raises cmd_<type>_timeout and sends the next command.
            hide_output: bool, False by default. When True, the output of a command
                the queue sent is hidden from the client. A typed command is never
                hidden.
            hide_start: regex for the first line of the reply. Defaults to regex.
            hide_end: regex for the last line of the reply, which is hidden too.
                Without it the window closes at the first prompt line after
                command.finish, or at command.finish when no prompt has been seen.
            hide_max: line cap, an int of at least 1, 500 by default. Past it the
                window closes, a warning is logged and the line is shown.

        A regex that does not compile is logged as an error and nothing is added.
        An invalid hide_* value is logged as an error and nothing is added.
        """
        try:
            re.compile(regex)
        except re.error:
            get_logger(self.plugin_id).error(
                "_api_type_add - command type %s has an invalid regex %s",
                cmdtype,
                regex,
                exc_info=True,
            )
            return
        timeout = kwargs.get("timeout")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1
        ):
            get_logger(self.plugin_id).error(
                "_api_type_add - command type %s has an invalid timeout %r, "
                "it must be an int of at least 1",
                cmdtype,
                timeout,
            )
            return
        hide_output = kwargs.get("hide_output", False)
        hide_start = kwargs.get("hide_start")
        hide_end = kwargs.get("hide_end")
        hide_max = kwargs.get("hide_max", 500)
        if not self._valid_hide_args(cmdtype, hide_output, hide_start, hide_end, hide_max):
            return
        owner = kwargs.get("owner") or self.api("libs.api:caller.owner.get")(
            ignore_owner_list=[self.plugin_id]
        )
        beforef = kwargs.get("beforef")
        afterf = kwargs.get("afterf")
        if cmdtype not in self.cmds:
            self.cmds[cmdtype] = MudCmdType(
                cmd=cmd,
                regex=regex,
                ctype=cmdtype,
                owner=owner,
                beforef=beforef,
                afterf=afterf,
                timeout=timeout,
                hide_output=hide_output,
                hide_start=hide_start,
                hide_end=hide_end,
                hide_max=hide_max,
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
            self.api("plugins.core.events:event.add")(
                f"cmd_{cmdtype}_timeout",
                self.cmds[cmdtype].owner,
                description=[
                    f"event for the command {self.cmds[cmdtype].ctype} not finishing in time"
                ],
                arg_descriptions={
                    "cmd": "the command that timed out",
                    "seconds": "the seconds it was given to finish",
                },
            )

    def _valid_hide_args(
        self, cmdtype: str, hide_output: Any, hide_start: Any, hide_end: Any, hide_max: Any
    ) -> bool:
        """Check the hide_* arguments of type.add, logging an error for a bad one."""
        logger = get_logger(self.plugin_id)
        if not isinstance(hide_output, bool):
            logger.error(
                "_api_type_add - command type %s has an invalid hide_output %r, it must be a bool",
                cmdtype,
                hide_output,
            )
            return False
        for name, value in (("hide_start", hide_start), ("hide_end", hide_end)):
            if value is None:
                continue
            try:
                re.compile(value)
            except (re.error, TypeError):
                logger.error(
                    "_api_type_add - command type %s has an invalid %s %r, "
                    "it must be a regex that compiles",
                    cmdtype,
                    name,
                    value,
                    exc_info=True,
                )
                return False
        if isinstance(hide_max, bool) or not isinstance(hide_max, int) or hide_max < 1:
            logger.error(
                "_api_type_add - command type %s has an invalid hide_max %r, "
                "it must be an int of at least 1",
                cmdtype,
                hide_max,
            )
            return False
        return True

    def _close_hide(self, ctype: str | None = None) -> None:
        """Drop the open and armed hide windows, only those of ctype when given."""
        if self._hide_open and (ctype is None or self._hide_open.ctype == ctype):
            self._hide_open = None
        if self._hide_armed and (ctype is None or self._hide_armed.ctype == ctype):
            self._hide_armed = None

    @RegisterToEvent(event_name="ev_libs.net.mud_muddisconnect")
    def _eventcb_hide_disconnect(self) -> None:
        """The MUD link closed: drop hide windows and forget prompts seen."""
        self._close_hide()
        self._prompts_seen = False

    @RegisterToEvent(event_name="event_t_plugins.core.triggers_beall")
    def _eventcb_hide_line(self) -> None:
        """Hide the lines of a queued command's reply while its window is open."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if line.internal:
            return
        is_prompt = bool(getattr(line, "is_prompt", False))
        if is_prompt:
            self._prompts_seen = True
        window = self._hide_open
        if window is None:
            armed = self._hide_armed
            if armed is None or not armed.start.search(line.noansi):
                return
            self._hide_armed = None
            self._hide_open = window = armed
        if window.count + 1 > window.max_lines:
            get_logger(self.plugin_id).warning(
                "hiding the output of command type %s reached its cap of %s lines, "
                "showing the rest",
                window.ctype,
                window.max_lines,
            )
            self._hide_open = None
            return
        line.send = False
        window.count += 1
        if (window.end and window.end.search(line.noansi)) or (window.finished and is_prompt):
            self._hide_open = None

    def _arm_hide(self, cmdt: QueuedCommand) -> None:
        """Arm a hide window for a command the queue is sending, if its type hides."""
        ctype = self.cmds.get(cmdt.ctype)
        if ctype is None or not ctype.hide_output:
            return
        self._hide_armed = HideWindow(
            ctype=cmdt.ctype,
            cmd=cmdt.cmd,
            start=re.compile(ctype.hide_start or ctype.regex),
            end=re.compile(ctype.hide_end) if ctype.hide_end else None,
            max_lines=ctype.hide_max,
        )

    def _finish_hide(self, cmdt: QueuedCommand) -> None:
        """A command finished: close its window now or at the next prompt."""
        armed = self._hide_armed
        if armed is not None and armed.ctype == cmdt.ctype and armed.cmd == cmdt.cmd:
            # the reply never opened it, so there is nothing to hide
            self._hide_armed = None
        window = self._hide_open
        if window is None or window.ctype != cmdt.ctype or window.cmd != cmdt.cmd:
            return
        window.finished = True
        if window.end is None and not self._prompts_seen:
            self._hide_open = None

    def _finish_timing(self) -> None:
        """Finish the timer started for the current command, if any."""
        if self.timing_uid:
            self.api("libs.timing:timing.finish")(self.timing_uid)
            self.timing_uid = None

    def sendnext(self) -> None:
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
        self._arm_hide(cmdt)
        self.api("plugins.core.events:event.raise")(f"cmd_{self.current_command.ctype}_send")
        self._start_timeout(cmdt)
        SendDataDirectlyToMud(NetworkData(cmd))()

    def checkinqueue(self, cmd: str) -> bool:
        """Check for a command in the queue."""
        return any(i.cmd == cmd for i in self.queue)

    @AddAPI("command.finish", description="tell the plugin a command has finished")
    def _api_command_finish(self, cmdtype: str) -> None:
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

            self._cancel_timeout()
            self._finish_timing()
            self._finish_hide(self.current_command)
            self.api("plugins.core.events:event.raise")(
                f"cmd_{self.current_command.ctype}_completed"
            )
            self.current_command = None
            self.sendnext()

    @AddAPI("command.queue", description="add a command to the plugin")
    def _api_command_queue(self, cmdtype: str, arguments: str = "") -> None:
        """Add a command to the queue."""
        if cmdtype not in self.cmds:
            get_logger(self.plugin_id).error(
                "_api_command_queue - unknown command type %s", cmdtype
            )
            return
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

    def resetqueue(self, _: Any = None) -> None:
        """Reset the queue."""
        self.queue = []

    @AddParser(description="drop the last command")
    def _command_fixqueue(self) -> CommandResult:
        """Finish the last command."""
        if self.current_command:
            self._cancel_timeout()
            self._finish_timing()
            self._close_hide()
            self.current_command = None
            self.sendnext()

        return CommandResult(True, ["finished the currentcmd"])
