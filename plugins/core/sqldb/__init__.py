# Project: bastproxy
# Filename: plugins/core/sqldb/_init_.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast
"""this module is a sqlite3 interface

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

# these 4 are required
PLUGIN_NAME = "SQL DB base class"
PLUGIN_PURPOSE = "Hold the SQL DB baseclass"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1
