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
from bastproxy.libs.commandprefix import starts_with_command_prefix
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import NetworkData, SendDataDirectlyToClient, SendDataDirectlyToMud
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser, CommandResult

NAME_RE = re.compile(r"[A-Za-z0-9_]+")
GROUP_RE = re.compile(r"[A-Za-z0-9_]*")
ACTION_REF_RE = re.compile(r"%(%?)([1-9*c]|<[A-Za-z_][A-Za-z0-9_]*>)")
SEND_TARGETS = ("execute", "client", "mud")


def _clean(value: str, separator: str) -> str:
    """Remove CR and LF from a matched value and double the separator, so it never splits."""
    value = value.replace("\r", "").replace("\n", "")
    return value.replace(separator, separator * 2) if separator else value


def _escape_mud(value: str, separator: str) -> str:
    """Escape matched text for a part that goes to the MUD.

    ``@`` is doubled so a colour code in MUD text reaches the MUD as typed. ``%{`` is
    escaped later, over the whole part, because a reference can also form across
    the edge of a value (see ``_escape_references``).
    """
    return _clean(value, separator).replace("@", "@@")


def _escape_command(value: str, separator: str) -> str:
    """Escape matched text for a proxy command part: one shell-quoted argument."""
    return shlex.quote(_clean(value, separator))


def _escape_references(segments: list[tuple[str, bool]]) -> str:
    """Join text segments, escaping every ``%{`` that has a character from matched text.

    Each segment is ``(text, from_match)``. A ``%{`` whose ``%`` or ``{`` came from
    matched text becomes ``%%{``, which the variables plugin sends as a literal
    ``%{``. A ``%{`` written in the action's command is left alone.
    """
    chars = [(char, from_match) for text, from_match in segments for char in text]
    out: list[str] = []
    for index, (char, from_match) in enumerate(chars):
        if char == "%" and index + 1 < len(chars):
            next_char, next_from_match = chars[index + 1]
            if next_char == "{" and (from_match or next_from_match):
                out.append("%")
        out.append(char)
    return "".join(out)


def _first_word(text: str) -> str:
    """Return the first whitespace-separated word of text, or an empty string."""
    words = text.split(None, 1)
    return words[0] if words else ""


def expand_command(
    command: str,
    groups: Sequence[str | None],
    named: Mapping[str, Any],
    line: str,
    *,
    split_regex: str | None,
    separator: str,
    prefix: str,
    is_alias: Callable[[str], bool] | None = None,
    alias_resends: Callable[[str], bool] | None = None,
    escape_command_references: bool = False,
    colorline: str = "",
) -> list[str] | None:
    """Split a stored command into parts and substitute the matched text in each.

    ``%1`` to ``%9`` are the numbered groups, ``%*`` is the whole line, ``%c`` the
    line with its colours as colour codes (``colorline``) and ``%<name>`` a named group.
    ``%%`` before a reference makes it literal. A group
    that did not take part is empty. Substitution is one pass. Matched text is
    escaped for the kind of part it lands in.

    Returns None, meaning nothing may run, when matched text would decide what
    runs instead of only filling in its text:

    - a MUD-bound part would start with the command prefix;
    - the first word of a MUD-bound part comes from matched text and is an alias
      (``is_alias``);
    - a MUD-bound part holds matched text and starts with an alias whose expansion
      is re-sent through the input path (``alias_resends``), where the matched text
      would be split or reach a proxy command unescaped;
    - a value substituted into a proxy command part starts with ``-``, which the
      command would read as an option.

    In a proxy command part holding matched text, ``%{`` from the match is escaped
    to ``%%{`` when ``escape_command_references`` is set, so matched text never
    becomes a variable reference, even in a command that re-sends its arguments.
    """
    parts = regex.split(split_regex, command) if split_regex else [command]
    result: list[str] = []
    for part in parts:
        is_command = starts_with_command_prefix(part, prefix)
        escape = _escape_command if is_command else _escape_mud
        segments: list[tuple[str, bool]] = []
        option_like = False
        has_match_text = False
        position = 0
        for match in ACTION_REF_RE.finditer(part):
            segments.append((part[position : match.start()], False))
            position = match.end()
            if match.group(1):
                segments.append(("%" + match.group(2), False))
                continue
            ref = match.group(2)
            if ref == "*":
                value: Any = line
            elif ref == "c":
                value = colorline
            elif ref.startswith("<"):
                value = named.get(ref[1:-1])
            else:
                index = int(ref) - 1
                value = groups[index] if index < len(groups) else None
            text_value = "" if value is None else str(value)
            if is_command and _clean(text_value, separator).lstrip().startswith("-"):
                option_like = True
            has_match_text = has_match_text or bool(text_value)
            segments.append((escape(text_value, separator), True))
        segments.append((part[position:], False))
        if is_command:
            if option_like:
                return None
            command_text = "".join(text for text, _ in segments)
            if escape_command_references and has_match_text:
                command_text = _escape_references(segments)
            result.append(command_text)
            continue
        text = _escape_references(segments)
        if starts_with_command_prefix(text, prefix):
            return None
        if (
            is_alias is not None
            and _first_word_from_match(segments)
            and is_alias(_first_word(text))
        ):
            return None
        if (
            alias_resends is not None
            and any(value and from_match for value, from_match in segments)
            and alias_resends(text)
        ):
            return None
        result.append(text)
    return result


def expand_text(
    command: str,
    groups: Sequence[str | None],
    named: Mapping[str, Any],
    line: str,
    colorline: str,
    *,
    escape_at: bool,
) -> str:
    """Substitute the matched text into a command in one pass, for the client or the MUD.

    Nothing is split or parsed: no separator, no ``%{}`` variable and no command
    prefix check. Values lose CR and LF. With ``escape_at`` a value has ``@`` doubled
    so it shows as typed after colour conversion; ``%c`` is never doubled, so its
    colour codes stay colours. ``%%`` before a reference makes it literal.
    """

    def _replace(match: re.Match[str]) -> str:
        if match.group(1):
            return "%" + match.group(2)
        ref = match.group(2)
        if ref == "c":
            return colorline.replace("\r", "").replace("\n", "")
        if ref == "*":
            value: Any = line
        elif ref.startswith("<"):
            value = named.get(ref[1:-1])
        else:
            index = int(ref) - 1
            value = groups[index] if index < len(groups) else None
        text = "" if value is None else str(value).replace("\r", "").replace("\n", "")
        return text.replace("@", "@@") if escape_at else text

    return ACTION_REF_RE.sub(_replace, command)


def _first_word_from_match(segments: list[tuple[str, bool]]) -> bool:
    """Check if any character of the first word of the joined segments came from matched text."""
    started = False
    for text, from_match in segments:
        for char in text:
            if char.isspace():
                if started:
                    return False
                continue
            started = True
            if from_match:
                return True
    return False


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
        self.state = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "state.txt", "c"
        )
        self.session_hits: dict[str, int] = {}
        self._upgrade()

    @RegisterPluginHook("save")
    def _phook_actions_save(self) -> None:
        """Save the actions (with their hit counts), the group state and the id counter."""
        self.actions.sync()
        self.groups.sync()
        self.state.sync()

    def _upgrade(self) -> None:
        """Bring actions loaded from an older file up to date.

        Every action gets ``hits``, ``send`` (``execute``) and, when it lacks one, an
        ``id`` in sorted name order, and the id counter moves past every id in use.
        Nothing is written unless something changed. A digit-only name from an older
        file stays an integer key, because PersistentDict turns every digit-only key
        into one; it never matched a trigger name and is reachable by its id.
        """
        changed = False
        highest = 0
        for item in self.actions.values():
            for key, default in (("hits", 0), ("send", "execute")):
                if key not in item:
                    item[key] = default
                    changed = True
            if isinstance(item.get("id"), int):
                highest = max(highest, item["id"])
        next_id = max(int(self.state.get("next_id", 1)), highest + 1)
        for name in sorted(self.actions, key=str):
            item = self.actions[name]
            if not isinstance(item.get("id"), int):
                item["id"] = next_id
                next_id += 1
                changed = True
        if self.state.get("next_id") != next_id:
            self.state["next_id"] = next_id
            changed = True
        if changed:
            self.actions.sync()
            self.state.sync()

    def _next_id(self) -> int:
        """Return the next free action id and advance the counter, which is never lowered."""
        value = int(self.state.get("next_id", 1))
        self.state["next_id"] = value + 1
        self.state.sync()
        return value

    def _resolve(self, key: Any) -> Any:
        """Return the stored key of the action for a typed name or id, or None.

        A name wins; otherwise a digit string is looked up as an id. The stored key
        is a string, except for a digit-only name from an older file.
        """
        key = str(key)
        if key in self.actions:
            return key
        if key.isdigit():
            for name, item in self.actions.items():
                if item.get("id") == int(key):
                    return name
        return None

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
            elif ref not in ("*", "c") and int(ref) > compiled.groups:
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
        send: str = "execute",
    ) -> bool:
        """Add an action or replace an existing one.

        @Yname@w          = the action name, letters, digits and underscores
        @Yregex_text@w    = the regex a line of MUD output must match
        @Ycommand@w       = the command to run, may reference the match
        @Ygroup@w         = the group, letters, digits and underscores, optional
        @Yenabled@w       = whether the action is enabled
        @Ymatchcolor@w    = match against the line with colour codes
        @Ysend@w          = where the text goes: execute (run as commands), client or mud

        An empty command is allowed only for send mud: the action then sends one
        empty line to the MUD. An existing action is replaced and keeps its id and
        hit count. This function returns True when the action was stored. It returns
        False, changing nothing, for a bad name (digits only is refused), regex, command,
        group or send.
        """
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name.isdigit():
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
            or "\r" in command
            or "\n" in command
            # only a mud action may send an empty line (#808)
            or (not command.strip() and send != "mud")
        ):
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad command for %s", name)
            return False
        if not command.strip():
            command = ""
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
        if send not in SEND_TARGETS:
            log_to([self.plugin_id], logging.WARNING, "_api_action_add: bad send for %s", name)
            return False
        old = self.actions.get(name)
        self.actions[name] = {
            "regex": regex_text,
            "command": command,
            "group": group,
            "enabled": bool(enabled),
            "matchcolor": bool(matchcolor),
            "send": send,
            "id": old["id"] if old is not None else self._next_id(),
            "hits": old.get("hits", 0) if old is not None else 0,
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

        This function returns a dict with regex, command, group, enabled, matchcolor,
        send, id and hits, or None.
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

    def _is_alias(self, word: str) -> bool:
        """Check if word is an enabled alias of the aliases plugin, when it is loaded."""
        location = "plugins.client.aliases:alias.is.enabled"
        if not word or not self.api("libs.api:api.exists")(location):
            return False
        return bool(self.api(location)(word))

    def _alias_resends(self, text: str) -> bool:
        """Check if the aliases plugin would re-send the expansion of text, when it is loaded."""
        location = "plugins.client.aliases:alias.expansion.is.resent"
        if not self.api("libs.api:api.exists")(location):
            return False
        return bool(self.api(location)(text))

    def _trigger_matched(self) -> None:
        """Run the command of the action whose trigger fired."""
        record = self.api("plugins.core.events:event.current.record.get")()
        if not record:
            return
        name = record["trigger_name"]
        if name not in self.actions or not self._api_action_is_enabled(name):
            return
        item = self.actions[name]
        command = item["command"]
        send = item.get("send", "execute")
        line = record["line"]
        colorline = str(line.colorcoded) if "%c" in command else ""
        groups = record.get("groups") or ()
        logger = get_logger(self.plugin_id)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("action %s matched: %r", name, str(line.noansi))
        if send == "execute":
            parts = expand_command(
                command,
                groups,
                record["matches"],
                str(line.noansi),
                split_regex=self.api.command_split_regex,
                separator=self.api.command_separator,
                prefix=self.api("plugins.core.commands:command.prefix.get")(),
                is_alias=self._is_alias,
                alias_resends=self._alias_resends,
                escape_command_references=bool(
                    self.api("libs.api:api.exists")("plugins.client.variables:variable.get")
                ),
                colorline=colorline,
            )
            if parts is None:
                log_to(
                    [self.plugin_id],
                    logging.WARNING,
                    "action %s: matched text would decide the command to run, nothing was run",
                    name,
                )
                return
        else:
            parts = [
                expand_text(
                    command,
                    groups,
                    record["matches"],
                    str(line.noansi),
                    colorline,
                    escape_at=send == "client",
                )
            ]
        self.session_hits[name] = self.session_hits.get(name, 0) + 1
        item["hits"] = item.get("hits", 0) + 1
        for part in parts:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("action %s sends to %s: %r", name, send, part)
            if send == "client":
                SendDataDirectlyToClient(NetworkData([part], owner_id=self.plugin_id))()
            elif send == "mud":
                SendDataDirectlyToMud(NetworkData([part], owner_id=self.plugin_id))()
            else:
                self.api("plugins.core.commands:command.line.run")(part, show_in_history=False)

    @AddCommand(literal_args=True)
    @AddParser(description="add an action or change it")
    @AddArgument("-g", "--group", help="the group of the action", default="")
    @AddArgument("-d", "--disabled", help="add the action disabled", action="store_true")
    @AddArgument("-c", "--color", help="match the line with colour codes", action="store_true")
    @AddArgument(
        "-s",
        "--send",
        help="where the text goes: execute it as commands, or send it to the client or the MUD",
        choices=list(SEND_TARGETS),
        default="execute",
    )
    @AddArgument(
        "-o", "--overwrite", help="replace the action when the name exists", action="store_true"
    )
    @AddArgument("name", help="the action name")
    @AddArgument("regex", help="the regex a MUD line must match, quote it")
    @AddArgument(
        "command",
        help='the command to run; "" (two quotes) is an empty line, only with -s mud',
        nargs="*",
    )
    def _command_add(self) -> CommandResult:
        """Add an action or change it."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["command"]:
            return CommandResult(
                False, ["Please provide a command, use remove to delete an action"]
            )
        name = args["name"]
        if name in self.actions and not args.get("overwrite", False):
            return CommandResult(False, [f"action {name} exists, use -o to replace it"])
        regex_text = args["regex"]
        command = " ".join(args["command"])
        # a typed line is split on the command separator before this command runs,
        # so a doubled separator is how a user types one; store it single
        separator = self.api.command_separator
        if separator:
            regex_text = regex_text.replace(separator * 2, separator)
            command = command.replace(separator * 2, separator)
        if self.api(f"{self.plugin_id}:action.add")(
            name,
            regex_text,
            command,
            args["group"],
            not args["disabled"],
            args["color"],
            args.get("send", "execute"),
        ):
            return CommandResult(True, [f"action {name} set"])
        return CommandResult(
            False,
            [
                f"could not set {name}: the name needs letters, digits and underscores, not only "
                "digits, the "
                "regex must compile, the group letters, digits and underscores, the command "
                "can only reference groups the regex has and is empty only with -s mud, and "
                "neither can contain a line break"
            ],
        )

    @AddCommand(literal_args=True)
    @AddParser(description="remove an action")
    @AddArgument("name", help="the action name or id")
    def _command_remove(self) -> CommandResult:
        """Remove an action."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = self._resolve(args["name"])
        if name is not None and self.api(f"{self.plugin_id}:action.remove")(name):
            return CommandResult(True, [f"action {name} removed"])
        return CommandResult(False, [f"action {args['name']} does not exist"])

    @AddCommand(literal_args=True)
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
        names = sorted((name for name in self.actions if not match or match in str(name)), key=str)
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
            if item.get("send", "execute") != "execute":
                tags.append(f"send {item['send']}")
            suffix = f" ({', '.join(tags)})" if tags else ""
            lines.append(
                f"[{item['id']}] {escape(str(name))} : {escape(item['regex'])} -> "
                f"{escape(item['command'])}{suffix}"
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
        resolved = self._resolve(name)
        if resolved is not None and self.api(f"{self.plugin_id}:action.enabled.set")(
            resolved, enabled
        ):
            return (True, [f"action {resolved} {word}"])
        return (False, [f"action {name} does not exist"])

    @AddCommand(literal_args=True)
    @AddParser(description="enable an action or a group of actions")
    @AddArgument("name", help="the action name or id", default="", nargs="?")
    @AddArgument("-g", "--group", help="enable this group instead", default="")
    def _command_enable(self) -> CommandResult:
        """Enable an action or a group."""
        success, lines = self._set_enabled(True)
        return CommandResult(success, lines)

    @AddCommand(literal_args=True)
    @AddParser(description="disable an action or a group of actions")
    @AddArgument("name", help="the action name or id", default="", nargs="?")
    @AddArgument("-g", "--group", help="disable this group instead", default="")
    def _command_disable(self) -> CommandResult:
        """Disable an action or a group."""
        success, lines = self._set_enabled(False)
        return CommandResult(success, lines)

    @AddCommand(literal_args=True)
    @AddParser(description="toggle an action or a group of actions")
    @AddArgument("name", help="the action name or id", default="", nargs="?")
    @AddArgument("-g", "--group", help="toggle this group instead", default="")
    def _command_toggle(self) -> CommandResult:
        """Flip an action or a group between enabled and disabled."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name, group = args["name"], args["group"]
        if bool(name) == bool(group):
            return CommandResult(False, ["Please give exactly one of an action name or -g GROUP"])
        if group:
            enabled = not self._api_action_group_is_enabled(group)
        else:
            resolved = self._resolve(name)
            if resolved is None:
                return CommandResult(False, [f"action {name} does not exist"])
            enabled = not self.actions[resolved]["enabled"]
        success, lines = self._set_enabled(enabled)
        return CommandResult(success, lines)

    @AddCommand(literal_args=True)
    @AddParser(description="show an action")
    @AddArgument("name", help="the action name or id")
    def _command_show(self) -> CommandResult:
        """Show an action."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = self._resolve(args["name"])
        item = self.actions.get(name) if name is not None else None
        if name is None or item is None:
            return CommandResult(False, [f"action {args['name']} does not exist"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        group = item["group"]
        trigger = self.api("plugins.core.triggers:trigger.get")(str(name))
        return CommandResult(
            True,
            [
                f"action        : {escape(str(name))}",
                f"id            : {item['id']}",
                f"regex         : {escape(item['regex'])}",
                f"command       : {escape(item['command'])}",
                f"group         : {group or '(none)'}",
                f"enabled       : {item['enabled']}",
                f"group enabled : {self._api_action_group_is_enabled(group) if group else True}",
                f"match color   : {item.get('matchcolor', False)}",
                f"send          : {item.get('send', 'execute')}",
                f"total hits    : {item.get('hits', 0)}",
                f"session hits  : {self.session_hits.get(name, 0)}",
                f"trigger hits  : {trigger.hits if trigger else 0}",
            ],
        )
