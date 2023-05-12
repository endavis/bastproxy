# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/info/loadedplugininfo.py
#
# File Description: a "package" to manage info classes
#
# By: Bast
# Standard Library
import datetime
import types
from pathlib import Path

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin

class LoadedPluginInfo():
    """
    a class to hold information about a plugin
    """
    def __init__(self):
        """
        initialize the instance
        """
        self.author: str = ''
        self.base_plugin_dir: Path = Path()
        self.dev: bool = False
        self.full_import_location: str | None = None
        self.importedtime: datetime.datetime = datetime.datetime(1970, 1, 1)
        self.isimported: bool = False
        self.isinitialized: bool = False
        self.isrequired: bool = False
        self.module: types.ModuleType | None = None
        self.name: str = ''
        self.plugin_id: str = ''
        self.plugin_path: Path = Path()
        self.plugininstance: BasePlugin | None = None
        self.purpose: str = ''
        self.version: int = 1
        self.short_name: str = ''

    def copy_from_module(self, module):
        """
        copy the relevant info from a module
        """
        self.module = module
        self.name = module.NAME
        self.purpose = module.PURPOSE
        self.author = module.AUTHOR
        self.version = module.VERSION
        if hasattr(module, 'REQUIRED'):
            self.isrequired = module.REQUIRED
        self.short_name = self.plugin_path.stem
        self.importedtime = datetime.datetime.now(datetime.timezone.utc)
