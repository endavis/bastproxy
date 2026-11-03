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
from pathlib import Path
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.exceptions import PluginDependencyError, PluginValidationError
from bastproxy.plugins._baseplugin import BasePlugin

# Expected type of each metadata assignment in a plugin's __init__.py.
_METADATA_TYPES: dict[str, type] = {
    "PLUGIN_NAME": str,
    "PLUGIN_PURPOSE": str,
    "PLUGIN_AUTHOR": str,
    "PLUGIN_VERSION": int,
    "PLUGIN_REQUIRED": bool,
}


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
        self.plugin_instance: BasePlugin | None = None
        # The imported time
        self.imported_time: datetime.datetime = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


class PluginInfo:
    """Class to hold information about a plugin package."""

    def __init__(self, plugin_id: str) -> None:
        """Initialize the plugin information.

        This method sets up the initial state for the plugin information, including
        paths, metadata, and runtime information.

        Args:
            plugin_id: The unique identifier for the plugin.

        """
        self.package_init_file_path: Path = Path()
        self.package_path: Path = Path()
        self.package_import_location: str = ""
        self.plugin_id: str = plugin_id
        self.package: str = plugin_id.rsplit(".", 1)[0]
        self.name: str = ""
        self.short_name: str = plugin_id.split(".")[-1]
        self.author: str = ""
        self.purpose: str = ""
        self.version: int = -1
        self.is_dev = self.short_name.startswith("_")
        self.dependencies: list[str] = []
        self.is_required: bool = False
        self.is_plugin: bool = False
        self.is_valid_python_code: bool = True
        self.has_been_reloaded: bool = False
        self.files: dict = {}

        self.data_directory: Path = Path()

        self.last_updated = datetime.datetime.now(datetime.UTC)
        self.runtime_info: PluginRuntimeInfo = PluginRuntimeInfo()
        self.import_errors: list = []

    @property
    def plugin_class_import_location(self) -> str:
        """Module name the plugin class is imported from.

        Always the real package name (``package_import_location`` + ``.plugin``),
        never the plugin ID, so each plugin module lives in ``sys.modules`` under
        one name only. Empty until discovery has set ``package_import_location``.
        """
        if not self.package_import_location:
            return ""
        return f"{self.package_import_location}.plugin"

    def check_file_is_valid_python_code(self, file: Path) -> tuple[bool, Exception | None]:
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
            ast.parse(file.read_text(encoding="utf-8"))
        except Exception as E:
            return False, E
        else:
            return True, None

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
                files["files"][file] for file in files["files"] if files["files"][file][flag]
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
            rel_parent = file.parent.relative_to(self.package_path)
            parent_dir = rel_parent.as_posix()  # "." for the package root
            parent_dir_imp_loc = "" if parent_dir == "." else ".".join(rel_parent.parts)
            if parent_dir not in self.files:
                self.files[parent_dir] = {"files": {}}
            file_modified_time = datetime.datetime.fromtimestamp(
                file.stat().st_mtime, tz=datetime.UTC
            )
            has_changed = bool(
                self.runtime_info.is_loaded and file_modified_time > self.runtime_info.imported_time
            )

            cached = oldfiles.get(parent_dir, {}).get("files", {}).get(file.name)
            if cached is not None and file_modified_time == cached["modified_time"]:
                cached["has_changed"] = has_changed
                self.is_valid_python_code = (
                    not cached["invalid_python_code"] and self.is_valid_python_code
                )
                self.files[parent_dir]["files"][file.name] = cached
                continue

            success, exception = self.check_file_is_valid_python_code(file)
            self.is_valid_python_code = success and self.is_valid_python_code

            module_parts = [self.package_import_location]
            if parent_dir_imp_loc:
                module_parts.append(parent_dir_imp_loc)
            if file.name != "__init__.py":
                module_parts.append(file.stem)
            full_import_location = ".".join(module_parts)

            self.files[parent_dir]["files"][file.name] = {
                "modified_time": file_modified_time,
                "invalid_python_code": not success,
                "exception": exception,
                "has_changed": has_changed,
                "full_import_location": full_import_location,
                "full_path": file,
            }

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

        The values are read from the top-level assignments of the file with ``ast``
        (the last assignment wins), so trailing comments and quote style do not
        matter and no code is executed. It looks for:
          PLUGIN_REQUIRED (bool)
          PLUGIN_NAME (str)
          PLUGIN_PURPOSE (str)
          PLUGIN_AUTHOR (str)
          PLUGIN_VERSION (int)
          PLUGIN_DEPENDENCIES (parsed separately, see _parse_dependencies)

        A value of the wrong type, or one that is not a literal, adds an entry to
        ``import_errors`` and is skipped. A file with a syntax error adds an entry to
        ``import_errors`` and keeps only the single-line assignments that parse.

        Returns:
            None

        Raises:
            None

        """
        contents = self.package_init_file_path.read_text()
        self._parse_metadata(contents)
        self._parse_dependencies(contents)

    def _parse_metadata(self, contents: str) -> None:
        """Parse the PLUGIN_NAME/PURPOSE/AUTHOR/VERSION/REQUIRED assignments.

        Args:
            contents: The text of the package ``__init__.py``.

        """
        self.import_errors = [
            err
            for err in self.import_errors
            if not (isinstance(err, tuple) and isinstance(err[1], PluginValidationError))
        ]
        body: list[ast.stmt]
        try:
            body = ast.parse(contents).body
        except SyntaxError as exc:
            msg = (
                f"{self.plugin_id}: syntax error in {self.package_init_file_path.name} "
                f"line {exc.lineno}: {exc.msg}"
            )
            self.import_errors.append((self.package_import_location, PluginValidationError(msg)))
            # Tolerant fallback: keep the single-line PLUGIN_* assignments that parse
            # on their own so the plugin is still discovered and fails at import.
            body = []
            for line in contents.splitlines():
                if line.startswith("PLUGIN_"):
                    try:
                        body.extend(ast.parse(line).body)
                    except SyntaxError:
                        continue

        value_nodes: dict[str, ast.expr] = {}
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in _METADATA_TYPES:
                        value_nodes[target.id] = node.value
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id in _METADATA_TYPES
                and node.value is not None
            ):
                value_nodes[node.target.id] = node.value

        values: dict[str, Any] = {}
        for key, value_node in value_nodes.items():
            expected = _METADATA_TYPES[key]
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                value = None
                valid = False
            else:
                valid = isinstance(value, expected) and (
                    expected is bool or not isinstance(value, bool)
                )
            if not valid:
                msg = f"{self.plugin_id}: {key} must be a literal {expected.__name__}"
                self.import_errors.append(
                    (self.package_import_location, PluginValidationError(msg))
                )
                continue
            values[key] = value

        if "PLUGIN_NAME" in values:
            self.is_plugin = True
            self.name = values["PLUGIN_NAME"]
        if "PLUGIN_PURPOSE" in values:
            self.purpose = values["PLUGIN_PURPOSE"]
        if "PLUGIN_AUTHOR" in values:
            self.author = values["PLUGIN_AUTHOR"]
        if "PLUGIN_VERSION" in values:
            self.version = values["PLUGIN_VERSION"]
        if "PLUGIN_REQUIRED" in values:
            self.is_required = values["PLUGIN_REQUIRED"]

    def _parse_dependencies(self, contents: str) -> None:
        """Parse the top-level ``PLUGIN_DEPENDENCIES`` assignment of the init file.

        The value is read with ``ast.literal_eval`` so no code is executed. It must
        be a list or tuple of strings; anything else gives an empty list and an
        entry in ``import_errors``. Duplicates and self-references are dropped.
        The list is reset on every call.

        Args:
            contents: The text of the package ``__init__.py``.

        """
        self.dependencies = []
        self.import_errors = [
            err
            for err in self.import_errors
            if not (isinstance(err, tuple) and isinstance(err[1], PluginDependencyError))
        ]
        try:
            tree = ast.parse(contents)
        except SyntaxError:
            return

        value_node: ast.expr | None = None
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "PLUGIN_DEPENDENCIES" for t in node.targets
                )
            ) or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "PLUGIN_DEPENDENCIES"
                and node.value is not None
            ):
                value_node = node.value
        if value_node is None:
            return

        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError, SyntaxError):
            value = None
        if not isinstance(value, list | tuple) or not all(isinstance(v, str) for v in value):
            msg = (
                f"{self.plugin_id}: PLUGIN_DEPENDENCIES must be a list or tuple of "
                "plugin ID strings"
            )
            self.import_errors.append((self.package_import_location, PluginDependencyError(msg)))
            return

        for dep in value:
            if dep != self.plugin_id and dep not in self.dependencies:
                self.dependencies.append(dep)

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
