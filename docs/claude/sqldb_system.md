---
title: SQLite Database System
description: How plugins store data in SQLite through the sqldb plugin
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - sqldb
---

# SQLite Database System

## Overview

The sqldb plugin (`plugins.core.sqldb`) gives plugins SQLite databases. A plugin declares its
tables and schema migrations as plain data and calls one API, `plugins.core.sqldb:database.add`.
The plugin gets back a ready database object: tables created, migrations applied, its APIs and
maintenance commands registered under the plugin, and the database closed when the plugin unloads.

The decision behind this design is [ADR-0014](../decisions/0014-plugins-add-sqldb-databases-through-databaseadd-with-plain-data-definitions.md).
The plugin-author walkthrough is in the
[plugin developer guide](../plugin-developer-guide.md#storing-data-in-sqlite).

## Key Components

| Component | Location | Role |
| :--- | :--- | :--- |
| `SQLDBPlugin` | `src/bastproxy/plugins/core/sqldb/plugin/_sqldb.py` | The plugin: the `database.add` factory, database tracking, close on unload |
| `Sqldb` | `src/bastproxy/plugins/core/sqldb/libs/_sqlite.py` | One database: connection, statements, migrations, backups, `db*` commands |
| `create_database` | `src/bastproxy/plugins/core/sqldb/libs/_sqlite.py` | Validates the plain-data definition and builds a `Sqldb` |
| `SQLTable` | `src/bastproxy/plugins/core/sqldb/libs/_sqlite.py` | One registered table: create SQL, key field, hooks and the columns sqlite reports |

Plugins never import these modules. The loader treats `src/bastproxy/plugins/core/sqldb/libs` as part of the
sqldb plugin and reloads it with the plugin, so another plugin reaches it only through the API.

## Creating a Database

```python
self.statdb = self.api("plugins.core.sqldb:database.add")(
    self.plugin_id,                      # owner_id
    "stats",                             # name, [a-z][a-z0-9_]*
    [{"name": "stats", "sql": STATS_SQL, "keyfield": "stat_id"}],
    version=2,
    migrations={2: "ALTER TABLE stats ADD COLUMN redos INT DEFAULT 0;"},
)
```

Call it from an `after_load` plugin hook, and declare
`PLUGIN_DEPENDENCIES = ["plugins.core.sqldb"]` in the plugin package's `__init__.py`. The sqldb
plugin reloads its dependents, so a sqldb reload reloads the owner, which adds its database again.

### Arguments

- **`owner_id`**: the owning plugin's id. An id the loader does not know is refused.
- **`name`**: the database name. It becomes the file name and the first part of the
  database's API names. One owner cannot add two databases with the same name.
- **`tables`**: a sequence of dicts:
  - `name` and `sql` (required): the table name and its `CREATE TABLE` statement. The `sql` is the
    **current** schema, including columns that later migrations add to older files.
  - `keyfield` (optional): the key column, used by `getrow`, `getlast`, `remove` and `dbremove`.
  - `precreate`, `postcreate` (optional): callables taking the database, run before and after the
    table is created on a database that does not have it yet.
- **`version`** (default 1): the schema version.
- **`migrations`**: maps every version from 2 to `version` to a step. A step is a SQL script string
  or a callable taking the database.
- **`directory`**: where the `<name>.sqlite` file lives. Default: the owner's plugin data directory.

- **`journal_mode`** (optional, keyword-only): a sqlite journal mode, `delete`, `truncate`,
  `persist`, `memory`, `wal` or `off`, in any case. `PRAGMA journal_mode=<mode>` runs on each
  connection the database opens, so the mode is set again after `close()` and a reopen. Default
  `None`: no pragma is run and sqlite keeps its default (`delete`). An unknown mode raises
  `ValueError` before any file is created. If sqlite reports another mode back, a warning is
  logged and the open still succeeds. Use `"wal"` when another connection reads the file while the
  proxy writes: in rollback mode readers and the writer block each other. `backupdb` uses the
  online backup API, so a backup of a WAL database holds the committed rows still in the `-wal`
  file. The plugin cannot set the pragma itself: `modify()` runs in a savepoint, where sqlite
  refuses to change the mode.

A definition with an unknown key, a missing field, a hook that is not callable, a duplicate table
or a gap in the migrations raises `ValueError` before any file is created.

### What Happens

1. The definition is validated.
2. The `Sqldb` is built and each table is registered. Its columns and defaults come from sqlite's
   `PRAGMA table_info` on an in-memory copy of the create statement, not from parsing the text.
3. The schema version is checked (`PRAGMA user_version`):
   - a new file is set to `version` without running any step;
   - an older file is backed up, then each step from its version up to `version` runs in its own
     transaction together with the `user_version` bump.
4. Missing tables are created, with their `precreate` and `postcreate` hooks.
5. The database is tracked under the owner, and its APIs and `db*` commands are registered.

If a step fails, the database is closed, nothing is tracked, and the error is raised. The file
stays at the last step that succeeded.

## Using a Database

### Statement Methods

| Method | Use |
| :--- | :--- |
| `select(sql, params=())` | Rows as a list of dicts |
| `selectbykeyword(sql, keyword)` | Rows as a dict keyed by one column |
| `modify(sql, data=None)` | One insert, update or delete; returns `(lastrowid, None)` |
| `modifymany(sql, data)` | One statement run for each item of `data` |
| `modifyscript(sql)` | Several statements, all or none |
| `transaction()` | A `with` block: its statements commit once, or none are kept when it raises. Synchronous use only, never across an `await` |
| `getrow(row_id, table)` | One row by key field |
| `getlast(table, num, where=...)` | The last `num` rows by key field; `where` is a column-to-value mapping |
| `getlastrowid(table)` | The highest key value, or `-1` for an empty table |
| `remove(table, key)` | Delete one row by key field |

Pass values as parameters (`?` or `:name` placeholders), never formatted into the SQL text. Table
and column names given to these helpers are checked against the registered tables. `fixsql()`
and a string `where` for `getlast` still work but emit `DeprecationWarning`.

Every statement runs in a savepoint. A failure is logged, rolled back and raised as
`sqlite3.Error`; callers catch that instead of checking for empty results.

### Connection

The connection opens on first use. After `close()` (or the `dbclose` command) the next call opens
it again. The sqldb plugin closes a plugin's databases when the plugin unloads.

### Helpers for Building Statements

`converttoinsert(table)`, `converttoupdate(table, wherekey)` and `checkdictforcolumns(table, row)`
build named-parameter statements and complete rows from the table's columns and their defaults.

## APIs

`database.add` registers these under the owner, for a database named `<name>`:

| API | Calls |
| :--- | :--- |
| `<owner>:<name>.select` | `select` |
| `<owner>:<name>.modify` | `modify` |
| `<owner>:<name>.modify.many` | `modifymany` |
| `<owner>:<name>.row.get` | `getrow` |

The sqldb plugin's own APIs are `plugins.core.sqldb:database.add`,
`plugins.core.sqldb:database.register` (track a database for closing on unload; `database.add`
calls it) and the deprecated `plugins.core.sqldb:baseclass.get`.

## Commands

Each owner gets one set of `db*` commands, run as `#bp.<plugin>.<command>`:

| Command | Arguments | Does |
| :--- | :--- | :--- |
| `dbselect` | `stmt` | Run a select and show the rows |
| `dbmodify` | `stmt` | Run an insert, update or delete |
| `dbtables` | `table` (optional) | List the tables, or one table's columns |
| `dbremove` | `table rownumber` | Delete a row by key field |
| `dbbackup` | `name` (optional) | Back up into `archive/<name>_<backup>.sqlite.zip`; the default backup name is the date |
| `dbvac` | | Vacuum the database |
| `dbclose` | | Close the connection until the next use |

Every command also takes `--db <name>`. With one database it is optional. With several it picks
the database, and a command without it, or with an unknown name, lists the available databases and
changes nothing. `dbtables` without `--db` and without a table lists the tables of every database.
A backup name must be a plain file name.

## Unload and Reload

When the owner unloads:

- the sqldb plugin closes its databases (on `ev_plugin_unloaded`);
- the base plugin removes the owner's APIs, including `<owner>:<name>.*`;
- the commands plugin removes the owner's commands, including the `db*` commands.

When the sqldb plugin reloads, the plugins that declare it as a dependency reload too.

## Deprecated: the Subclass Pattern

Before `database.add`, a plugin fetched the class with `plugins.core.sqldb:baseclass.get`,
subclassed it inside a factory function, called `addtable(...)` and finally `postinit()`. That
still works, but `baseclass.get` emits `DeprecationWarning`, and such a database's APIs are not
registered for it. Use `database.add`.
