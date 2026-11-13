# Project: bastproxy
# Filename: plugins/core/triggers/_triggers.py
#
# File Description: a plugin to handle internal triggers
#
# By: Bast

# Standard Library
import bisect
import logging
import sys
from typing import Any, TypedDict

# 3rd Party
import regex as re

# Project
from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser
from bastproxy.plugins.core.events import RegisterToEvent

# The "Triggers" section this plugin adds to a stats event record's "stats" dict.
# The keys are display labels, so the functional syntax is needed.
TriggerStats = TypedDict(
    "TriggerStats",
    {
        "showorder": list[str],
        "Total Triggers": int,
        "Enabled Triggers": int,
        "Disabled Triggers": int,
        "Overall Trigger Hits": int,
        "Triggers Memory Usage": int,
    },
)

# Keyword arguments trigger.add passes on to TriggerItem
_ADD_KEYWORDS = frozenset(
    {"enabled", "group", "omit", "priority", "stopevaluating", "argtypes", "matchcolor"}
)

_UPDATABLE_TRIGGER_KEYS = frozenset(
    {"regex", "enabled", "group", "omit", "priority", "stopevaluating", "argtypes", "matchcolor"}
)


def _order_key(item: "TriggerItem") -> tuple[int, int]:
    """Sort key for matching: lower priority first, then the order added."""
    return (item.priority, item.order)


class TriggerItem:
    def __init__(
        self,
        owner_id,
        trigger_name,
        regex,
        regex_id,
        original_regex,
        enabled=True,
        group=None,
        omit=False,
        priority=100,
        stopevaluating=False,
        argtypes=None,
        matchcolor=False,
        trigger_id=None,
        original_regex_compiled=None,
        order=0,
    ) -> None:
        """Initialize the instance."""
        self.api = API(owner_id=f"{owner_id}:{trigger_name}")
        self.enabled = enabled
        self.owner_id = owner_id
        self.trigger_name = trigger_name
        self.regex = regex
        self.regex_id = regex_id
        self.original_regex = original_regex
        self.original_regex_compiled = original_regex_compiled
        self.group = group
        self.omit = omit
        self.priority = priority
        self.stopevaluating = stopevaluating
        self.argtypes = argtypes
        self.matchcolor = matchcolor
        self.hits = 0
        self.order = order
        # True while another enabled trigger has the same pattern and text variant
        self.shared_pattern = False
        self._share_key: tuple[Any, bool] | None = None
        self.trigger_id = trigger_id
        self.event_name = f"event_{self.trigger_id}"

    def raisetrigger(self, args):
        """Raise an event for this trigger."""
        self.hits += 1
        if self.omit:
            args["line"].send = False

        args["trigger_name"] = self.trigger_name
        args["trigger_id"] = self.trigger_id

        args = self.api("plugins.core.events:event.raise")(self.event_name, event_args=args)
        log_to(
            [self.owner_id, "plugins.core.triggers"],
            logging.DEBUG,
            "raisetrigger - trigger %s raised event %s with args %s",
            self.trigger_id,
            self.event_name,
            args,
        )

        return args


class TriggersPlugin(BasePlugin):
    """a plugin to handle internal triggers."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance."""
        self.can_reload_f = False
        self.beall_id = self.create_trigger_id("beall", self.plugin_id)
        self.all_id = self.create_trigger_id("all", self.plugin_id)
        self.emptyline_id = self.create_trigger_id("emptyline", self.plugin_id)

        # The dictionary of triggers
        # This will likely get moved into the source plugin
        # key: trigger_id
        self.triggers = {}

        # The dictionary of trigger groups
        # key is group name
        # value is a list of trigger ids
        self.trigger_groups = {}

        # The enabled regex triggers, sorted by (priority, order added)
        self._ordered: list = []
        # enabled triggers per (compiled pattern, matchcolor) in _ordered
        self._share_counts: dict[tuple[Any, bool], int] = {}
        self._next_order = 0

        # Mirror of the "enabled" setting, kept current by _eventcb_enabled_modify
        # so the per-line check does not pay for a setting.get
        self._matching_enabled = True

    @RegisterPluginHook("after_load")
    def _phook_initialize(self):
        """Initialize the plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "enabled", "True", bool, "enable triggers"
        )

        self.api("plugins.core.triggers:trigger.add")("beall", None, self.plugin_id)
        self.api("plugins.core.triggers:trigger.add")("all", None, self.plugin_id)
        self.api("plugins.core.triggers:trigger.add")("emptyline", None, self.plugin_id)

    @RegisterToEvent(event_name="ev_{plugin_id}_var_enabled_modified")
    def _eventcb_enabled_modify(self):
        """Cache the enabled setting; the settings plugin raises this at load and on change."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._matching_enabled = bool(event_record["newvalue"])

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self.api(f"{self.plugin_id}:trigger.remove.for.owner")(event_record["plugin_id"])

    def _set_shared(self, key, shared):
        """Set ``shared_pattern`` on every item in the matching list with ``key``."""
        for existing in self._ordered:
            if existing._share_key == key:
                existing.shared_pattern = shared

    def _sync_order_remove(self, item):
        """Take an item out of the matching list."""
        for index, existing in enumerate(self._ordered):
            if existing is item:
                del self._ordered[index]
                break
        key = item._share_key
        if key is None:
            return
        item._share_key = None
        item.shared_pattern = False
        count = self._share_counts.get(key, 1) - 1
        if count > 0:
            self._share_counts[key] = count
            if count == 1:
                self._set_shared(key, False)
        else:
            self._share_counts.pop(key, None)

    def _sync_order(self, item):
        """Put an item in or out of the matching list to fit its state."""
        self._sync_order_remove(item)
        if item.enabled and item.original_regex_compiled is not None:
            bisect.insort(self._ordered, item, key=_order_key)
            key = (item.original_regex_compiled, bool(item.matchcolor))
            item._share_key = key
            count = self._share_counts.get(key, 0) + 1
            self._share_counts[key] = count
            if count == 2:
                self._set_shared(key, True)
            else:
                item.shared_pattern = count > 2

    @staticmethod
    def create_trigger_id(name, owner_id):
        """Get a unique name for a trigger."""
        return f"t_{owner_id}_{name}"

    @AddAPI("trigger.register", description="register a function to a trigger")
    def _api_trigger_register(self, trigger_name, function, **kwargs):
        """Register a function to a trigger.

        trigger_name is a trigger name or id.
        this function returns True on success, False (and logs an error) for an unknown trigger
        """
        trigger_id = trigger_name
        if trigger_id not in self.triggers:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
            trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "_api_trigger_register - could not find trigger %s",
                trigger_name,
            )
            return False
        self.api("plugins.core.events:event.register")(
            self.triggers[trigger_id].event_name, function, **kwargs
        )
        return True

    @AddAPI("trigger.unregister", description="unregister a function from a trigger")
    def _api_trigger_unregister(self, trigger_name, function):
        """Unregister a function from a trigger.

        trigger_name is a trigger name or id.
        this function returns True on success, False (and logs an error) for an unknown trigger
        """
        trigger_id = trigger_name
        if trigger_id not in self.triggers:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
            trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "_api_trigger_unregister - could not find trigger %s",
                trigger_name,
            )
            return False
        self.api("plugins.core.events:event.unregister")(
            self.triggers[trigger_id].event_name, function
        )
        return True

    @AddAPI("trigger.update", description="update a trigger without deleting it")
    def _api_trigger_update(self, trigger_name, trigger_data):
        """Update a trigger without deleting it."""
        owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        trigger_id = self.create_trigger_id(trigger_name, owner_id)

        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_update - could not find trigger %s (maybe %s)",
                trigger_name,
                owner_id,
            )
            return False

        item = self.triggers[trigger_id]

        unknown = [key for key in trigger_data if key not in _UPDATABLE_TRIGGER_KEYS]
        if unknown:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_update - trigger %s: unknown keys %s",
                trigger_name,
                unknown,
            )
            return False

        new_regex = None
        new_compiled = None
        if "regex" in trigger_data and trigger_data["regex"] != item.original_regex:
            new_regex = trigger_data["regex"]
            try:
                new_compiled = re.compile(new_regex)
            except re.error:
                log_to(
                    [self.plugin_id, owner_id],
                    logging.ERROR,
                    "_api_trigger_update - could not compile regex for trigger %s : %s",
                    trigger_name,
                    new_regex,
                    exc_info=True,
                )
                return False

        if new_regex is not None:
            item.regex = new_regex
            item.original_regex = new_regex
            item.original_regex_compiled = new_compiled

        for key, new_value in trigger_data.items():
            if key == "regex":
                continue
            old_value = getattr(item, key)
            if old_value == new_value:
                continue
            setattr(item, key, new_value)
            if key == "group":
                if old_value is not None and trigger_id in self.trigger_groups.get(old_value, []):
                    self.trigger_groups[old_value].remove(trigger_id)
                if new_value:
                    self.trigger_groups.setdefault(new_value, []).append(trigger_id)

        if new_regex is not None or {"enabled", "priority", "matchcolor"} & trigger_data.keys():
            self._sync_order(item)
        return True

    @AddAPI("trigger.add", description="add a trigger")
    def _api_trigger_add(self, trigger_name, regex, owner_id=None, **kwargs):  # pylint: disable=too-many-branches
        """Add a trigger.

        @Ytrigger_name@w   = The trigger name
        @Yregex@w    = the regular expression that matches this trigger
        @Yowner_id@w   = the id for the owner this comes from, added
              automatically if using the api through BaseClass
        @Ykeyword@w arguments:
          @Yenabled@w  = (optional) whether the trigger is enabled (default: True)
          @Ygroup@w    = (optional) the group the trigger is a member of
          @Yomit@w     = (optional) True to omit the line from the client,
                                  False otherwise
          @Yargtypes@w = (optional) a dict of keywords in the regex and their type
          @Ypriority@w = (optional) the priority of the trigger, default is 100
          @Ymatchcolor@w = (optional) match with color
          @Ystopevaluating@w = (optional) True to stop trigger evauluation if this
                                  trigger is matched.

        this function always returns a 2-tuple: (True, the new TriggerItem), or
        (False, None) on failure (and logs an error), so unpacking never raises
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        if not owner_id:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "_api_trigger_add - could not find an owner for trigger %s",
                trigger_name,
            )
            return False, None

        if unknown := sorted(set(kwargs) - _ADD_KEYWORDS):
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_add - trigger %s: unknown keywords %s",
                trigger_name,
                unknown,
            )
            return False, None

        trigger_id = self.create_trigger_id(trigger_name, owner_id)

        if trigger_id in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_add - trigger %s already exists in plugin: %s",
                trigger_name,
                self.triggers[trigger_id].owner_id,
            )
            return False, None

        args = kwargs.copy()

        original_regex = None

        args["trigger_id"] = trigger_id
        if "enabled" not in args:
            args["enabled"] = True

        if regex:
            original_regex = regex
            try:
                args["original_regex_compiled"] = re.compile(original_regex)
            except re.error:
                log_to(
                    [self.plugin_id, owner_id],
                    logging.ERROR,
                    "_api_trigger_add - Could not compile regex for trigger: %s : %s",
                    trigger_name,
                    original_regex,
                    exc_info=True,
                )
                return False, None

        if args.get("group"):
            if args["group"] not in self.trigger_groups:
                self.trigger_groups[args["group"]] = []
            self.trigger_groups[args["group"]].append(trigger_id)

        self.triggers[trigger_id] = TriggerItem(
            owner_id,
            trigger_name,
            original_regex,
            None,
            original_regex,
            order=self._next_order,
            **args,
        )
        self._next_order += 1
        self._sync_order(self.triggers[trigger_id])

        log_to(
            [self.plugin_id, owner_id],
            logging.DEBUG,
            "_api_trigger_add - added trigger %s (unique name: %s) for %s",
            trigger_name,
            trigger_id,
            owner_id,
        )

        return True, self.triggers[trigger_id]

    @AddAPI("trigger.remove", description="remove a trigger")
    def _api_trigger_remove(self, trigger_name, force=False, owner_id=None):
        """Remove a trigger.

        @Ytrigger_name@w   = The trigger name
        @Yforce@w         = True to remove it even if other functions
                                  are registered
           (default: False).

        this function returns True if the trigger was removed,
                                  False if it wasn't
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        if not owner_id:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "_api_trigger_remove - could not find owner for trigger %s",
                trigger_name,
            )
            return False

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_remove - trigger %s (maybe %s) does not exist",
                trigger_name,
                owner_id,
            )
            return False

        if (
            (
                event := self.api("plugins.core.events:event.get")(
                    self.triggers[trigger_id].event_name
                )
            )
            and not event.isempty()
            and not force
        ):
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_remove - trigger %s for %s has functions registered",
                trigger_name,
                owner_id,
            )
            return False

        self._sync_order_remove(self.triggers[trigger_id])

        group = self.triggers[trigger_id].group
        if group in self.trigger_groups:
            members = self.trigger_groups[group]
            self.trigger_groups[group] = [i for i in members if i != trigger_id]
            if not self.trigger_groups[group]:
                del self.trigger_groups[group]

        if trigger_id in self.triggers:
            del self.triggers[trigger_id]

        log_to(
            [self.plugin_id, owner_id],
            logging.DEBUG,
            "_api_trigger_remove - removed trigger %s for %s",
            trigger_name,
            owner_id,
        )

        return True

    @AddAPI("trigger.get", description="get a trigger")
    def _api_trigger_get(self, trigger_name, owner_id=None):
        """Get a trigger.

        @Ytrigger_name@w   = The trigger name.

        this function returns the TriggerItem, or None if there is none (a query: nothing is logged)
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        return self.triggers.get(trigger_id, None)

    @AddAPI("trigger.remove.for.owner", description="remove all triggers related to a owner")
    def _api_trigger_remove_for_owner(self, owner_id):
        """Remove all triggers related to a owner.

        @Yowner_id@w   = The owner id.

        this function returns True if every trigger was removed, False (and logs
        an error) if any removal failed
        """
        log_to(
            [self.plugin_id, owner_id],
            logging.DEBUG,
            "_api_trigger_remove_for_owner - removing triggers for %s",
            owner_id,
        )
        trigs = [
            trigger.trigger_name
            for trigger in self.triggers.values()
            if trigger.owner_id == owner_id
        ]
        all_removed = True
        for trigger in trigs:
            try:
                if not self.api("plugins.core.triggers:trigger.remove")(
                    trigger, force=True, owner_id=owner_id
                ):
                    all_removed = False
            except Exception:  # pylint: disable=broad-except
                log_to(
                    [self.plugin_id, owner_id],
                    logging.ERROR,
                    "_api_trigger_remove_for_owner - removing trigger %s failed",
                    trigger,
                    exc_info=True,
                )
                all_removed = False
        return all_removed

    @AddAPI("trigger.toggle.enable", description="toggle a trigger")
    def _api_trigger_toggle_enable(self, trigger_name, flag, owner_id=None):
        """Toggle a trigger.

        @Ytrigger_name@w = The trigger name
        @Yflag@w        = (optional) True to enable, False otherwise.

        this function returns True on success, False (and logs an error) for an unknown trigger
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "toggletrigger - trigger %s (maybe %s) does not exist",
                trigger_name,
                owner_id,
            )
            return False
        self.triggers[trigger_id].enabled = bool(flag)
        self._sync_order(self.triggers[trigger_id])
        return True

    @AddAPI("trigger.toggle.omit", description="toggle the omit flag for a trigger")
    def _api_trigger_toggle_omit(self, trigger_name, flag, owner_id=None):
        """Toggle a trigger.

        @Ytrigger_name@w = The trigger name
        @Yflag@w        = (optional) True to omit the line, False otherwise.

        this function returns True on success, False (and logs an error) for an unknown trigger
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "toggletriggeromit - trigger %s (maybe %s) does not exist",
                trigger_name,
                owner_id,
            )
            return False
        self.triggers[trigger_id].omit = flag
        return True

    @AddAPI("group.toggle.enable", description="toggle a trigger group")
    def _api_group_toggle_enable(self, trigger_group, flag):
        """Toggle a trigger group.

        @Ytrigger_group@w = The triggergroup name
        @Yflag@w        = (optional) True to enable, False otherwise.

        this function returns True on success, False (and logs an error) for an unknown group
        """
        get_logger(self.plugin_id).debug(
            "toggletriggergroup - toggling trigger group %s to %s", trigger_group, flag
        )
        if trigger_group not in self.trigger_groups:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "toggletriggergroup - trigger group %s does not exist",
                trigger_group,
            )
            return False
        # The group holds trigger ids, not names, so set each item directly.
        for trigger_id in self.trigger_groups[trigger_group]:
            if trigger_id in self.triggers:
                self.triggers[trigger_id].enabled = bool(flag)
                self._sync_order(self.triggers[trigger_id])
        return True

    def _match_line(self, line, data):
        """Raise the event of every enabled trigger whose regex matches the line.

        Triggers run in (priority, order added) order. Each one sees the line as
        it was when matching began, and a failing trigger does not stop the rest.
        Triggers that share a pattern (same text and flags) and the same text variant
        reuse one match for the line; each still builds its own ``groupdict()``.
        """
        match_logger = get_logger(self.plugin_id)
        debug = match_logger.isEnabledFor(logging.DEBUG)
        colorcoded = None
        matched = False
        # per-line match results, only for triggers that share a pattern (#383);
        # compiled patterns compare equal for the same text and flags
        shared_results: dict[tuple[Any, bool], Any] = {}
        for item in tuple(self._ordered):
            if not item.enabled or self.triggers.get(item.trigger_id) is not item:
                continue
            try:
                if item.matchcolor:
                    if colorcoded is None:
                        colorcoded = line.colorcoded
                    text = colorcoded
                else:
                    text = data
                if item.shared_pattern:
                    key = (item.original_regex_compiled, bool(item.matchcolor))
                    if key in shared_results:
                        match = shared_results[key]
                    else:
                        match = shared_results[key] = item.original_regex_compiled.match(text)
                else:
                    match = item.original_regex_compiled.match(text)
                if not match:
                    continue
                matched = True
                group_dict = match.groupdict()
                if item.argtypes:
                    for arg, argtype in item.argtypes.items():
                        # an optional group that did not take part stays None
                        if group_dict.get(arg) is not None:
                            group_dict[arg] = argtype(group_dict[arg])
                if debug:
                    match_logger.debug(
                        "_eventcb_check_trigger - line %s matched trigger %s",
                        line.colorcoded,
                        item.trigger_id,
                    )
                item.raisetrigger({"line": line, "matches": group_dict})
            except Exception:  # pylint: disable=broad-except
                log_to(
                    [self.plugin_id, item.owner_id],
                    logging.ERROR,
                    "_eventcb_check_trigger - trigger %s failed on line %s",
                    item.trigger_id,
                    data,
                    exc_info=True,
                )
                continue
            if item.stopevaluating:
                break
        if not matched and debug:
            match_logger.debug("_eventcb_check_trigger - line %s did not match any triggers", data)

    def _raise_builtin(self, trigger_id, event_record):
        """Raise a built-in trigger, only if something listens to it."""
        item = self.triggers[trigger_id]
        event = self.api("plugins.core.events:event.get")(item.event_name)
        if event and not event.isempty():
            item.raisetrigger(event_record)

    @RegisterToEvent(event_name="ev_to_client_data_modify")
    def _eventcb_check_trigger(self):
        """Check a line of text from the mud to see if it matches any triggers."""
        if not self._matching_enabled:
            return

        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return

        # don't check internal data
        line = event_record["line"]
        if line.internal:
            return

        data = line.noansi
        self._raise_builtin(self.beall_id, event_record)

        if data == "":
            self._raise_builtin(self.emptyline_id, event_record)
        else:
            self._match_line(line, data)

        self._raise_builtin(self.all_id, event_record)

    @AddParser(description="list triggers")
    @AddArgument(
        "match",
        help="list only triggers that contain this string in them",
        default="",
        nargs="?",
    )
    def _command_list(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list triggers and the plugins they are defined in
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        trigger_ids = self.triggers.keys()
        trigger_ids = sorted(trigger_ids)
        match = args["match"]

        template = "%-25s : %-30s %-9s %-5s %s"

        message = [
            template % ("Name", "Defined in", "Enabled", "Hits", "Id"),
            "@B" + "-" * 60 + "@w",
        ]
        for trigger_id in trigger_ids:
            trigger = self.triggers[trigger_id]
            if not match or match in trigger_id or trigger.owner_id == match:
                message.append(
                    template
                    % (
                        trigger.trigger_name,
                        trigger.owner_id,
                        trigger.enabled,
                        trigger.hits,
                        trigger_id,
                    )
                )

        return True, message

    @RegisterToEvent(event_name="ev_plugin_{plugin_id}_stats")
    def _eventcb_triggers_ev_plugins_stats(self):
        """Return stats for the plugin."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            overall_hit_count = 0
            total_enabled_triggers = 0
            total_disabled_triggers = 0
            for trigger in self.triggers:
                overall_hit_count = overall_hit_count + self.triggers[trigger].hits
                if self.triggers[trigger].enabled:
                    total_enabled_triggers = total_enabled_triggers + 1
                else:
                    total_disabled_triggers = total_disabled_triggers + 1

            stats: TriggerStats = {
                "showorder": [
                    "Total Triggers",
                    "Enabled Triggers",
                    "Disabled Triggers",
                    "Overall Trigger Hits",
                    "Triggers Memory Usage",
                ],
                "Total Triggers": len(self.triggers),
                "Enabled Triggers": total_enabled_triggers,
                "Disabled Triggers": total_disabled_triggers,
                "Overall Trigger Hits": overall_hit_count,
                "Triggers Memory Usage": sys.getsizeof(self.triggers),
            }
            event_record["stats"]["Triggers"] = stats

    @AddParser(description="get details for triggers")
    @AddArgument("trigger", help="the trigger to detail", default=[], nargs="*")
    def _command_detail(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the details of a trigger
        @CUsage@w: detail.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message = []
        if args["trigger"]:
            columnwidth = 24

            for trigger in args["trigger"]:
                if trigger in self.triggers:
                    event_name = self.triggers[trigger].event_name
                    message.extend(
                        (
                            f"{'Name':<{columnwidth}} : {self.triggers[trigger].trigger_name}",
                            f"{'Internal Id':<{columnwidth}} : {self.triggers[trigger].trigger_id}",
                            f"{'Defined in':<{columnwidth}} : {self.triggers[trigger].owner_id}",
                            f"{'Enabled':<{columnwidth}} : {self.triggers[trigger].enabled}",
                            f"{'Regex':<{columnwidth}} : {self.triggers[trigger].original_regex}",
                            f"{'Event Name':<{columnwidth}} : {self.triggers[trigger].event_name}",
                            f"{'Match Color':<{columnwidth}} : {self.triggers[trigger].matchcolor}",
                            f"{'Group':<{columnwidth}} : {self.triggers[trigger].group}",
                        )
                    )
                    if self.triggers[trigger].argtypes:
                        message.append(
                            f"{'Argument Types':<{columnwidth}} : {self.triggers[trigger].argtypes}"
                        )
                    message.extend(
                        (
                            f"{'Priority':<{columnwidth}} : {self.triggers[trigger].priority}",
                            f"{'Omit':<{columnwidth}} : {self.triggers[trigger].omit}",
                            f"{'Hits':<{columnwidth}} : {self.triggers[trigger].hits}",
                            f"{'Stop Evaluating':<{columnwidth}} : {self.triggers[trigger].stopevaluating}",
                        )
                    )
                    if self.api("plugins.core.events:event.exists")(event_name):
                        message.extend(("", "Event Details:"))
                        event_details = self.api("plugins.core.events:event.detail.get")(event_name)
                        message.extend(event_details)
                    else:
                        message.extend(["", "No functions registered for this trigger"])
                else:
                    message.append(f"trigger {trigger} does not exist")
        else:
            message.append("Please provide a trigger name")

        return True, message
