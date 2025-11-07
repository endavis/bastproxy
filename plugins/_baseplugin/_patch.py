# Project: bastproxy
# Filename: plugins/_baseplugin/_patch.py
#
# File Description: holds the plugin patching implementation
#
# By: Bast

# Standard Library
import sys
import types
from importlib import import_module

# 3rd Party
# Project
from libs.api import API as APIClass
from libs.records import LogRecord

from ._base import Plugin

API = APIClass(__name__)

modules_patched = []

def patch(full_import_location, override=False):
    """
    patch the base class with any function in the specified module
    """
    added = False
    if full_import_location not in sys.modules:
        try:
            module = import_module(full_import_location)
        except Exception as e:
            LogRecord(f"Could not load module {full_import_location} for patching of base", level='warning', sources=['baseplugin'], exc_info=True)()
            return False
    else:
        module = sys.modules[full_import_location]
    if module.__name__ in modules_patched and not override:
        LogRecord(f"module {module.__name__} has already patched base", level='warning', sources=['baseplugin'])()
        return False
    if module.__name__ not in modules_patched:
        modules_patched.append(module.__name__)
    LogRecord(f"patching base from module {module.__name__}", level='info', sources=['baseplugin'])()
    for item in dir(module):
        itemo = getattr(module, item)
        if isinstance(itemo, types.FunctionType) and item.startswith('_'):
            if hasattr(Plugin, itemo.__name__):
                LogRecord(f"skipping {module.__name__}:{itemo.__name__} as it already exists in base", level='warning', sources=['baseplugin'])()
                continue

            LogRecord(f"adding {itemo.__name__}", level='info', sources=['baseplugin'])()
            setattr(Plugin, itemo.__name__, itemo)
            added = True

    if added and not API.startup:
        API('plugins.core.events:raise.event')('ev_baseplugin_patched')

    return True
