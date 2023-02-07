"""
holds functions to import plugins and files
"""
# Standard Library
import os
import sys
import pkgutil
import pprint
from importlib import import_module
from pathlib import Path

# 3rd Party

# Project

def find_modules(directory, prefix):
    """
    find all modules recursively in a directory
    """
    matches = []
    for (loader, module_name, ispkg) in \
            pkgutil.walk_packages([directory.as_posix()], prefix):

        filename = module_name.split('.')[-1]

        if not ispkg:
            # print(f"finding module: {module_name}")
            tmod = loader.find_module(module_name)
            # print(f"found module: {tmod}")
            # print(f"name: {tmod.name}")
            # print(f"path: {tmod.path}")
            # print(f"type: {type(tmod.path)}")
            matches.append({'plugin_id':tmod.name.replace('plugins.', ''),
                            'fullpath':Path(tmod.path),
                            'filename':filename,
                            'full_import_path':tmod.name})

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
    if not base_path:
        value1 = '.'.join([mod])
        value2 = mod
    else:
        value1 = '.'.join([base_path, mod])
        value2 = mod

    return value1, value2

# import a module
def importmodule(module_path, base_path, plugin, import_base, silent=False):
    """
    import a single module
    """
    _module = None

    import_location, _ = get_module_name(module_path)
    full_import_location = import_base + '.' + import_location

    try:
        if full_import_location in sys.modules:
            return (True, 'already',
                    sys.modules[full_import_location], full_import_location)

        if not silent:
            plugin.api('libs.io:send:msg')('%-30s : attempting import' % \
                                    full_import_location.replace('plugins.', ''), primary=plugin.plugin_id)
        _module = import_module(full_import_location)

        if not silent:
            plugin.api('libs.io:send:msg')('%-30s : successfully imported' % full_import_location.replace('plugins.', ''), \
                                      primary=plugin.plugin_id)
        return True, 'import', _module, full_import_location

    except Exception: # pylint: disable=broad-except
        if full_import_location in sys.modules:
            del sys.modules[full_import_location]

        plugin.api('libs.io:send:traceback')(
            "Module '%s' refuses to import/load." % full_import_location)
        return False, 'error', _module, full_import_location

def deletemodule(full_import_location, modules_to_keep=None):
    """
    delete a module
    """
    all_modules_to_keep = ['baseplugin', 'baseconfig']
    if modules_to_keep:
        all_modules_to_keep.extend(modules_to_keep)
    keep = [True for item in all_modules_to_keep if item in full_import_location]
    if keep:
        return False

    if full_import_location in sys.modules:
        del sys.modules[full_import_location]
        return True

    return False
