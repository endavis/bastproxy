# Project: bastproxy
# Filename: plugins/core/sqldb/_plugin.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

# Standard Library
import contextlib
import copy
import datetime
import shutil
import sqlite3
import zipfile
from pathlib import Path

# 3rd Party
# Project
from libs.api import API, AddAPI
from libs.records import LogRecord
from plugins.core.commands import AddArgument, AddCommand, AddParser


def dict_factory(cursor, row):
    """Create a dictionary for a sql row."""
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


class Sqldb:
    # pylint: disable=too-many-public-methods
    """a class to manage sqlite3 databases."""

    def __init__(self, plugin_id, **kwargs):
        """Initialize the class."""
        self.db_connection = None
        self.plugin_id = plugin_id
        self.database_name = kwargs["dbname"] or "db" if "dbname" in kwargs else "db"
        self.api = API(owner_id=f"{self.plugin_id}:{self.database_name}")
        self.backup_template = f"{self.database_name}_%%s.sqlite"
        self.database_data_directory = self.api.BASEPATH / "data" / "db"
        if "dbdir" in kwargs:
            self.database_data_directory = kwargs["dbdir"]
        Path(self.database_data_directory).mkdir(parents=True, exist_ok=True)

        self.db_file = self.database_data_directory / f"{self.database_name}.sqlite"
        self.turnonpragmas()
        self.connections = 0
        self.version = 1
        self.version_functions = {}
        self.tables = {}

    @AddAPI(
        "{database_name}.select",
        description="execute a select statement against the database",
    )
    def _api_select(self, sql_statement):
        """Run a select sql_statement against the db."""
        return self.select(sql_statement)

    @AddAPI(
        "{database_name}.modify",
        description="execute an update/insert statement against the database",
    )
    def _api_modify(self, sql_statement, data=None):
        """Modify the database."""
        return self.modify(sql_statement, data)

    @AddAPI(
        "{database_name}.modify.many",
        description="execute an update/insert statement multiple times against the database",
    )
    def _api_modify_many(self, sql_statement, data):
        """Update many rows in a database."""
        return self.modifymany(sql_statement, data)

    @AddAPI("{database_name}.get.single.row", description="get a row from a table")
    def _api_get_single_row(self, row_id, table_name):
        """Get a row from a table."""
        return self.getrow(row_id, table_name)

    def close(self):
        """Close the database."""
        import inspect

        LogRecord(
            f"close: called by - {inspect.stack()[1][3]}",
            level="debug",
            sources=["plugins.core.sqldb", self.plugin_id],
        )()
        if self.db_connection:
            with contextlib.suppress(Exception):
                self.db_connection.close()
        self.db_connection = None

    def open(self):
        """Open the database."""
        import inspect

        function_name = inspect.stack()[1][3]
        if function_name == "__getattribute__":
            function_name = inspect.stack()[2][3]
        LogRecord(
            f"open: called by - {function_name}",
            level="debug",
            sources=["plugins.core.sqldb", self.plugin_id],
        )()
        self.db_connection = sqlite3.connect(
            self.db_file, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        self.db_connection.row_factory = dict_factory
        # only return byte strings so is easier to send to a client or the mud
        self.db_connection.text_factory = str

    def __getattribute__(self, name):
        """Override getattribute to make sure the database is open."""
        import inspect

        bad_functions = ["open"]
        attr = object.__getattribute__(self, name)
        if (
            inspect.ismethod(attr)
            and name[0] != "_"
            and name not in bad_functions
            and not self.db_connection
        ):
            self.open()
        return attr

    def fixsql(self, temp_string, like=False):
        # pylint: disable=no-self-use
        """Fix quotes in a item that will be passed into a sql statement."""
        if temp_string := str(temp_string):
            if like:
                return "'%" + temp_string.replace("'", "''") + "%'"

            return "'" + temp_string.replace("'", "''") + "'"

        return "NULL"

    @AddCommand(group="DB")
    @AddParser(description="backup the database")
    @AddArgument("stmt", help="the sql statement", default="", nargs="?")
    def _command_dbselect(self):
        """Run a cmd against the database."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = []
        if args:
            if sqlstmt := args["stmt"]:
                results = self.api(f"{self.plugin_id}:{self.database_name}.select")(
                    sqlstmt
                )
                message.extend(f"{i}" for i in results)
            else:
                message.append("Please enter a select statement")
        return True, message

    @AddCommand(group="DB")
    @AddParser(description="show tables and fields in database")
    @AddArgument("table", help="the table (not required)", default="", nargs="?")
    def _command_dbtables(self):
        """Show tables and fields."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = []
        if args:
            if args["table"]:
                if not self.checktable(args["table"]):
                    return True, [f"Table {args['table']} does not exist"]
                if self.db_connection:
                    cursor = self.db_connection.cursor()
                    cursor.execute(f'PRAGMA table_info({args["table"]})')
                    desc = cursor.fetchall()
                    cursor.close()
                    message.extend((f"Fields in table {args['table']}:", "-" * 40))
                    message.extend(
                        f"{item['name']:<25} : {item['type']}" for item in desc
                    )
                    return True, message
            else:
                tables = []
                if self.db_connection:
                    cursor = self.db_connection.cursor()
                    tables.extend(
                        row["name"]
                        for row in cursor.execute(
                            'SELECT * FROM sqlite_master WHERE type = "table";'
                        )
                    )
                    cursor.close()
                if tables:
                    message.append(f"Tables in database {self.database_name}:")
                    message.extend(
                        f"{item}" for item in tables if item != "sqlite_sequence"
                    )
                else:
                    message.append(f"No tables in database {self.database_name}")
                return True, message
        return True, message

    @AddCommand(group="DB")
    @AddParser(description="run a sql update/insert against the database")
    @AddArgument("stmt", help="the sql statement", default="", nargs="?")
    def _command_dbmodify(self):
        """Run a cmd against the database."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = []
        if args:
            if sqlstmt := args["stmt"]:
                self.api(f"{self.plugin_id}:{self.database_name}.modify")(sqlstmt)
            else:
                message.append("Please enter an update statement")
        return True, message

    @AddCommand(group="DB")
    @AddParser(description="vacuum the database")
    def _command_dbvac(self):
        """Vacuum the database."""
        if self.db_connection:
            self.db_connection.execute("VACUUM")

        return True, ["Database Vacuumed"]

    @AddCommand(group="DB")
    @AddParser(description="close the database")
    def _command_dbclose(self):
        """Close the database."""
        self.close()
        return True, [f"Database {self.database_name} was closed"]

    @AddCommand(group="DB")
    @AddParser(description="remove a row from a table")
    @AddArgument(
        "table", help="the table to remove the row from", default="", nargs="?"
    )
    @AddArgument("rownumber", help="the row number to remove", default=-1, nargs="?")
    def _command_dbremove(self):
        """Remove a table from the database."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = []
        if not args["table"] or args["table"] not in self.tables:
            message.append("Please include a valid table")
        elif not args["rownumber"] or args["rownumber"] < 0:
            message.append("Please include a valid row number")
        else:
            _, new_message = self.remove(args["table"], args["rownumber"])
            message.append(new_message)

        return True, message

    @AddCommand(group="DB")
    @AddParser(description="backup the database")
    @AddArgument("name", help="the name to backup to", default="", nargs="?")
    def _command_dbbackup(self):
        """Backup the database."""
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = []
        if args["name"]:
            name = args["name"]
        else:
            name = datetime.datetime.now(datetime.UTC).strftime("%a-%b-%d-%Y-%H-%M-%Z")

        backup_file_name = self.backup_template % name + ".zip"
        if self.backupdb(name):
            message.append(
                f"backed up {self.database_name} with name {backup_file_name}"
            )
        else:
            message.append(
                f"could not back up {self.database_name} with name {backup_file_name}"
            )

        return True, message

    def postinit(self):
        """Do post init stuff, checks and upgrades the database, creates tables."""
        self.checkversion()

        for i in self.tables:
            self.checktable(i)

    def turnonpragmas(self):
        """Turn on pragmas."""

    def addtable(self, tablename, sql, **kwargs):
        """Add a table to the database.

        Args:
            tablename: The name of the table to add.
            sql: The SQL CREATE TABLE statement.
            **kwargs: Optional arguments including precreate, postcreate, keyfield.

        """
        args = copy.copy(kwargs) if kwargs else {}
        if "precreate" not in args:
            args["precreate"] = None
        if "postcreate" not in args:
            args["postcreate"] = None
        if "keyfield" not in args:
            args["keyfield"] = None

        args["createsql"] = sql

        self.tables[tablename] = args
        column, columnbykeys, defcolumnvals = self.getcolumnumnsfromsql(tablename)
        self.tables[tablename]["columnumns"] = column
        self.tables[tablename]["columnumnsbykeys"] = columnbykeys
        self.tables[tablename]["defcolumnvals"] = defcolumnvals

    def remove(self, table, rownumber):
        """Remove an item."""
        if table in self.tables:
            key_field = self.tables[table]["keyfield"]
            sql = f"DELETE FROM {table} where {key_field}={rownumber};" % (
                table,
                key_field,
                rownumber,
            )
            self.api(f"{self.plugin_id}:{self.database_name}.modify")(sql)
            return True, f"{rownumber} was removed from table {table}"

        return False, f"{table} is not a table"

    def getcolumnumnsfromsql(self, tablename):
        """Build a list of columnumns from the create statement for the table."""
        columnumns = []
        columnumnsbykeys = {}
        columnumn_defaults = {}
        if self.tables[tablename]:
            sql_statement_list = self.tables[tablename]["createsql"].splitlines()
            for sql_line in sql_statement_list:
                sql_line = sql_line.strip()
                if (
                    sql_line
                    and sql_line[:2] != "--"
                    and "CREATE" not in sql_line
                    and ")" not in sql_line
                ):
                    sql_line_split_list = sql_line.split(" ")
                    column = sql_line_split_list[0]
                    columnumns.append(column)
                    columnumnsbykeys[column] = True
                    if (
                        "default" in sql_line_split_list
                        or "Default" in sql_line_split_list
                    ):
                        columnumn_defaults[column] = sql_line_split_list[-1].strip(",")
                    else:
                        columnumn_defaults[column] = None

        return columnumns, columnumnsbykeys, columnumn_defaults

    def checkdictforcolumnumns(self, tablename, temp_dict):
        """Check that a dictionary has the correct columnumns and return

        a new dictionary.
        """
        new_dict = {}
        columnumns = self.tables[tablename]["columnumns"]
        columnumn_defaults = self.tables[tablename]["defcolumnvals"]
        for column in columnumns:
            if column not in temp_dict:
                new_dict[column] = columnumn_defaults[column]
            else:
                new_dict[column] = temp_dict[column]
        return new_dict

    def converttoinsert(self, tablename, keynull=False, replace=False):
        """Create an insert statement based on the columnumns of a table."""
        sql_string = ""
        if self.tables[tablename]:
            columns = self.tables[tablename]["columnumns"]
            temp_list = [f":{i}" for i in columns]
            columnstring = ", ".join(temp_list)
            if replace:
                sql_string = (
                    f"INSERT OR REPLACE INTO {tablename} VALUES ({columnstring})"
                )
            else:
                sql_string = f"INSERT INTO {tablename} VALUES ({columnstring})"
            if keynull and self.tables[tablename]["keyfield"]:
                sql_string = sql_string.replace(
                    f":{self.tables[tablename]['keyfield']}", "NULL"
                )
        return sql_string

    def checkcolumnumnexists(self, table, columnumnname):
        """Check if a columnumn exists."""
        return (
            table in self.tables
            and columnumnname in self.tables[table]["columnumnsbykeys"]
        )

    def converttoupdate(self, tablename, wherekey="", nokey=None):
        """Create an update statement based on the columnumns of a table."""
        if nokey is None:
            nokey = {}
        sql_string = ""
        if self.tables[tablename]:
            columns = self.tables[tablename]["columnumns"]
            sql_string_list = [
                f"{column} = :{column}"
                for column in columns
                if column != wherekey and (not nokey or column not in nokey)
            ]
            columnstring = ",".join(sql_string_list)
            sql_string = (
                f"UPDATE {tablename} SET {columnstring} WHERE {wherekey} = :{wherekey};"
            )
        return sql_string

    def getversion(self):
        """Get the version of the database."""
        version = 1
        if self.db_connection:
            cursor = self.db_connection.cursor()
            cursor.execute("PRAGMA user_version;")
            row = cursor.fetchone()
            version = row["user_version"]
            cursor.close()
        return version

    def checktable(self, tablename):
        """Check to see if a table exists, if not create it."""
        if self.tables[tablename] and not self.checktableexists(tablename):
            if self.tables[tablename]["precreate"]:
                self.tables[tablename]["precreate"]()
            self.modifyscript(self.tables[tablename]["createsql"])
            if self.tables[tablename]["postcreate"]:
                self.tables[tablename]["postcreate"]()
        return True

    def checktableexists(self, tablename):
        """Query the database master table to see if a table exists."""
        retv = False
        if self.db_connection:
            cursor = self.db_connection.cursor()
            retv = any(
                row["name"] == tablename
                for row in cursor.execute(
                    f'SELECT * FROM sqlite_master WHERE name = "{tablename}" AND type = "table";'
                )
            )
            cursor.close()
        return retv

    def checkversion(self):
        """Checks the version of the database, upgrades if neccessary."""
        database_version = self.getversion()
        if database_version == 0:
            self.setversion(self.version)
        elif self.version > database_version:
            self.updateversion(database_version, self.version)

    def setversion(self, version):
        """Set the version of the database."""
        if self.db_connection:
            cursor = self.db_connection.cursor()
            cursor.execute(f"PRAGMA user_version={version};")
            self.db_connection.commit()
            cursor.close()

    def updateversion(self, old_version, new_version):
        """Update a database from old_version to new_version."""
        LogRecord(
            f"updateversion - updating {self.db_file} from version {old_version} to {new_version}",
            level="debug",
            sources=[self.plugin_id, "plugins.core.sqldb"],
        )()
        self.backupdb(old_version)
        for version in range(old_version + 1, new_version + 1):
            try:
                self.version_functions[version]()
                LogRecord(
                    f"updateversion - updated to version {version}",
                    level="debug",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                )()
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"updateversion - could not upgrade db: {self.database_name} in plugin: {self.plugin_id}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()
                return
        self.setversion(new_version)
        LogRecord(
            f"updateversion - updated {self.db_file} to version {new_version}",
            level="debug",
            sources=[self.plugin_id, "plugins.core.sqldb"],
        )()

    def select(self, sql_statement):
        """Run a select statement against the database, returns a list."""
        result = []
        if self.db_connection:
            cursor = self.db_connection.cursor()
            try:
                result.extend(iter(cursor.execute(sql_statement)))
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"select - could not run sql statement : {sql_statement}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()
            cursor.close()
        return result

    def modify(self, sql_statement, data=None):
        """Run a statement to modify the database."""
        result = []
        row_id = -1
        if self.db_connection:
            cursor = self.db_connection.cursor()
            try:
                if data:
                    cursor.execute(sql_statement, data)
                else:
                    cursor.execute(sql_statement)
                row_id = cursor.lastrowid
                result = self.db_connection.commit()
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"modify - could not run sql statement : {sql_statement}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()
            cursor.close()

        return row_id, result

    def modifymany(self, sql_statement, data=None):
        """Run a statement to modify many rows in the database."""
        result = []
        row_id = -1
        if self.db_connection and data:
            cursor = self.db_connection.cursor()
            try:
                cursor.executemany(sql_statement, data)
                row_id = cursor.lastrowid
                result = self.db_connection.commit()
                cursor.close()
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"modifymany - could not run sql statement : {sql_statement}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()

        return row_id, result

    def modifyscript(self, sql_statement):
        """Run a statement to execute a script."""
        result = []
        row_id = -1
        if self.db_connection:
            cursor = self.db_connection.cursor()
            try:
                cursor.executescript(sql_statement)
                row_id = cursor.lastrowid
                result = self.db_connection.commit()
                cursor.close()
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"modifyscript - could not run sql statement : {sql_statement}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()

        return row_id, result

    def selectbykeyword(self, selectstmt, keyword):
        """Run a select statement against the database, return a dictionary

        where the keys are the keyword specified.
        """
        result = {}
        if self.db_connection:
            cursor = self.db_connection.cursor()
            try:
                for row in cursor.execute(selectstmt):
                    result[row[keyword]] = row
            except Exception:  # pylint: disable=broad-except
                LogRecord(
                    f"selectbykeyword - could not run sql statement : {selectstmt}",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                    exc_info=True,
                )()
            cursor.close()
        return result

    def getlast(self, table_name, num, where=""):
        """Get the last num items from a table."""
        if table_name not in self.tables:
            LogRecord(
                f"getlast - table {table_name} does not exist in getlast",
                level="error",
                sources=[self.plugin_id, "plugins.core.sqldb"],
            )()
            return {}

        column_id_name = self.tables[table_name]["keyfield"]
        sql_string = ""
        if where:
            sql_string = f"SELECT * FROM {table_name} WHERE {where} ORDER by {column_id_name} desc limit {num}"
        else:
            sql_string = (
                f"SELECT * FROM {table_name} ORDER by {column_id_name} desc limit {num}"
            )

        return self.api(f"{self.plugin_id}:{self.database_name}.select")(sql_string)

    def getrow(self, row_id, table_name):
        """Get a row by id."""
        if table_name not in self.tables:
            LogRecord(
                f"getrow - table {table_name} does not exist in getrow",
                level="error",
                sources=[self.plugin_id, "plugins.core.sqldb"],
            )()
            return {}

        column_id_name = self.tables[table_name]["keyfield"]

        sql_string = f"SELECT * FROM {table_name} WHERE {column_id_name} = {row_id}"

        return self.api(f"{self.plugin_id}:{self.database_name}.select")(sql_string)

    def getlastrowid(self, table_name):
        """Return the id of the last row in a table."""
        column_id_name = self.tables[table_name]["keyfield"]
        return (
            rows[0]["MAX"]
            if (
                rows := self.api(f"{self.plugin_id}:{self.database_name}.select")(
                    f"SELECT MAX({column_id_name}) AS MAX FROM {table_name}"
                )
            )
            else -1
        )

    def backupdb(self, postname):
        """Backup the database."""
        success = False
        # self._command_dbvac()
        LogRecord(
            f"backupdb - backing up database {self.database_name}",
            level="debug",
            sources=[self.plugin_id, "plugins.core.sqldb"],
        )()
        if self.db_connection:
            cursor = self.db_connection.cursor()
            cursor.execute("PRAGMA integrity_check")
            ret = cursor.fetchone()
            cursor.close()
            integrity = ret["integrity_check"] == "ok"
            if not integrity:
                LogRecord(
                    "backupdb - integrity check failed, aborting backup",
                    level="error",
                    sources=[self.plugin_id, "plugins.core.sqldb"],
                )()
                return success
            self.close()

        archivedir = self.database_data_directory / "archive"
        archivedir.mkdir(parents=True, exist_ok=True)

        backupzip_filename = self.backup_template % postname + ".zip"
        backupzipfile = archivedir / backupzip_filename
        backup_filename = self.backup_template % postname
        backupfile = archivedir / backup_filename

        try:
            shutil.copy(self.db_file, backupfile)
        except OSError:
            LogRecord(
                f"backupdb - could not copy file {self.db_file} to {backupfile}",
                level="error",
                sources=[self.plugin_id, "plugins.core.sqldb"],
            )()
            return success

        try:
            with zipfile.ZipFile(backupzipfile, "w", zipfile.ZIP_DEFLATED) as myzip:
                myzip.write(backupfile, arcname=Path(backupfile).name)
            Path(backupfile).unlink()
            success = True
            LogRecord(
                f"backupdb - {self.db_file} was backed up to {backupzipfile}",
                level="debug",
                sources=[self.plugin_id, "plugins.core.sqldb"],
            )()
        except OSError:
            LogRecord(
                f"backupdb - could not zip backupfile {backupfile}",
                level="error",
                sources=[self.plugin_id, "plugins.core.sqldb"],
            )()
            return success

        return success
