# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/sqldb/plugin/_init_.py
#
# File Description: a plugin to create a sqlite3 interface
#
# By: Bast

__all__ = ['Plugin']

from ._sqldb import SQLDBPlugin as Plugin
