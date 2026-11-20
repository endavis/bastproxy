# Project: bastproxy
# Filename: plugins/test/_sqldb/plugin/_sqldb.py
#
# File Description: a plugin to test the sqldb plugin
#
# By: Bast
"""This plugin is used to test the sqldb plugin"""

from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook

STATS_SQL = """CREATE TABLE stats(
        stat_id INTEGER NOT NULL PRIMARY KEY autoincrement,
        name TEXT NOT NULL,
        level INT default 1,
        totallevels INT default 1,
        remorts INT default 1,
        tiers INT default 0,
        race TEXT default "",
        sex TEXT default "",
        subclass TEXT default "",
        qpearned INT default 0,
        questscomplete INT default 0 ,
        questsfailed INT default 0,
        campaignsdone INT default 0,
        campaignsfld INT default 0,
        gquestswon INT default 0,
        duelswon INT default 0,
        duelslost INT default 0,
        timeskilled INT default 0,
        monsterskilled INT default 0,
        combatmazewins INT default 0,
        combatmazedeaths INT default 0,
        powerupsall INT default 0,
        totaltrivia INT default 0,
        time INT default 0,
        milestone TEXT,
        redos INT default 0
    );"""


class SQLDBPlugin(BasePlugin):
    """a plugin to test the sqldb plugin"""

    @RegisterPluginHook("after_load")
    def _phook_sqldb_test_create_db(self) -> None:
        """Create the stats database through the sqldb factory API."""
        self.statdb = self.api("plugins.core.sqldb:database.add")(
            self.plugin_id,
            "stats",
            [{"name": "stats", "sql": STATS_SQL, "keyfield": "stat_id"}],
        )
