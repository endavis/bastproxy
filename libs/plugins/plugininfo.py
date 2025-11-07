# Project: bastproxy
# Filename: libs/info/pluginfile.py
#
# File Description: a "package" to manage info classes
#
# By: Bast
"""Module for managing plugin information and runtime details.

This module provides the `PluginInfo` and `PluginRuntimeInfo` classes, which handle
the management of plugin metadata and runtime information. It includes methods for
validating Python files, tracking file changes, and extracting plugin details from
initialization files.

Key Components:
    - PluginInfo: A class that holds information about a plugin package.
    - PluginRuntimeInfo: A class that holds runtime information about a plugin.
    - Methods for validating Python files, tracking file changes, and extracting
        plugin details.

Features:
    - Validation of Python files within a plugin package.
    - Tracking of file changes and invalid Python files.
    - Extraction of plugin metadata from initialization files.
    - Management of runtime information for plugins.

Usage:
    - Instantiate PluginInfo with a plugin ID to manage its metadata and runtime info.
    - Use `get_changed_files` to retrieve a list of changed files.
    - Use `find_file_by_name` to locate a specific file within the plugin package.
    - Use `update_from_init` to extract plugin details from the initialization file.
    - Reset runtime information using `reset_runtime_info`.

Classes:
    - `PluginInfo`: Represents a class that holds information about a plugin package.
    - `PluginRuntimeInfo`: Represents a class that holds runtime information about a
        plugin.

"""
# Standard Library
import ast
import datetime
import re
from pathlib import Path
from typing import Any

# 3rd Party
# Project
from plugins._baseplugin import BasePlugin

REQUIREDRE = re.compile(r"^REQUIRED = (?P<value>.*)$")
NAMERE = re.compile(r"^PLUGIN_NAME = \'(?P<value>.*)\'$")
AUTHORRE = re.compile(r"^PLUGIN_AUTHOR = \'(?P<value>.*)\'$")
VERSIONRE = re.compile(r"^PLUGIN_VERSION = (?P<value>.*)$")
PURPOSERE = re.compile(r"^PLUGIN_PURPOSE = \'(?P<value>.*)\'$")


class PluginRuntimeInfo:
    """Class to hold runtime information about a plugin."""

    def __init__(self) -> None:
        """Initialize the runtime information for a plugin.

        This method sets up the initial state for the runtime information of a plugin,
        including flags for whether the plugin is loaded or imported, the plugin
        instance, and the imported time.

        """
        # The plugin is fully loaded
        self.is_loaded: bool = False
        # The plugin package has been imported
        self.is_imported: bool = False
        # The plugin instance
        self.plugin_instance: None | BasePlugin = None
        # The imported time
        self.imported_time: datetime.datetime = datetime.datetime(
            1970, 1, 1, tzinfo=datetime.UTC
        )


class PluginInfo:
    """Class to hold information about a plugin package."""

    def __init__(self, plugin_id: str) -> None:
        """Initialize the plugin information.

        This method sets up the initial state for the plugin information, including
        paths, metadata, and runtime information.

        Args:
            plugin_id: The unique identifier for the plugin.

        """
        self.package_init_file_path: Path = Path("")
        self.package_path: Path = Path("")
        self.package_import_location: str = ""
        self.plugin_id: str = plugin_id
        self.package: str = plugin_id.rsplit(".", 1)[0]
        self.plugin_class_import_location = f"{self.plugin_id}.plugin"
        self.name: str = ""
        self.short_name: str = plugin_id.split(".")[-1]
        self.author: str = ""
        self.purpose: str = ""
        self.version: int = -1
        self.is_dev = self.short_name.startswith("_")
        self.is_required: bool = False
        self.is_plugin: bool = False
        self.is_valid_python_code: bool = True
        self.has_been_reloaded: bool = False
        self.files: dict = {}

        self.data_directory: Path = Path("")

        self.last_updated = datetime.datetime.now(datetime.UTC)
        self.runtime_info: PluginRuntimeInfo = PluginRuntimeInfo()
        self.import_errors: list = []

    def check_file_is_valid_python_code(
        self, file: Path
    ) -> tuple[bool, Exception | None]:
        """Check if a file contains valid Python code.

        This method attempts to parse the provided file to determine if it contains
        valid Python code. If the file is valid, it returns True and None. If the
        file is invalid, it returns False and the exception encountered during
        parsing.

        Args:
            file: The path to the file to check.

        Returns:
            A tuple containing a boolean indicating validity and an exception if
            the file is invalid.

        Raises:
            None

        """
        try:
            ast.parse(file.read_text())
            return True, None
        except Exception as E:
            return False, E

    def _get_files_by_flag_helper(self, files: dict, flag: str) -> list[dict[str, Any]]:
        """Get files by a specific flag helper method.

        This method recursively searches through the provided files dictionary to
        find files that match the specified flag. It returns a list of dictionaries
        containing information about the matched files.

        Args:
            files: The dictionary of files to search through.
            flag: The flag to match files against.

        Returns:
            A list of dictionaries containing information about the matched files.

        Raises:
            None

        """
        changed_files = []
        if "files" in files:
            changed_files.extend(
                files["files"][file]
                for file in files["files"]
                if files["files"][file][flag]
            )

        for item, value in files.items():
            if item != "files":
                changed_files.extend(self._get_files_by_flag_helper(value, flag))

        return changed_files

    def get_changed_files(self, flag: str = "has_changed") -> list[dict[str, Any]]:
        """Get a list of files that have changed.

        This method retrieves a list of files that have changed based on the specified
        flag. It updates the file data before performing the search.

        Args:
            flag: The flag to match files against.

        Returns:
            A list of dictionaries containing information about the changed files.

        Raises:
            None

        """
        self.get_file_data()

        return self._get_files_by_flag_helper(self.files, flag)

    def get_invalid_python_files(self) -> list[dict[str, Any]]:
        """Get a list of files that contain invalid Python code.

        This method retrieves a list of files that contain invalid Python code. It
        updates the file data before performing the search.

        Returns:
            A list of dictionaries containing information about the invalid Python
            files.

        Raises:
            None

        """
        self.get_file_data()

        return self._get_files_by_flag_helper(self.files, "invalid_python_code")

    def get_file_data(self) -> dict:
        """Retrieve and update file data for the plugin package.

        This method scans the plugin package directory for Python files, updates the
        file data, and checks if the files contain valid Python code. It also tracks
        file modifications and updates the runtime information accordingly.

        Returns:
            A dictionary containing the updated file data.

        Raises:
            None

        """
        oldfiles = self.files
        self.files = {}
        for file in self.package_path.rglob("*.py"):
            if "__init__" not in file.name:
                if str(file.relative_to(self.package_path)) == file.name:
                    parent_dir = "."
                    parent_dir_imp_loc = ""
                else:
                    parent_dir = file.parent.name
                    parent_dir_imp_loc = file.parent.name
                if parent_dir not in self.files:
                    self.files[parent_dir] = {"files": {}}
                file_modified_time = datetime.datetime.fromtimestamp(
                    file.stat().st_mtime, tz=datetime.UTC
                )
                if (
                    parent_dir in oldfiles
                    and file.name in oldfiles[parent_dir]
                    and file_modified_time
                    == oldfiles[parent_dir][file.name]["modified_time"]
                ):
                    self.files[parent_dir][file.name] = oldfiles[parent_dir][file.name]
                    continue

                success, exception = self.check_file_is_valid_python_code(file)
                self.is_valid_python_code = success and self.is_valid_python_code

                has_changed = False
                if (
                    self.runtime_info.is_loaded
                    and file_modified_time > self.runtime_info.imported_time
                ):
                    has_changed = True

                full_import_location = (
                    f"{self.package_import_location}"
                    f"{f'.{parent_dir_imp_loc}' if parent_dir_imp_loc else ''}."
                    f"{file.name.replace('.py', '')}"
                )

                file_info = {
                    "modified_time": file_modified_time,
                    "invalid_python_code": not success,
                    "exception": exception,
                    "has_changed": has_changed,
                    "full_import_location": full_import_location,
                    "full_path": file,
                }

                self.files[parent_dir]["files"][file.name] = file_info

        return self.files

    def _find_file_by_name_helper(self, file_name: str, files: dict) -> list:
        """Find a file by name helper method.

        This method recursively searches through the provided files dictionary to find
        files that match the specified file name. It returns a list of dictionaries
        containing information about the matched files.

        Args:
            file_name: The name of the file to search for.
            files: The dictionary of files to search through.

        Returns:
            A list of dictionaries containing information about the matched files.

        Raises:
            None

        """
        list_of_files = []
        if "files" in files and file_name in files["files"]:
            list_of_files.append(files["files"][file_name])

        for item, value in files.items():
            if item != "files":
                list_of_files.extend(self._find_file_by_name_helper(file_name, value))

        return list_of_files

    def find_file_by_name(self, file_name: str) -> list:
        """Find a file by its name.

        This method searches for a file with the specified name within the plugin
        package. It updates the file data before performing the search.

        Args:
            file_name: The name of the file to search for.

        Returns:
            A list of dictionaries containing information about the matched files.

        Raises:
            None

        """
        self.get_file_data()

        return self._find_file_by_name_helper(file_name, self.files)

    def update_from_init(self) -> None:
        """Update plugin information from the initialization file.

        This method reads the initialization file of the plugin package and extracts
        metadata such as the plugin name, purpose, author, version, and required
        status. It updates the corresponding attributes of the PluginInfo instance.

        It looks for the following items:
          a PLUGIN_REQUIRED line
          a PLUGIN_NAME line
          a PLUGIN_PURPOSE line
          a PLUGIN_AUTHOR line
          a PLUGIN_VERSION line

        Returns:
            None

        Raises:
            None

        """
        contents = self.package_init_file_path.read_text()

        for tline in contents.splitlines():

            if name_match := NAMERE.match(tline):
                self.is_plugin = True
                gdict = name_match.groupdict()
                self.name = gdict["value"]
                continue

            if purpose_match := PURPOSERE.match(tline):
                gdict = purpose_match.groupdict()
                self.purpose = gdict["value"]
                continue

            if author_match := AUTHORRE.match(tline):
                gdict = author_match.groupdict()
                self.author = gdict["value"]
                continue

            if version_match := VERSIONRE.match(tline):
                gdict = version_match.groupdict()
                self.version = int(gdict["value"])
                continue

            if required_match := REQUIREDRE.match(tline):
                gdict = required_match.groupdict()
                if gdict["value"].lower() == "true":
                    self.is_required = True
                continue

            if (
                self.is_required
                and self.is_plugin
                and self.name
                and self.author
                and self.purpose
                and self.version > -1
            ):
                break

    def reset_runtime_info(self) -> None:
        """Reset the runtime information for the plugin.

        This method resets the runtime information for the plugin by creating a new
        instance of PluginRuntimeInfo and assigning it to the runtime_info attribute.

        Returns:
            None

        Raises:
            None

        """
        self.runtime_info = PluginRuntimeInfo()
