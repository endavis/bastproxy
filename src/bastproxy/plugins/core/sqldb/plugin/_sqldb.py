# Project: bastproxy
# Filename: plugins/core/sqldb/_sqldb.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

# Standard Library
import logging
import sqlite3
import warnings
import weakref
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.scan import find_methods
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb, create_database


class SQLDBPlugin(BasePlugin):
    """a plugin to handle the base sqldb."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        self.reload_dependents_f = True
        self.databases: dict[str, weakref.WeakSet[Sqldb]] = {}

    @AddAPI("baseclass.get", description="return the sql baseclass (deprecated)")
    def _api_baseclass_get(self) -> type[Sqldb]:
        # pylint: disable=no-self-use
        """Return the sql baseclass.

        Deprecated: use ``plugins.core.sqldb:database.add`` instead.
        """
        warnings.warn(
            "plugins.core.sqldb:baseclass.get is deprecated; use plugins.core.sqldb:database.add",
            DeprecationWarning,
            stacklevel=2,
        )
        return Sqldb

    @AddAPI(
        "database.add",
        description="create a database from plain-data table and migration definitions",
    )
    def _api_database_add(
        self,
        owner_id: str,
        name: str,
        tables: Sequence[Mapping[str, Any]] = (),
        *,
        version: int = 1,
        migrations: Mapping[int, str | Callable[[Sqldb], Any]] | None = None,
        directory: Path | None = None,
    ) -> Sqldb:
        """Create a database for a plugin, with tables created and migrations applied.

        Args:
            owner_id: The plugin id that owns the database.
            name: The database name, ``[a-z][a-z0-9_]*``.
            tables: Table definitions, dicts with ``name`` and ``sql`` and optionally
                ``keyfield``, ``precreate`` and ``postcreate`` (callables taking the db).
            version: The version the database should be at.
            migrations: Maps each version from 2 to ``version`` to a SQL script string
                or a callable taking the db.
            directory: Where the file lives, default the owner's plugin data directory.

        Returns:
            The ready Sqldb. Its ``{name}.*`` APIs and ``db*`` commands are registered
            under the owner and the database is closed when the owner unloads.
            The ``db*`` commands act on one of the owner's databases: pass
            ``--db <name>`` to pick it. It is optional with a single database and
            required with several.

        Raises:
            ValueError: The owner is unknown, the database exists or a definition is invalid.
            sqlite3.Error: A table or a migration failed.

        """
        loader_api = "libs.plugins.loader:plugin.id.is.valid"
        if self.api("libs.api:api.exists")(loader_api) and not self.api(loader_api)(owner_id):
            msg = f"{owner_id!r} is not a plugin id"
            raise ValueError(msg)
        if any(db.database_name == name for db in self.databases.get(owner_id, ())):
            msg = f"plugin {owner_id} already has a database named {name!r}"
            raise ValueError(msg)
        if directory is None:
            directory = self.api.BASEDATAPLUGINPATH / owner_id
        try:
            db = create_database(
                owner_id, name, tables, version=version, migrations=migrations, directory=directory
            )
        except Exception:
            for tracked in list(self.databases.get(owner_id, ())):
                if tracked.database_name == name:
                    self.databases[owner_id].discard(tracked)
            raise
        self._api_database_register(db)
        self.api("libs.api:api.add.for.object")(owner_id, db)
        add_command = "plugins.core.commands:command.add.by.func"
        if self.api("libs.api:api.exists")(add_command):
            for command in find_methods(
                db,
                lambda m: hasattr(m, "command_data") and m.__name__.startswith("_command_"),
            ):
                self.api(add_command)(command)
        return db

    @AddAPI(
        "database.register",
        description="track a database so it is closed when its plugin unloads",
    )
    def _api_database_register(self, db: Sqldb) -> None:
        """Track a database under the plugin that owns it."""
        owned = self.databases.setdefault(db.plugin_id, weakref.WeakSet())
        owned.add(db)
        db.owner_databases = owned

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
