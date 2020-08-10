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
import sqlite3
import os
import shutil
import time
import zipfile
import copy

import libs.argp as argp
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
  tdict = {}
  for idx, col in enumerate(cursor.description):
    tdict[col[0]] = row[idx]
  return tdict


class Sqldb(object):
  # pylint: disable=too-many-public-methods
  """
  a class to manage sqlite3 databases
  """
  def __init__(self, plugin, **kwargs):
    """
    initialize the class
    """
    self.dbconn = None
    self.plugin = plugin
    self.short_name = plugin.short_name
    self.name = plugin.name
    self.api = plugin.api
    if 'dbname' in kwargs:
      self.dbname = kwargs['dbname'] or "db"
    else:
      self.dbname = "db"
    self.api('log.adddtype')('sqlite')
    #self.api('log.console')('sqlite')
    self.backupform = '%s_%%s.sqlite' % self.dbname
    self.dbdir = os.path.join(self.api.BASEPATH, 'data', 'db')
    if 'dbdir' in kwargs:
      self.dbdir = kwargs['dbdir'] or os.path.join(self.api.BASEPATH,
                                                   'data', 'db')
    try:
      os.makedirs(self.dbdir)
    except OSError:
      pass
    self.dbfile = os.path.join(self.dbdir, self.dbname + '.sqlite')
    self.turnonpragmas()
    self.conns = 0
    self.version = 1
    self.version_functions = {}
    self.tables = {}

    self.api('api.add')('select', self.api_select)
    self.api('api.add')('modify', self.api_modify)
    self.api('api.add')('modifymany', self.api_modifymany)
    self.api('api.add')('getrow', self.api_getrow)

  # execute a select statement against the database
  def api_select(self, stmt):
    """
    run a select stmt against the db
    """
    return self.select(stmt)

  # execute a update/insert statement against the database
  def api_modify(self, stmt, data=None):
    """
    modify the database
    """
    return self.modify(stmt, data)

  # execute a update/insert statement multiple times
  def api_modifymany(self, stmt, data):
    """
    update many rows in a database
    """
    return self.modifymany(stmt, data)

  # get a row from a table
  def api_getrow(self, rowid, ttable):
    """
    get a row from a table
    """
    return self.getrow(rowid, ttable)

  def close(self):
    """
    close the database
    """
    import inspect
    self.api('send.msg')('close: called by - %s' % inspect.stack()[1][3])
    try:
      self.dbconn.close()
    except Exception: # pylint: disable=broad-except
      pass
    self.dbconn = None

  def open(self):
    """
    open the database
    """
    import inspect
    funcname = inspect.stack()[1][3]
    if funcname == '__getattribute__':
      funcname = inspect.stack()[2][3]
    self.api('send.msg')('open: called by - %s' % funcname)
    self.dbconn = sqlite3.connect(
        self.dbfile,
        detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    self.dbconn.row_factory = dict_factory
    # only return byte strings so is easier to send to a client or the mud
    self.dbconn.text_factory = str

  def __getattribute__(self, name):
    """
    override getattribute to make sure the database is open
    """
    import inspect
    badfuncs = ['open']
    attr = object.__getattribute__(self, name)
    if inspect.ismethod(attr) and name[0] != '_' and \
        name not in badfuncs:
      if not self.dbconn:
        self.open()
    return attr

  def fixsql(self, tstr, like=False):
    # pylint: disable=no-self-use
    """
    Fix quotes in a item that will be passed into a sql statement
    """
    tstr = str(tstr)
    if tstr:
      if like:
        return "'%" + tstr.replace("'", "''") + "%'"

      return "'" + tstr.replace("'", "''") + "'"

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
    self.api('commands.add')('dbbackup',
                             self.cmd_backup,
                             parser=parser,
                             group='DB')

    parser = argp.ArgumentParser(add_help=False,
                                 description='close the database')
    self.api('commands.add')('dbclose',
                             self.cmd_close,
                             parser=parser,
                             group='DB')

    parser = argp.ArgumentParser(add_help=False,
                                 description='vacuum the database')
    self.api('commands.add')('dbvac',
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
    self.api('commands.add')('dbselect',
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
    self.api('commands.add')('dbmodify',
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
    self.api('commands.add')('dbremove',
                             self.cmd_remove,
                             parser=parser,
                             group='DB')

  def cmd_select(self, args=None):
    """
    run a cmd against the database
    """
    msg = []
    if args:
      sqlstmt = args['stmt']
      if sqlstmt:
        results = self.api('%s.select' % self.plugin.short_name)(sqlstmt)
        for i in results:
          msg.append('%s' % i)
      else:
        msg.append('Please enter a select statement')
    return True, msg

  def cmd_modify(self, args=None):
    """
    run a cmd against the database
    """
    msg = []
    if args:
      sqlstmt = args['stmt']
      if sqlstmt:
        self.api('%s.modify' % self.plugin.short_name)(sqlstmt)
      else:
        msg.append('Please enter an update statement')
    return True, msg

  def cmd_vac(self, _=None):
    """
    vacuum the database
    """
    msg = []
    self.dbconn.execute('VACUUM')
    msg.append('Database Vacuumed')
    return True, msg

  def cmd_close(self, _):
    """
    close the database
    """
    msg = []
    self.close()
    msg.append('Database %s was closed' % (self.dbname))

    return True, msg

  def cmd_remove(self, args):
    """
    remove a table from the database
    """
    msg = []
    if not args['table'] or args['table'] not in self.tables:
      msg.append('Please include a valid table')
    elif not args['rownumber'] or args['rownumber'] < 0:
      msg.append('Please include a valid row number')
    else:
      dummy, nmsg = self.remove(args['table'], args['rownumber'])
      msg.append(nmsg)

    return True, msg

  def cmd_backup(self, args):
    """
    backup the database
    """
    msg = []
    if args['name']:
      name = args['name']
    else:
      name = time.strftime('%a-%b-%d-%Y-%H-%M', time.localtime())

    newname = self.backupform % name + '.zip'
    if self.backupdb(name):
      msg.append('backed up %s with name %s' % \
                      (self.dbname, newname))
    else:
      msg.append('could not back up %s with name %s' % \
                      (self.dbname, newname))

    return True, msg

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
    col, colbykeys, defcolvals = self.getcolumnsfromsql(tablename)
    self.tables[tablename]['columns'] = col
    self.tables[tablename]['columnsbykeys'] = colbykeys
    self.tables[tablename]['defcolvals'] = defcolvals

  def remove(self, table, rownumber):
    """
    remove an item
    """
    if table in self.tables:
      keyfield = self.tables[table]['keyfield']
      sql = "DELETE FROM %s where %s=%s;" % (table, keyfield, rownumber)
      self.api('%s.modify' % self.plugin.short_name)(sql)
      return True, '%s was removed from table %s' % (rownumber, table)

    return False, '%s is not a table' % table

  def getcolumnsfromsql(self, tablename):
    """
    build a list of columns from the create statement for the table
    """
    columns = []
    columnsbykeys = {}
    columndefaults = {}
    if self.tables[tablename]:
      tlist = self.tables[tablename]['createsql'].split('\n')
      for i in tlist:
        i = i.strip()
        if i and i[0:2] != '--':
          if 'CREATE' not in i and ')' not in i:
            ilist = i.split(' ')
            col = ilist[0]
            columns.append(col)
            columnsbykeys[col] = True
            if 'default' in ilist or 'Default' in ilist:
              columndefaults[col] = ilist[-1].strip(',')
            else:
              columndefaults[col] = None


    return columns, columnsbykeys, columndefaults

  def checkdictforcolumns(self, tablename, tdict):
    """
    check that a dictionary has the correct columns and return
    a new dictionary
    """
    newdict = {}
    columns = self.tables[tablename]['columns']
    columndefaults = self.tables[tablename]['defcolvals']
    for col in columns:
      if col not in tdict:
        newdict[col] = columndefaults[col]
      else:
        newdict[col] = tdict[col]
    return newdict

  def converttoinsert(self, tablename, keynull=False, replace=False):
    """
    create an insert statement based on the columns of a table
    """
    execstr = ''
    if self.tables[tablename]:
      cols = self.tables[tablename]['columns']
      tlist = [':%s' % i for i in cols]
      colstring = ', '.join(tlist)
      if replace:
        execstr = "INSERT OR REPLACE INTO %s VALUES (%s)" % \
                          (tablename, colstring)
      else:
        execstr = "INSERT INTO %s VALUES (%s)" % (tablename, colstring)
      if keynull and self.tables[tablename]['keyfield']:
        execstr = execstr.replace(":%s" % self.tables[tablename]['keyfield'],
                                  'NULL')
    return execstr


  def checkcolumnexists(self, table, columnname):
    """
    check if a column exists
    """
    if table in self.tables:
      if columnname in self.tables[table]['columnsbykeys']:
        return True

    return False

  def converttoupdate(self, tablename, wherekey='', nokey=None):
    """
    create an update statement based on the columns of a table
    """
    if nokey is None:
      nokey = {}
    execstr = ''
    if self.tables[tablename]:
      cols = self.tables[tablename]['columns']
      sqlstr = []
      for i in cols:
        if i == wherekey or (nokey and i in nokey):
          pass
        else:
          sqlstr.append(i + ' = :' + i)
      colstring = ','.join(sqlstr)
      execstr = "UPDATE %s SET %s WHERE %s = :%s;" % \
          (tablename, colstring, wherekey, wherekey)
    return execstr

  def getversion(self):
    """
    get the version of the database
    """
    version = 1
    cur = self.dbconn.cursor()
    cur.execute('PRAGMA user_version;')
    ret = cur.fetchone()
    version = ret['user_version']
    cur.close()
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
    cur = self.dbconn.cursor()
    for row in cur.execute(
        'SELECT * FROM sqlite_master WHERE name = "%s" AND type = "table";'
        % tablename):
      if row['name'] == tablename:
        retv = True
    cur.close()
    return retv

  def checkversion(self):
    """
    checks the version of the database, upgrades if neccessary
    """
    dbversion = self.getversion()
    if dbversion == 0:
      self.setversion(self.version)
    elif self.version > dbversion:
      self.updateversion(dbversion, self.version)

  def setversion(self, version):
    """
    set the version of the database
    """
    cur = self.dbconn.cursor()
    cur.execute('PRAGMA user_version=%s;' % version)
    self.dbconn.commit()
    cur.close()

  def updateversion(self, oldversion, newversion):
    """
    update a database from oldversion to newversion
    """
    self.api('send.msg')('updating %s from version %s to %s' % \
                              (self.dbfile, oldversion, newversion))
    self.backupdb(oldversion)
    for i in range(oldversion + 1, newversion + 1):
      try:
        self.version_functions[i]()
        self.api('send.msg')('updated to version %s' % i)
      except Exception: # pylint: disable=broad-except
        self.api('send.traceback')(
            'could not upgrade db: %s in plugin: %s' % (self.dbname,
                                                        self.plugin.short_name))
        return
    self.setversion(newversion)
    self.api('send.msg')('Done upgrading!')

  def select(self, stmt):
    """
    run a select statement against the database, returns a list
    """
    result = []
    cur = self.dbconn.cursor()
    try:
      for row in cur.execute(stmt):
        result.append(row)
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not run sql statement : %s' % \
                            stmt)
    cur.close()
    return result

  def modify(self, stmt, data=None):
    """
    run a statement to modify the database
    """
    result = []
    rowid = -1
    cur = self.dbconn.cursor()
    try:
      if data:
        cur.execute(stmt, data)
      else:
        cur.execute(stmt)
      rowid = cur.lastrowid
      result = self.dbconn.commit()
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not run sql statement : %s' % \
                            stmt)

    return rowid, result

  def modifymany(self, stmt, data=None):
    """
    run a statement to modify many rows in the database
    """
    result = []
    rowid = -1
    cur = self.dbconn.cursor()
    try:
      cur.executemany(stmt, data)
      rowid = cur.lastrowid
      result = self.dbconn.commit()
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not run sql statement : %s' % \
                            stmt)

    return rowid, result

  def modifyscript(self, stmt):
    """
    run a statement to execute a script
    """
    result = []
    rowid = -1
    cur = self.dbconn.cursor()
    try:
      cur.executescript(stmt)
      rowid = cur.lastrowid
      result = self.dbconn.commit()
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not run sql statement : %s' % \
                            stmt)

    return rowid, result

  def selectbykeyword(self, selectstmt, keyword):
    """
    run a select statement against the database, return a dictionary
    where the keys are the keyword specified
    """
    result = {}
    cur = self.dbconn.cursor()
    try:
      for row in cur.execute(selectstmt):
        result[row[keyword]] = row
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')('could not run sql statement : %s' % \
                                      selectstmt)
    cur.close()
    return result

  def getlast(self, ttable, num, where=''):
    """
    get the last num items from a table
    """
    results = {}
    if ttable not in self.tables:
      self.api('send.msg')('table %s does not exist in getlast' % ttable)
      return {}

    colid = self.tables[ttable]['keyfield']
    tstring = ''
    if where:
      tstring = "SELECT * FROM %s WHERE %s ORDER by %s desc limit %d" % \
                        (ttable, where, colid, num)
    else:
      tstring = "SELECT * FROM %s ORDER by %s desc limit %d" % \
                        (ttable, colid, num)

    results = self.api('%s.select' % self.plugin.short_name)(tstring)

    return results

  def getrow(self, rowid, ttable):
    """
    get a row by id
    """
    if ttable not in self.tables:
      self.api('send.msg')('table %s does not exist in getrow' % ttable)
      return {}

    colid = self.tables[ttable]['keyfield']

    tstring = "SELECT * FROM %s WHERE %s = %s" % (ttable, colid, rowid)

    results = self.api('%s.select' % self.plugin.short_name)(tstring)

    return results

  def getlastrowid(self, ttable):
    """
    return the id of the last row in a table
    """
    last = -1
    colid = self.tables[ttable]['keyfield']
    rows = self.api('%s.select' % self.plugin.short_name)(
        "SELECT MAX(%s) AS MAX FROM %s" % (colid, ttable))
    if rows:
      last = rows[0]['MAX']

    return last

  def backupdb(self, postname):
    """
    backup the database
    """
    success = False
    #self.cmd_vac()
    self.api('send.msg')('backing up database %s' % self.dbname)
    integrity = True
    cur = self.dbconn.cursor()
    cur.execute('PRAGMA integrity_check')
    ret = cur.fetchone()
    if ret['integrity_check'] != 'ok':
      integrity = False

    if not integrity:
      self.api('send.msg')('Integrity check failed, aborting backup')
      return success
    self.close()
    try:
      os.makedirs(os.path.join(self.dbdir, 'archive'))
    except OSError:
      pass

    backupzipfile = os.path.join(self.dbdir, 'archive',
                                 self.backupform % postname + '.zip')
    backupfile = os.path.join(self.dbdir, 'archive',
                              self.backupform % postname)

    try:
      shutil.copy(self.dbfile, backupfile)
    except IOError:
      self.api('send.msg')('backup failed, could not copy file')
      return success

    try:
      with zipfile.ZipFile(backupzipfile, 'w', zipfile.ZIP_DEFLATED) as myzip:
        myzip.write(backupfile, arcname=os.path.basename(backupfile))
      os.remove(backupfile)
      success = True
      self.api('send.msg')('%s was backed up to %s' % (self.dbfile,
                                                       backupzipfile))
    except IOError:
      self.api('send.msg')('could not zip backupfile')
      return success

    return success

class Plugin(BasePlugin):
  """
  a plugin to handle the base sqldb
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.reload_dependents_f = True

    self.api('api.add')('baseclass', self.api_baseclass)

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
