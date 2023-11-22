# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_patch.py
#
# File Description: holds the plugin patching implementation
#
# By: Bast

# Standard Library
import types

# 3rd Party

# Project
from ._base import Plugin
from libs.records import LogRecord

modules_patched = []

def patch(module, override=False):
    """
    patch the base class with any function in the specified module
    """
    if module.__name__ in modules_patched and not override:
        LogRecord(f"module {module.__name__} has already patched base", level='warning', sources=['baseplugin'])()
        return
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
