# Project: bastproxy
# Filename: plugins/core/sqldb/_sqldb.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

# Standard Library
import logging
import sqlite3
import weakref

# 3rd Party
# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb


class SQLDBPlugin(BasePlugin):
    """a plugin to handle the base sqldb."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        self.reload_dependents_f = True
        self.databases: dict[str, weakref.WeakSet[Sqldb]] = {}

    @AddAPI("baseclass.get", description="return the sql baseclass")
    def _api_baseclass_get(self) -> type[Sqldb]:
        # pylint: disable=no-self-use
        """Return the sql baseclass."""
        return Sqldb

    @AddAPI(
        "database.register",
        description="track a database so it is closed when its plugin unloads",
    )
    def _api_database_register(self, db: Sqldb) -> None:
        """Track a database under the plugin that owns it."""
        self.databases.setdefault(db.plugin_id, weakref.WeakSet()).add(db)

    def _close_databases_for(self, plugin_id: str) -> None:
        """Close and forget every database a plugin registered."""
        for db in list(self.databases.pop(plugin_id, ())):
            try:
                db.close()
            except sqlite3.Error:
                log_to(
                    [self.plugin_id, plugin_id],
                    logging.ERROR,
                    "_close_databases_for - could not close database %s of plugin %s",
                    db.database_name,
                    plugin_id,
                    exc_info=True,
                )

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded, close its databases."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            log_to(
                [self.plugin_id, event_record["plugin_id"]],
                logging.DEBUG,
                "_eventcb_plugin_unloaded - closing databases for plugin %s",
                event_record["plugin_id"],
            )
            self._close_databases_for(event_record["plugin_id"])
