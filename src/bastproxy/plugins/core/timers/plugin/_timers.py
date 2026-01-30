# Project: bastproxy
# Filename: plugins/core/timers/_timers.py
#
# File Description: a plugin to handle timers
#
# By: Bast

# Standard Library
import asyncio
import datetime
import math
import sys
import time
from collections.abc import Callable

from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.callback import Callback
from bastproxy.libs.records import LogRecord

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser
from bastproxy.plugins.core.events import RegisterToEvent


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

    def get_first_fire(self) -> datetime.datetime:
        """Gets the first fire time of the timer.

        Returns:
            datetime: First fire time of the timer.
        """
        now = datetime.datetime.now(datetime.UTC)
        new_date = now + datetime.timedelta(seconds=self.seconds)
        if self.time:
            hour_minute = time.strptime(self.time, "%H%M")
            new_date = now.replace(
                hour=hour_minute.tm_hour, minute=hour_minute.tm_min, second=0
            )
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

    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        """Initialize the plugin."""
        LogRecord(
            f"initialize - lasttime:  {self.time_last_checked}",
            "debug",
            sources=[self.plugin_id],
        )()

        # setup the task to check for timers to fire
        self.api("libs.asynch:task.add")(
            self.check_for_timers_to_fire, "Timer Plugin task"
        )

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:get.current.event.record")():
            LogRecord(
                f"_eventcb_plugin_unloaded - removing timers for plugin {event_record['plugin_id']}",
                "debug",
                sources=[self.plugin_id, event_record["plugin_id"]],
            )()
            self.api(f"{self.plugin_id}:remove.data.for.plugin")(
                event_record["plugin_id"]
            )

    @AddParser(description="toggle log flag for a timer")
    @AddArgument("timername", help="the timer name", default="", nargs="?")
    def _command_log(self) -> tuple[bool, list[str]]:
        """Change the log flag for a timer."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message: list[str] = []
        if args["timername"] in self.timer_lookup:
            self.timer_lookup[args["timername"]].log = not self.timer_lookup[
                args["timername"]
            ].log
            message.append(
                f"changed log flag to {self.timer_lookup[args['timername']].log} for timer {args['timername']}"
            )
        else:
            message.append(f"timer {args['timername']} does not exist")

        return True, message

    # @RegisterPluginHook('stats')
    # def _phook_timer_stats(self, **kwargs):
    @RegisterToEvent(event_name="ev_plugin_{plugin_id}_stats")
    def _eventcb_timers_ev_plugins_stats(self):
        """Return stats for the plugin."""
        if event_record := self.api("plugins.core.events:get.current.event.record")():
            disabled = 0
            enabled = 0

            for i in self.timer_lookup:
                if self.timer_lookup[i].enabled:
                    enabled = enabled + 1
                else:
                    disabled = disabled + 1

            event_record["stats"]["Overall Timer Stats"] = {
                "showorder": ["Total", "Enabled", "Disabled", "Fired", "Memory Usage"],
                "Total": len(self.timer_lookup),
                "Enabled": enabled,
                "Disabled": disabled,
                "Fired": self.overall_fire_count,
                "Memory Usage": sys.getsizeof(self.timer_events),
            }

    @RegisterToEvent(event_name="ev_plugin_stats")
    def _eventcb_event_get_stats_for_plugin(self) -> None:
        """Get stats for a plugin."""
        if not (
            event_record := self.api("plugins.core.events:get.current.event.record")()
        ):
            return

        plugin_id = event_record["plugin_id"]
        timers = [
            timer.name
            for timer in self.timer_lookup.values()
            if timer.owner_id == plugin_id
        ]

        if not timers:
            return

        timers_str = "".join(f"{'':<23}{item}\n" for item in timers)

        event_record["stats"][f"{plugin_id} Timer Stats"] = {
            "showorder": ["Total Timers Owned", "Timers Owned"],
            "Total Timers Owned": len(timers),
            "Timers Owned": timers_str.strip(),
        }

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
        args = self.api("plugins.core.commands:get.current.command.args")()
        output_header_color = self.api("plugins.core.settings:get")(
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
                templatestring
                % ("Name", "Defined in", "Enabled", "Fired", "Next Fire"),
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

        return True, message

    @AddParser(description="get details for a timer")
    @AddArgument(
        "timers", help="a list of timers to get details", default=None, nargs="*"
    )
    def _command_detail(self) -> tuple[bool, list[str]]:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the details of a timer
        @CUsage@w: detail.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()
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
                        message.append(
                            f"{'Last Fire':<{columnwidth}} : {last_fire_time}"
                        )
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

        return True, message

    @AddAPI("has.timer", description="check if a timer exists")
    def _api_has_timer(self, name: str):
        """Check if a timer exists.

        @Yname@w   = the name of the timer to check.

        returns True if the timer exists, False otherwise
        """
        return name in self.timer_lookup

    @AddAPI("get.timer.next.fire", description="get the next fire time for a timer")
    def _api_get_timer_next_fire(self, name: str) -> datetime.datetime | None:
        """Get the next fire time for a timer.

        @Yname@w   = the name of the timer to check.

        returns the next fire time for the timer, or None if the timer does not exist
        """
        if name in self.timer_lookup:
            return self.timer_lookup[name].next_fire_datetime
        return None

    @AddAPI("add.timer", description="add a timer")
    def _api_add_timer(
        self, name: str, func: Callable, seconds: int, **kwargs
    ) -> Timer | None:
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
        plugin_id: str = self.api("libs.api:get.caller.owner")(
            ignore_owner_list=[self.plugin_id]
        )

        if "plugin_id" in kwargs:
            plugin_instance = self.api("libs.plugins.loader:get.plugin.instance")(
                kwargs["plugin_id"]
            )
            plugin_id = plugin_instance.plugin_id
            del kwargs["plugin_id"]

        if not plugin_id or not self.api("libs.plugins.loader:is.plugin.id")(plugin_id):
            LogRecord(
                f"_api_add_timer: timer {name} has no plugin, not adding",
                "error",
                sources=[self.plugin_id],
            )()
            return None

        if seconds <= 0:
            LogRecord(
                f"_api_add_timer: timer {name} has seconds <= 0, not adding",
                "error",
                sources=[self.plugin_id, plugin_id],
            )()
            return None
        if not func:
            LogRecord(
                f"_api_add_timer: timer {name} has no function, not adding",
                "error",
                sources=[self.plugin_id, plugin_id],
            )()
            return None

        if "unique" in kwargs and kwargs["unique"] and name in self.timer_lookup:
            LogRecord(
                f"_api_add_timer: timer {name} already exists, not adding",
                "error",
                sources=[self.plugin_id, plugin_id],
            )()
            return None

        timer = Timer(name, func, seconds, plugin_id, **kwargs)
        LogRecord(
            f"_api_add_timer: adding timer {name}",
            level="debug",
            sources=[self.plugin_id, plugin_id],
        )()
        self._add_timer_internal(timer)
        return timer

    @AddAPI("remove.data.for.plugin", description="remove all data for a plugin")
    def _api_remove_data_for_plugin(self, name: str):
        """Remove all timers associated with a plugin.

        @Yname@w   = the name of the plugin.

        this function returns no values
        """
        plugin_instance = self.api("libs.plugins.loader:get.plugin.instance")(name)
        LogRecord(
            f"removing timers for {name}", level="debug", sources=[self.plugin_id, name]
        )()
        timers_to_remove: list[str] = [
            i
            for i in self.timer_lookup
            if plugin_instance.plugin_id == self.timer_lookup[i].owner_id
        ]
        for i in timers_to_remove:
            self.api(f"{self.plugin_id}:remove.timer")(i)

    @AddAPI("remove.timer", description="remove a timer")
    def _api_remove_timer(self, name: str):
        """Remove a timer.

        @Yname@w   = the name of the timer to remove.

        this function returns no values
        """
        try:
            if timer := self.timer_lookup[name]:
                LogRecord(
                    f"_api_remove_timer - removing {timer}",
                    level="debug",
                    sources=[self.plugin_id, timer.owner_id],
                )()
                self._remove_timer_internal(timer)

        except KeyError:
            LogRecord(
                f"_api_remove_timer - could not remove timer {name}",
                level="error",
                sources=[self.plugin_id],
                stack_info=True,
            )()

    @AddAPI("toggle.timer", description="toggle a timer to be enabled/disabled")
    def _api_toggle_timer(self, name: str, flag: bool):
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
        if (
            timer_next_time_to_fire != -1
            and timer_next_time_to_fire in self.timer_events
        ):
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
                    LogRecord(
                        f"check_for_timers_to_fire - timer fired: {timer}",
                        level="debug",
                        sources=[self.plugin_id, timer.owner_id],
                    )()
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"check_for_timers_to_fire - timer had an error: {timer}",
                    level="error",
                    sources=[self.plugin_id, timer.owner_id],
                    exc_info=True,
                )()
        try:
            self.timer_events[time].remove(timer)
        except ValueError:
            LogRecord(
                f"check_for_timers_to_fire - timer {timer.name} did not exist in timerevents",
                level="error",
                sources=[self.plugin_id, timer.owner_id],
            )()
        if not timer.onetime:
            timer.next_fire_datetime = timer.get_next_fire()
            if timer.log:
                LogRecord(
                    f"check_for_timers_to_fire - re adding timer {timer.name} for {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}",
                    level="debug",
                    sources=[self.plugin_id, timer.owner_id],
                )()
            self._add_timer_internal(timer)
        else:
            self.api(f"{self.plugin_id}:remove.timer")(timer.name)

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
                        LogRecord(
                            f"check_for_timers_to_fire - timer had to check multiple seconds: {now - self.time_last_checked}",
                            level="warning",
                            sources=[self.plugin_id],
                        )()
                else:
                    LogRecord(
                        "Checking timers coroutine has started",
                        level="debug",
                        sources=[self.plugin_id],
                    )()
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
