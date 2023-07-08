# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/sqldb/_sqldb.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from libs.api import AddAPI
from plugins._baseplugin import BasePlugin
from ._sqlite import Sqldb

class SQLDBPlugin(BasePlugin):
    """
    a plugin to handle the base sqldb
    """
    def __init__(self, *args, **kwargs):
        BasePlugin.__init__(self, *args, **kwargs)

        self.reload_dependents_f = True

    @AddAPI('baseclass', description='return the sql baseclass')
    def _api_baseclass(self):
        # pylint: disable=no-self-use
        """
        return the sql baseclass
        """
        return Sqldb
