# Project: bastproxy
# Filename: plugins/core/ssc/_ssc.py
#
# File Description: a plugin to save settings that should not stay in memory
#
# By: Bast

# Standard Library
import os
import stat
from pathlib import Path

# 3rd Party
# Project
from libs.api import API, AddAPI
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from plugins.core.commands import AddArgument, AddCommand, AddParser


class SSC:
    """a class to manage settings."""

    def __init__(self, name, plugin_id, data_directory, **kwargs):
        """Initialize the class."""
        self.name = name
        self.api = API(owner_id=f"{plugin_id}:{name}")
        self.plugin_id = plugin_id
        self.data_directory = data_directory
        self.file_name = Path(self.data_directory) / Path(self.name)

        self.default = kwargs.get("default", "")
        self.desc = kwargs.get("desc", "setting")

    @AddAPI("ssc.{name}", description="get the {desc} value")
    def _api_getss(self, quiet=False):
        """Read the secret from a file."""
        first_line = ""
        try:
            with open(self.file_name) as fileo:
                first_line = fileo.readline()

            return first_line.strip()
        except OSError:
            if not quiet:
                LogRecord(
                    f"getss - Please set the {self.desc} with {self.api('plugins.core.commands:get.command.format')(self.plugin_id, self.name)}",
                    level="warning",
                    sources=[self.plugin_id],
                )()

        return self.default

    @AddCommand(name="{name}", show_in_history=False)
    @AddParser(description="set the {desc}")
    @AddArgument("value", help="the new {desc}", default="", nargs="?")
    def _command_setssc(self):
        """Set the secret."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        if args["value"]:
            with open(self.file_name, "w") as data_file:
                data_file.write(args["value"])
            os.chmod(self.file_name, stat.S_IRUSR | stat.S_IWUSR)
            return True, [f"{self.desc} saved"]

        return True, [f"Please enter the {self.desc}"]


class SSCPlugin(BasePlugin):
    """a plugin to handle secret settings."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.reload_dependents_f = True

    @AddAPI("baseclass.get", description="return the ssc baseclass")
    def _api_baseclass_get(self):
        # pylint: disable=no-self-use
        """Return the ssc baseclass."""
        return SSC
