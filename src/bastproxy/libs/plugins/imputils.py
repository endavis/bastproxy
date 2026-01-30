# Project: bastproxy
# Filename: libs/plugins/imputils.py
#
# File Description: import utility functions
#
# By: Bast
"""Module for import utility functions for plugins.

This module provides utility functions to handle the import and management of
plugin modules. It includes functions to check if a module is a plugin, find
packages and plugins in a directory, import a module, and delete a module.

Key Components:
    - is_plugin: Checks if a module is a plugin.
    - find_packages_and_plugins: Finds all packages and plugins recursively in a
        directory.
    - importmodule: Imports a single module.
    - deletemodule: Deletes a module.

Features:
    - Regular expression-based plugin detection.
    - Recursive package and plugin discovery.
    - Safe module import with error handling.
    - Module deletion with exclusion list.

Usage:
    - Use `is_plugin` to check if a module is a plugin.
    - Use `find_packages_and_plugins` to discover packages and plugins in a
        directory.
    - Use `importmodule` to import a specific module.
    - Use `deletemodule` to delete a specific module, with an optional exclusion
        list.

Functions:
    - `is_plugin`: Checks if a module is a plugin.
    - `find_packages_and_plugins`: Finds all packages and plugins recursively in
        a directory.
    - `importmodule`: Imports a single module.
    - `deletemodule`: Deletes a module.

"""

# Standard Library
import pkgutil
import re
import sys
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

# 3rd Party

# Project

NAMERE = re.compile(r"PLUGIN_NAME = ['\"](?P<value>.*)['\"]")


def is_plugin(package_path: str) -> bool:
    """Check if a module is a plugin.

    This function reads the contents of the specified package path and uses a
    regular expression to determine if the module is a plugin.

    Args:
        package_path: The path to the package to check.

    Returns:
        True if the module is a plugin, False otherwise.

    Raises:
        FileNotFoundError: If the specified package path does not exist.
        IOError: If there is an error reading the package file.

    Example:
        >>> is_plugin("/path/to/plugin")
        True

    """
    contents = Path(package_path).read_text()
    return bool(NAMERE.search(contents))


def find_packages_and_plugins(directory, prefix) -> tuple[list, list, dict[str, tuple]]:
    """Find all packages and plugins recursively in a directory.

    This function walks through the specified directory and identifies all
    packages and plugins. It returns a tuple containing lists of packages,
    plugins, and a dictionary of errors encountered during the process.

    Args:
        directory: The directory to search for packages and plugins.
        prefix: The prefix to use for the package names.

    Returns:
        A tuple containing:
            - A list of packages found.
            - A list of plugins found.
            - A dictionary of errors encountered.

    Raises:
        None

    Example:
        >>> find_packages_and_plugins(Path("/path/to/dir"), "prefix")
        (['package1', 'package2'], ['plugin1', 'plugin2'], {})

    """
    matches = {"packages": [], "plugins": []}
    errors = {}

    def on_error(package: str) -> None:
        """Handle errors encountered during package and plugin discovery.

        This function captures the current exception information and stores it in
        the errors dictionary with the package name as the key.

        Args:
            package: The name of the package where the error occurred.

        Returns:
            None

        Raises:
            None

        """
        errors[package] = sys.exc_info()

    for module_info in pkgutil.walk_packages([directory.as_posix()], prefix, onerror=on_error):
        if module_info.ispkg and (tspec := find_spec(module_info.name)):
            loader_path: str = (
                tspec.loader.path  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
            )
            if tspec.origin:
                if is_plugin(tspec.origin):
                    # if the name ends in .plugin, remove it
                    matches["plugins"].append(
                        {
                            "plugin_id": re.sub(".plugin$", "", tspec.name),
                            "package_init_file_path": Path(loader_path),
                            "package_path": Path(loader_path).parent,
                            "package_import_location": tspec.name,
                        }
                    )
                else:
                    matches["packages"].append(
                        {
                            "package_id": tspec.name,
                            "fullpath": Path(loader_path).parent,
                        }
                    )

    return matches["packages"], matches["plugins"], errors


# import a module
def importmodule(full_import_location) -> dict[str, Any]:
    """Import a single module.

    This function imports a module specified by its full import location. If the
    module is already imported, it returns the existing module. Otherwise, it
    attempts to import the module and returns the result.

    Args:
        full_import_location: The full import path of the module to import.

    Returns:
        A dictionary containing:
            - success: A boolean indicating if the import was successful.
            - message: A message indicating the result of the import.
            - module: The imported module, or None if the import failed.
            - exception: The exception raised during import, if any.
            - full_import_location: The full import path of the module.

    Raises:
        None

    Example:
        >>> importmodule("os")
        {'success': True, 'message': 'imported', 'module': <module 'os' from ...>,
         'exception': None, 'full_import_location': 'os'}

    """
    _module = None

    return_dict = {
        "success": False,
        "message": "",
        "module": None,
        "exception": None,
        "full_import_location": full_import_location,
    }

    if full_import_location in sys.modules:
        return_dict["success"] = True
        return_dict["message"] = "already"
        return_dict["module"] = sys.modules[full_import_location]
        return_dict["full_import_location"] = full_import_location
        return return_dict

    try:
        _module = import_module(full_import_location)
    except Exception as e:
        return_dict["success"] = False
        return_dict["message"] = "error"
        return_dict["exception"] = e
        return return_dict

    return_dict["success"] = True
    return_dict["message"] = "imported"
    return_dict["module"] = _module
    return_dict["full_import_location"] = full_import_location
    return return_dict


def deletemodule(full_import_location, modules_to_keep=None) -> bool:
    """Delete a module.

    This function deletes a module specified by its full import location. It
    ensures that certain modules, specified in the exclusion list, are not
    deleted.

    Args:
        full_import_location: The full import path of the module to delete.
        modules_to_keep: A list of module names to exclude from deletion.

    Returns:
        True if the module was deleted, False otherwise.

    Raises:
        None

    Example:
        >>> deletemodule("os")
        True

    """
    all_modules_to_keep = ["baseplugin", "baseconfig"]
    if modules_to_keep:
        all_modules_to_keep.extend(modules_to_keep)
    if [True for item in all_modules_to_keep if item in full_import_location]:
        return False

    if full_import_location in sys.modules:
        del sys.modules[full_import_location]
        return True

    return False
