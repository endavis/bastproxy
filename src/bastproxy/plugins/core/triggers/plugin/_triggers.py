# Project: bastproxy
# Filename: plugins/core/triggers/_triggers.py
#
# File Description: a plugin to handle internal triggers
#
# By: Bast

# Standard Library
import bisect
import dataclasses
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict, cast

# 3rd Party
import regex as re

# Project
from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.records import NetworkData, NetworkDataLine, SendDataDirectlyToMud
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

from ._conditions import Condition, check, parse_conditions
from ._echo import EchoRecord
from ._prompt import PromptQueue
from ._waiters import (
    DEFAULT_MAX_LINES,
    DEFAULT_TIMEOUT,
    LineWaiter,
    WaiterRegistry,
    WaitResult,
)

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
    {
        "enabled",
        "group",
        "omit",
        "priority",
        "stopevaluating",
        "argtypes",
        "matchcolor",
        "when",
        "on_prompt",
    }
)

_UPDATABLE_TRIGGER_KEYS = frozenset(
    {
        "regex",
        "enabled",
        "group",
        "omit",
        "priority",
        "stopevaluating",
        "argtypes",
        "matchcolor",
        "when",
        "on_prompt",
    }
)


def _order_key(item: "TriggerItem") -> tuple[int, int]:
    """Sort key for matching: lower priority first, then the order added."""
    return (item.priority, item.order)


class TriggerItem:
    def __init__(
        self,
        owner_id: str,
        trigger_name: str,
        regex: str | None,
        regex_id: str | None,
        original_regex: str | None,
        enabled: bool = True,
        group: str | None = None,
        omit: bool = False,
        priority: int = 100,
        stopevaluating: bool = False,
        argtypes: dict[str, Callable[[str], Any]] | None = None,
        matchcolor: bool = False,
        trigger_id: str | None = None,
        original_regex_compiled: re.Pattern[str] | None = None,
        order: int = 0,
        when: dict[str, str] | None = None,
        conditions: tuple[Condition, ...] = (),
        on_prompt: bool = False,
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
        # GMCP conditions: the original mapping and its parsed form
        self.when = when
        self.conditions = conditions
        # True to hold the trigger's events until the next prompt line (#544)
        self.on_prompt = on_prompt
        # True while another enabled trigger has the same pattern and text variant
        self.shared_pattern = False
        self._share_key: tuple[Any, bool] | None = None
        self.trigger_id = trigger_id
        self.event_name = f"event_{self.trigger_id}"

    def raisetrigger(self, args: dict[str, Any], apply_omit: bool = True) -> Any:
        """Raise an event for this trigger.

        ``apply_omit`` is False for an event held for a prompt: its line was omitted
        when it matched, and by now the line has been sent on.
        """
        self.hits += 1
        if self.omit and apply_omit:
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


@dataclasses.dataclass(slots=True)
class TriggerAddResult:
    """The result of ``plugins.core.triggers:trigger.add``."""

    success: bool
    trigger: TriggerItem | None


async def _none_result() -> WaitResult | None:
    """An awaitable that resolves to None, for a waiter API that failed (#548)."""
    return None


class TriggersPlugin(BasePlugin):
    """a plugin to handle internal triggers."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.can_reload_f = False
        self.beall_id = self.create_trigger_id("beall", self.plugin_id)
        self.all_id = self.create_trigger_id("all", self.plugin_id)
        self.emptyline_id = self.create_trigger_id("emptyline", self.plugin_id)
        self.prompt_id = self.create_trigger_id("prompt", self.plugin_id)

        # The dictionary of triggers
        # This will likely get moved into the source plugin
        # key: trigger_id
        self.triggers: dict[str, TriggerItem] = {}

        # The dictionary of trigger groups
        # key is group name
        # value is a list of trigger ids
        self.trigger_groups: dict[str, list[str]] = {}

        # The enabled regex triggers, sorted by (priority, order added)
        self._ordered: list[TriggerItem] = []
        # enabled triggers per (compiled pattern, matchcolor) in _ordered
        self._share_counts: dict[tuple[Any, bool], int] = {}
        self._next_order = 0

        # Mirror of the "enabled" setting, kept current by _eventcb_enabled_modify
        # so the per-line check does not pay for a setting.get
        self._matching_enabled = True

        # Lines the proxy sent to the MUD, so the MUD's echo of one is not matched (#545)
        self._echoes = EchoRecord()

        # True once the MUD has sent a line marked as a prompt (GA/EOR). Until then
        # on_prompt triggers fire at once, as a MUD without GA/EOR never ends a burst.
        self._prompts_seen = False
        # Events of on_prompt triggers waiting for the next prompt (#544)
        self._pending = PromptQueue()
        # Open line waiters, fed from ev_to_client_data_modify (#548)
        self._waiters = WaiterRegistry(sender=self._send_to_mud)

    @RegisterPluginHook("after_load")
    def _phook_initialize(self) -> None:
        """Initialize the plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "enabled", "True", bool, "enable triggers"
        )

        self.api("plugins.core.triggers:trigger.add")("beall", None, self.plugin_id)
        self.api("plugins.core.triggers:trigger.add")("all", None, self.plugin_id)
        self.api("plugins.core.triggers:trigger.add")("emptyline", None, self.plugin_id)
        self.api("plugins.core.triggers:trigger.add")("prompt", None, self.plugin_id)

    @RegisterToEvent(event_name="ev_{plugin_id}_var_enabled_modified")
    def _eventcb_enabled_modify(self) -> None:
        """Cache the enabled setting; the settings plugin raises this at load and on change."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._matching_enabled = bool(event_record["newvalue"])

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self.api(f"{self.plugin_id}:trigger.remove.for.owner")(event_record["plugin_id"])

    def _set_shared(self, key: tuple[Any, bool], shared: bool) -> None:
        """Set ``shared_pattern`` on every item in the matching list with ``key``."""
        for existing in self._ordered:
            if existing._share_key == key:
                existing.shared_pattern = shared

    def _sync_order_remove(self, item: TriggerItem) -> None:
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

    def _sync_order(self, item: TriggerItem) -> None:
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
    def create_trigger_id(name: str, owner_id: str) -> str:
        """Get a unique name for a trigger."""
        return f"t_{owner_id}_{name}"

    @AddAPI("trigger.register", description="register a function to a trigger")
    def _api_trigger_register(
        self, trigger_name: str, function: Callable[..., Any], **kwargs: Any
    ) -> bool:
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
    def _api_trigger_unregister(self, trigger_name: str, function: Callable[..., Any]) -> bool:
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
    def _api_trigger_update(self, trigger_name: str, trigger_data: dict[str, Any]) -> bool:
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

        new_conditions: tuple[Condition, ...] = ()
        if trigger_data.get("when") is not None:
            try:
                new_conditions = parse_conditions(trigger_data["when"])
            except ValueError as err:
                log_to(
                    [self.plugin_id, owner_id],
                    logging.ERROR,
                    "_api_trigger_update - trigger %s: %s",
                    trigger_name,
                    err,
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
            if key == "when":
                item.when = dict(new_value) if new_value else None
                item.conditions = new_conditions
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
    def _api_trigger_add(  # pylint: disable=too-many-branches
        self, trigger_name: str, regex: str | None, owner_id: str | None = None, **kwargs: Any
    ) -> TriggerAddResult:
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
          @Yon_prompt@w = (optional) True to hold the trigger's events until the next
                                  prompt line (GA/EOR) after the burst it matched in;
                                  the callback gets the prompt line as args["prompt"]
          @Ywhen@w     = (optional) a dict of dotted GMCP paths to comparison strings,
                                  such as {"Char.Vitals.hp": ">50"}; the trigger
                                  raises its event only when every one holds

        returns a TriggerAddResult: success=True with trigger set to the new
        TriggerItem, or success=False with trigger None on failure (and logs an
        error). Check result.success before using result.trigger.
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
            return TriggerAddResult(False, None)

        if unknown := sorted(set(kwargs) - _ADD_KEYWORDS):
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_add - trigger %s: unknown keywords %s",
                trigger_name,
                unknown,
            )
            return TriggerAddResult(False, None)

        trigger_id = self.create_trigger_id(trigger_name, owner_id)

        if trigger_id in self.triggers:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_add - trigger %s already exists in plugin: %s",
                trigger_name,
                self.triggers[trigger_id].owner_id,
            )
            return TriggerAddResult(False, None)

        args = kwargs.copy()

        try:
            args["conditions"] = parse_conditions(args.get("when"))
        except ValueError as err:
            log_to(
                [self.plugin_id, owner_id],
                logging.ERROR,
                "_api_trigger_add - trigger %s: %s",
                trigger_name,
                err,
            )
            return TriggerAddResult(False, None)
        args["when"] = dict(args["when"]) if args.get("when") else None

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
                return TriggerAddResult(False, None)

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

        return TriggerAddResult(True, self.triggers[trigger_id])

    @AddAPI("trigger.remove", description="remove a trigger")
    def _api_trigger_remove(
        self, trigger_name: str, force: bool = False, owner_id: str | None = None
    ) -> bool:
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
    def _api_trigger_get(
        self, trigger_name: str, owner_id: str | None = None
    ) -> TriggerItem | None:
        """Get a trigger.

        @Ytrigger_name@w   = The trigger name.

        this function returns the TriggerItem, or None if there is none (a query: nothing is logged)
        """
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        return self.triggers.get(trigger_id, None)

    @AddAPI("trigger.remove.for.owner", description="remove all triggers related to a owner")
    def _api_trigger_remove_for_owner(self, owner_id: str) -> bool:
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
    def _api_trigger_toggle_enable(
        self, trigger_name: str, flag: bool, owner_id: str | None = None
    ) -> bool:
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
    def _api_trigger_toggle_omit(
        self, trigger_name: str, flag: bool, owner_id: str | None = None
    ) -> bool:
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
    def _api_group_toggle_enable(self, trigger_group: str, flag: bool) -> bool:
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

    def _match_line(self, line: NetworkDataLine, data: str) -> None:
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
            if not item.enabled or self.triggers.get(cast(str, item.trigger_id)) is not item:
                continue
            try:
                if item.matchcolor:
                    if colorcoded is None:
                        colorcoded = line.colorcoded
                    text = colorcoded
                else:
                    text = data
                if item.shared_pattern:
                    compiled = cast(re.Pattern[str], item.original_regex_compiled)
                    key = (item.original_regex_compiled, bool(item.matchcolor))
                    if key in shared_results:
                        match = shared_results[key]
                    else:
                        match = shared_results[key] = compiled.match(text)
                else:
                    match = cast(re.Pattern[str], item.original_regex_compiled).match(text)
                if not match:
                    continue
                if item.conditions and not self._conditions_hold(item):
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
                self._fire(item, {"line": line, "matches": group_dict}, line)
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

    def _fire(self, item: TriggerItem, args: dict[str, Any], line: NetworkDataLine) -> None:
        """Raise a matched trigger's event, or hold it for the next prompt (#544)."""
        if item.on_prompt:
            if self._prompts_seen:
                if item.omit:
                    line.send = False
                self._pending.add(item, args)
                return
            args["prompt"] = None
        item.raisetrigger(args)

    def _raise_pending(
        self, entries: list[tuple[TriggerItem, dict[str, Any]]], prompt: NetworkDataLine | None
    ) -> None:
        """Raise events that were held; skip a trigger removed or disabled meanwhile."""
        for item, args in entries:
            if not item.enabled or self.triggers.get(cast(str, item.trigger_id)) is not item:
                continue
            args["prompt"] = prompt
            try:
                item.raisetrigger(args, apply_omit=False)
            except Exception:  # pylint: disable=broad-except
                log_to(
                    [self.plugin_id, item.owner_id],
                    logging.ERROR,
                    "_raise_pending - trigger %s failed",
                    item.trigger_id,
                    exc_info=True,
                )

    def _prompt_arrived(self, line: NetworkDataLine, event_record: dict[str, Any]) -> None:
        """A prompt line passed through: raise held events, then the ``prompt`` trigger."""
        self._raise_pending(self._pending.take_all(), line)
        self._raise_builtin(self.prompt_id, event_record)

    @RegisterToEvent(event_name="ev_libs.net.mud_muddisconnect")
    def _eventcb_prompts_disconnect(self) -> None:
        """The MUD link closed: forget prompts seen and drop held events."""
        self._prompts_seen = False
        self._pending.clear()

    def _conditions_hold(self, item: TriggerItem) -> bool:
        """Whether every GMCP condition of the trigger holds right now."""
        if check(item.conditions, self.api("libs.net.protocols:gmcp.cache.get")):
            return True
        log_to(
            [self.plugin_id, item.owner_id],
            logging.DEBUG,
            "_conditions_hold - trigger %s matched but its conditions did not hold: %s",
            item.trigger_id,
            item.when,
        )
        return False

    def _raise_builtin(self, trigger_id: str, event_record: dict[str, Any]) -> None:
        """Raise a built-in trigger, only if something listens to it."""
        item = self.triggers[trigger_id]
        event = self.api("plugins.core.events:event.get")(item.event_name)
        if event and not event.isempty():
            item.raisetrigger(event_record)

    @RegisterToEvent(event_name="ev_to_mud_data_read")
    def _eventcb_record_sent(self) -> None:
        """Record a line a plugin or trigger sent, so its echo skips matching (#545)."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if line.internal and line.is_io and isinstance(line.line, str):
            self._echoes.add(line.noansi.rstrip("\r\n"))

    @RegisterToEvent(event_name="ev_to_client_data_modify")
    def _eventcb_check_trigger(self) -> None:
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
        # getattr: a line-like object without the flag counts as no prompt
        is_prompt = bool(getattr(line, "is_prompt", False))
        if is_prompt:
            self._prompts_seen = True
        if self._pending:
            self._raise_pending(self._pending.take_expired(), None)
        self._raise_builtin(self.beall_id, event_record)

        if data == "":
            self._raise_builtin(self.emptyline_id, event_record)
        elif not self._echoes.consume(data):
            self._match_line(line, data)

        if is_prompt:
            self._prompt_arrived(line, event_record)

        self._raise_builtin(self.all_id, event_record)

    @AddParser(description="list triggers")
    @AddArgument(
        "match",
        help="list only triggers that contain this string in them",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list triggers and the plugins they are defined in
        @CUsage@w: list.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        trigger_ids = sorted(self.triggers.keys())
        match = args["match"]

        template = "%-25s : %-30s %-9s %-5s %s"
        rule_width = min(60, self.api("plugins.core.proxy:line.length.get")())

        message = [
            template % ("Name", "Defined in", "Enabled", "Hits", "Id"),
            "@B" + "-" * rule_width + "@w",
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

        return CommandResult(True, message)

    @RegisterToEvent(event_name="ev_{plugin_id}_stats")
    def _eventcb_triggers_ev_plugins_stats(self) -> None:
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
    def _command_detail(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the details of a trigger
        @CUsage@w: detail.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
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
                    if self.triggers[trigger].on_prompt:
                        message.append(f"{'On Prompt':<{columnwidth}} : True")
                    if self.triggers[trigger].conditions:
                        message.append(
                            f"{'Conditions':<{columnwidth}} : {self.triggers[trigger].when}"
                        )
                    message.extend(
                        (
                            f"{'Priority':<{columnwidth}} : {self.triggers[trigger].priority}",
                            f"{'Omit':<{columnwidth}} : {self.triggers[trigger].omit}",
                            f"{'Hits':<{columnwidth}} : {self.triggers[trigger].hits}",
                            f"{'Stop Evaluating':<{columnwidth}} : "
                            ""
                            f"{self.triggers[trigger].stopevaluating}",
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

        return CommandResult(True, message)

    # --- waiting for output (#548) -------------------------------------------------

    def _send_to_mud(self, command: str, owner_id: str) -> None:
        """Send a command to the MUD for a waiter."""
        SendDataDirectlyToMud(NetworkData(command, owner_id=f"{owner_id}:waiter"))()

    @RegisterToEvent(event_name="ev_to_client_data_modify", priority=40)
    def _eventcb_feed_waiters(self) -> None:
        """Offer each MUD line to the open waiters, before triggers see it."""
        if not self._waiters:
            return
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if line.internal:
            return
        self._waiters.feed(line.noansi, line.is_prompt)

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_close_waiters_on_unload(self) -> None:
        """Close the waiters of a plugin that was unloaded."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self.api(f"{self.plugin_id}:waiter.remove.for.owner")(event_record["plugin_id"])

    def _waiter_owner(self, owner_id: str | None, what: str) -> str | None:
        """Resolve the owner for a waiter API, logging an error if there is none."""
        if not owner_id:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        if not owner_id:
            log_to([self.plugin_id], logging.ERROR, "%s - could not find an owner", what)
            return None
        return cast(str, owner_id)

    @AddAPI("waiter.add", description="open a waiter that queues MUD lines")
    def _api_waiter_add(
        self, owner_id: str | None = None, max_lines: int = DEFAULT_MAX_LINES
    ) -> LineWaiter | None:
        """Open a LineWaiter that queues MUD lines from now on.

        @Yowner_id@w   = the owner, added automatically through the api
        @Ymax_lines@w  = the most lines queued; the oldest are dropped

        Use it as a context manager, or call close(). Returns None (and logs
        an error) if no owner is found.
        """
        if (owner := self._waiter_owner(owner_id, "_api_waiter_add")) is None:
            return None
        return self._waiters.add(owner, max_lines)

    @AddAPI("waiter.remove.for.owner", description="close all waiters of an owner")
    def _api_waiter_remove_for_owner(self, owner_id: str) -> int:
        """Close every waiter of an owner; returns how many were closed."""
        return self._waiters.close_for_owner(owner_id)

    @AddAPI("waiter.count", description="the number of open waiters")
    def _api_waiter_count(self) -> int:
        """Return the number of open waiters."""
        return len(self._waiters)

    @AddAPI("line.get.next", description="wait for the next MUD line matching a pattern")
    def _api_line_get_next(
        self, pattern: str, timeout: float = DEFAULT_TIMEOUT, owner_id: str | None = None
    ) -> Awaitable[WaitResult | None]:
        """Return an awaitable that resolves to the next line matching ``pattern``.

        The pattern is matched with ``.match()``. Resolves to None on timeout
        or error (logged). Nothing is registered until it is awaited.
        """
        if (owner := self._waiter_owner(owner_id, "_api_line_get_next")) is None:
            return _none_result()
        return self._waiters.once(owner, lambda w: w.wait_for(pattern, timeout))

    @AddAPI("prompt.get.next", description="wait for the next MUD prompt")
    def _api_prompt_get_next(
        self, timeout: float = DEFAULT_TIMEOUT, owner_id: str | None = None
    ) -> Awaitable[WaitResult | None]:
        """Return an awaitable that resolves to the next prompt line (needs GA/EOR)."""
        if (owner := self._waiter_owner(owner_id, "_api_prompt_get_next")) is None:
            return _none_result()
        return self._waiters.once(owner, lambda w: w.wait_for_prompt(timeout))

    @AddAPI("line.get.after.send", description="send a command, then wait for a line")
    def _api_line_get_after_send(
        self,
        command: str,
        pattern: str,
        timeout: float = DEFAULT_TIMEOUT,
        owner_id: str | None = None,
    ) -> Awaitable[WaitResult | None]:
        """Return an awaitable that sends ``command``, then resolves to the first
        line matching ``pattern`` (None on timeout or error)."""
        if (owner := self._waiter_owner(owner_id, "_api_line_get_after_send")) is None:
            return _none_result()
        return self._waiters.once(owner, lambda w: w.send_and_wait(command, pattern, timeout))
