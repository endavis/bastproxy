# Project: bastproxy
# Filename: plugins/client/aliases/plugin/_aliases.py
#
# File Description: a plugin that stores user aliases and expands them in client input
#
# By: Bast
"""User aliases and the expansion of the first word of client input (ADR-0017)."""

# Standard Library
import logging
import re
from typing import Any

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import NetworkData, SendDataDirectlyToClient, UpdateFlag
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

ARG_RE = re.compile(r"%(%?)([1-9*])")
GROUP_RE = re.compile(r"[A-Za-z0-9_]*")

# runs after the commands plugin's callback (50) and before variables (60)
ALIAS_PRIORITY = 55

# the most expansions one typed line may go through, across chains and re-sends
MAX_DEPTH = 10


def substitute_arguments(expansion: str, rest: str) -> str:
    """Substitute ``%1`` to ``%9`` and ``%*`` in an expansion in a single pass.

    ``rest`` is the text typed after the alias name. ``%%1`` and ``%%*`` become
    the literal ``%1`` and ``%*``. A missing word becomes empty and an argument
    is never substituted again. When the expansion has no reference and
    arguments were typed, they are appended after a space.
    """
    words = rest.split()
    stripped = rest.strip()
    found = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal found
        if match.group(1):
            return "%" + match.group(2)
        found = True
        ref = match.group(2)
        if ref == "*":
            return stripped
        index = int(ref) - 1
        return words[index] if index < len(words) else ""

    result = ARG_RE.sub(_replace, expansion)
    if not found and stripped:
        return f"{result} {stripped}"
    return result


class AliasesPlugin(BasePlugin):
    """a plugin that stores user aliases and expands them in client input."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.aliases = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "aliases.txt", "c"
        )
        self.groups = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "groups.txt", "c"
        )
        self.session_hits: dict[str, int] = {}
        self._resend_depth = 0

    @RegisterPluginHook("save")
    def _phook_aliases_save(self) -> None:
        """Save the aliases and the group state."""
        self.aliases.sync()
        self.groups.sync()

    def _valid_name(self, name: Any) -> bool:
        """Check that a name is a single word the input path can match."""
        if not isinstance(name, str) or not name or re.search(r"\s", name) or "%" in name:
            return False
        if name.startswith(self.api("plugins.core.commands:command.prefix.get")()):
            return False
        regex = self.api.command_split_regex
        return not (regex and len(re.split(regex, name)) > 1)

    @AddAPI("alias.add", description="add an alias or replace an existing one")
    def _api_alias_add(
        self, name: str, expansion: str, group: str = "", enabled: bool = True
    ) -> bool:
        """Add an alias or replace an existing one.

        @Yname@w        = the alias name, one word, no %, not starting with the prefix
        @Yexpansion@w   = the text to send, a string without CR or LF
        @Ygroup@w       = the group, letters, digits and underscores, optional
        @Yenabled@w     = whether the alias is enabled

        This function returns True when the alias was stored. It returns False,
        changing nothing, for a bad name, expansion or group.
        """
        if not self._valid_name(name):
            log_to([self.plugin_id], logging.WARNING, "_api_alias_add: bad alias name")
            return False
        if (
            not isinstance(expansion, str)
            or not expansion.strip()
            or "\r" in expansion
            or "\n" in expansion
        ):
            log_to([self.plugin_id], logging.WARNING, "_api_alias_add: bad expansion for %s", name)
            return False
        if not isinstance(group, str) or not GROUP_RE.fullmatch(group):
            log_to([self.plugin_id], logging.WARNING, "_api_alias_add: bad group for %s", name)
            return False
        self.aliases[name] = {"expansion": expansion, "group": group, "enabled": bool(enabled)}
        self.aliases.sync()
        return True

    @AddAPI("alias.remove", description="remove an alias")
    def _api_alias_remove(self, name: str) -> bool:
        """Remove an alias.

        @Yname@w   = the alias name

        This function returns True when removed, False when it was not defined.
        """
        if name not in self.aliases:
            return False
        del self.aliases[name]
        self.aliases.sync()
        self.session_hits.pop(name, None)
        return True

    @AddAPI("alias.get", description="get an alias")
    def _api_alias_get(self, name: str) -> dict[str, Any] | None:
        """Get a copy of an alias.

        @Yname@w   = the alias name

        This function returns a dict with expansion, group and enabled, or None.
        """
        item = self.aliases.get(name)
        return dict(item) if item is not None else None

    @AddAPI("alias.exists", description="check if an alias is defined")
    def _api_alias_exists(self, name: str) -> bool:
        """Check if an alias is defined.

        @Yname@w   = the alias name
        """
        return name in self.aliases

    @AddAPI("alias.list", description="get all aliases")
    def _api_alias_list(self) -> dict[str, dict[str, Any]]:
        """Get a copy of all aliases as a name to alias dict."""
        return {name: dict(item) for name, item in self.aliases.items()}

    @AddAPI("alias.enabled.set", description="enable or disable an alias")
    def _api_alias_enabled_set(self, name: str, enabled: bool) -> bool:
        """Enable or disable an alias.

        @Yname@w      = the alias name
        @Yenabled@w   = True to enable, False to disable

        This function returns True when the alias exists, False otherwise.
        """
        if name not in self.aliases:
            return False
        item = dict(self.aliases[name])
        item["enabled"] = bool(enabled)
        self.aliases[name] = item
        self.aliases.sync()
        return True

    @AddAPI("alias.is.enabled", description="check if an alias is enabled")
    def _api_alias_is_enabled(self, name: str) -> bool:
        """Check if an alias is enabled.

        @Yname@w   = the alias name

        This function returns True only when the alias and its group are enabled.
        """
        item = self.aliases.get(name)
        if item is None or not item["enabled"]:
            return False
        group = item["group"]
        return not group or self.groups.get(group, True)

    @AddAPI("alias.group.enabled.set", description="enable or disable a group of aliases")
    def _api_alias_group_enabled_set(self, group: str, enabled: bool) -> int:
        """Enable or disable a group of aliases.

        @Ygroup@w     = the group name
        @Yenabled@w   = True to enable, False to disable

        This function returns how many aliases are in the group.
        """
        self.groups[group] = bool(enabled)
        self.groups.sync()
        return sum(1 for item in self.aliases.values() if item["group"] == group)

    @AddAPI("alias.group.is.enabled", description="check if a group of aliases is enabled")
    def _api_alias_group_is_enabled(self, group: str) -> bool:
        """Check if a group of aliases is enabled.

        @Ygroup@w   = the group name

        A group that was never disabled is enabled.
        """
        return bool(self.groups.get(group, True))

    @AddAPI(
        "alias.expansion.is.resent",
        description="check if the alias expansion of a line is sent back through the input path",
    )
    def _api_alias_expansion_is_resent(self, line: str) -> bool:
        """Check if expanding the aliases at the start of a line re-sends the result.

        @Yline@w   = the line, as it would be typed

        This function returns True when the line starts with an enabled alias whose
        expansion, following any chain of aliases, contains the command separator or
        starts with the command prefix. Such an expansion is sent back through the
        input path, so its parts are split and proxy commands in it run. It returns
        False for a line that starts with the command prefix, a line whose first
        word is not an alias, and a chain that would stop at the depth limit.
        Session hits are not counted.
        """
        command_prefix = self.api("plugins.core.commands:command.prefix.get")()
        if line.lstrip().startswith(command_prefix):
            return False
        outcome, _text, _depth, _name = self._expand_chain(
            line, 0, command_prefix, count_hits=False
        )
        return outcome == "resend"

    @AddParser(description="add an alias or change its expansion")
    @AddArgument("-g", "--group", help="the group of the alias", default="")
    @AddArgument("-d", "--disabled", help="add the alias disabled", action="store_true")
    @AddArgument("name", help="the alias name")
    @AddArgument("expansion", help="the text to send", nargs="*")
    def _command_add(self) -> CommandResult:
        """Add an alias or change its expansion."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["expansion"]:
            return CommandResult(
                False, ["Please provide an expansion, use remove to delete an alias"]
            )
        name = args["name"]
        expansion = " ".join(args["expansion"])
        # a typed line is split on the command separator before this command runs,
        # so a doubled separator is how a user types one; store it single so the
        # expansion splits when it is re-sent
        separator = self.api.command_separator
        if separator:
            expansion = expansion.replace(separator * 2, separator)
        if self.api(f"{self.plugin_id}:alias.add")(
            name, expansion, args["group"], not args["disabled"]
        ):
            return CommandResult(True, [f"alias {name} set"])
        return CommandResult(
            False,
            [
                f"could not set {name}: the name must be one word without % that does not "
                "start with the command prefix or contain the command separator, the group "
                "letters, digits and underscores, and the expansion cannot contain a line break"
            ],
        )

    @AddParser(description="remove an alias")
    @AddArgument("name", help="the alias name")
    def _command_remove(self) -> CommandResult:
        """Remove an alias."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        if self.api(f"{self.plugin_id}:alias.remove")(name):
            return CommandResult(True, [f"alias {name} removed"])
        return CommandResult(False, [f"alias {name} does not exist"])

    @AddParser(description="list aliases")
    @AddArgument(
        "match",
        help="list only aliases that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List aliases."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        match = args["match"]
        names = sorted(name for name in self.aliases if not match or match in name)
        if not names:
            return CommandResult(True, ["No aliases defined"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        lines = []
        for name in names:
            item = self.aliases[name]
            tags = []
            if item["group"]:
                tags.append(f"group {item['group']}")
            if not self._api_alias_is_enabled(name):
                tags.append("disabled")
            suffix = f" ({', '.join(tags)})" if tags else ""
            lines.append(f"{escape(name)} : {escape(item['expansion'])}{suffix}")
        return CommandResult(True, lines)

    def _set_enabled(self, enabled: bool) -> tuple[bool, list[str]]:
        """Enable or disable the alias or group named in the command arguments.

        Returns the success flag and the message lines for the command result.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        name, group = args["name"], args["group"]
        word = "enabled" if enabled else "disabled"
        if bool(name) == bool(group):
            return (False, ["Please give exactly one of an alias name or -g GROUP"])
        if group:
            count = self.api(f"{self.plugin_id}:alias.group.enabled.set")(group, enabled)
            return (True, [f"group {group} {word}, {count} aliases in it"])
        if self.api(f"{self.plugin_id}:alias.enabled.set")(name, enabled):
            return (True, [f"alias {name} {word}"])
        return (False, [f"alias {name} does not exist"])

    @AddParser(description="enable an alias or a group of aliases")
    @AddArgument("name", help="the alias name", default="", nargs="?")
    @AddArgument("-g", "--group", help="enable this group instead", default="")
    def _command_enable(self) -> CommandResult:
        """Enable an alias or a group."""
        success, lines = self._set_enabled(True)
        return CommandResult(success, lines)

    @AddParser(description="disable an alias or a group of aliases")
    @AddArgument("name", help="the alias name", default="", nargs="?")
    @AddArgument("-g", "--group", help="disable this group instead", default="")
    def _command_disable(self) -> CommandResult:
        """Disable an alias or a group."""
        success, lines = self._set_enabled(False)
        return CommandResult(success, lines)

    @AddParser(description="show an alias")
    @AddArgument("name", help="the alias name")
    def _command_show(self) -> CommandResult:
        """Show an alias."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        item = self.aliases.get(name)
        if item is None:
            return CommandResult(False, [f"alias {name} does not exist"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        group = item["group"]
        return CommandResult(
            True,
            [
                f"alias         : {escape(name)}",
                f"expansion     : {escape(item['expansion'])}",
                f"group         : {group or '(none)'}",
                f"enabled       : {item['enabled']}",
                f"group enabled : {self._api_alias_group_is_enabled(group) if group else True}",
                f"session hits  : {self.session_hits.get(name, 0)}",
            ],
        )

    def _has_separator(self, text: str) -> bool:
        """Check if the text would be split by the command separator."""
        regex = self.api.command_split_regex
        return regex is not None and len(re.split(regex, text)) > 1

    def _stop(self, event_record: Any, name: str) -> None:
        """Drop a line whose expansion went past MAX_DEPTH and tell the client."""
        event_record["line"].send = False
        log_to(
            [self.plugin_id],
            logging.WARNING,
            "alias %s: expansion stopped after %s levels",
            name,
            MAX_DEPTH,
        )
        event_record.addupdate(UpdateFlag.MODIFY, "alias expansion stopped", savedata=False)
        client_id = event_record["client_id"]
        if client_id:
            SendDataDirectlyToClient(
                NetworkData(
                    [f"alias {name}: expansion stopped after {MAX_DEPTH} levels"],
                    owner_id=self.plugin_id,
                ),
                clients=[client_id],
            )()

    @RegisterToEvent(event_name="ev_to_mud_data_modify", priority=ALIAS_PRIORITY)
    def _eventcb_expand_line(self) -> None:
        """Expand an alias in the first word of a client line."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if not line.is_io or not line.send or line.mask_log:
            return
        command_prefix = self.api("plugins.core.commands:command.prefix.get")()
        text = line.line
        if text.lstrip().startswith(command_prefix):
            return
        outcome, text, depth, name = self._expand_chain(
            text, self._resend_depth, command_prefix, count_hits=True
        )
        if outcome == "stop":
            self._stop(event_record, name)
        elif outcome == "resend":
            self._resend(event_record, text, name, depth)
        elif outcome == "inplace":
            line.line = text
            event_record.addupdate(UpdateFlag.MODIFY, f"alias {name} expanded", savedata=False)

    def _expand_chain(
        self, text: str, depth: int, command_prefix: str, *, count_hits: bool
    ) -> tuple[str, str, int, str]:
        """Expand the alias at the start of text, following a chain of aliases.

        Returns ``(outcome, text, depth, name)``. The outcome is ``"none"`` when the
        first word is not an enabled alias, ``"inplace"`` when the result is one line
        to send, ``"resend"`` when the result contains the command separator or
        starts with the command prefix, and ``"stop"`` when the chain went past
        ``MAX_DEPTH``. ``name`` is the last alias expanded, or the one that stopped.
        """
        name = ""
        outcome = "none"
        while True:
            parts = text.lstrip().split(None, 1)
            if not parts or not self._api_alias_is_enabled(parts[0]):
                return outcome, text, depth, name
            name = parts[0]
            if depth >= MAX_DEPTH:
                return "stop", text, depth, name
            depth += 1
            outcome = "inplace"
            if count_hits:
                self.session_hits[name] = self.session_hits.get(name, 0) + 1
            text = substitute_arguments(
                self.aliases[name]["expansion"], parts[1] if len(parts) > 1 else ""
            )
            if text.lstrip().startswith(command_prefix) or self._has_separator(text):
                return "resend", text, depth, name

    def _resend(self, event_record: Any, text: str, name: str, depth: int) -> None:
        """Send the expansion back through the input path and drop the typed line."""
        event_record["line"].send = False
        event_record.addupdate(UpdateFlag.MODIFY, f"alias {name} re-sent", savedata=False)
        previous = self._resend_depth
        self._resend_depth = depth
        try:
            self.api("plugins.core.commands:command.line.run")(text, show_in_history=False)
        finally:
            self._resend_depth = previous
