# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/imputils.py
#
# File Description: import utility functions
#
# By: Bast
"""
holds functions to import plugins and files
"""
# Standard Library
import os
import sys
import pkgutil
from importlib import import_module
from pathlib import Path

# 3rd Party

# Project
from libs.records import LogRecord

def find_modules(directory, prefix):
    """
    find all modules recursively in a directory
    """
    matches = []
    for (loader, module_name, ispkg) in pkgutil.walk_packages([directory.as_posix()], prefix):

        if not ispkg:
            if tspec := loader.find_spec(module_name):
                filename = module_name.split('.')[-1]

                matches.append({'plugin_id':tspec.name,
                                'fullpath':Path(tspec.loader.path),
                                'filename':filename,
                                'full_import_path':tspec.name})

    # print('found the following plugins:')
    # print(pprint.pformat(matches))
    return matches

def get_module_name(module_path):
    """
    get a module name
    """
    file_name = os.path.basename(module_path)
    directory_name = os.path.dirname(module_path)
    base_path = directory_name.replace(os.path.sep, '.')
    if base_path[0] == '.':
        base_path = base_path[1:]
    mod = os.path.splitext(file_name)[0]
    value1 = '.'.join([base_path, mod]) if base_path else '.'.join([mod])
    value2 = mod
    return value1, value2

# import a module
def importmodule(module_path, plugin, import_base, silent=False):
    """
    import a single module
    """
    _module = None

    import_location, _ = get_module_name(module_path)
    full_import_location = f'{import_base}.{import_location}'

    try:
        if full_import_location in sys.modules:
            return (True, 'already',
                    sys.modules[full_import_location], full_import_location)

        if not silent:
            LogRecord(f"{full_import_location:<30} : attempting import", level='info', sources=[plugin.plugin_id]).send()
        _module = import_module(full_import_location)

        if not silent:
            LogRecord(f"{full_import_location:<30} : successfully imported", level='info', sources=[plugin.plugin_id]).send()
        return True, 'import', _module, full_import_location

    except Exception: # pylint: disable=broad-except
        if full_import_location in sys.modules:
            del sys.modules[full_import_location]

        LogRecord(f"Module '{full_import_location}' failed to import/load.", level='error', sources=[plugin.plugin_id], exc_info=True).send()
        return False, 'error', _module, full_import_location

def deletemodule(full_import_location, modules_to_keep=None):
    """
    delete a module
    """
    all_modules_to_keep = ['baseplugin', 'baseconfig']
    if modules_to_keep:
        all_modules_to_keep.extend(modules_to_keep)
    if keep := [
        True for item in all_modules_to_keep if item in full_import_location
    ]:
        return False

    if full_import_location in sys.modules:
        del sys.modules[full_import_location]
        return True

    return False
