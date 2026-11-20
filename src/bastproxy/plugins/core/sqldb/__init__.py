# Project: bastproxy
# Filename: plugins/core/sqldb/_init_.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast
"""this module is a sqlite3 interface.

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
    mydb = dbcreate(self.api('plugins.core.sqldb:baseclass.get')(), self,
                           dbname='mydb')
```

## Behavior

- The connection opens lazily on first use, and a call after `close()` opens it again.
- Statement methods (`select`, `selectbykeyword`, `modify`, `modifymany`, `modifyscript`)
  log a failure, roll it back and raise `sqlite3.Error`.
- Each upgrade step in `version_functions` runs atomically with its `user_version` bump. A
  failed or missing step raises out of `postinit`.
- The sqldb plugin closes a plugin's databases when the plugin unloads.
"""

# these 4 are required
PLUGIN_NAME = "SQL DB base class"
PLUGIN_PURPOSE = "Hold the SQL DB baseclass"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1
