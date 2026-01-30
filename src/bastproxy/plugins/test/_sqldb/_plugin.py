# Project: bastproxy
# Filename: plugins/test/sqldb/_plugin.py
#
# File Description: a plugin to test the sqldb plugin
#
# By: Bast
"""This plugin is used to test the sqldb plugin"""

from bastproxy.plugins._baseplugin import BasePlugin


def dbcreate(sqldbclass, plugin, **kwargs):
    """Create the statdb class, this is needed because the Sqldb baseclass
    can be reloaded since it is a plugin
    """

    class Statdb(sqldbclass):  # pylint: disable=too-many-public-methods
        """a class to manage a sqlite database for aardwolf events"""

        def __init__(self, plugin, **kwargs):
            """Initialize the class"""
            sqldbclass.__init__(self, plugin, **kwargs)

            self.addtable(
                "stats",
                """CREATE TABLE stats(
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
                    );""",
                keyfield="stat_id",
            )

            # Need to do this after adding tables
            self.postinit()

    return Statdb(plugin, **kwargs)


class SQLDBPlugin(BasePlugin):
    """a plugin to test the sqldb plugin"""

    def initialize(self):
        """Initialize the plugin"""
        BasePlugin.initialize(self)

        self.statdb = dbcreate(
            self.api("plugins.core.sqldb:baseclass")(),
            self.plugin_id,
            dbname="stats",
            dbdir=self.data_directory,
        )
