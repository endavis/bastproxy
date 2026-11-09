# Project: bastproxy
# Filename: plugins/core/log/_log.py
#
# File Description: a plugin to change logging settings
#
# By: Bast

# Standard Library
import logging
import numbers

from bastproxy.libs.api import AddAPI

# 3rd Party
# Project
from bastproxy.libs.logger import LEVELS, get_logger, log_to, set_threshold
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import RMANAGER
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.log import get_toplevel
from bastproxy.plugins.core.log.libs._custom_logger import setup_loggers, type_counts


class LogPlugin(BasePlugin):
    """a class to manage logging."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Init the class."""
        self.record_manager = RMANAGER
        self.log_directory = self.api.BASEDATAPATH / "logs"
        self.logtype_col_length = 35

        self.type_counts = type_counts

        self.handlers = {}
        self.handlers["client"] = PersistentDict(
            self.plugin_id,
            self.plugin_info.data_directory / "logtypes_to_client.txt",
            "c",
        )
        self.handlers["console"] = PersistentDict(
            self.plugin_id,
            self.plugin_info.data_directory / "logtypes_to_console.txt",
            "c",
        )
        self.handlers["file"] = PersistentDict(
            self.plugin_id,
            self.plugin_info.data_directory / "logtypes_to_file.txt",
            "c",
        )

    @RegisterPluginHook("__init__", priority=99)
    def _phook_log_post_init_custom_logging(
        self,
    ):  # pyright: ignore[reportInvalidTypeVarUse]
        # setup file logging and network data logging
        get_logger(self.plugin_id).debug("setting up custom logging")
        setup_loggers(logging.DEBUG)
        for handler in ("client", "console", "file"):
            for name in list(self.handlers[handler]):
                self._sync_threshold(name)

    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        """Initialize the plugin."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "color_error",
            "@x136",
            "color",
            "the color for error messages",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "color_warning",
            "@y",
            "color",
            "the color for warning messages",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "color_info", "@w", "color", "the color for info messages"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "color_debug",
            "@x246",
            "color",
            "the color for debug messages",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "color_critical",
            "@r",
            "color",
            "the color for critical messages",
        )

    @AddAPI("log.level.color.get", description="get the color for a log level")
    def _api_log_level_color_get(self, level):
        """Get the color for a log level."""
        if isinstance(level, int):
            level = logging.getLevelName(level).lower()

        match level:
            case "error":
                try:
                    return self.api("plugins.core.settings:setting.get")(
                        self.plugin_id, "color_error"
                    )
                except Exception:
                    return "@x136"
            case "warning":
                try:
                    return self.api("plugins.core.settings:setting.get")(
                        self.plugin_id, "color_warning"
                    )
                except Exception:
                    return "@y"
            case "info":
                try:
                    return self.api("plugins.core.settings:setting.get")(
                        self.plugin_id, "color_info"
                    )
                except Exception:
                    return "@w"
            case "debug":
                try:
                    return self.api("plugins.core.settings:setting.get")(
                        self.plugin_id, "color_debug"
                    )
                except Exception:
                    return "@x246"
            case "critical":
                try:
                    return self.api("plugins.core.settings:setting.get")(
                        self.plugin_id, "color_critical"
                    )
                except Exception:
                    return "@r"
            case _:
                return ""

    def _sync_threshold(self, name: str) -> None:
        """Set the pre-filter threshold of a logger from the three handler settings.

        The threshold is never above a level any handler would accept for the name,
        so the handlers still make the routing decision.
        """
        top = get_toplevel(name)
        levels = [
            getattr(logging, self.handlers[handler][top].upper(), logging.INFO)
            for handler in ("client", "console", "file")
            if top in self.handlers[handler] and self.handlers[handler][top]
        ]
        lowest = min(levels, default=logging.INFO)
        set_threshold(top, lowest if lowest < logging.INFO else None)

    @AddAPI("logger.console.is.enabled", description="check if a logger can log to the console")
    def _api_logger_console_is_enabled(self, logger, level):
        """Check if a logger can log to the console.

        if the logger hasn't been seen, it will default to logging.INFO
        """
        logger_name = get_toplevel(logger)
        if logger_name not in self.handlers["console"]:
            self.handlers["console"][logger_name] = "info"
            self.handlers["console"].sync()

        convlevel = getattr(logging, self.handlers["console"][logger_name].upper(), logging.INFO)
        return level >= convlevel

    @AddAPI("logger.file.is.enabled", description="check if a logger can log to file")
    def _api_logger_file_is_enabled(self, logger, level):
        """Check if a logger can log to the file.

        if the logger hasn't been seen, it will default to logging.INFO
        """
        logger_name = get_toplevel(logger)
        if logger_name not in self.handlers["file"]:
            self.handlers["file"][logger_name] = "info"
            self.handlers["file"].sync()

        convlevel = getattr(logging, self.handlers["file"][logger_name].upper(), logging.INFO)
        return level >= convlevel

    @AddAPI("logger.client.is.enabled", description="check if a logger can log to the client")
    def _api_logger_client_is_enabled(self, logger, level):
        """Check if a logger can log to the client.

        if the logger hasn't been seen, do not allow logging to the client
        logging to the client must be explicitly enabled
        """
        logger_name = get_toplevel(logger)
        return logger_name in self.handlers["client"] and level >= getattr(
            logging, self.handlers["client"][logger_name].upper(), logging.INFO
        )

    @AddAPI("logger.client.level.set", description="toggle a log type to show to clients")
    def _api_logger_client_level_set(self, logtype, level: str = "info", flag=True):
        """Toggle a log type to show to clients.

        @Ylogtype@w   = the type to toggle, can be multiple (list)
        @Yflag@w      = True to send to clients, false otherwise (default: True).

        this function returns no values
        """
        get_logger(self.plugin_id).debug(
            "_api_logger_client_level_set: %s %s %s", logtype, level, flag
        )

        logger_name = get_toplevel(logtype)
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            log_to(
                [self.plugin_id, logger_name],
                logging.ERROR,
                "api_toggletoclient: invalid log level %s",
                level,
            )
            return

        if flag and logger_name not in self.handlers["client"]:
            self.handlers["client"][logger_name] = level
            log_to(
                [self.plugin_id, logger_name],
                logging.DEBUG,
                "setting %s to log to client at level %s",
                logger_name,
                level,
            )
        elif not flag and logger_name in self.handlers["client"]:
            del self.handlers["client"][logger_name]
            log_to(
                [self.plugin_id, logger_name],
                logging.DEBUG,
                "removing %s logging to client %s",
                logger_name,
                level,
            )

        self._sync_threshold(logger_name)
        self.handlers["client"].sync()

    @AddParser(
        description="""toggle logtypes to clients

          if no arguments, log types that are currenty sent to clients will be listed"""
    )
    @AddArgument("logtype", help="a list of logtypes to toggle", default=[], nargs="*")
    @AddArgument(
        "-l",
        "--level",
        help="the level to log at",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
    )
    @AddArgument(
        "-r",
        "--remove",
        help="remove the logtype from logging to the client",
        action="store_true",
        default=False,
    )
    def _command_client(self):
        """Toggle logtypes shown to client."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        tmsg = []
        level = args["level"]
        if args["logtype"]:
            remove = not args["remove"]
            for i in args["logtype"]:
                logger_name = get_toplevel(i)
                self.api(f"{self.plugin_id}:logger.client.level.set")(
                    logger_name, level=level, flag=remove
                )
                if logger_name in self.handlers["client"]:
                    tmsg.append(f"setting {logger_name} to log to client at level {level}")
                else:
                    tmsg.append(f"no longer sending {logger_name} to client")

            self.handlers["client"].sync()
            return True, tmsg

        tmsg.extend(
            (
                "Current types going to client",
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['client'][i]:<}"
            for i in self.handlers["client"]
            if self.handlers["client"][i]
        )
        return True, tmsg

    @AddAPI("logger.console.level.set", description="toggle a log type to show to console")
    def _api_logger_console_level_set(self, logtype, level="info"):
        """Toggle a log type to show to console.

        @Ylogtype@w   = the type to toggle
        @Yflag@w      = True to send to console, false otherwise (default: True).

        this function returns no values
        """
        get_logger(self.plugin_id).debug("_api_logger_console_level_set: %s %s", logtype, level)

        logger_name = get_toplevel(logtype)
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            log_to(
                [self.plugin_id, logger_name],
                logging.ERROR,
                "_api_logger_console_level_set: invalid log level %s",
                level,
            )
            return

        self.handlers["console"][logger_name] = level
        log_to(
            [self.plugin_id, logger_name],
            logging.DEBUG,
            "setting %s to log to console at level %s",
            logger_name,
            level,
        )

        self._sync_threshold(logger_name)
        self.handlers["console"].sync()

    @AddParser(
        description="""change the level of logging for a logtype to the console
          this will toggle the logtype between 'info' and 'debug'

          if no arguments, log types that are currenty sent to the console will be listed"""
    )
    @AddArgument("logtype", help="a list of logtypes to toggle", default=[], nargs="*")
    def _command_console(self):
        """Toggle logtypes to the console."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        tmsg = []
        if args["logtype"]:
            for i in args["logtype"]:
                logger_name = get_toplevel(i)
                if logger_name not in self.handlers["console"]:
                    self.handlers["console"][logger_name] = "info"
                if self.handlers["console"][logger_name] == "info":
                    self.api(f"{self.plugin_id}:logger.console.level.set")(
                        logger_name, level="debug"
                    )
                    tmsg.append(f"setting {logger_name} to log to console at level 'debug'")
                else:
                    self.api(f"{self.plugin_id}:logger.console.level.set")(
                        logger_name, level="info"
                    )
                    tmsg.append(f"setting {logger_name} to log to console at default level 'info'")

            self.handlers["console"].sync()
            return True, tmsg

        tmsg.extend(
            (
                "Current types going to console",
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['console'][i]:<}"
            for i in self.handlers["console"]
            if self.handlers["console"][i]
        )
        return True, tmsg

    @AddAPI("logger.file.level.set", description="toggle a log type to log to a file")
    def _api_logger_file_level_set(self, logtype, level="info"):
        """Toggle a log type to log to a file.

        @Ylogtype@w   = the type to toggle
        @Yflag@w      = True to send to file, false otherwise (default: True).

        this function returns no values
        """
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            log_to(
                [self.plugin_id, logtype],
                logging.ERROR,
                "_api_logger_file_level_set: invalid log level %s",
                level,
            )
            return

        logger_name = get_toplevel(logtype)
        self.handlers["file"][logger_name] = level
        log_to(
            [self.plugin_id, logger_name],
            logging.DEBUG,
            "setting %s to log to file at level %s",
            logger_name,
            level,
        )

        self._sync_threshold(logger_name)
        self.handlers["file"].sync()

    @AddParser(
        description="""toggle logtypes to log to a file

          the file will be located in the data/logs/<logtype> directory

          if no arguments, types that are sent to file will be listed"""
    )
    @AddArgument("logtype", help="a list of logtypes to toggle", default=[], nargs="*")
    @AddArgument(
        "-n",
        "--notimestamp",
        help="do not log to file with a timestamp",
        action="store_false",
    )
    def _command_file(self):
        """Toggle a logtype to log to a file."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        tmsg = []
        if args["logtype"]:
            for i in args["logtype"]:
                logger_name = get_toplevel(i)
                if logger_name not in self.handlers["file"]:
                    self.handlers["file"][logger_name] = "info"
                if self.handlers["file"][logger_name] == "info":
                    self.api(f"{self.plugin_id}:logger.file.level.set")(logger_name, level="debug")
                    tmsg.append(f"setting {logger_name} to log to file at level 'debug'")
                else:
                    self.api(f"{self.plugin_id}:logger.file.level.set")(logger_name, level="info")
                    tmsg.append(f"setting {logger_name} to log to file at default level 'info'")

            self.handlers["file"].sync()
            return True, tmsg

        tmsg.extend(
            (
                "Current types going to file",
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['file'][i]:<}"
            for i in self.handlers["file"]
            if self.handlers["file"][i]
        )
        return True, tmsg

    @AddParser(description="list all logging types")
    @AddArgument(
        "match",
        help="only list logtypes that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_types(self):
        """List log types."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        types = []
        types.extend(self.handlers["client"].keys())
        types.extend(self.handlers["console"].keys())
        types.extend(self.handlers["file"].keys())
        types = sorted(set(types))
        tmsg = [
            "-" * 79,
        ]
        match = args["match"]

        if match:
            types = [i for i in types if match in i]

        if types:
            tmsg.extend(
                (
                    f"{'logtype':<{self.logtype_col_length}} : {'debug':<5} {'info':<5} {'warning':<7} {'error':<5} {'critical':<8}",
                    "-" * 79,
                )
            )
            for i in types:
                if i in self.type_counts:
                    tmsg.append(
                        f"{i:<{self.logtype_col_length}} : {self.type_counts[i]['debug']:<5} {self.type_counts[i]['info']:<5} {self.type_counts[i]['warning']:<7} {self.type_counts[i]['error']:<5} {self.type_counts[i]['critical']:<8}"
                    )
                else:
                    tmsg.append(
                        f"{i:<{self.logtype_col_length}} : {'0':<5} {'0':<5} {'0':<7} {'0':<5} {'0':<8}"
                    )
        else:
            tmsg.append(f"No matches found for {match}")

        return True, tmsg

    @AddParser(description="test logging facilities")
    @AddArgument("message", help="the text to log")
    @AddArgument("-l", "--logtype", help="the facility to test", required=True)
    @AddArgument(
        "-ll",
        "--loglevel",
        help="the level for the test",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        required=True,
    )
    def _command_test(self):
        """Send test records to logging facilities."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        logtype = args["logtype"]
        message = args["message"]
        level = args["loglevel"]

        tmsg = [f"'{message}' sent to '{logtype}' as level '{level}'"]

        levelno = LEVELS[level]
        console = not self.api.quiet_mode and self.api(
            f"{self.plugin_id}:logger.console.is.enabled"
        )(logtype, levelno)
        to_file = self.api(f"{self.plugin_id}:logger.file.is.enabled")(logtype, levelno)
        client = not self.api.startup and (
            self.api(f"{self.plugin_id}:logger.client.is.enabled")(logtype, levelno)
            or levelno >= logging.ERROR
        )

        get_logger(logtype).log(levelno, "%s", message)

        tmsg.extend(
            (
                f"Console: {bool(console)}",
                f"File: {bool(to_file)}",
                f"Client: {bool(client)}",
            )
        )
        return True, tmsg

    @AddAPI("logger.type.clean", description="clean log types that have not been logged to")
    def _api_logger_type_clean(self):
        """Clean log types with no counts."""
        remove = []

        types = []
        types.extend(self.handlers["client"].keys())
        types.extend(self.handlers["console"].keys())
        types.extend(self.handlers["file"].keys())
        types = sorted(set(types))

        for i in types:
            if i not in self.type_counts or max(self.type_counts[i].values()) <= 0:
                remove.append(i)

        for i in remove:
            if i in self.handlers["client"]:
                del self.handlers["client"][i]
            if i in self.handlers["console"]:
                del self.handlers["console"][i]
            if i in self.handlers["file"]:
                del self.handlers["file"][i]
            if i in self.type_counts:
                del self.type_counts[i]
            self._sync_threshold(i)

        self.handlers["file"].sync()
        self.handlers["client"].sync()
        self.handlers["console"].sync()

        return remove

    @RegisterToEvent(event_name="ev_plugins.core.proxy_shutdown")
    def _eventcb_proxy_shutdown(self):
        """Clean up log types."""
        self.api(f"{self.plugin_id}:logger.type.clean")()

    @AddParser(description="remove log types that have not been used")
    def _command_clean(self):
        """Remove log types that have not been used."""
        remove = self.api(f"{self.plugin_id}:logger.type.clean")()

        tmsg = ["Removed the following types:"]

        tmsg.extend(remove)

        return True, tmsg

    @RegisterPluginHook("save")
    def _phook_log_save(self):
        """Save items not covered by baseplugin class."""
        self.handlers["client"].sync()
        self.handlers["file"].sync()
        self.handlers["console"].sync()
