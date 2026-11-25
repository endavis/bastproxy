# Project: bastproxy
# Filename: plugins/client/variables/plugin/_variables.py
#
# File Description: a plugin that stores user variables and expands them in client input
#
# By: Bast
"""User variables and the expansion of ``%{name}`` references in client input."""

# Standard Library
import logging
import re
from collections.abc import Mapping

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import UpdateFlag
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
REFERENCE_RE = re.compile(r"%(%?)\{([A-Za-z_][A-Za-z0-9_]*)\}")

# runs after the commands plugin's callback (priority 50, lower runs first)
EXPAND_PRIORITY = 60


def expand_references(text: str, values: Mapping[str, str]) -> str:
    """Expand ``%{name}`` references in text in a single pass.

    ``%%{name}`` becomes the literal ``%{name}``. A reference to an undefined
    name stays as typed. A value is never expanded again.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(2)
        if match.group(1):
            return "%{" + name + "}"
        return values.get(name, match.group(0))

    return REFERENCE_RE.sub(_replace, text)


class VariablesPlugin(BasePlugin):
    """a plugin that stores user variables and expands them in client input."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.variables = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "variables.txt", "c"
        )

    @RegisterPluginHook("save")
    def _phook_variables_save(self) -> None:
        """Save the variables."""
        self.variables.sync()

    @AddAPI("variable.get", description="get the value of a variable")
    def _api_variable_get(self, name: str) -> str | None:
        """Get the value of a variable.

        @Yname@w   = the variable name

        This function returns the value, or None when the variable is not defined.
        """
        return self.variables.get(name)

    @AddAPI("variable.set", description="set a variable")
    def _api_variable_set(self, name: str, value: str) -> bool:
        """Set a variable.

        @Yname@w    = the variable name, letters, digits and underscores, not starting with a digit
        @Yvalue@w   = the value, a string without CR or LF

        This function returns True when the variable was set. It returns False,
        changing nothing, for a bad name, a value that is not a string or a value
        containing CR or LF.
        """
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            log_to([self.plugin_id], logging.WARNING, "_api_variable_set: bad variable name")
            return False
        if not isinstance(value, str) or "\r" in value or "\n" in value:
            log_to(
                [self.plugin_id],
                logging.WARNING,
                "_api_variable_set: bad value for variable %s",
                name,
            )
            return False
        self.variables[name] = value
        self.variables.sync()
        return True

    @AddAPI("variable.remove", description="remove a variable")
    def _api_variable_remove(self, name: str) -> bool:
        """Remove a variable.

        @Yname@w   = the variable name

        This function returns True when removed, False when it was not defined.
        """
        if name not in self.variables:
            return False
        del self.variables[name]
        self.variables.sync()
        return True

    @AddAPI("variable.exists", description="check if a variable is defined")
    def _api_variable_exists(self, name: str) -> bool:
        """Check if a variable is defined.

        @Yname@w   = the variable name
        """
        return name in self.variables

    @AddAPI("variable.list", description="get all variables")
    def _api_variable_list(self) -> dict[str, str]:
        """Get a copy of all variables as a name to value dict."""
        return dict(self.variables)

    @AddAPI(
        "variable.reference.to.value",
        # braces are doubled: the description goes through str.format
        description="replace %{{name}} references in text with variable values",
    )
    def _api_variable_reference_to_value(self, text: str) -> str:
        """Replace ``%{name}`` references in text with the variables' values.

        @Ytext@w   = the text

        ``%%{name}`` becomes the literal ``%{name}``, an undefined name stays as
        typed, and a value is not expanded again.
        """
        return expand_references(text, self.variables)

    @AddParser(description="add a variable or change its value")
    @AddArgument(
        "-o", "--overwrite", help="replace the variable when the name exists", action="store_true"
    )
    @AddArgument("name", help="the variable name")
    @AddArgument("value", help="the value", nargs="*")
    def _command_add(self) -> CommandResult:
        """Add a variable or change its value."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["value"]:
            return CommandResult(False, ["Please provide a value, use remove to delete a variable"])
        name = args["name"]
        if name in self.variables and not args.get("overwrite", False):
            return CommandResult(False, [f"variable {name} exists, use -o to replace it"])
        if self.api(f"{self.plugin_id}:variable.set")(name, " ".join(args["value"])):
            return CommandResult(True, [f"variable {name} set"])
        return CommandResult(
            False,
            [
                f"could not set {name}: the name must be letters, digits and underscores "
                "and not start with a digit, and the value cannot contain a line break"
            ],
        )

    @AddParser(description="remove a variable")
    @AddArgument("name", help="the variable name")
    def _command_remove(self) -> CommandResult:
        """Remove a variable."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        if self.api(f"{self.plugin_id}:variable.remove")(name):
            return CommandResult(True, [f"variable {name} removed"])
        return CommandResult(False, [f"variable {name} does not exist"])

    @AddParser(description="list variables")
    @AddArgument(
        "match",
        help="list only variables that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List variables."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        match = args["match"]
        names = sorted(name for name in self.variables if not match or match in name)
        if not names:
            return CommandResult(True, ["No variables defined"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        return CommandResult(True, [f"{name} : {escape(self.variables[name])}" for name in names])

    @RegisterToEvent(event_name="ev_to_mud_data_modify", priority=EXPAND_PRIORITY)
    def _eventcb_expand_line(self) -> None:
        """Expand variable references in a client line."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if not line.is_io or not line.send or line.mask_log:
            return
        command_prefix = self.api("plugins.core.commands:command.prefix.get")()
        if line.line.lstrip().startswith(command_prefix):
            return
        expanded = expand_references(line.line, self.variables)
        if expanded != line.line:
            line.line = expanded
            event_record.addupdate(UpdateFlag.MODIFY, "variables expanded", savedata=False)
