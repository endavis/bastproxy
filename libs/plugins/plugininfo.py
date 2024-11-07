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

class PluginRuntimeInfo():
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
        self.plugin_class_import_location = f'{self.plugin_id}.plugin'
        self.name: str = ''
        self.short_name = plugin_id.split('.')[-1]
        self.author: str = ''
        self.purpose: str = ''
        self.version: int = -1
        self.is_dev = self.short_name.startswith('_')
        self.is_required: bool = False
        self.is_plugin: bool = False
        self.is_valid_python_code: bool = True
        self.has_been_reloaded: bool = False
        self.files = {}

        self.data_directory: Path = Path('')

        self.last_updated =  datetime.datetime.now(datetime.timezone.utc)
        self.runtime_info = PluginRuntimeInfo()
        self.import_errors = []

    def check_file_is_valid_python_code(self, file):
        try:
            ast.parse(file.read_text())
            return True, None
        except Exception as E:
            return False, E

    def _get_files_by_flag_helper(self, files: dict, flag) -> list:
        """
        return a list of changed files
        """
        changed_files = []
        if 'files' in files:
            changed_files.extend(
                files['files'][file]
                for file in files['files']
                if files['files'][file][flag]
            )

        for item, value in files.items():
            if item != 'files':
                changed_files.extend(self._get_files_by_flag_helper(value, flag))

        return changed_files

    def get_changed_files(self, flag='has_changed'):
        """
        return a list of changed files
        """
        self.get_file_data()

        return self._get_files_by_flag_helper(self.files, flag)

    def get_invalid_python_files(self):
        self.get_file_data()

        return self._get_files_by_flag_helper(self.files, 'invalid_python_code')

    def get_file_data(self):
        """
        read the files
        """
        oldfiles = self.files
        self.files = {}
        for file in self.package_path.rglob('*.py'):
            if '__init__' not in file.name:
                if str(file.relative_to(self.package_path)) == file.name:
                    parent_dir = '.'
                    parent_dir_import_location = ''
                else:
                    parent_dir = file.parent.name
                    parent_dir_import_location = file.parent.name
                if parent_dir not in self.files:
                    self.files[parent_dir] = {'files': {}}
                file_modified_time = datetime.datetime.fromtimestamp(file.stat().st_mtime, tz=datetime.timezone.utc)
                if parent_dir in oldfiles and file.name in oldfiles[parent_dir] and file_modified_time == oldfiles[parent_dir][file.name]['modified_time']:
                    self.files[parent_dir][file.name] = oldfiles[parent_dir][file.name]
                    continue

                success, exception = self.check_file_is_valid_python_code(file)
                self.is_valid_python_code = success and self.is_valid_python_code

                has_changed = False
                if self.runtime_info.is_loaded and file_modified_time > self.runtime_info.imported_time:
                    has_changed = True

                file_info = {
                    'modified_time': file_modified_time,
                    'invalid_python_code': not success,
                    'exception': exception,
                    'has_changed': has_changed,
                    'full_import_location': (
                        f'{self.package_import_location}{f".{parent_dir_import_location}" if parent_dir_import_location else ""}.'
                        + file.name.replace('.py', '')
                    ),
                    'full_path': file,
                }

                self.files[parent_dir]['files'][file.name] = file_info

        return self.files

    def _find_file_by_name_helper(self, file_name: str, files: dict) -> list:
        """
        find a file
        """
        list_of_files = []
        if 'files' in files and file_name in files['files']:
            list_of_files.append(files['files'][file_name])

        for item, value in files.items():
            if item != 'files':
                list_of_files.extend(self._find_file_by_name_helper(file_name, value))

        return list_of_files

    def find_file_by_name(self, file_name: str) -> list:
        """
        find a file
        """
        self.get_file_data()

        return self._find_file_by_name_helper(file_name, self.files)

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

        for tline in contents.splitlines():

            if name_match := NAMERE.match(tline):
                self.is_plugin = True
                gdict = name_match.groupdict()
                self.name = gdict['value']
                continue

            if purpose_match := PURPOSERE.match(tline):
                gdict = purpose_match.groupdict()
                self.purpose = gdict['value']
                continue

            if author_match := AUTHORRE.match(tline):
                gdict = author_match.groupdict()
                self.author = gdict['value']
                continue

            if version_match := VERSIONRE.match(tline):
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

    def reset_runtime_info(self):
        """
        reset the loaded info
        """
        self.runtime_info = PluginRuntimeInfo()
