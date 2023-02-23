# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/sqldb.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast
"""
this module is a sqlite3 interface


## Using
See the source for [aardwolf.statdb](/bastproxy/plugins/aardwolf/statdb.html)
for an example of using sqldb

### Wrap the class creation in a function

```python
    def dbcreate(sqldb, plugin, **kwargs):
      \"\"\"
      create the mydb class, this is needed because the Sqldb baseclass
      can be reloaded since it is a plugin
      \"\"\"
      class mydb(sqldb):
        \"\"\"
        a class to manage a sqlite database
        \"\"\"
        def __init__(self, plugin, **kwargs):
          \"\"\"
          initialize the class
          \"\"\"
          sqldb.__init__(self, plugin, **kwargs)

          # postinit will need to be run at the end of the subclass __init__
          self.postinit()

      return mydb(plugin, **kwargs)
```

### call the function in initialize

```python
    mydb = dbcreate(self.api('sqldb.baseclass')(), self,
                           dbname='mydb')
```
"""
# Standard Library
import sqlite3
import os
import shutil
import zipfile
import copy
import datetime

# 3rd Party

# Project
import libs.argp as argp
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin

NAME = 'SQL DB base class'
SNAME = 'sqldb'
PURPOSE = 'Hold the SQL DB baseclass'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

def dict_factory(cursor, row):
    """
    create a dictionary for a sql row
    """
    temp_dict = {}
    for index, column in enumerate(cursor.description):
        temp_dict[column[0]] = row[index]
    return temp_dict


class Sqldb(object):
    # pylint: disable=too-many-public-methods
    """
    a class to manage sqlite3 databases
    """
    def __init__(self, plugin, **kwargs):
        """
        initialize the class
        """
        self.db_connection = None
        self.plugin = plugin
        self.plugin_id = plugin.plugin_id
        self.name = plugin.name
        self.api = plugin.api
        if 'dbname' in kwargs:
            self.database_name = kwargs['dbname'] or 'db'
        else:
            self.database_name = 'db'
        self.api('plugins.core.log:add:datatype')('sqlite')
        #self.api('plugins.core.log:toggle:to:console')('sqlite')
        self.backup_template = f"{self.database_name}_%%s.sqlite"
        self.database_save_directory = self.api.BASEPATH / 'data' / 'db'
        if 'dbdir' in kwargs:
            self.database_save_directory = kwargs['dbdir']
        os.makedirs(self.database_save_directory, exist_ok=True)

        self.db_file = self.database_save_directory / f"{self.database_name}.sqlite"
        self.turnonpragmas()
        self.connections = 0
        self.version = 1
        self.version_functions = {}
        self.tables = {}

        # new api format
        self.api('libs.api:add')(f"{self.database_name}:select", self._api_select)
        self.api('libs.api:add')(f"{self.database_name}:modify", self._api_modify)
        self.api('libs.api:add')(f"{self.database_name}:modify:many", self._api_modify_many)
        self.api('libs.api:add')(f"{self.database_name}:get:single:row", self._api_get_single_row)

    # execute a select statement against the database
    def _api_select(self, sql_statement):
        """
        run a select sql_statement against the db
        """
        return self.select(sql_statement)

    # execute a update/insert statement against the database
    def _api_modify(self, sql_statement, data=None):
        """
        modify the database
        """
        return self.modify(sql_statement, data)

    # execute a update/insert statement multiple times
    def _api_modify_many(self, sql_statement, data):
        """
        update many rows in a database
        """
        return self.modifymany(sql_statement, data)

    # get a row from a table
    def _api_get_single_row(self, row_id, table_name):
        """
        get a row from a table
        """
        return self.getrow(row_id, table_name)

    def close(self):
        """
        close the database
        """
        import inspect
        LogRecord(f"close: called by - {inspect.stack()[1][3]}", 'debug', sources=[__name__, self.plugin_id]).send()
        try:
            self.db_connection.close()
        except Exception: # pylint: disable=broad-except
            pass
        self.db_connection = None

    def open(self):
        """
        open the database
        """
        import inspect
        function_name = inspect.stack()[1][3]
        if function_name == '__getattribute__':
            function_name = inspect.stack()[2][3]
        LogRecord(f"open: called by - {function_name}", 'debug', sources=[__name__, self.plugin_id]).send()
        self.db_connection = sqlite3.connect(
            self.dbfile,
            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.db_connection.row_factory = dict_factory
        # only return byte strings so is easier to send to a client or the mud
        self.db_connection.text_factory = str

    def __getattribute__(self, name):
        """
        override getattribute to make sure the database is open
        """
        import inspect
        bad_functions = ['open']
        attr = object.__getattribute__(self, name)
        if inspect.ismethod(attr) and name[0] != '_' and \
            name not in bad_functions:
            if not self.db_connection:
                self.open()
        return attr

    def fixsql(self, temp_string, like=False):
        # pylint: disable=no-self-use
        """
        Fix quotes in a item that will be passed into a sql statement
        """
        temp_string = str(temp_string)
        if temp_string:
            if like:
                return "'%" + temp_string.replace("'", "''") + "%'"

            return "'" + temp_string.replace("'", "''") + "'"

        return 'NULL'

    def addcmds(self):
        """
        add commands to the plugin to use the database
        """
        parser = argp.ArgumentParser(add_help=False,
                                     description='backup the database')
        parser.add_argument('name',
                            help='the name to backup to',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('dbbackup',
                                              self.cmd_backup,
                                              parser=parser,
                                              group='DB')

        parser = argp.ArgumentParser(add_help=False,
                                     description='close the database')
        self.api('plugins.core.commands:command:add')('dbclose',
                                              self.cmd_close,
                                              parser=parser,
                                              group='DB')

        parser = argp.ArgumentParser(add_help=False,
                                     description='vacuum the database')
        self.api('plugins.core.commands:command:add')('dbvac',
                                              self.cmd_vac,
                                              parser=parser,
                                              group='DB')

        parser = argp.ArgumentParser(
            add_help=False,
            description='run a sql statement against the database')
        parser.add_argument('stmt',
                            help='the sql statement',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('dbselect',
                                              self.cmd_select,
                                              parser=parser,
                                              group='DB')

        parser = argp.ArgumentParser(
            add_help=False,
            description='run a sql update/insert against the database')
        parser.add_argument('stmt',
                            help='the sql statement',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('dbmodify',
                                              self.cmd_modify,
                                              parser=parser,
                                              group='DB')

        parser = argp.ArgumentParser(
            add_help=False,
            description='remove a row from a table')
        parser.add_argument('table',
                            help='the table to remove the row from',
                            default='',
                            nargs='?')
        parser.add_argument('rownumber',
                            help='the row number to remove',
                            default=-1,
                            nargs='?')
        self.api('plugins.core.commands:command:add')('dbremove',
                                              self.cmd_remove,
                                              parser=parser,
                                              group='DB')

    def cmd_select(self, args=None):
        """
        run a cmd against the database
        """
        message = []
        if args:
            sqlstmt = args['stmt']
            if sqlstmt:
                results = self.api('%s:%s:select' % (self.plugin.plugin_id, self.database_name))(sqlstmt)
                for i in results:
                    message.append('%s' % i)
            else:
                message.append('Please enter a select statement')
        return True, message

    def cmd_modify(self, args=None):
        """
        run a cmd against the database
        """
        message = []
        if args:
            sqlstmt = args['stmt']
            if sqlstmt:
                self.api('%s:%s:modify' % (self.plugin.plugin_id, self.database_name))(sqlstmt)
            else:
                message.append('Please enter an update statement')
        return True, message

    def cmd_vac(self, _=None):
        """
        vacuum the database
        """
        message = []
        self.db_connection.execute('VACUUM')
        message.append('Database Vacuumed')
        return True, message

    def cmd_close(self, _):
        """
        close the database
        """
        message = []
        self.close()
        message.append('Database %s was closed' % (self.database_name))

        return True, message

    def cmd_remove(self, args):
        """
        remove a table from the database
        """
        message = []
        if not args['table'] or args['table'] not in self.tables:
            message.append('Please include a valid table')
        elif not args['rownumber'] or args['rownumber'] < 0:
            message.append('Please include a valid row number')
        else:
            _, new_message = self.remove(args['table'], args['rownumber'])
            message.append(new_message)

        return True, message

    def cmd_backup(self, args):
        """
        backup the database
        """
        message = []
        if args['name']:
            name = args['name']
        else:
            name = datetime.datetime.now(datetime.timezone.utc).strftime('%a-%b-%d-%Y-%H-%M-%Z')

        backup_file_name = self.backup_template % name + '.zip'
        if self.backupdb(name):
            message.append('backed up %s with name %s' % \
                            (self.database_name, backup_file_name))
        else:
            message.append('could not back up %s with name %s' % \
                            (self.database_name, backup_file_name))

        return True, message

    def postinit(self):
        """
        do post init stuff, checks and upgrades the database, creates tables
        """
        self.addcmds()
        self.checkversion()

        for i in self.tables:
            self.checktable(i)

    def turnonpragmas(self):
        """
        turn on pragmas
        """
        pass

    def addtable(self, tablename, sql, **kwargs):
        """
        add a table to the database

        keyword args:
         precreate
         postcreate
         keyfield

        """
        if not kwargs:
            args = {}
        else:
            args = copy.copy(kwargs)


        if 'precreate' not in args:
            args['precreate'] = None
        if 'postcreate' not in args:
            args['postcreate'] = None
        if 'keyfield' not in args:
            args['keyfield'] = None

        args['createsql'] = sql

        self.tables[tablename] = args
        column, columnbykeys, defcolumnvals = self.getcolumnumnsfromsql(tablename)
        self.tables[tablename]['columnumns'] = column
        self.tables[tablename]['columnumnsbykeys'] = columnbykeys
        self.tables[tablename]['defcolumnvals'] = defcolumnvals

    def remove(self, table, rownumber):
        """
        remove an item
        """
        if table in self.tables:
            key_field = self.tables[table]['keyfield']
            sql = f"DELETE FROM {table} where {key_field}={rownumber};" % (table, key_field, rownumber)
            self.api(f"{self.plugin.plugin_id}:{self.database_name}:modify")(sql)
            return True, f"{rownumber} was removed from table {table}"

        return False, f"{table} is not a table"

    def getcolumnumnsfromsql(self, tablename):
        """
        build a list of columnumns from the create statement for the table
        """
        columnumns = []
        columnumnsbykeys = {}
        columnumn_defaults = {}
        if self.tables[tablename]:
            sql_statement_list = self.tables[tablename]['createsql'].split('\n')
            for sql_line in sql_statement_list:
                sql_line = sql_line.strip()
                if sql_line and sql_line[0:2] != '--':
                    if 'CREATE' not in sql_line and ')' not in sql_line:
                        sql_line_split_list = sql_line.split(' ')
                        column = sql_line_split_list[0]
                        columnumns.append(column)
                        columnumnsbykeys[column] = True
                        if 'default' in sql_line_split_list or 'Default' in sql_line_split_list:
                            columnumn_defaults[column] = sql_line_split_list[-1].strip(',')
                        else:
                            columnumn_defaults[column] = None


        return columnumns, columnumnsbykeys, columnumn_defaults

    def checkdictforcolumnumns(self, tablename, temp_dict):
        """
        check that a dictionary has the correct columnumns and return
        a new dictionary
        """
        new_dict = {}
        columnumns = self.tables[tablename]['columnumns']
        columnumn_defaults = self.tables[tablename]['defcolumnvals']
        for column in columnumns:
            if column not in temp_dict:
                new_dict[column] = columnumn_defaults[column]
            else:
                new_dict[column] = temp_dict[column]
        return new_dict

    def converttoinsert(self, tablename, keynull=False, replace=False):
        """
        create an insert statement based on the columnumns of a table
        """
        sql_string = ''
        if self.tables[tablename]:
            columns = self.tables[tablename]['columnumns']
            temp_list = [':%s' % i for i in columns]
            columnstring = ', '.join(temp_list)
            if replace:
                sql_string = f"INSERT OR REPLACE INTO {tablename} VALUES ({columnstring})"
            else:
                sql_string = f"INSERT INTO {tablename} VALUES ({columnstring})"
            if keynull and self.tables[tablename]['keyfield']:
                sql_string = sql_string.replace(f":{self.tables[tablename]['keyfield']}",
                                                'NULL')
        return sql_string


    def checkcolumnumnexists(self, table, columnumnname):
        """
        check if a columnumn exists
        """
        if table in self.tables:
            if columnumnname in self.tables[table]['columnumnsbykeys']:
                return True

        return False

    def converttoupdate(self, tablename, wherekey='', nokey=None):
        """
        create an update statement based on the columnumns of a table
        """
        if nokey is None:
            nokey = {}
        sql_string = ''
        if self.tables[tablename]:
            columns = self.tables[tablename]['columnumns']
            sql_string_list = []
            for column in columns:
                if column == wherekey or (nokey and column in nokey):
                    pass
                else:
                    sql_string_list.append(column + ' = :' + column)
            columnstring = ','.join(sql_string_list)
            sql_string = f"UPDATE {tablename} SET {columnstring} WHERE {wherekey} = :{wherekey};"
        return sql_string

    def getversion(self):
        """
        get the version of the database
        """
        version = 1
        cursor = self.db_connection.cursor()
        cursor.execute('PRAGMA user_version;')
        row = cursor.fetchone()
        version = row['user_version']
        cursor.close()
        return version

    def checktable(self, tablename):
        """
        check to see if a table exists, if not create it
        """
        if self.tables[tablename]:
            if not self.checktableexists(tablename):
                if self.tables[tablename]['precreate']:
                    self.tables[tablename]['precreate']()
                self.modifyscript(self.tables[tablename]['createsql'])
                if self.tables[tablename]['postcreate']:
                    self.tables[tablename]['postcreate']()
        return True

    def checktableexists(self, tablename):
        """
        query the database master table to see if a table exists
        """
        retv = False
        cursor = self.db_connection.cursor()
        for row in cursor.execute(
                f"SELECT * FROM sqlite_master WHERE name = \"{tablename}\" AND type = \"table\";"):
            if row['name'] == tablename:
                retv = True
        cursor.close()
        return retv

    def checkversion(self):
        """
        checks the version of the database, upgrades if neccessary
        """
        database_version = self.getversion()
        if database_version == 0:
            self.setversion(self.version)
        elif self.version > database_version:
            self.updateversion(database_version, self.version)

    def setversion(self, version):
        """
        set the version of the database
        """
        cursor = self.db_connection.cursor()
        cursor.execute(f"PRAGMA user_version={version};")
        self.db_connection.commit()
        cursor.close()

    def updateversion(self, old_version, new_version):
        """
        update a database from old_version to new_version
        """
        LogRecord(f"updateversion - updating {self.db_file} from version {old_version} to {new_version}",
                  level='debug', sources=[self.plugin_id, __name__]).send()
        self.backupdb(old_version)
        for version in range(old_version + 1, new_version + 1):
            try:
                self.version_functions[version]()
                LogRecord(f"updateversion - updated to version {version}",
                          level='debug', sources=[self.plugin_id, __name__]).send()
            except Exception: # pylint: disable=broad-except
                LogRecord(f"updateversion - could not upgrade db: {self.database_name} in plugin: {self.plugin_id}",
                          level='error', sources=[self.plugin_id, __name__], exc_info=True).send()
                return
        self.setversion(new_version)
        LogRecord(f"updateversion - updated {self.db_file} to version {new_version}",
                    level='debug', sources=[self.plugin_id, __name__]).send()

    def select(self, sql_statement):
        """
        run a select statement against the database, returns a list
        """
        result = []
        cursor = self.db_connection.cursor()
        try:
            for row in cursor.execute(sql_statement):
                result.append(row)
        except Exception: # pylint: disable=broad-except
            LogRecord(f"select - could not run sql statement : {sql_statement}",
                      level='error', sources=[self.plugin_id, __name__], exc_info=True).send()
        cursor.close()
        return result

    def modify(self, sql_statement, data=None):
        """
        run a statement to modify the database
        """
        result = []
        row_id = -1
        cursor = self.db_connection.cursor()
        try:
            if data:
                cursor.execute(sql_statement, data)
            else:
                cursor.execute(sql_statement)
            row_id = cursor.lastrowid
            result = self.db_connection.commit()
        except Exception: # pylint: disable=broad-except
            LogRecord(f"modify - could not run sql statement : {sql_statement}",
                      level='error', sources=[self.plugin_id, __name__], exc_info=True).send()

        return row_id, result

    def modifymany(self, sql_statement, data=None):
        """
        run a statement to modify many rows in the database
        """
        result = []
        row_id = -1
        cursor = self.db_connection.cursor()
        try:
            cursor.executemany(sql_statement, data)
            row_id = cursor.lastrowid
            result = self.db_connection.commit()
            cursor.close()
        except Exception: # pylint: disable=broad-except
            LogRecord(f"modifymany - could not run sql statement : {sql_statement}",
                      level='error', sources=[self.plugin_id, __name__], exc_info=True).send()

        return row_id, result

    def modifyscript(self, sql_statement):
        """
        run a statement to execute a script
        """
        result = []
        row_id = -1
        cursor = self.db_connection.cursor()
        try:
            cursor.executescript(sql_statement)
            row_id = cursor.lastrowid
            result = self.db_connection.commit()
            cursor.close()
        except Exception: # pylint: disable=broad-except
            LogRecord(f"modifyscript - could not run sql statement : {sql_statement}",
                      level='error', sources=[self.plugin_id, __name__], exc_info=True).send()

        return row_id, result

    def selectbykeyword(self, selectstmt, keyword):
        """
        run a select statement against the database, return a dictionary
        where the keys are the keyword specified
        """
        result = {}
        cursor = self.db_connection.cursor()
        try:
            for row in cursor.execute(selectstmt):
                result[row[keyword]] = row
        except Exception: # pylint: disable=broad-except
            LogRecord(f"selectbykeyword - could not run sql statement : {selectstmt}",
                      level='error', sources=[self.plugin_id, __name__], exc_info=True).send()
        cursor.close()
        return result

    def getlast(self, table_name, num, where=''):
        """
        get the last num items from a table
        """
        results = {}
        if table_name not in self.tables:
            LogRecord(f"getlast - table {table_name} does not exist in getlast",
                      level='error', sources=[self.plugin_id, __name__]).send()
            return {}

        column_id_name = self.tables[table_name]['keyfield']
        sql_string = ''
        if where:
            sql_string = f"SELECT * FROM {table_name} WHERE {where} ORDER by {column_id_name} desc limit {num}"
        else:
            sql_string = f"SELECT * FROM {table_name} ORDER by {column_id_name} desc limit {num}"

        results = self.api(f"{self.plugin.plugin_id}:{self.database_name}:select")(sql_string)

        return results

    def getrow(self, row_id, table_name):
        """
        get a row by id
        """
        if table_name not in self.tables:
            LogRecord(f"getrow - table {table_name} does not exist in getrow",
                        level='error', sources=[self.plugin_id, __name__]).send()
            return {}

        column_id_name = self.tables[table_name]['keyfield']

        sql_string = f"SELECT * FROM {table_name} WHERE {column_id_name} = {row_id}"

        results = self.api(f"{self.plugin.plugin_id}:{self.database_name}:select")(sql_string)

        return results

    def getlastrowid(self, table_name):
        """
        return the id of the last row in a table
        """
        last = -1
        column_id_name = self.tables[table_name]['keyfield']
        rows = self.api(f"{self.plugin.plugin_id}:{self.database_name}:select")(
            f"SELECT MAX({column_id_name}) AS MAX FROM {table_name}")
        if rows:
            last = rows[0]['MAX']

        return last

    def backupdb(self, postname):
        """
        backup the database
        """
        success = False
        #self.cmd_vac()
        LogRecord(f"backupdb - backing up database {self.database_name}",
                  level='debug', sources=[self.plugin_id, __name__]).send()
        integrity = True
        cursor = self.db_connection.cursor()
        cursor.execute('PRAGMA integrity_check')
        ret = cursor.fetchone()
        cursor.close()
        if ret['integrity_check'] != 'ok':
            integrity = False

        if not integrity:
            LogRecord(f"backupdb - integrity check failed, aborting backup",
                      level='error', sources=[self.plugin_id, __name__]).send()
            return success
        self.close()

        archivedir = self.database_save_directory / 'archive'
        os.makedirs(archivedir, exist_ok=True)

        backupzip_filename = self.backup_template % postname + '.zip'
        backupzipfile = archivedir / backupzip_filename
        backup_filename = self.backup_template % postname
        backupfile = archivedir / backup_filename

        try:
            shutil.copy(self.db_file, backupfile)
        except IOError:
            LogRecord(f"backupdb - could not copy file {self.db_file} to {backupfile}",
                      level='error', sources=[self.plugin_id, __name__]).send()
            return success

        try:
            with zipfile.ZipFile(backupzipfile, 'w', zipfile.ZIP_DEFLATED) as myzip:
                myzip.write(backupfile, arcname=os.path.basename(backupfile))
            os.remove(backupfile)
            success = True
            LogRecord(f"backupdb - {self.db_file} was backed up to {backupzipfile}",
                      level='debug', sources=[self.plugin_id, __name__]).send()
        except IOError:
            LogRecord(f"backupdb - could not zip backupfile {backupfile}",
                      level='error', sources=[self.plugin_id, __name__]).send()
            return success

        return success

class Plugin(BasePlugin):
    """
    a plugin to handle the base sqldb
    """
    def __init__(self, *args, **kwargs):
        BasePlugin.__init__(self, *args, **kwargs)

        self.reload_dependents_f = True

        self.api('libs.api:add')('baseclass', self.api_baseclass)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

    # return the sql baseclass
    def api_baseclass(self):
        # pylint: disable=no-self-use
        """
        return the sql baseclass
        """
        return Sqldb
