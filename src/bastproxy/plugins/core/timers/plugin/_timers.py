# Project: bastproxy
# Filename: plugins/core/timers/_timers.py
#
# File Description: a plugin to handle timers
#
# By: Bast

# Standard Library
import asyncio
import datetime
import logging
import math
import sys
import time
from collections.abc import Callable
from typing import TypedDict

from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.callback import Callback
from bastproxy.libs.logger import get_logger, log_to

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

# The sections this plugin adds to a stats event record's "stats" dict. The keys
# are display labels, so the functional syntax is needed.
OverallTimerStats = TypedDict(
    "OverallTimerStats",
    {
        "showorder": list[str],
        "Total": int,
        "Enabled": int,
        "Disabled": int,
        "Fired": int,
        "Memory Usage": int,
    },
)
PluginTimerStats = TypedDict(
    "PluginTimerStats",
    {
        "showorder": list[str],
        "Total Timers Owned": int,
        "Timers Owned": str,
    },
)


class Timer(Callback):
    """a class for a timer."""

    def __init__(self, name, func, seconds, plugin_id, enabled=True, **kwargs):
        """Initialize the class. Time should be in military format, e.g.,"1430".

        Parameters:
        name (str): Name of the timer event.
        func (func): Function to execute on the timer event.
        seconds (int): Time interval in seconds.
        plugin (obj): Plugin related to the timer event.
        **kwargs (Optional): Additional keyword arguments
            onetime (bool): True if the timer is one-time only. Defaults to False.
            enabled (bool): True if the timer is enabled. Defaults to True.
            time (str): Time (in military format) when the timer should fire. If None, timer will fire according to the "seconds" value. Defaults to None.
            log (bool): True if the timer should show up in the logs. Defaults to True.
        """
        super().__init__(name, plugin_id, func, enabled)
        self.seconds: int = seconds
        self.api = API(owner_id=f"{plugin_id}:Timer:{name}")

        self.onetime: bool = False
        if "onetime" in kwargs:
            self.onetime = kwargs["onetime"]

        self.time: str = ""
        if "time" in kwargs:
            self.time = kwargs["time"]

        self.log = True
        if "log" in kwargs:
            self.log = kwargs["log"]

        self.last_fired_datetime: datetime.datetime | None = None

        # this should be a datetime object
        self.next_fire_datetime: datetime.datetime = self.get_first_fire()

    def __hash__(self) -> int:
        """Hash by identity so timers with the same func, owner and name stay distinct."""
        return object.__hash__(self)

    def __eq__(self, other: object) -> bool:
        """Compare timers by identity; compare against plain callables as Callback does."""
        if isinstance(other, Timer):
            return self is other
        return super().__eq__(other)

    def get_first_fire(self) -> datetime.datetime:
        """Gets the first fire time of the timer.

        Returns:
            datetime: First fire time of the timer.
        """
        now = datetime.datetime.now(datetime.UTC)
        new_date = now + datetime.timedelta(seconds=self.seconds)
        if self.time:
            hour_minute = time.strptime(self.time, "%H%M")
            new_date = now.replace(hour=hour_minute.tm_hour, minute=hour_minute.tm_min, second=0)
            while new_date < now:
                new_date = new_date + datetime.timedelta(days=1)

        else:
            while new_date < now:
                new_date = new_date + datetime.timedelta(seconds=self.seconds)

        return new_date

    def get_next_fire(self) -> datetime.datetime:
        """Gets the next timestamp when the timer should fire.

        Returns:
            int: Timestamp of the next time when the timer should fire.
        """
        now = datetime.datetime.now(datetime.UTC)
        if not self.last_fired_datetime:
            return self.get_first_fire()
        next_fire = self.last_fired_datetime + datetime.timedelta(seconds=self.seconds)
        while next_fire < now:
            next_fire = next_fire + datetime.timedelta(seconds=self.seconds)
        return next_fire

    def __str__(self) -> str:
        """Return a string representation of the timer."""
        return f"Timer {self.name:<10} : {self.owner_id:<15} : {self.seconds:05d} : {self.enabled:<6} : {self.next_fire_datetime.strftime(self.api.time_format)}"


class TimersPlugin(BasePlugin):
    """a plugin to handle timers."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.can_reload_f: bool = False

        self.timer_events: dict[int, list[Timer]] = {}
        self.timer_lookup: dict[str, Timer] = {}
        self.overall_fire_count: int = 0
        self.time_last_checked: datetime.datetime = datetime.datetime.now(datetime.UTC)

    @RegisterPluginHook("after_load")
    def _phook_initialize(self):
        """Initialize the plugin."""
        get_logger(self.plugin_id).debug("initialize - lasttime:  %s", self.time_last_checked)

        # setup the task to check for timers to fire
        self.api("libs.asynch:task.add")(self.check_for_timers_to_fire, "Timer Plugin task")

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            log_to(
                [self.plugin_id, event_record["plugin_id"]],
                logging.DEBUG,
                "_eventcb_plugin_unloaded - removing timers for plugin %s",
                event_record["plugin_id"],
            )
            self.api(f"{self.plugin_id}:timer.remove.for.plugin")(event_record["plugin_id"])

    @AddParser(description="toggle log flag for a timer")
    @AddArgument("timername", help="the timer name", default="", nargs="?")
    def _command_log(self) -> tuple[bool, list[str]]:
        """Change the log flag for a timer."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args["timername"] in self.timer_lookup:
            self.timer_lookup[args["timername"]].log = not self.timer_lookup[args["timername"]].log
            message.append(
                f"changed log flag to {self.timer_lookup[args['timername']].log} for timer {args['timername']}"
            )
        else:
            message.append(f"timer {args['timername']} does not exist")

        return CommandResult(True, message)

    # @RegisterPluginHook('stats')
    # def _phook_timer_stats(self, **kwargs):
    @RegisterToEvent(event_name="ev_plugin_{plugin_id}_stats")
    def _eventcb_timers_ev_plugins_stats(self):
        """Return stats for the plugin."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            disabled = 0
            enabled = 0

            for i in self.timer_lookup:
                if self.timer_lookup[i].enabled:
                    enabled = enabled + 1
                else:
                    disabled = disabled + 1

            overall: OverallTimerStats = {
                "showorder": ["Total", "Enabled", "Disabled", "Fired", "Memory Usage"],
                "Total": len(self.timer_lookup),
                "Enabled": enabled,
                "Disabled": disabled,
                "Fired": self.overall_fire_count,
                "Memory Usage": sys.getsizeof(self.timer_events),
            }
            event_record["stats"]["Overall Timer Stats"] = overall

    @RegisterToEvent(event_name="ev_plugin_stats")
    def _eventcb_event_get_stats_for_plugin(self) -> None:
        """Get stats for a plugin."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return

        plugin_id = event_record["plugin_id"]
        timers = [timer.name for timer in self.timer_lookup.values() if timer.owner_id == plugin_id]

        if not timers:
            return

        timers_str = "".join(f"{'':<23}{item}\n" for item in timers)

        owned: PluginTimerStats = {
            "showorder": ["Total Timers Owned", "Timers Owned"],
            "Total Timers Owned": len(timers),
            "Timers Owned": timers_str.strip(),
        }
        event_record["stats"][f"{plugin_id} Timer Stats"] = owned

    @AddParser(description="list timers")
    @AddArgument(
        "match",
        help="list only events that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_list(self) -> tuple[bool, list[str]]:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list timers and the plugins they are defined in
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        output_header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )
        match: str = args["match"]

        message: list[str] = [
            f"UTC time is: {datetime.datetime.now(datetime.UTC).strftime('%a %b %d %Y %H:%M:%S %Z')}",
            output_header_color + "-" * 80 + "@w",
        ]
        templatestring = "%-20s : %-25s %-9s %-8s %s"
        message.extend(
            (
                templatestring % ("Name", "Defined in", "Enabled", "Fired", "Next Fire"),
                output_header_color + "-" * 80 + "@w",
            )
        )
        for i in self.timer_lookup:
            if not match or match in i:
                timer = self.timer_lookup[i]
                message.append(
                    templatestring
                    % (
                        timer.name,
                        timer.owner_id,
                        timer.enabled,
                        timer.raised_count,
                        timer.next_fire_datetime.strftime("%a %b %d %Y %H:%M:%S %Z"),
                    )
                )

        return CommandResult(True, message)

    @AddParser(description="get details for a timer")
    @AddArgument("timers", help="a list of timers to get details", default=None, nargs="*")
    def _command_detail(self) -> tuple[bool, list[str]]:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the details of a timer
        @CUsage@w: detail.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args["timers"]:
            columnwidth: int = 13
            for timer_name in args["timers"]:
                if timer_name in self.timer_lookup:
                    timer = self.timer_lookup[timer_name]
                    message.extend(
                        (
                            f"{'Name':<{columnwidth}} : {timer.name}",
                            f"{'Enabled':<{columnwidth}} : {timer.enabled}",
                            f"{'Owner':<{columnwidth}} : {timer.owner_id}",
                            f"{'Onetime':<{columnwidth}} : {timer.onetime}",
                            f"{'Time':<{columnwidth}} : {timer.time or 'None'}",
                            f"{'Seconds':<{columnwidth}} : {timer.seconds}",
                            f"{'Times Fired':<{columnwidth}} : {timer.raised_count}",
                            f"{'Log':<{columnwidth}} : {timer.log}",
                        )
                    )
                    last_fire_time = "None"
                    if timer.last_fired_datetime:
                        last_fire_time = timer.last_fired_datetime.strftime(
                            "%a %b %d %Y %H:%M:%S %Z"
                        )
                        message.append(f"{'Last Fire':<{columnwidth}} : {last_fire_time}")
                    message.extend(
                        (
                            f"{'Next Fire':<{columnwidth}} : {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}",
                            "",
                        )
                    )
                else:
                    message.append(f"Timer {timer_name} does not exist")

        else:
            message.append("Please specify a timer name")

        return CommandResult(True, message)

    @AddAPI("timer.exists", description="check if a timer exists")
    def _api_timer_exists(self, name: str):
        """Check if a timer exists.

        @Yname@w   = the name of the timer to check.

        returns True if the timer exists, False otherwise
        """
        return name in self.timer_lookup

    @AddAPI("timer.next.fire.get", description="get the next fire time for a timer")
    def _api_timer_next_fire_get(self, name: str) -> datetime.datetime | None:
        """Get the next fire time for a timer.

        @Yname@w   = the name of the timer to check.

        returns the next fire time for the timer, or None if the timer does not exist
        """
        if name in self.timer_lookup:
            return self.timer_lookup[name].next_fire_datetime
        return None

    @AddAPI("timer.add", description="add a timer")
    def _api_timer_add(self, name: str, func: Callable, seconds: int, **kwargs) -> Timer | None:
        """Add a timer.

        @Yname@w   = The timer name
        @Yfunc@w  = the function to call when firing the timer
        @Yseconds@w   = the interval (in seconds) to fire the timer
        @Yargs@w arguments:
          @Yunique@w    = True if no duplicates of this timer are allowed,
                                        False otherwise
          @Yonetime@w   = True for a onetime timer, False otherwise
          @Yenabled@w   = True if enabled, False otherwise
          @Ytime@w      = The time to start this timer, e.g. 1300 for 1PM.

        returns an Event instance
        """
        plugin_id: str = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        if "plugin_id" in kwargs:
            given = kwargs.pop("plugin_id")
            plugin_id = given.plugin_id if isinstance(given, BasePlugin) else given

        if not plugin_id or not self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            get_logger(self.plugin_id).error(
                "_api_timer_add: timer %s has no plugin, not adding", name
            )
            return None

        if seconds <= 0:
            log_to(
                [self.plugin_id, plugin_id],
                logging.ERROR,
                "_api_timer_add: timer %s has seconds <= 0, not adding",
                name,
            )
            return None
        if not func:
            log_to(
                [self.plugin_id, plugin_id],
                logging.ERROR,
                "_api_timer_add: timer %s has no function, not adding",
                name,
            )
            return None

        if "unique" in kwargs and kwargs["unique"] and name in self.timer_lookup:
            log_to(
                [self.plugin_id, plugin_id],
                logging.ERROR,
                "_api_timer_add: timer %s already exists, not adding",
                name,
            )
            return None

        timer = Timer(name, func, seconds, plugin_id, **kwargs)
        log_to([self.plugin_id, plugin_id], logging.DEBUG, "_api_timer_add: adding timer %s", name)
        self._add_timer_internal(timer)
        return timer

    @AddAPI("timer.remove.for.plugin", description="remove all data for a plugin")
    def _api_timer_remove_for_plugin(self, name: str):
        """Remove all timers associated with a plugin.

        @Yname@w   = the name of the plugin.

        this function returns no values
        """
        log_to([self.plugin_id, name], logging.DEBUG, "removing timers for %s", name)
        timers_to_remove: list[str] = [
            i for i in self.timer_lookup if self.timer_lookup[i].owner_id == name
        ]
        for i in timers_to_remove:
            self.api(f"{self.plugin_id}:timer.remove")(i)

    @AddAPI("timer.remove", description="remove a timer")
    def _api_timer_remove(self, name: str):
        """Remove a timer.

        @Yname@w   = the name of the timer to remove.

        this function returns no values
        """
        try:
            if timer := self.timer_lookup[name]:
                log_to(
                    [self.plugin_id, timer.owner_id],
                    logging.DEBUG,
                    "_api_timer_remove - removing %s",
                    timer,
                )
                self._remove_timer_internal(timer)

        except KeyError:
            get_logger(self.plugin_id).error(
                "_api_timer_remove - could not remove timer %s", name, stack_info=True
            )

    @AddAPI("timer.toggle", description="toggle a timer to be enabled/disabled")
    def _api_timer_toggle(self, name: str, flag: bool):
        """Toggle a timer to be enabled/disabled.

        @Yname@w   = the name of the timer to toggle
        @Yflag@w   = True to enable, False to disable.

        this function returns no values
        """
        if name in self.timer_lookup:
            self.timer_lookup[name].enabled = flag

    def _add_timer_internal(self, timer: Timer):
        """Internally add a timer."""
        timer_next_time_to_fire = math.floor(timer.next_fire_datetime.timestamp())
        if timer_next_time_to_fire != -1:
            if timer_next_time_to_fire not in self.timer_events:
                self.timer_events[timer_next_time_to_fire] = []
            self.timer_events[timer_next_time_to_fire].append(timer)
        self.timer_lookup[timer.name] = timer

    def _remove_timer_internal(self, timer: Timer):
        """Internally remove a timer."""
        timer_next_time_to_fire = math.floor(timer.next_fire_datetime.timestamp())
        if timer_next_time_to_fire != -1 and timer_next_time_to_fire in self.timer_events:
            if timer in self.timer_events[timer_next_time_to_fire]:
                self.timer_events[timer_next_time_to_fire].remove(timer)
            if not self.timer_events[timer_next_time_to_fire]:
                del self.timer_events[timer_next_time_to_fire]
        if timer.name in self.timer_lookup:
            del self.timer_lookup[timer.name]

    def execute_timer(self, time, timer: Timer):
        """Executes and reschedules the given timer.

        Args:
            time: The current time when the timer is being executed.
            timer: The timer to be executed.

        Returns:
            None

        Raises:
            Exception: If an error occurs during the execution of the timer.

        """
        if timer.enabled:
            try:
                timer.execute()
                self.overall_fire_count = self.overall_fire_count + 1
                if timer.log:
                    log_to(
                        [self.plugin_id, timer.owner_id],
                        logging.DEBUG,
                        "check_for_timers_to_fire - timer fired: %s",
                        timer,
                    )
            except Exception:  # pylint: disable=broad-except
                log_to(
                    [self.plugin_id, timer.owner_id],
                    logging.ERROR,
                    "check_for_timers_to_fire - timer had an error: %s",
                    timer,
                    exc_info=True,
                )
        try:
            self.timer_events[time].remove(timer)
        except ValueError:
            log_to(
                [self.plugin_id, timer.owner_id],
                logging.ERROR,
                "check_for_timers_to_fire - timer %s did not exist in timerevents",
                timer.name,
            )
        if not timer.onetime:
            timer.next_fire_datetime = timer.get_next_fire()
            if timer.log:
                log_to(
                    [self.plugin_id, timer.owner_id],
                    logging.DEBUG,
                    "check_for_timers_to_fire - re adding timer %s for %s",
                    timer.name,
                    timer.next_fire_datetime.strftime("%a %b %d %Y %H:%M:%S %Z"),
                )
            self._add_timer_internal(timer)
        else:
            self.api(f"{self.plugin_id}:timer.remove")(timer.name)

    async def check_for_timers_to_fire(self):
        # this is a callback, so disable unused-argument
        # pylint: disable=unused-argument,too-many-nested-blocks
        """Check all timers."""
        firstrun: bool = True
        keepgoing: bool = True
        while keepgoing:
            now = datetime.datetime.now(datetime.UTC)
            if now != self.time_last_checked:
                if not firstrun:
                    diff = now - self.time_last_checked
                    if diff.total_seconds() > 1:
                        get_logger(self.plugin_id).warning(
                            "check_for_timers_to_fire - timer had to check multiple seconds: %s",
                            now - self.time_last_checked,
                        )
                else:
                    get_logger(self.plugin_id).debug("Checking timers coroutine has started")
                firstrun = False
                for i in range(
                    math.floor(self.time_last_checked.timestamp()),
                    math.floor(now.timestamp()) + 1,
                ):
                    if self.timer_events.get(i):
                        for timer in self.timer_events[i][:]:
                            self.execute_timer(i, timer)

                self.time_last_checked = now

            await asyncio.sleep(0.2)
