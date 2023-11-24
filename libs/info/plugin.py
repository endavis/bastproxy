# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/info/pluginfile.py
#
# File Description: a "package" to manage info classes
#
# By: Bast
# Standard Library
from pathlib import Path
import types
import datetime
import ast
import re

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin

REQUIREDRE = re.compile(r'^REQUIRED = (?P<value>.*)$')
NAMERE = re.compile(r'^PLUGIN_NAME = \'(?P<value>.*)\'$')
AUTHORRE = re.compile(r'^PLUGIN_AUTHOR = \'(?P<value>.*)\'$')
VERSIONRE = re.compile(r'^PLUGIN_VERSION = (?P<value>.*)$')
PURPOSERE = re.compile(r'^PLUGIN_PURPOSE = \'(?P<value>.*)\'$')

class LoadedPluginInfo():
    """
    a class to hold information about a plugin
    """
    def __init__(self):
        """
        initialize the instance
        """
        # The plugin is fully loaded
        self.is_loaded = False
        # The plugin package has been imported
        self.is_imported: bool = False
        # The plugin has been initialized
        self.is_initialized: bool = False
        # The plugin module
        self.module: types.ModuleType | None = None
        # The plugin instance
        self.plugin_instance: None | BasePlugin = None
        # The imported time
        self.imported_time: datetime.datetime = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

class PluginInfo():
    """
    a class to hold information about a plugin package
    """
    def __init__(self, plugin_id: str):
        self.package_init_file_path: Path = Path('')
        self.package_path: Path = Path('')
        self.package_import_location: str = ''
        self.plugin_id: str = plugin_id
        self.package: str = plugin_id.rsplit('.', 1)[0]
        self.name: str = ''
        self.short_name = plugin_id.split('.')[-1]
        self.author: str = ''
        self.purpose: str = ''
        self.version: int = -1
        self.is_dev = self.package[0] == '_'
        self.is_required: bool = False
        self.is_plugin: bool = False
        self.is_valid_python_code: bool = True
        self.files = {}

        self.data_directory: Path = Path('')

        self.last_updated =  datetime.datetime.now(datetime.timezone.utc)
        self.loaded_info = LoadedPluginInfo()
        self.import_errors = []

    def check_file_is_valid_python_code(self, file):
        contents = file.read_text()

        try:
            ast.parse(contents)
            return True, None
        except Exception as E:
            return False, E

    def get_changed_files(self):
        """
        return a list of changed files
        """
        self.get_files()

        return [file for file in self.files if self.files[file]['has_changed']]

    def get_invalid_python_files(self):
        self.get_files()

        return [file for file in self.files if not self.files[file]['is_valid_python_code']]

    def get_files(self):
        """
        read the files
        """
        oldfiles = self.files
        self.files = {}
        for file in self.package_path.iterdir():
            if file.is_file() and '__init__' not in file.name and file.name.endswith('.py'):
                file_modified_time = datetime.datetime.fromtimestamp(file.stat().st_mtime, tz=datetime.timezone.utc)
                if file.name in oldfiles and file_modified_time == oldfiles[file.name]['modified_time']:
                    self.files[file.name] = oldfiles[file.name]
                    continue

                success, exception = self.check_file_is_valid_python_code(file)
                self.is_valid_python_code = success and self.is_valid_python_code

                has_changed = False
                if self.loaded_info.is_loaded and file_modified_time > self.loaded_info.imported_time:
                    has_changed = True

                file_info = {
                    'modified_time': file_modified_time,
                    'is_valid_python_code': success,
                    'exception': exception,
                    'has_changed': has_changed,
                    'full_import_location': f'{self.package_import_location}.'
                                        + file.name.replace('.py', ''),
                }

                self.files[file.name] = file_info

        return self.files

    def update_from_init(self):
        """
        function to read info directly from a plugin file
        It looks for the foillowing items:
          a PLUGIN_REQUIRED line
          a PLUGIN_NAME line
          a PLUGIN_PURPOSE line
          a PLUGIN_AUTHOR line
          a PLUGIN_VERSION line

        arguments:
          required:
            path - the location to the file on disk
        returns:
          a dict with the keys: required, isplugin, sname, isvalidpythoncode
        """
        contents = self.package_init_file_path.read_text()

        for tline in contents.split('\n'):

            if not self.name and (name_match := NAMERE.match(tline)):
                self.is_plugin = True
                gdict = name_match.groupdict()
                self.name = gdict['value']
                continue

            if not self.purpose and (purpose_match := PURPOSERE.match(tline)):
                gdict = purpose_match.groupdict()
                self.purpose = gdict['value']
                continue

            if not self.author and (author_match := AUTHORRE.match(tline)):
                gdict = author_match.groupdict()
                self.author = gdict['value']
                continue

            if self.version == -1 and (version_match := VERSIONRE.match(tline)):
                gdict = version_match.groupdict()
                self.version = int(gdict['value'])
                continue

            if required_match := REQUIREDRE.match(tline):
                gdict = required_match.groupdict()
                if gdict['value'].lower() == 'true':
                    self.is_required = True
                continue

            if self.is_required and self.is_plugin and \
                   self.name and self.author and self.purpose and self.version > -1:
                break

    def reset_loaded_info(self):
        """
        reset the loaded info
        """
        self.loaded_info = LoadedPluginInfo()
