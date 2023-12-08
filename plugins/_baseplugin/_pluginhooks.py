# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_pluginhooks.py
#
# File Description: holds the RegisterPluginHook decorator
#
# By: Bast
"""
plugin hooks are for plugins to register functions to be called at certain
points in the plugins lifecycle
"""
# Standard Library

# 3rd Party

# Project

class RegisterPluginHook:
    def __init__(self, hook_name, priority=50):
        """
        '__init__' - invoked for __init__ at the end of baseplugin.__init__
        'initialize' - invoked for initialize
        'save' - invoked when saving the plugin
        'uninitialize' - invoked when uninitializing the plugin

        hook_name: the hook to register to
        priority: the priority to register the function with (default: 50)
        """
        self.hook_name = hook_name
        self.priority = priority

    def __call__(self, func):
        if not hasattr(func, 'plugin_hooks'):
            func.plugin_hooks = {}
        func.plugin_hooks[self.hook_name] = self.priority

        return func
