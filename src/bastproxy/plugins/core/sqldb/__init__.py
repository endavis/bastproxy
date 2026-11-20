# Project: bastproxy
# Filename: plugins/core/sqldb/_init_.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast
"""this module is a sqlite3 interface.

## Using

Call `plugins.core.sqldb:database.add` from the owning plugin, with plain data. See the
[plugin developer guide](/docs/plugin-developer-guide.md#storing-data-in-sqlite).

```python
    self.mydb = self.api('plugins.core.sqldb:database.add')(
        self.plugin_id,
        'mydb',
        [{'name': 'things', 'sql': THINGS_SQL, 'keyfield': 'thing_id'}],
        version=2,
        migrations={2: 'ALTER TABLE things ADD COLUMN extra TEXT;'},
    )
```

The returned database has its tables created and its migrations applied. Its `{name}.*` APIs
and `db*` commands are registered under the owner, and it is closed when the owner unloads.
The `db*` command names are fixed, so a second database in one plugin replaces the first one's
commands (issue #603). `baseclass.get` and subclassing `Sqldb` are deprecated.

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
