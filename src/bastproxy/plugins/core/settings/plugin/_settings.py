# Project: bastproxy
# Filename: plugins/core/example/_settings.py
#
# File Description: settings plugin
#
# By: Bast

# Standard Library
import contextlib
import logging
import textwrap
from pathlib import Path

from bastproxy.libs import argp

# 3rd Party
# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.settings.libs._settinginfo import (
    SettingInfo,
    SettingValidationError,
)

logger = get_logger(__name__)


class SettingsPlugin(BasePlugin):
    """a test plugin."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Initialize the instance through common __init__ method."""
        # a map of setting names to plugins
        # this is used to check for conflicts
        self.settings_map = {}

        # a dictionary of settings info
        # the key is the plugin_id and the value is a dictionary of settings info
        self.settings_info = {}

        # a dictionary of settings values with plugin_id as key
        # the value is a PersistentDict object
        self.settings_values = {}

    @AddAPI("setting.add", description="add a setting to a plugin")
    def _api_setting_add(self, plugin_id, setting_name, default, stype, help, **kwargs):
        """@Yplugin_id@w     = the plugin_id of the owner of the setting.

        @Ysetting_name@w  = the name of the setting
        @Ydefault@w    = the default value of the setting
        @Ystype@w      = the type of the setting
        @Yshelp@w      = the help associated with the setting
        Keyword Arguments
          @Ynocolor@w    = if True, don't parse colors when showing value
          @Yreadonly@w   = if True, can't be changed by a client
          @Yhidden@w     = if True, don't show in @Ysettings@w command
          @Yaftersetmessage@w = message to send to client after setting is changed.
          @Yvalidator@w  = optional callable taking the converted value; returns
                           None or "" if valid, else an error message string
        """
        get_logger(self.plugin_id).debug(
            "setting %s.%s %s %s %s %s", plugin_id, setting_name, default, stype, help, kwargs
        )
        if plugin_id not in self.settings_info:
            self.settings_info[plugin_id] = {}
        if setting_name in self.settings_info[plugin_id]:
            get_logger(self.plugin_id).error(
                "setting %s.%s already exists", plugin_id, setting_name
            )
            return

        setting_info = SettingInfo(setting_name, default, help, stype, **kwargs)
        get_logger(self.plugin_id).debug(
            "setting info %s", self.dump_object_as_string(setting_info)
        )

        if not setting_info.hidden:
            if setting_name in self.settings_map:
                get_logger(self.plugin_id).error(
                    "setting %s already exists in %s", setting_name, self.settings_map[setting_name]
                )

                return

            self.settings_map[setting_name] = plugin_id

        if plugin_id not in self.settings_values:
            data_directory = self.api(f"{plugin_id}:data.directory.get")()
            settings_file: Path = data_directory / "settingvalues.txt"
            self.settings_values[plugin_id] = PersistentDict(plugin_id, settings_file, "c")

        if setting_name not in self.settings_values[plugin_id]:
            self.settings_values[plugin_id][setting_name] = setting_info.default

        self.settings_info[plugin_id][setting_name] = setting_info

    @AddAPI("setting.get", description="get the value of a setting")
    def _api_setting_get(self, plugin_id, setting):
        """Get the value of a setting.

        @Ysetting@w = the setting value to get
        @Yplugin@w = the plugin to get the setting from (optional).

        Returns:
          the value of the setting, None if not found
        """
        returnval = None

        with contextlib.suppress(KeyError):
            returnval = (
                self.api("plugins.core.utils:value.verify")(
                    self.settings_values[plugin_id][setting],
                    self.settings_info[plugin_id][setting].stype,
                )
                if self.api("libs.api:api.exists")("plugins.core.utils:value.verify")
                else self.settings_values[plugin_id][setting]
            )

        return returnval

    @RegisterToEvent(event_name="ev_plugin_loaded")
    def _eventcb_settings_plugin_loaded(self):
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            plugin_id = event_record["plugin_id"]
            self.api(f"{self.plugin_id}:setting.event.raise.all")(plugin_id)

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_settings_plugin_unloaded(self):
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            plugin_id = event_record["plugin_id"]
            # a plugin that failed to load may never have added a setting
            if plugin_id in self.settings_values or plugin_id in self.settings_info:
                self.api(f"{self.plugin_id}:setting.save.for.plugin")(plugin_id)
                self.api(f"{self.plugin_id}:setting.remove.for.plugin")(plugin_id)

    @RegisterToEvent(event_name="ev_plugin_save")
    def _eventcb_settings_plugin_save(self):
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            plugin_id = event_record["plugin_id"]
            self.api(f"{self.plugin_id}:setting.save.for.plugin")(plugin_id)

    @RegisterToEvent(event_name="ev_plugin_reset")
    def _eventcb_plugin_reset(self):
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            plugin_id = event_record["plugin_id"]
            self.api(f"{self.plugin_id}:setting.reset")(plugin_id)
            event_record["plugins_that_acted"].append(self.plugin_id)

    @AddAPI("setting.reset", description="reset all settings for a plugin to their default values")
    def _api_setting_reset(self, plugin_id):
        """Reset all settings for a plugin to their default values."""
        self.settings_values[plugin_id].clear()
        for i in self.settings_info[plugin_id]:
            self.settings_values[plugin_id][i] = self.settings_info[plugin_id][i].default
        self.settings_values[plugin_id].sync()

    @AddAPI("setting.set", description="change the value of a setting")
    def _api_setting_set(self, plugin_id, setting, value):
        """Change a setting.

        @Yplugin_id@w     = the plugin_id of the owner of the setting
        @Ysetting@w    = the name of the setting to change
        @Yvalue@w      = the value to set it as.

        Raises:
          SettingValidationError (a ValueError) if the setting's validator
          rejects the value; the old value is kept

        Returns:
          True if the value was changed, False otherwise
        """
        if plugin_id not in self.settings_info:
            return False

        if setting not in self.settings_info[plugin_id]:
            return False

        if value == "default":
            value = self.settings_info[plugin_id][setting].default
        elif self.api("libs.plugins.loader:plugin.is.loaded")("plugins.core.utils"):
            value = self.api("plugins.core.utils:value.verify")(
                value, self.settings_info[plugin_id][setting].stype
            )

        validator = getattr(self.settings_info[plugin_id][setting], "validator", None)
        if validator and (error := validator(value)):
            raise SettingValidationError(error)

        old_value = self.api("plugins.core.settings:setting.get")(plugin_id, setting)

        if old_value == value:
            return True

        self.settings_values[plugin_id][setting] = value
        self.settings_values[plugin_id].sync()

        if not self.api("libs.plugins.loader:plugin.is.loaded")(plugin_id) or self.api(
            "plugins.core.settings:setting.is.hidden"
        )(plugin_id, setting):
            return True
        if self.api.startup:
            return True

        new_value = self.api("plugins.core.settings:setting.get")(plugin_id, setting)

        event_name = f"ev_{plugin_id}_var_{setting}_modified"

        if self.api("libs.api:api.exists")("plugins.core.events:event.raise"):
            self.api("plugins.core.events:event.raise")(
                event_name,
                event_args={
                    "var": setting,
                    "newvalue": new_value,
                    "oldvalue": old_value,
                },
            )

        return True

    @AddAPI("setting.info.get", description="get the info for a setting")
    def _api_setting_info_get(self, plugin_id, setting):
        """Get the info for a setting."""
        if plugin_id not in self.settings_info:
            return None
        if setting not in self.settings_info[plugin_id]:
            return None
        return self.settings_info[plugin_id][setting]

    @AddAPI("setting.initialize.for.plugin", description="initialize the settings for a plugin")
    def _api_setting_initialize_for_plugin(self, plugin_id):
        """Initialize the settings for a plugin."""
        log_to(
            [self.plugin_id, plugin_id], logging.DEBUG, "initializing settings for %s", plugin_id
        )
        if plugin_id not in self.settings_info:
            self.settings_info[plugin_id] = {}

        for i in self.settings_info[plugin_id]:
            if self.api("plugins.core.settings:setting.is.hidden")(plugin_id, i):
                continue
            self.api("plugins.core.events:event.add")(
                f"ev_{plugin_id}_var_{i}_modified",
                plugin_id,
                description=[f"An event to modify the setting {i}"],
                arg_descriptions={
                    "var": "the variable that was modified",
                    "newvalue": "the new value",
                    "oldvalue": "the old value",
                },
            )

    @AddAPI("setting.remove.for.plugin", description="remove the settings for a plugin")
    def _api_setting_remove_for_plugin(self, plugin_id):
        """Removing the settings for a plugin."""
        log_to([self.plugin_id, plugin_id], logging.DEBUG, "Removing settings for %s", plugin_id)
        for i in self.settings_info.pop(plugin_id, {}):
            if i in self.settings_map:
                del self.settings_map[i]

        if (values := self.settings_values.pop(plugin_id, None)) is not None:
            values.close()

    @AddAPI("setting.save.for.plugin", description="save the settings for a plugin")
    def _api_setting_save_for_plugin(self, plugin_id):
        """Save the settings for a plugin."""
        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "%s : Saving settings for %s",
            self.plugin_id,
            plugin_id,
        )
        self.settings_values[plugin_id].sync()

    @AddAPI("setting.list", description="get all settings for a plugin")
    def _api_setting_list(self, plugin_id):
        """Get all settings info for a plugin."""
        return self.settings_info[plugin_id]

    @AddAPI("setting.event.raise.all", description="raise an event for all settings")
    def _api_setting_event_raise_all(self, plugin_id):
        """Raise an event for all settings."""
        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "Raising events for all settings in %s",
            plugin_id,
        )
        old_value = "__init__"
        for i in self.settings_info[plugin_id]:
            if self.api("plugins.core.settings:setting.is.hidden")(plugin_id, i):
                continue
            event_name = f"ev_{plugin_id}_var_{i}_modified"
            new_value = self.api("plugins.core.settings:setting.get")(plugin_id, i)

            self.api("plugins.core.events:event.raise")(
                event_name,
                event_args={"var": i, "newvalue": new_value, "oldvalue": old_value},
            )

    @AddAPI("setting.is.hidden", description="check if a plugin setting is flagged hidden")
    def _api_setting_is_hidden(self, plugin_id, setting):
        """Check if a plugin setting is hidden."""
        return self.settings_info[plugin_id][setting].hidden

    @AddAPI("setting.map.add", description="add a setting to the settings map")
    def _api_setting_map_add(self, plugin_id, setting_name):
        """Add a setting to the settings map."""
        if setting_name in self.settings_map:
            logger.error(
                "setting %s.%s conflicts %s:%s",
                plugin_id,
                setting_name,
                self.settings_map[setting_name],
                setting_name,
            )
            return
        self.settings_map[setting_name] = plugin_id

    def format_setting_for_print(self, plugin_id, setting_name):
        """Format a setting for printing."""
        value = self.api(f"{self.plugin_id}:setting.get")(plugin_id, setting_name)
        setting_info = self.api(f"{self.plugin_id}:setting.info.get")(plugin_id, setting_name)
        if setting_info.nocolor:
            value = value.replace("@", "@@")
        elif setting_info.stype == "color":
            value = f"{value}{value.replace('@', '@@')}@w"
        elif setting_info.stype == "timelength":
            value = self.api("plugins.core.utils:timelength.format")(
                self.api("plugins.core.utils:value.verify")(value, "timelength")
            )

        return str(value)

    @AddAPI("setting.format", description="format a setting")
    def _api_setting_format(self, plugin_id, setting_name):
        """Format a setting."""
        val = self.api(f"{self.plugin_id}:setting.get")(plugin_id, setting_name)
        info = self.api(f"{self.plugin_id}:setting.info.get")(plugin_id, setting_name)

        if info.hidden:
            return ""

        value_column_width = 15
        help = info.help
        value_string = self.format_setting_for_print(plugin_id, setting_name)
        if info.stype == "color":
            tlen = len(val)
            value_column_width = value_column_width + 3 + tlen
            help = f"{val}{help}@w"

        return f"{setting_name:<22} : {value_string:<{value_column_width}} - {help}"

    @AddAPI("setting.list.formatted", description="get all settings formatted")
    def _api_setting_list_formatted(self, plugin_id):
        """Get all settings formatted."""
        tmsg = []
        if not self.settings_info[plugin_id]:
            return [f"There are no settings defined in {plugin_id}"]

        for i in self.settings_info[plugin_id]:
            if formatted_setting := self.api("plugins.core.settings:setting.format")(plugin_id, i):
                tmsg.append(formatted_setting)

        return tmsg or [f"There are no settings defined in {plugin_id}"]

    @AddCommand(group="Settings", show_in_history=False)
    @AddParser(description="List all settings")
    @AddArgument(
        "search",
        help="only list settings with the included string",
        default="",
        nargs="?",
    )
    @AddArgument(
        "-p",
        "--plugin",
        help="onyl show settings in the specific plugin",
        default="",
        nargs="?",
    )
    def _command_list(self):
        """List all settings."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        line_length = self.api("plugins.core.commands:output.line.length.get")()
        header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )
        loaded_plugins = self.api("libs.plugins.loader:plugin.list.loaded")()

        default_message = ["No settings found"]

        settings = {}
        if args["plugin"]:
            default_message = [f"No settings found for {args['plugin']}"]
            if self.api("libs.plugins.loader:plugin.is.loaded")(args["plugin"]):
                settings[args["plugin"]] = self.api(f"{self.plugin_id}:setting.list")(
                    args["plugin"]
                )
            else:
                return CommandResult(True, ["Plugin does not exist"])
        else:
            for plugin_id in loaded_plugins:
                settings[plugin_id] = self.api(f"{self.plugin_id}:setting.list")(plugin_id)

        if not settings:
            return CommandResult(True, ["No settings found"])

        message = [
            f"{'Plugin ID':<30} {'Setting':<22} : {'Value':<15} - Help",
            header_color + "-" * line_length + "@w",
        ]
        plugin_message = []
        for plugin_id, plugin_settings in settings.items():
            for setting_name in plugin_settings:
                if args["search"] and args["search"] not in setting_name:
                    continue
                if plugin_settings[setting_name].readonly:
                    continue
                if setting_format := self.api(f"{self.plugin_id}:setting.format")(
                    plugin_id, setting_name
                ):
                    plugin_message.append(f"{plugin_id:<30} {setting_format}")

        if not plugin_message:
            return CommandResult(True, default_message)

        message.extend(plugin_message)
        return CommandResult(True, message)

    @AddCommand(group="Settings", name="pset", show_in_history=False)
    @AddParser(
        formatter_class=argp.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
                change a setting in the plugin

                if there are no arguments or 'list' is the first argument then
                it will list the settings for the plugin"""
        ),
    )
    @AddArgument("name", help="the setting name", default="list", nargs="?")
    @AddArgument("value", help="the new value of the setting", default="", nargs="?")
    @AddArgument("-p", "--plugin", help="the plugin of the setting", default="", nargs="?")
    def _command_settings_plugin_sets(self):
        """Command to set a plugin setting."""
        args = self.api("plugins.core.commands:command.current.args.get")()

        success, message = self.api(f"{self.plugin_id}:setting.set.from.user")(
            args["name"], args["value"], args["plugin"]
        )
        return CommandResult(success, message)

    @AddAPI(
        "setting.set.from.user",
        description="validate and change a setting from user input, returning a message",
    )
    def _api_setting_set_from_user(
        self, setting_name: str, value: str, plugin_id: str = ""
    ) -> tuple[bool, list[str]]:
        """Validate user input and change a setting.

        @Ysetting_name@w = the name of the setting to change
        @Yvalue@w        = the value to set it as
        @Yplugin_id@w    = the plugin that owns the setting, looked up from the
                           settings map when empty

        Returns:
          a tuple of (success, list of message lines to show the user)
        """
        if not value:
            return False, ["please specify a value to set the setting to"]

        if setting_name not in self.settings_map:
            return True, [f"plugin setting {setting_name} does not exist"]

        plugin_id = plugin_id or self.settings_map[setting_name]

        if not (
            setting_info := self.api("plugins.core.settings:setting.info.get")(
                plugin_id, setting_name
            )
        ):
            return True, [f"plugin setting {plugin_id} {setting_name} does not exist"]
        if setting_info.hidden:
            return True, [f"plugin setting {plugin_id} {setting_name} does not exist"]
        if setting_info.readonly:
            return True, [f"{setting_name} is a readonly setting"]

        val = value
        try:
            self.api("plugins.core.settings:setting.set")(plugin_id, setting_name, val)
            tsetting_name = self.format_setting_for_print(plugin_id, setting_name)
            tmsg = [f"{plugin_id} : {setting_name} is now set to {tsetting_name}"]
            if setting_info.aftersetmessage:
                tmsg.extend(["\n", setting_info.aftersetmessage])
        except SettingValidationError as err:
            return True, [str(err)]
        except ValueError:
            msg = [f"Cannot convert {val} to {setting_info.stype}"]
            return True, msg
        else:
            return True, tmsg
