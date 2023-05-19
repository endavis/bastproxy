# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/info/pluginfile.py
#
# File Description: a "package" to manage info classes
#
# By: Bast
# Standard Library
from pathlib import Path
import datetime

# 3rd Party

# Project

class PluginPackageInfo():
    """
    a class to hold information about a plugin package
    """
    def __init__(self):
        self.author: str = ''
        self.isplugin: bool = False
        self.fullpath: Path = Path('')
        self.full_import_location: str = ''
        self.isrequired: bool = False
        self.isvalidpythoncode: bool = False
        self.name: str = ''
        self.plugin_id: str = ''
        self.plugin_path: Path = Path('')
        self.package: str = ''
        self.purpose: str = ''
        self.version: int = -1
        self.filename = ''
        self.files = []
        self.lastchecked =  datetime.datetime.now(datetime.timezone.utc)
