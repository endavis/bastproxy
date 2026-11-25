# Project: bastproxy
# Filename: plugins/core/watch/_watch.py
#
# File Description: a plugin to watch for commands from the client
#
# By: Bast

# Standard Library
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import echo_off_placeholder, get_logger, log_to
from bastproxy.libs.records import UpdateFlag

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

# runs after the commands plugin's callback (50), so a rewrite is not parsed as a
# proxy command, and before aliases (55) and variables (60), so a rewritten line
# is still expanded
WATCH_PRIORITY = 52


@dataclass(slots=True)
class WatchItem:
    """One registered watch: a compiled client-input regex and its hit count."""

    name: str
    regex: str
    owner: str
    event_name: str
    compiled: re.Pattern[str]
    hits: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class WatchPlugin(BasePlugin):
    """a plugin to watch for commands coming from the client."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.can_reload_f = False

        self.regex_lookup: dict[str, str] = {}
        self.watch_data: dict[str, WatchItem] = {}

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded."""
        event_record = self.api("plugins.core.events:event.current.record.get")()
        log_to(
            [self.plugin_id, event_record["plugin_id"]],
            logging.DEBUG,
            "event_plugin_unloaded - removing watches for plugin %s",
            event_record["plugin_id"],
        )
        self.api(f"{self.plugin_id}:watch.remove.for.plugin")(event_record["plugin_id"])

    @AddParser(description="list watches")
    @AddArgument(
        "match",
        help="list only watches that have this argument in them",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List watches."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        watches = sorted(self.watch_data.keys())
        match = args["match"]

        template = "%-25s : %-13s %s"
        rule_width = min(60, self.api("plugins.core.proxy:line.length.get")())

        message = [
            template % ("Name", "Defined in", "Hits"),
            "@B" + "-" * rule_width + "@w",
        ]
        for watch_name in watches:
            watch = self.watch_data[watch_name]
            if not match or match in watch_name or watch.owner == match:
                message.append(template % (watch_name, watch.owner, watch.hits))

        return CommandResult(True, message)

    @AddParser(description="get details of a watch")
    @AddArgument("watch", help="the trigger to detail", default=[], nargs="*")
    def _command_detail(self) -> CommandResult:
        """List the details of a watch."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args["watch"]:
            columnwidth = 13
            for watch in args["watch"]:
                if watch in self.watch_data:
                    item = self.watch_data[watch]
                    watch_event = self.api("plugins.core.events:event.detail.get")(item.event_name)
                    message.extend(
                        (
                            f"{'Name':<{columnwidth}} : {watch}",
                            f"{'Defined in':<{columnwidth}} : {item.owner}",
                            f"{'Regex':<{columnwidth}} : {item.regex}",
                            f"{'Hits':<{columnwidth}} : {item.hits}",
                        )
                    )
                    message.extend(watch_event)
                else:
                    message.append(f"watch {watch} does not exist")
        else:
            message.append("Please provide a watch name")

        return CommandResult(True, message)

    @AddAPI("watch.add", description="add a watch")
    def _api_watch_add(
        self, watch_name: str, regex: str, owner: str | None = None, **kwargs: Any
    ) -> bool:
        """Add a command watch.

        @Ywatch_name@w   = name
        @Yregex@w    = the regular expression that matches this command
        @Yplugin@w   = the plugin this comes from
        @Ykeyword args@w arguments:
          stored unchanged in the watch's `extra` dict.

        The regex is matched against the typed line with surrounding whitespace
        stripped. A callback registered to the watch's event receives the args
        `matched`, `cmdname`, `data` (the stripped text) and `line`, the
        `NetworkDataLine` being sent: set `line.line` to rewrite it, or
        `line.send = False` to stop it.

        Adding an existing name replaces that watch. This function returns True
        when the watch was added or replaced. It returns False, changing nothing,
        when no owner can be found, the regex does not compile, or the regex
        already belongs to a watch with a different name.
        """
        if not owner:
            owner = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        if not owner:
            get_logger(self.plugin_id).error(
                "_api_watch_add: no plugin could be found to add %s", watch_name
            )
            return False

        try:
            compiled = re.compile(regex)
        except re.error:
            log_to(
                [self.plugin_id, owner],
                logging.ERROR,
                "_api_watch_add: watch %s failed to compile regex %s",
                watch_name,
                regex,
                exc_info=True,
            )
            return False

        existing_name = self.regex_lookup.get(regex)
        if existing_name is not None and existing_name != watch_name:
            log_to(
                [self.plugin_id, owner],
                logging.WARNING,
                "_api_watch_add: watch %s tried to add a regex that already existed for %s",
                watch_name,
                existing_name,
            )
            return False

        old = self.watch_data.get(watch_name)
        if old and self.regex_lookup.get(old.regex) == watch_name:
            del self.regex_lookup[old.regex]

        item = WatchItem(
            name=watch_name,
            regex=regex,
            owner=owner,
            event_name=f"watch_{watch_name}",
            compiled=compiled,
            extra=dict(kwargs),
        )
        self.watch_data[watch_name] = item
        self.regex_lookup[regex] = watch_name
        log_to(
            [self.plugin_id, owner],
            logging.DEBUG,
            "_api_watch_add: watch %s added for %s",
            watch_name,
            owner,
        )

        # add the event so it can be tracked
        self.api("plugins.core.events:event.add")(
            item.event_name,
            item.owner,
            description=[f"event for {watch_name} for {regex}"],
            arg_descriptions={
                "matched": "The matched arguments from the regex",
                "cmdname": "The command name that was matched",
                "data": "The data that was matched",
                "line": (
                    "The NetworkDataLine being sent; set .line to rewrite it "
                    "or .send = False to stop it"
                ),
            },
        )
        return True

    @AddAPI("watch.remove", description="remove a watch")
    def _api_watch_remove(self, watch_name: str, force: bool = False) -> bool:
        """Remove a command watch.

        @Ywatch_name@w   = The watch name
        @Yforce@w       = force removal if functions are registered.

        this function returns True if the watch was removed. It returns False
        when the watch does not exist, or when functions are registered to it
        and force is not set.
        """
        if watch_name not in self.watch_data:
            get_logger(self.plugin_id).error(
                "_api_watch_remove: watch %s does not exist", watch_name
            )
            return False

        item = self.watch_data[watch_name]
        plugin = item.owner
        if not force and self.api("plugins.core.events:event.has.registrations")(item.event_name):
            log_to(
                [self.plugin_id, plugin],
                logging.ERROR,
                "_api_watch_remove: watch %s for plugin %s has functions registered",
                watch_name,
                plugin,
            )
            return False
        if self.regex_lookup.get(item.regex) == watch_name:
            del self.regex_lookup[item.regex]
        del self.watch_data[watch_name]
        self.api("plugins.core.events:event.remove")(item.event_name, force=True)
        log_to(
            [self.plugin_id, plugin],
            logging.DEBUG,
            "_api_watch_remove: watch %s for plugin %s removed",
            watch_name,
            plugin,
        )
        return True

    @AddAPI("watch.remove.for.plugin", description="remove all watches for a plugin")
    def _api_watch_remove_for_plugin(self, plugin: str) -> None:
        """Remove all watches related to a plugin.

        @Yplugin@w   = The plugin.

        this function returns no values
        """
        log_to(
            [self.plugin_id, plugin],
            logging.DEBUG,
            "_api_watch_remove_for_plugin: removing watches for plugin %s",
            plugin,
        )
        for name, item in list(self.watch_data.items()):
            if item.owner == plugin:
                self.api(f"{self.plugin_id}:watch.remove")(name)

    @RegisterToEvent(event_name="ev_to_mud_data_modify", priority=WATCH_PRIORITY)
    def _eventcb_check_command(self) -> None:
        """Check input from the client and see if we are watching for it.

        The line is matched stripped, as the old proxy did. A callback gets the
        line as ``args["line"]``: setting ``.line`` rewrites it and ``.send = False``
        stops it.
        """
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if not line.is_io:
            return
        client_data = line.line.strip()
        for watch_name, item in list(self.watch_data.items()):
            if match_data := item.compiled.match(client_data):
                item.hits += 1
                match_args = {
                    "matched": match_data.groupdict(),
                    "cmdname": f"cmd_{watch_name}",
                    "data": client_data,
                    "line": line,
                }
                get_logger(self.plugin_id).debug(
                    "_eventcb_check_command: watch %s matched %s, raising %s",
                    watch_name,
                    echo_off_placeholder(client_data) if line.mask_log else client_data,
                    match_args["cmdname"],
                )
                before = (line.line, line.send)
                self.api("plugins.core.events:event.raise")(item.event_name, event_args=match_args)
                if line.line != before[0]:
                    event_record.addupdate(
                        UpdateFlag.MODIFY, f"watch {watch_name} rewrote the line", savedata=False
                    )
                if line.send != before[1]:
                    event_record.addupdate(
                        UpdateFlag.MODIFY, f"watch {watch_name} stopped the line", savedata=False
                    )
