"""
holds functions to import plugins and files
"""
import os
import sys
import pkgutil
from importlib import import_module
from pathlib import Path

def find_modules(directory, prefix):
  """
  find all modules recursively in a directory
  """
  matches = []
  for (loader, module_name, ispkg) in \
          pkgutil.walk_packages([Path(directory).as_posix()], prefix):

    if not ispkg:
      tmod = loader.find_module(module_name)
      matches.append({'plugin_id':tmod.fullname.replace('plugins.', ''), 'fullpath':tmod.filename})

  return matches

def get_module_name(module_path):
  """
  get a module name
  """
  file_name = os.path.basename(module_path)
  directory_name = os.path.dirname(module_path)
  base = directory_name.replace(os.path.sep, '.')
  if base[0] == '.':
    base = base[1:]
  mod = os.path.splitext(file_name)[0]
  if not base:
    value1 = '.'.join([mod])
    value2 = mod
  else:
    value1 = '.'.join([base, mod])
    value2 = mod

  return value1, value2

# import a module
def importmodule(module_path, base_path, plugin, import_base, silent=False):
  """
  import a single module
  """
  _module = None
  if base_path in module_path:
    module_path = module_path.replace(base_path, '')

  imploc, module_name = get_module_name(module_path)
  full_import_location = import_base + '.' + imploc

  if module_name.startswith("_"):
    if not silent:
      plugin.api('send.msg')('did not import %s because it is in development' % \
                               full_import_location, primary=plugin.short_name)
    return False, 'dev module', _module, full_import_location

  try:
    if full_import_location in sys.modules:
      return (True, 'already',
              sys.modules[full_import_location], full_import_location)

    if not silent:
      plugin.api('send.msg')('%-30s : attempting import' % \
                              full_import_location.replace('plugins.', ''), primary=plugin.short_name)
    _module = import_module(full_import_location)

    if not silent:
      plugin.api('send.msg')('%-30s : successfully imported' % full_import_location.replace('plugins.', ''), \
                                primary=plugin.short_name)
    return True, 'import', _module, full_import_location

  except Exception: # pylint: disable=broad-except
    if full_import_location in sys.modules:
      del sys.modules[full_import_location]

    plugin.api('send.traceback')(
        "Module '%s' refuses to import/load." % full_import_location)
    return False, 'error', _module, full_import_location

def deletemodule(full_import_location, modules_to_keep=None):
  """
  delete a module
  """
  all_modules_to_keep = ['baseplugin', 'baseconfig']
  if modules_to_keep:
    all_modules_to_keep.extend(modules_to_keep)
  keep = [True for item in modules_to_keep if item in full_import_location]
  if keep:
    return False

  if full_import_location in sys.modules:
    del sys.modules[full_import_location]
    return True

  return False
