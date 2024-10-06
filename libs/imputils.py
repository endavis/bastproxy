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
import re
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

# 3rd Party

# Project

NAMERE = re.compile(r'PLUGIN_NAME = \'(?P<value>.*)\'')

def is_plugin(package_path):
    """
    check if a module is a plugin
    """
    contents = Path(package_path).read_text()
    return bool(NAMERE.search(contents))

def find_packages_and_plugins(directory, prefix):
    """
    finds all packages and plugins recursively in a directory

    returns nested dicts with a list of packages
    """
    matches = {'packages':[], 'plugins':[]}
    errors = {}

    def on_error(package):
        """
        handle errors
        """
        errors[package] = sys.exc_info()

    for module_info in pkgutil.walk_packages([directory.as_posix()], prefix, onerror=on_error):
        if module_info.ispkg:
            if tspec := find_spec(module_info.name):
                loader_path: str = tspec.loader.path # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
                if tspec.origin:
                    if is_plugin(tspec.origin):
                        # if the name ends in .plugin, remove it
                        matches['plugins'].append({'plugin_id':re.sub('.plugin$','',tspec.name),
                                'package_init_file_path':Path(loader_path),
                                'package_path':Path(loader_path).parent,
                                'package_import_location':tspec.name})
                    else:
                        matches['packages'].append({'package_id':tspec.name,
                                                    'fullpath':Path(loader_path).parent})

    return matches['packages'], matches['plugins'], errors

# import a module
def importmodule(full_import_location):
    """
    import a single module
    """
    _module = None

    return_dict = {'success':False,
                     'message':'',
                     'module':None,
                     'exception':None,
                     'full_import_location':full_import_location}

    if full_import_location in sys.modules:
        return_dict['success'] = True
        return_dict['message'] = 'already'
        return_dict['module'] = sys.modules[full_import_location]
        return_dict['full_import_location'] = full_import_location
        return return_dict

    try:
        _module = import_module(full_import_location)
    except Exception as e:
        return_dict['success'] = False
        return_dict['message'] = 'error'
        return_dict['exception'] = e
        return return_dict

    return_dict['success'] = True
    return_dict['message'] = 'imported'
    return_dict['module'] = _module
    return_dict['full_import_location'] = full_import_location
    return return_dict


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
