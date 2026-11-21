# Project: bastproxy
# Filename: plugins/client/actions/plugin/_actions.py
#
# File Description: a plugin that runs commands when MUD output matches a regex
#
# By: Bast
"""User actions: a trigger per action, with matched text substituted into a command (ADR-0018)."""

# Standard Library
import logging
import re
import shlex
from collections.abc import Callable, Mapping, Sequence
from typing import Any

# Third Party
import regex

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult

NAME_RE = re.compile(r"[A-Za-z0-9_]+")
GROUP_RE = re.compile(r"[A-Za-z0-9_]*")
ACTION_REF_RE = re.compile(r"%(%?)([1-9*]|<[A-Za-z_][A-Za-z0-9_]*>)")


def _clean(value: str, separator: str) -> str:
    """Remove CR and LF from a matched value and double the separator, so it never splits."""
    value = value.replace("\r", "").replace("\n", "")
    return value.replace(separator, separator * 2) if separator else value


def _escape_mud(value: str, separator: str) -> str:
    """Escape matched text for a part that goes to the MUD."""
    # %{ would be a variable reference and @ a colour code; keep both literal
    return _clean(value, separator).replace("%{", "%%{").replace("@", "@@")


def _escape_command(value: str, separator: str) -> str:
    """Escape matched text for a proxy command part: one shell-quoted argument."""
    return shlex.quote(_clean(value, separator))


def expand_command(
    command: str,
    groups: Sequence[str | None],
    named: Mapping[str, Any],
    line: str,
    *,
    split_regex: str | None,
    separator: str,
    prefix: str,
) -> list[str] | None:
    """Split a stored command into parts and substitute the matched text in each.

    ``%1`` to ``%9`` are the numbered groups, ``%*`` is the whole line and
    ``%<name>`` a named group. ``%%`` before a reference makes it literal. A group
    that did not take part is empty. Substitution is one pass. Matched text is
    escaped for the kind of part it lands in. Returns None, meaning nothing may
    run, when a MUD-bound part would start with the command prefix after substitution.
    """
    parts = regex.split(split_regex, command) if split_regex else [command]
    result: list[str] = []
    for part in parts:
        is_command = part.lstrip().startswith(prefix)
        escape = _escape_command if is_command else _escape_mud

        def _replace(match: re.Match[str], escape: Callable[[str, str], str] = escape) -> str:
            if match.group(1):
                return "%" + match.group(2)
            ref = match.group(2)
            if ref == "*":
                value: Any = line
            elif ref.startswith("<"):
                value = named.get(ref[1:-1])
            else:
                index = int(ref) - 1
                value = groups[index] if index < len(groups) else None
            return escape("" if value is None else str(value), separator)

        text = ACTION_REF_RE.sub(_replace, part)
        if not is_command and text.lstrip().startswith(prefix):
            return None
        result.append(text)
    return result


class ActionsPlugin(BasePlugin):
    """a plugin that runs commands when MUD output matches a regex."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.actions = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "actions.txt", "c"
        )
        self.groups = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "groups.txt", "c"
        )
        self.session_hits: dict[str, int] = {}

    @RegisterPluginHook("save")
    def _phook_actions_save(self) -> None:
        """Save the actions and the group state."""
        self.actions.sync()
        self.groups.sync()

    @RegisterPluginHook("after_load")
    def _phook_actions_after_load(self) -> None:
        """Create a trigger for every stored action."""
        for name in list(self.actions):
            if not self._register(name):
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "action %s could not be registered, it is kept but will not fire",
                    name,
                )

    @RegisterPluginHook("uninitialize")
    def _phook_actions_uninitialize(self) -> None:
        """Remove the triggers this plugin owns."""
        self.api("plugins.core.triggers:trigger.remove.for.owner")(self.plugin_id)

    def _register(self, name: str) -> bool:
        """Create the trigger of a stored action and register the callback to it."""
        item = self.actions[name]
        if self.api("plugins.core.triggers:trigger.get")(name):
            self.api("plugins.core.triggers:trigger.remove")(name, force=True)
        result = self.api("plugins.core.triggers:trigger.add")(
            name,
            item["regex"],
            enabled=self._api_action_is_enabled(name),
            matchcolor=bool(item.get("matchcolor", False)),
        )
        if not result.success:
            return False
        return bool(self.api("plugins.core.triggers:trigger.register")(name, self._trigger_matched))

    def _sync_trigger(self, name: str) -> None:
        """Give the trigger the effective state of its action."""
        self.api("plugins.core.triggers:trigger.toggle.enable")(
            name, self._api_action_is_enabled(name)
        )

    def _refs_fit(self, command: str, compiled: Any) -> bool:
        """Check that every reference in the command exists in the regex."""
        for match in ACTION_REF_RE.finditer(command):
            if match.group(1):
                continue
            ref = match.group(2)
            if ref.startswith("<"):
                if ref[1:-1] not in compiled.groupindex:
                    return False
            elif ref != "*" and int(ref) > compiled.groups:
                return False
        return True

    @AddAPI("action.add", description="add an action or replace an existing one")
    def _api_action_add(
        self,
        name: str,
        regex_text: str,
        command: str,
        group: str = "",
        enabled: bool = True,
        matchcolor: bool = False,
    ) -> bool:
        """Add an action or replace an existing one.

        @Yname@w          = the action name, letters, digits and underscores
        @Yregex_text@w    = the regex a line of MUD output must match
        @Ycommand@w       = the command to run, may reference the match
        @Ygroup@w         = the group, letters, digits and underscores, optional
        @Yenabled@w       = whether the action is enabled
        @Ymatchcolor@w    = match against the line with colour codes

        This function returns True when the action was stored. It returns False,
        changing nothing, for a bad name, regex, command or group.
        """
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad action name")
            return False
        if (
            not isinstance(regex_text, str)
            or not regex_text
            or "\r" in regex_text
            or "\n" in regex_text
        ):
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad regex for %s", name)
            return False
        try:
            compiled = regex.compile(regex_text)
        except regex.error:
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad regex for %s", name)
            return False
        if (
            not isinstance(command, str)
            or not command.strip()
            or "\r" in command
            or "\n" in command
        ):
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad command for %s", name)
            return False
        if not self._refs_fit(command, compiled):
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "_api_action_add: command for %s references a group the regex lacks",
                name,
            )
            return False
        if not isinstance(group, str) or not GROUP_RE.fullmatch(group):
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad group for %s", name)
            return False
        self.actions[name] = {
            "regex": regex_text,
            "command": command,
            "group": group,
            "enabled": bool(enabled),
            "matchcolor": bool(matchcolor),
        }
        self.actions.sync()
        return self._register(name)

    @AddAPI("action.remove", description="remove an action")
    def _api_action_remove(self, name: str) -> bool:
        """Remove an action.

        @Yname@w   = the action name

        This function returns True when removed, False when it was not defined.
        """
        if name not in self.actions:
            return False
        del self.actions[name]
        self.actions.sync()
        self.api("plugins.core.triggers:trigger.remove")(name, force=True)
        self.session_hits.pop(name, None)
        return True

    @AddAPI("action.get", description="get an action")
    def _api_action_get(self, name: str) -> dict[str, Any] | None:
        """Get a copy of an action.

        @Yname@w   = the action name

        This function returns a dict with regex, command, group, enabled and
        matchcolor, or None.
        """
        item = self.actions.get(name)
        return dict(item) if item is not None else None

    @AddAPI("action.exists", description="check if an action is defined")
    def _api_action_exists(self, name: str) -> bool:
        """Check if an action is defined.

        @Yname@w   = the action name
        """
        return name in self.actions

    @AddAPI("action.list", description="get all actions")
    def _api_action_list(self) -> dict[str, dict[str, Any]]:
        """Get a copy of all actions as a name to action dict."""
        return {name: dict(item) for name, item in self.actions.items()}

    @AddAPI("action.enabled.set", description="enable or disable an action")
    def _api_action_enabled_set(self, name: str, enabled: bool) -> bool:
        """Enable or disable an action.

        @Yname@w      = the action name
        @Yenabled@w   = True to enable, False to disable

        This function returns True when the action exists, False otherwise.
        """
        if name not in self.actions:
            return False
        item = dict(self.actions[name])
        item["enabled"] = bool(enabled)
        self.actions[name] = item
        self.actions.sync()
        self._sync_trigger(name)
        return True

    @AddAPI("action.is.enabled", description="check if an action is enabled")
    def _api_action_is_enabled(self, name: str) -> bool:
        """Check if an action is enabled.

        @Yname@w   = the action name

        This function returns True only when the action and its group are enabled.
        """
        item = self.actions.get(name)
        if item is None or not item["enabled"]:
            return False
        group = item["group"]
        return not group or bool(self.groups.get(group, True))

    @AddAPI("action.group.enabled.set", description="enable or disable a group of actions")
    def _api_action_group_enabled_set(self, group: str, enabled: bool) -> int:
        """Enable or disable a group of actions.

        @Ygroup@w     = the group name
        @Yenabled@w   = True to enable, False to disable

        This function returns how many actions are in the group.
        """
        self.groups[group] = bool(enabled)
        self.groups.sync()
        members = [name for name, item in self.actions.items() if item["group"] == group]
        for name in members:
            self._sync_trigger(name)
        return len(members)

    @AddAPI("action.group.is.enabled", description="check if a group of actions is enabled")
    def _api_action_group_is_enabled(self, group: str) -> bool:
        """Check if a group of actions is enabled.

        @Ygroup@w   = the group name

        A group that was never disabled is enabled.
        """
        return bool(self.groups.get(group, True))

    def _trigger_matched(self) -> None:
        """Run the command of the action whose trigger fired."""
        record = self.api("plugins.core.events:event.current.record.get")()
        if not record:
            return
        name = record["trigger_name"]
        if name not in self.actions or not self._api_action_is_enabled(name):
            return
        parts = expand_command(
            self.actions[name]["command"],
            record.get("groups") or (),
            record["matches"],
            str(record["line"].noansi),
            split_regex=self.api.command_split_regex,
            separator=self.api.command_separator,
            prefix=self.api("plugins.core.commands:command.prefix.get")(),
        )
        if parts is None:
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "action %s: matched text would start a proxy command, nothing was run",
                name,
            )
            return
        self.session_hits[name] = self.session_hits.get(name, 0) + 1
        for part in parts:
            self.api("plugins.core.commands:command.line.run")(part, show_in_history=False)

    @AddParser(description="add an action or change it")
    @AddArgument("-g", "--group", help="the group of the action", default="")
    @AddArgument("-d", "--disabled", help="add the action disabled", action="store_true")
    @AddArgument("-c", "--color", help="match the line with colour codes", action="store_true")
    @AddArgument("name", help="the action name")
    @AddArgument("regex", help="the regex a MUD line must match, quote it")
    @AddArgument("command", help="the command to run", nargs="*")
    def _command_add(self) -> CommandResult:
        """Add an action or change it."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["command"]:
            return CommandResult(
                False, ["Please provide a command, use remove to delete an action"]
            )
        name = args["name"]
        regex_text = args["regex"]
        command = " ".join(args["command"])
        # a typed line is split on the command separator before this command runs,
        # so a doubled separator is how a user types one; store it single
        separator = self.api.command_separator
        if separator:
            regex_text = regex_text.replace(separator * 2, separator)
            command = command.replace(separator * 2, separator)
        if self.api(f"{self.plugin_id}:action.add")(
            name, regex_text, command, args["group"], not args["disabled"], args["color"]
        ):
            return CommandResult(True, [f"action {name} set"])
        return CommandResult(
            False,
            [
                f"could not set {name}: the name needs letters, digits and underscores, the "
                "regex must compile, the group letters, digits and underscores, the command "
                "can only reference groups the regex has, and neither can contain a line break"
            ],
        )

    @AddParser(description="remove an action")
    @AddArgument("name", help="the action name")
    def _command_remove(self) -> CommandResult:
        """Remove an action."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        if self.api(f"{self.plugin_id}:action.remove")(name):
            return CommandResult(True, [f"action {name} removed"])
        return CommandResult(False, [f"action {name} does not exist"])

    @AddParser(description="list actions")
    @AddArgument(
        "match",
        help="list only actions that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List actions."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        match = args["match"]
        names = sorted(name for name in self.actions if not match or match in name)
        if not names:
            return CommandResult(True, ["No actions defined"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        lines = []
        for name in names:
            item = self.actions[name]
            tags = []
            if item["group"]:
                tags.append(f"group {item['group']}")
            if not self._api_action_is_enabled(name):
                tags.append("disabled")
            suffix = f" ({', '.join(tags)})" if tags else ""
            lines.append(
                f"{escape(name)} : {escape(item['regex'])} -> {escape(item['command'])}{suffix}"
            )
        return CommandResult(True, lines)

    def _set_enabled(self, enabled: bool) -> tuple[bool, list[str]]:
        """Enable or disable the action or group named in the command arguments.

        Returns the success flag and the message lines for the command result.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        name, group = args["name"], args["group"]
        word = "enabled" if enabled else "disabled"
        if bool(name) == bool(group):
            return (False, ["Please give exactly one of an action name or -g GROUP"])
        if group:
            count = self.api(f"{self.plugin_id}:action.group.enabled.set")(group, enabled)
            return (True, [f"group {group} {word}, {count} actions in it"])
        if self.api(f"{self.plugin_id}:action.enabled.set")(name, enabled):
            return (True, [f"action {name} {word}"])
        return (False, [f"action {name} does not exist"])

    @AddParser(description="enable an action or a group of actions")
    @AddArgument("name", help="the action name", default="", nargs="?")
    @AddArgument("-g", "--group", help="enable this group instead", default="")
    def _command_enable(self) -> CommandResult:
        """Enable an action or a group."""
        success, lines = self._set_enabled(True)
        return CommandResult(success, lines)

    @AddParser(description="disable an action or a group of actions")
    @AddArgument("name", help="the action name", default="", nargs="?")
    @AddArgument("-g", "--group", help="disable this group instead", default="")
    def _command_disable(self) -> CommandResult:
        """Disable an action or a group."""
        success, lines = self._set_enabled(False)
        return CommandResult(success, lines)

    @AddParser(description="show an action")
    @AddArgument("name", help="the action name")
    def _command_show(self) -> CommandResult:
        """Show an action."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        item = self.actions.get(name)
        if item is None:
            return CommandResult(False, [f"action {name} does not exist"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        group = item["group"]
        trigger = self.api("plugins.core.triggers:trigger.get")(name)
        return CommandResult(
            True,
            [
                f"action        : {escape(name)}",
                f"regex         : {escape(item['regex'])}",
                f"command       : {escape(item['command'])}",
                f"group         : {group or '(none)'}",
                f"enabled       : {item['enabled']}",
                f"group enabled : {self._api_action_group_is_enabled(group) if group else True}",
                f"match color   : {item.get('matchcolor', False)}",
                f"session hits  : {self.session_hits.get(name, 0)}",
                f"trigger hits  : {trigger.hits if trigger else 0}",
            ],
        )
