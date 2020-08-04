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

def get_module_name(modulepath):
  """
  get a module name
  """
  filename = os.path.basename(modulepath)
  dirname = os.path.dirname(modulepath)
  base = dirname.replace(os.path.sep, '.')
  if base[0] == '.':
    base = base[1:]
  mod = os.path.splitext(filename)[0]
  if not base:
    value1 = '.'.join([mod])
    value2 = mod
  else:
    value1 = '.'.join([base, mod])
    value2 = mod

  return value1, value2

# import a module
def importmodule(modulepath, basepath, plugin, impbase, silent=False):
  """
  import a single module
  """
  _module = None
  if basepath in modulepath:
    modulepath = modulepath.replace(basepath, '')

  imploc, modname = get_module_name(modulepath)
  full_import_location = impbase + '.' + imploc

  if modname.startswith("_"):
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

def deletemodule(full_import_location, modulestokeep=None):
  """
  delete a module
  """
  nmodulestokeep = ['baseplugin', 'baseconfig']
  if modulestokeep:
    nmodulestokeep.extend(modulestokeep)
  keep = [True for item in modulestokeep if item in full_import_location]
  if keep:
    return False

  if full_import_location in sys.modules:
    del sys.modules[full_import_location]
    return True

  return False
