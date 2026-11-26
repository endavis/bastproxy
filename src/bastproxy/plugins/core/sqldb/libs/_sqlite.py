# Project: bastproxy
# Filename: plugins/core/sqldb/libs/_sqlite.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

# Standard Library
import contextlib
import datetime
import functools
import logging
import re
import sqlite3
import warnings
import weakref
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser, CommandResult


def _is_plain_backup_name(name: str | int) -> bool:
    """Return True when name can be used inside a backup file name."""
    text = str(name)
    return bool(text) and text not in {".", ".."} and not any(c in text for c in "/\\\0")


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    """Create a dictionary for a sql row."""
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def _sql_default_to_value(text: str | None) -> str | None:
    """Turn the default text ``PRAGMA table_info`` reports into the value to store.

    ``NULL`` and a missing default become ``None``. A quoted string literal loses its
    quotes and its doubled inner quotes collapse. Anything else (numbers, expressions)
    stays text.
    """
    if text is None or text.upper() == "NULL":
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        quote = text[0]
        return text[1:-1].replace(quote * 2, quote)
    return text


def _split_script(script: str) -> list[str]:
    """Split a sql script into single statements.

    Chunks split on ``;`` are joined until sqlite reports a complete statement, so a
    trigger body or a quoted ``;`` stays in one statement.
    """
    statements: list[str] = []
    buffer = ""
    parts = script.split(";")
    for index, chunk in enumerate(parts):
        buffer += chunk
        if index < len(parts) - 1:
            buffer += ";"
        if sqlite3.complete_statement(buffer):
            if buffer.strip(" \t\r\n;"):
                statements.append(buffer)
            buffer = ""
    if buffer.strip():
        statements.append(buffer)
    return statements


@dataclass(slots=True)
class SQLTable:
    """One registered table: its create statement, hooks and derived columns."""

    name: str
    createsql: str
    keyfield: str | None = None
    precreate: Callable[[], None] | None = None
    postcreate: Callable[[], None] | None = None
    columns: list[str] = field(default_factory=list)
    columns_by_keys: dict[str, bool] = field(default_factory=dict)
    default_column_values: dict[str, str | None] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


JOURNAL_MODES = frozenset({"delete", "truncate", "persist", "memory", "wal", "off"})


def check_journal_mode(journal_mode: str | None) -> str | None:
    """Return the lower-case journal mode, or None when no mode is asked for.

    Raises:
        ValueError: The mode is not one of sqlite's journal modes.

    """
    if journal_mode is None:
        return None
    mode = journal_mode.lower() if isinstance(journal_mode, str) else journal_mode
    if mode not in JOURNAL_MODES:
        msg = f"unknown journal mode {journal_mode!r}, use one of {sorted(JOURNAL_MODES)}"
        raise ValueError(msg)
    return str(mode)


class Sqldb:
    """a class to manage sqlite3 databases."""

    def __init__(self, plugin_id: str, **kwargs: Any) -> None:
        """Initialize the class."""
        self.db_connection: sqlite3.Connection | None = None
        self.journal_mode = check_journal_mode(kwargs.get("journal_mode"))
        self.plugin_id = plugin_id
        self.database_name = kwargs["dbname"] or "db" if "dbname" in kwargs else "db"
        self.api = API(owner_id=f"{self.plugin_id}:{self.database_name}")
        self.backup_template = f"{self.database_name}_%s.sqlite"
        self.database_data_directory = self.api.BASEPATH / "data" / "db"
        if "dbdir" in kwargs:
            self.database_data_directory = kwargs["dbdir"]
        Path(self.database_data_directory).mkdir(parents=True, exist_ok=True)

        self.db_file = self.database_data_directory / f"{self.database_name}.sqlite"
        self._txn_depth = 0
        self.version = 1
        self.version_functions: dict[int, Callable[..., Any]] = {}
        self.tables: dict[str, SQLTable] = {}
        self.owner_databases: weakref.WeakSet[Sqldb] | None = None
        register_api = "plugins.core.sqldb:database.register"
        if self.api("libs.api:api.exists")(register_api):
            self.api(register_api)(self)

    @AddAPI(
        "{database_name}.select",
        description="execute a select statement against the database",
    )
    def _api_select(
        self, sql_statement: str, params: Sequence[Any] | Mapping[str, Any] = ()
    ) -> list[dict[str, Any]]:
        """Run a select sql_statement against the db, binding params."""
        return self.select(sql_statement, params)

    @AddAPI(
        "{database_name}.modify",
        description="execute an update/insert statement against the database",
    )
    def _api_modify(self, sql_statement: str, data: Any = None) -> tuple[int | None, Any]:
        """Modify the database."""
        return self.modify(sql_statement, data)

    @AddAPI(
        "{database_name}.modify.many",
        description="execute an update/insert statement multiple times against the database",
    )
    def _api_modify_many(self, sql_statement: str, data: Any) -> tuple[int | None, Any]:
        """Update many rows in a database."""
        return self.modifymany(sql_statement, data)

    @AddAPI("{database_name}.row.get", description="get a row from a table")
    def _api_row_get(self, row_id: int, table_name: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Get a row from a table."""
        return self.getrow(row_id, table_name)

    def close(self) -> None:
        """Close the database. The next call that needs it opens it again."""
        log_to(["plugins.core.sqldb", self.plugin_id], logging.DEBUG, "close: closing database")
        if self.db_connection:
            with contextlib.suppress(sqlite3.Error):
                self.db_connection.close()
        self.db_connection = None

    def open(self) -> None:
        """Open the database. Does nothing if it is already open."""
        self._conn()

    def _connect(self) -> sqlite3.Connection:
        """Open a new connection and keep it as the database connection."""
        log_to(["plugins.core.sqldb", self.plugin_id], logging.DEBUG, "open: opening database")
        connection = sqlite3.connect(
            self.db_file,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            isolation_level=None,
        )
        connection.row_factory = dict_factory
        connection.text_factory = str
        if self.journal_mode is not None:
            self._apply_journal_mode(connection, self.journal_mode)
        self.db_connection = connection
        return connection

    def _apply_journal_mode(self, connection: sqlite3.Connection, mode: str) -> None:
        """Set the journal mode on a new connection and warn if sqlite keeps another."""
        # mode is one of JOURNAL_MODES (checked in __init__), and PRAGMA takes no bound value
        row = connection.execute(f"PRAGMA journal_mode={mode}").fetchone()
        actual = next(iter(row.values())) if row else None
        if actual is None or str(actual).lower() != mode:
            log_to(
                ["plugins.core.sqldb", self.plugin_id],
                logging.WARNING,
                "open: journal mode %s was asked for on %s but sqlite reports %s",
                mode,
                self.database_name,
                actual,
            )

    def _conn(self) -> sqlite3.Connection:
        """Return the open connection, opening the database if needed."""
        connection = self.db_connection
        if connection is None:
            connection = self._connect()
        return connection

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block atomically in a savepoint, so blocks nest.

        The block's changes are kept when it ends and undone when it raises.
        """
        connection = self._conn()
        name = f"sqldb_{self._txn_depth}"
        self._txn_depth += 1
        try:
            connection.execute(f"SAVEPOINT {name}")
            try:
                yield connection
            except BaseException:
                connection.execute(f"ROLLBACK TO {name}")
                connection.execute(f"RELEASE {name}")
                raise
            connection.execute(f"RELEASE {name}")
        finally:
            self._txn_depth -= 1

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Run several statements in one commit, all or none.

        Every ``modify``, ``modifymany`` and ``select`` inside the block nests in one
        savepoint, so the database commits once when the block ends and undoes every
        statement when it raises. Use it synchronously only, never across an ``await``:
        the connection is shared and any other statement would join the open block.

        Raises:
            sqlite3.Error: A statement failed and none were kept. It is logged first.

        """
        try:
            with self._transaction():
                yield
        except sqlite3.Error:
            self._log_failure("transaction", "<batch>")
            raise

    def _log_failure(self, method: str, sql: str) -> None:
        """Log the exception being handled for a failed statement."""
        log_to(
            [self.plugin_id, "plugins.core.sqldb"],
            logging.ERROR,
            "%s - could not run sql statement : %s",
            method,
            sql,
            exc_info=True,
        )

    def fixsql(self, temp_string: Any, like: bool = False) -> str:
        """Fix quotes in a item that will be passed into a sql statement.

        Deprecated: bind values with ``?`` parameters through ``select`` instead.
        """
        warnings.warn(
            "Sqldb.fixsql is deprecated; bind values as parameters instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if temp_string is None:
            return "NULL"

        if temp_string := str(temp_string):
            if like:
                return "'%" + temp_string.replace("'", "''") + "%'"

            return "'" + temp_string.replace("'", "''") + "'"

        return "NULL"

    def _command_candidates(self) -> "list[Sqldb]":
        """Return the databases a ``db*`` command can act on, sorted by name.

        These are the databases the owning plugin registered. A database that was
        never registered targets only itself.
        """
        siblings = self.owner_databases
        if not siblings:
            return [self]
        return sorted(siblings, key=lambda db: db.database_name)

    def _command_target(self, args: Mapping[str, Any] | None) -> "Sqldb | None":
        """Pick the database a ``db*`` command acts on.

        Args:
            args: The parsed command arguments, with an optional ``db`` name.

        Returns:
            The target database, or None when ``--db`` names no database or is needed
            to choose between several; ``_command_target_error`` gives the message.
        """
        candidates = self._command_candidates()
        requested = str((args or {}).get("db", "") or "")
        if requested:
            for db in candidates:
                if db.database_name == requested:
                    return db
            return None
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _command_target_error(self, args: Mapping[str, Any] | None) -> str:
        """Return the message for a ``db*`` command that found no target database."""
        names = ", ".join(db.database_name for db in self._command_candidates())
        if requested := str((args or {}).get("db", "") or ""):
            return f"Unknown database {requested}, available databases: {names}"
        return f"Several databases are available: {names}. Use --db <name>"

    def _table_lines(self) -> list[str]:
        """Return the lines listing the tables of this database."""
        cursor = self._conn().cursor()
        try:
            tables = [
                row["name"]
                for row in cursor.execute('SELECT * FROM sqlite_master WHERE type = "table";')
            ]
        finally:
            cursor.close()
        if tables:
            return [
                f"Tables in database {self.database_name}:",
                *(f"{item}" for item in tables if item != "sqlite_sequence"),
            ]
        return [f"No tables in database {self.database_name}"]

    @AddCommand(group="DB")
    @AddParser(description="run a select statement against the database")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    @AddArgument("stmt", help="the sql statement", default="", nargs="?")
    def _command_dbselect(self) -> CommandResult:
        """Run a cmd against the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args:
            target = self._command_target(args)
            if target is None:
                return CommandResult(True, [self._command_target_error(args)])
            if sqlstmt := args["stmt"]:
                try:
                    results = target.api(f"{target.plugin_id}:{target.database_name}.select")(
                        sqlstmt
                    )
                except sqlite3.Error as exc:
                    return CommandResult(True, [f"select failed: {exc}"])
                message.extend(f"{i}" for i in results)
            else:
                message.append("Please enter a select statement")
        return CommandResult(True, message)

    @AddCommand(group="DB")
    @AddParser(description="show tables and fields in database")
    @AddArgument("--db", help="the database to use, default all", default="")
    @AddArgument("table", help="the table (not required)", default="", nargs="?")
    def _command_dbtables(self) -> CommandResult:
        """Show tables and fields."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args:
            if not args["table"] and not args.get("db") and len(self._command_candidates()) > 1:
                for database in self._command_candidates():
                    try:
                        message.extend(database._table_lines())
                    except sqlite3.Error as exc:
                        message.append(f"tables failed for {database.database_name}: {exc}")
                return CommandResult(True, message)
            target = self._command_target(args)
            if target is None:
                return CommandResult(True, [self._command_target_error(args)])
            try:
                if args["table"]:
                    if not target.checktable(args["table"]):
                        return CommandResult(True, [f"Table {args['table']} does not exist"])
                    cursor = target._conn().cursor()
                    try:
                        cursor.execute("SELECT * FROM pragma_table_info(?)", (args["table"],))
                        desc = cursor.fetchall()
                    finally:
                        cursor.close()
                    rule_width = min(40, self.api("plugins.core.proxy:line.length.get")())
                    message.extend((f"Fields in table {args['table']}:", "-" * rule_width))
                    message.extend(f"{item['name']:<25} : {item['type']}" for item in desc)
                    return CommandResult(True, message)
                message.extend(target._table_lines())
            except sqlite3.Error as exc:
                return CommandResult(True, [f"tables failed: {exc}"])
            return CommandResult(True, message)
        return CommandResult(True, message)

    @AddCommand(group="DB")
    @AddParser(description="run a sql update/insert against the database")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    @AddArgument("stmt", help="the sql statement", default="", nargs="?")
    def _command_dbmodify(self) -> CommandResult:
        """Run a cmd against the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        message: list[str] = []
        if args:
            target = self._command_target(args)
            if target is None:
                return CommandResult(True, [self._command_target_error(args)])
            if sqlstmt := args["stmt"]:
                try:
                    target.api(f"{target.plugin_id}:{target.database_name}.modify")(sqlstmt)
                except sqlite3.Error as exc:
                    return CommandResult(True, [f"modify failed: {exc}"])
            else:
                message.append("Please enter an update statement")
        return CommandResult(True, message)

    @AddCommand(group="DB")
    @AddParser(description="vacuum the database")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    def _command_dbvac(self) -> CommandResult:
        """Vacuum the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        target = self._command_target(args)
        if target is None:
            return CommandResult(True, [self._command_target_error(args)])
        try:
            target._conn().execute("VACUUM")
        except sqlite3.Error as exc:
            return CommandResult(True, [f"vacuum failed: {exc}"])

        return CommandResult(True, ["Database Vacuumed"])

    @AddCommand(group="DB")
    @AddParser(description="close the database")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    def _command_dbclose(self) -> CommandResult:
        """Close the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        target = self._command_target(args)
        if target is None:
            return CommandResult(True, [self._command_target_error(args)])
        target.close()
        return CommandResult(True, [f"Database {target.database_name} was closed"])

    @AddCommand(group="DB")
    @AddParser(description="remove a row from a table")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    @AddArgument("table", help="the table to remove the row from", default="", nargs="?")
    @AddArgument("rownumber", help="the row number to remove", default=-1, nargs="?", type=int)
    def _command_dbremove(self) -> CommandResult:
        """Remove a table from the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        target = self._command_target(args)
        if target is None:
            return CommandResult(True, [self._command_target_error(args)])
        message: list[str] = []
        if not args["table"] or args["table"] not in target.tables:
            message.append("Please include a valid table")
        elif args["rownumber"] < 1:
            message.append("Please include a valid row number")
        else:
            try:
                _, new_message = target.remove(args["table"], args["rownumber"])
            except sqlite3.Error as exc:
                return CommandResult(True, [f"remove failed: {exc}"])
            message.append(new_message)

        return CommandResult(True, message)

    @AddCommand(group="DB")
    @AddParser(description="backup the database")
    @AddArgument("--db", help="the database to use, needed with several", default="")
    @AddArgument("name", help="the name to backup to", default="", nargs="?")
    def _command_dbbackup(self) -> CommandResult:
        """Backup the database."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        target = self._command_target(args)
        if target is None:
            return CommandResult(True, [self._command_target_error(args)])
        message: list[str] = []
        if args["name"]:
            name = args["name"]
        else:
            name = datetime.datetime.now(datetime.UTC).strftime("%a-%b-%d-%Y-%H-%M-%Z")

        backup_file_name = target.backup_template % name + ".zip"
        if not _is_plain_backup_name(name):
            return CommandResult(True, [f"{name!r} is not a plain backup name"])
        try:
            backed_up = target.backupdb(name)
        except sqlite3.Error as exc:
            return CommandResult(True, [f"backup failed: {exc}"])
        if backed_up:
            message.append(f"backed up {target.database_name} with name {backup_file_name}")
        else:
            message.append(f"could not back up {target.database_name} with name {backup_file_name}")

        return CommandResult(True, message)

    def postinit(self) -> None:
        """Do post init stuff, checks and upgrades the database, creates tables."""
        self.checkversion()

        for i in self.tables:
            self.checktable(i)

    def addtable(self, tablename: str, sql: str, **kwargs: Any) -> None:
        """Add a table to the database.

        Args:
            tablename: The name of the table to add.
            sql: The SQL CREATE TABLE statement.
            **kwargs: Optional arguments including precreate, postcreate, keyfield.

        """
        extra = dict(kwargs)
        self.tables[tablename] = SQLTable(
            name=tablename,
            createsql=sql,
            keyfield=extra.pop("keyfield", None),
            precreate=extra.pop("precreate", None),
            postcreate=extra.pop("postcreate", None),
            extra=extra,
        )
        table = self.tables[tablename]
        (
            table.columns,
            table.columns_by_keys,
            table.default_column_values,
        ) = self.getcolumnsfromsql(tablename)

    def remove(self, table: str, rownumber: int | str) -> tuple[bool, str]:
        """Remove the row whose key field equals rownumber from a table."""
        if table in self.tables:
            key_field = self.tables[table].keyfield
            if not key_field:
                return False, f"{table} has no key field"
            sql = f"DELETE FROM {table} WHERE {key_field} = ?;"
            self.api(f"{self.plugin_id}:{self.database_name}.modify")(sql, (rownumber,))
            return True, f"{rownumber} was removed from table {table}"

        return False, f"{table} is not a table"

    def getcolumnsfromsql(
        self, tablename: str
    ) -> tuple[list[str], dict[str, bool], dict[str, str | None]]:
        """Build the column names and defaults from the create statement for the table.

        The statement is run against an in-memory database and sqlite itself
        reports the columns through ``PRAGMA table_info``.
        """
        columns: list[str] = []
        columnsbykeys: dict[str, bool] = {}
        column_defaults: dict[str, str | None] = {}
        if self.tables[tablename]:
            connection = sqlite3.connect(":memory:")
            try:
                connection.executescript(self.tables[tablename].createsql)
                rows = connection.execute(
                    "SELECT name, dflt_value FROM pragma_table_info(?)", (tablename,)
                ).fetchall()
            except sqlite3.Error as exc:
                msg = f"could not read the columns of table {tablename}: {exc}"
                raise ValueError(msg) from exc
            finally:
                connection.close()
            for name, default in rows:
                columns.append(name)
                columnsbykeys[name] = True
                column_defaults[name] = default

        return columns, columnsbykeys, column_defaults

    getcolumnumnsfromsql = getcolumnsfromsql

    def checkdictforcolumns(self, tablename: str, temp_dict: dict[str, Any]) -> dict[str, Any]:
        """Check that a dictionary has the correct columns and return a new dictionary."""
        new_dict = {}
        columns = self.tables[tablename].columns
        column_defaults = self.tables[tablename].default_column_values
        for column in columns:
            if column not in temp_dict:
                new_dict[column] = _sql_default_to_value(column_defaults[column])
            else:
                new_dict[column] = temp_dict[column]
        return new_dict

    checkdictforcolumnumns = checkdictforcolumns

    def converttoinsert(self, tablename: str, keynull: bool = False, replace: bool = False) -> str:
        """Create an insert statement based on the columns of a table."""
        sql_string = ""
        if self.tables[tablename]:
            columns = self.tables[tablename].columns
            temp_list = [f":{i}" for i in columns]
            columnstring = ", ".join(temp_list)
            if replace:
                sql_string = f"INSERT OR REPLACE INTO {tablename} VALUES ({columnstring})"
            else:
                sql_string = f"INSERT INTO {tablename} VALUES ({columnstring})"
            if keynull and self.tables[tablename].keyfield:
                sql_string = sql_string.replace(f":{self.tables[tablename].keyfield}", "NULL")
        return sql_string

    def checkcolumnexists(self, table: str, columnname: str) -> bool:
        """Check if a column exists."""
        return table in self.tables and columnname in self.tables[table].columns_by_keys

    checkcolumnumnexists = checkcolumnexists

    def converttoupdate(
        self, tablename: str, wherekey: str = "", nokey: dict[str, Any] | None = None
    ) -> str:
        """Create an update statement based on the columns of a table."""
        if nokey is None:
            nokey = {}
        sql_string = ""
        if self.tables[tablename]:
            columns = self.tables[tablename].columns
            sql_string_list = [
                f"{column} = :{column}"
                for column in columns
                if column != wherekey and (not nokey or column not in nokey)
            ]
            columnstring = ",".join(sql_string_list)
            sql_string = f"UPDATE {tablename} SET {columnstring} WHERE {wherekey} = :{wherekey};"
        return sql_string

    def getversion(self) -> int:
        """Get the version of the database."""
        cursor = self._conn().cursor()
        try:
            cursor.execute("PRAGMA user_version;")
            row = cursor.fetchone()
            return int(row["user_version"])
        finally:
            cursor.close()

    def checktable(self, tablename: str) -> bool:
        """Check to see if a table exists, if not create it."""
        if tablename not in self.tables:
            return False

        if self.tables[tablename] and not self.checktableexists(tablename):
            precreate = self.tables[tablename].precreate
            if precreate:
                precreate()
            self.modifyscript(self.tables[tablename].createsql)
            postcreate = self.tables[tablename].postcreate
            if postcreate:
                postcreate()
        return True

    def checktableexists(self, tablename: str) -> bool:
        """Query the database master table to see if a table exists."""
        cursor = self._conn().cursor()
        try:
            return any(
                row["name"] == tablename
                for row in cursor.execute(
                    "SELECT * FROM sqlite_master WHERE name = ? AND type = 'table';",
                    (tablename,),
                )
            )
        finally:
            cursor.close()

    def checkversion(self) -> None:
        """Checks the version of the database, upgrades if neccessary."""
        database_version = self.getversion()
        if database_version == 0:
            self.setversion(self.version)
        elif self.version > database_version:
            self.updateversion(database_version, self.version)

    def setversion(self, version: int) -> None:
        """Set the version of the database."""
        version = int(version)
        with self._transaction() as connection:
            connection.execute(f"PRAGMA user_version={version};")

    def updateversion(self, old_version: int, new_version: int) -> None:
        """Update a database from old_version to new_version.

        Each step runs atomically with its version bump, so a failed step leaves the
        database at the last good version. A missing step raises before anything changes.
        """
        steps = range(old_version + 1, new_version + 1)
        if missing := [version for version in steps if version not in self.version_functions]:
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "updateversion - no upgrade function for version(s) %s of db: %s in plugin: %s",
                missing,
                self.database_name,
                self.plugin_id,
            )
            msg = (
                f"no upgrade function for version(s) {missing} of database "
                f"{self.database_name} in plugin {self.plugin_id}"
            )
            raise ValueError(msg)
        log_to(
            [self.plugin_id, "plugins.core.sqldb"],
            logging.DEBUG,
            "updateversion - updating %s from version %s to %s",
            self.db_file,
            old_version,
            new_version,
        )
        self.backupdb(old_version)
        for version in steps:
            try:
                with self._transaction() as connection:
                    self.version_functions[version]()
                    connection.execute(f"PRAGMA user_version={int(version)}")
            except Exception:
                log_to(
                    [self.plugin_id, "plugins.core.sqldb"],
                    logging.ERROR,
                    "updateversion - could not upgrade db: %s in plugin: %s",
                    self.database_name,
                    self.plugin_id,
                    exc_info=True,
                )
                raise
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.DEBUG,
                "updateversion - updated to version %s",
                version,
            )
        log_to(
            [self.plugin_id, "plugins.core.sqldb"],
            logging.DEBUG,
            "updateversion - updated %s to version %s",
            self.db_file,
            new_version,
        )

    def select(
        self, sql_statement: str, params: Sequence[Any] | Mapping[str, Any] = ()
    ) -> list[dict[str, Any]]:
        """Run a select statement against the database, returns a list.

        Values go in params and are bound to the ``?`` or ``:name`` placeholders.

        Raises:
            sqlite3.Error: The statement failed. It is logged first.

        """
        try:
            with self._transaction() as connection:
                cursor = connection.cursor()
                try:
                    return list(cursor.execute(sql_statement, params))
                finally:
                    cursor.close()
        except sqlite3.Error:
            self._log_failure("select", sql_statement)
            raise

    def modify(self, sql_statement: str, data: Any = None) -> tuple[int | None, Any]:
        """Run a statement to modify the database, returns (lastrowid, None).

        Raises:
            sqlite3.Error: The statement failed and was rolled back. It is logged first.

        """
        try:
            with self._transaction() as connection:
                cursor = connection.cursor()
                try:
                    if data:
                        cursor.execute(sql_statement, data)
                    else:
                        cursor.execute(sql_statement)
                    return cursor.lastrowid, None
                finally:
                    cursor.close()
        except sqlite3.Error:
            self._log_failure("modify", sql_statement)
            raise

    def modifymany(self, sql_statement: str, data: Any = None) -> tuple[int | None, Any]:
        """Run a statement to modify many rows in the database, all or none.

        Raises:
            sqlite3.Error: A row failed and none were kept. It is logged first.

        """
        if not data:
            return -1, []
        try:
            with self._transaction() as connection:
                cursor = connection.cursor()
                try:
                    cursor.executemany(sql_statement, data)
                    return cursor.lastrowid, None
                finally:
                    cursor.close()
        except sqlite3.Error:
            self._log_failure("modifymany", sql_statement)
            raise

    def modifyscript(self, sql_statement: str) -> tuple[int | None, Any]:
        """Run a script of statements, all or none.

        Raises:
            sqlite3.Error: A statement failed and none were kept. It is logged first.

        """
        try:
            with self._transaction() as connection:
                cursor = connection.cursor()
                try:
                    for statement in _split_script(sql_statement):
                        cursor.execute(statement)
                    return cursor.lastrowid, None
                finally:
                    cursor.close()
        except sqlite3.Error:
            self._log_failure("modifyscript", sql_statement)
            raise

    def selectbykeyword(self, selectstmt: str, keyword: str) -> dict[Any, dict[str, Any]]:
        """Run a select statement against the database, return a dictionary.

        where the keys are the keyword specified.

        Raises:
            sqlite3.Error: The statement failed. It is logged first.

        """
        result: dict[Any, dict[str, Any]] = {}
        try:
            with self._transaction() as connection:
                cursor = connection.cursor()
                try:
                    for row in cursor.execute(selectstmt):
                        result[row[keyword]] = row
                finally:
                    cursor.close()
        except sqlite3.Error:
            self._log_failure("selectbykeyword", selectstmt)
            raise
        return result

    def _keyfield_or_none(self, table_name: str, caller: str) -> str | None:
        """Return the key field of a registered table, logging when there is none."""
        if table_name not in self.tables:
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "%s - table %s does not exist in %s",
                caller,
                table_name,
                caller,
            )
            return None
        keyfield = self.tables[table_name].keyfield
        if not keyfield:
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "%s - table %s has no key field",
                caller,
                table_name,
            )
        return keyfield

    def getlast(
        self, table_name: str, num: int, where: str | Mapping[str, Any] = ""
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Get the last num items from a table.

        where is a mapping of column to value, joined with AND; None matches NULL.
        A string where is deprecated because it is pasted into the statement.
        """
        column_id_name = self._keyfield_or_none(table_name, "getlast")
        if not column_id_name:
            return {}

        params: list[Any] = []
        where_sql = ""
        if isinstance(where, Mapping):
            if where:
                conditions: list[str] = []
                for column, value in where.items():
                    if column not in self.tables[table_name].columns_by_keys:
                        msg = f"{column} is not a column of table {table_name}"
                        raise ValueError(msg)
                    if value is None:
                        conditions.append(f"{column} IS NULL")
                    else:
                        conditions.append(f"{column} = ?")
                        params.append(value)
                where_sql = " WHERE " + " AND ".join(conditions)
        elif where:
            warnings.warn(
                "a string where in Sqldb.getlast is deprecated; pass a mapping instead",
                DeprecationWarning,
                stacklevel=2,
            )
            where_sql = f" WHERE {where}"

        params.append(int(num))
        sql_string = f"SELECT * FROM {table_name}{where_sql} ORDER by {column_id_name} desc limit ?"
        last_rows: list[dict[str, Any]] = self.select(sql_string, tuple(params))
        return last_rows

    def getrow(self, row_id: int, table_name: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Get a row by id."""
        column_id_name = self._keyfield_or_none(table_name, "getrow")
        if not column_id_name:
            return {}

        sql_string = f"SELECT * FROM {table_name} WHERE {column_id_name} = ?"

        row_result: list[dict[str, Any]] = self.select(sql_string, (row_id,))
        return row_result

    def getlastrowid(self, table_name: str) -> int:
        """Return the id of the last row in a table, or -1 if the table is empty."""
        column_id_name = self.tables[table_name].keyfield
        rows = self.select(f"SELECT MAX({column_id_name}) AS MAX FROM {table_name}")
        if rows and rows[0]["MAX"] is not None:
            return int(rows[0]["MAX"])
        return -1

    def backupdb(self, postname: str | int) -> bool:
        """Backup the database."""
        success = False
        if not _is_plain_backup_name(postname):
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "backupdb - %r is not a plain backup name",
                postname,
            )
            return success
        # self._command_dbvac()
        log_to(
            [self.plugin_id, "plugins.core.sqldb"],
            logging.DEBUG,
            "backupdb - backing up database %s",
            self.database_name,
        )
        connection = self._conn()
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA integrity_check")
            ret = cursor.fetchone()
        finally:
            cursor.close()
        if ret["integrity_check"] != "ok":
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "backupdb - integrity check failed, aborting backup",
            )
            return success

        archivedir = self.database_data_directory / "archive"
        archivedir.mkdir(parents=True, exist_ok=True)

        backupzip_filename = self.backup_template % postname + ".zip"
        backupzipfile = archivedir / backupzip_filename
        backup_filename = self.backup_template % postname
        backupfile = archivedir / backup_filename

        try:
            with contextlib.closing(sqlite3.connect(backupfile)) as destination:
                connection.backup(destination)
        except OSError:
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "backupdb - could not copy file %s to %s",
                self.db_file,
                backupfile,
            )
            return success

        try:
            with zipfile.ZipFile(backupzipfile, "w", zipfile.ZIP_DEFLATED) as myzip:
                myzip.write(backupfile, arcname=Path(backupfile).name)
            Path(backupfile).unlink()
            success = True
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.DEBUG,
                "backupdb - %s was backed up to %s",
                self.db_file,
                backupzipfile,
            )
        except OSError:
            log_to(
                [self.plugin_id, "plugins.core.sqldb"],
                logging.ERROR,
                "backupdb - could not zip backupfile %s",
                backupfile,
            )
            return success

        return success


_DATABASE_NAME = re.compile(r"[a-z][a-z0-9_]*")
_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REQUIRED_TABLE_KEYS = frozenset({"name", "sql"})
_TABLE_KEYS = _REQUIRED_TABLE_KEYS | {"keyfield", "precreate", "postcreate"}


def _check_table(index: int, table: Any, seen: set[str]) -> None:
    """Check one table definition, raising ValueError when it is not valid."""
    where = f"table definition {index}"
    if not isinstance(table, Mapping):
        msg = f"{where} must be a dict, not {type(table).__name__}"
        raise ValueError(msg)
    if unknown := sorted(set(table) - _TABLE_KEYS, key=str):
        msg = f"{where} has unknown keys {unknown}; allowed keys are {sorted(_TABLE_KEYS)}"
        raise ValueError(msg)
    if missing := sorted(_REQUIRED_TABLE_KEYS - set(table)):
        msg = f"{where} is missing required keys {missing}"
        raise ValueError(msg)
    name = table["name"]
    if not isinstance(name, str) or not _TABLE_NAME.fullmatch(name):
        msg = f"{where} has an invalid table name {name!r}"
        raise ValueError(msg)
    if name in seen:
        msg = f"table {name!r} is defined more than once"
        raise ValueError(msg)
    seen.add(name)
    if not isinstance(table["sql"], str) or not table["sql"].strip():
        msg = f"table {name!r} needs a non-empty 'sql' string"
        raise ValueError(msg)
    keyfield = table.get("keyfield")
    if keyfield is not None and not isinstance(keyfield, str):
        msg = f"table {name!r} keyfield must be a string or None"
        raise ValueError(msg)
    for hook in ("precreate", "postcreate"):
        if table.get(hook) is not None and not callable(table[hook]):
            msg = f"table {name!r} {hook} must be callable"
            raise ValueError(msg)


def _check_definition(
    name: Any,
    tables: Any,
    version: Any,
    migrations: Any,
) -> None:
    """Validate a database definition, raising ValueError before anything is created."""
    if not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name):
        msg = f"database name {name!r} must match [a-z][a-z0-9_]*"
        raise ValueError(msg)
    if isinstance(tables, (str, bytes, Mapping)) or not isinstance(tables, Sequence):
        msg = "tables must be a sequence of dicts"
        raise ValueError(msg)
    seen: set[str] = set()
    for index, table in enumerate(tables):
        _check_table(index, table, seen)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        msg = f"version must be an integer of 1 or more, not {version!r}"
        raise ValueError(msg)
    if not isinstance(migrations, Mapping):
        msg = "migrations must be a dict of version to step"
        raise ValueError(msg)
    for key, step in migrations.items():
        if isinstance(key, bool) or not isinstance(key, int):
            msg = f"migration key {key!r} must be an integer version"
            raise ValueError(msg)
        if not isinstance(step, str) and not callable(step):
            msg = f"migration {key} must be a SQL script string or a callable"
            raise ValueError(msg)
    expected = set(range(2, version + 1))
    if gaps := sorted(expected - set(migrations)):
        msg = f"migrations are missing version(s) {gaps} needed to reach version {version}"
        raise ValueError(msg)
    if extras := sorted(set(migrations) - expected):
        msg = f"migrations for version(s) {extras} are outside 2..{version}"
        raise ValueError(msg)


def create_database(
    owner_id: str,
    name: str,
    tables: Sequence[Mapping[str, Any]],
    *,
    version: int = 1,
    migrations: Mapping[int, str | Callable[[Sqldb], Any]] | None = None,
    directory: Path,
    journal_mode: str | None = None,
) -> Sqldb:
    """Build a ``Sqldb`` from plain data, create its tables and apply migrations.

    Hooks and callable migrations receive the db. A SQL string migration runs through
    ``modifyscript``. Nothing is created on disk when the definition is invalid, and a
    failure while building closes the db before it is re-raised.

    Raises:
        ValueError: The definition or the journal mode is not valid.
        sqlite3.Error: A table or a migration failed.

    """
    check_journal_mode(journal_mode)
    steps: Mapping[int, str | Callable[[Sqldb], Any]] = migrations or {}
    _check_definition(name, tables, version, steps)
    db = Sqldb(owner_id, dbname=name, dbdir=directory, journal_mode=journal_mode)
    try:
        for table in tables:
            extra = {
                hook: functools.partial(table[hook], db)
                for hook in ("precreate", "postcreate")
                if table.get(hook) is not None
            }
            db.addtable(table["name"], table["sql"], keyfield=table.get("keyfield"), **extra)
        db.version = version
        for target, step in steps.items():
            db.version_functions[target] = (
                functools.partial(db.modifyscript, step)
                if isinstance(step, str)
                else functools.partial(step, db)
            )
        db.postinit()
    except Exception:
        db.close()
        raise
    return db
