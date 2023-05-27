# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/_baseplugin/_pluginhooks.py
#
# File Description: holds the RegisterPluginHook decorator
#
# By: Bast

# Standard Library

# 3rd Party

# Project

class RegisterPluginHook:
    def __init__(self, hook_name, priority=50):
        """
        'post_base_init' - invoked after the base plugin class __init__
        'post_init' - invoked after all __init__ have completed
        'pre_initialize' - invoked before the initialize method
        'post_initialize' - invoked after the initialize method
        'save' - invoked when saving the plugin
        'reset' - invoked when resetting the plugin
        'stats' - invoked when getting the stats of the plugin
                    returns a dict of stats

            hook_name: the hook to register to
            priority: the priority to register the function with (Default: 50)
        """
        self.hook_name = hook_name
        self.priority = priority

    def __call__(self, func):
        if not hasattr(func, 'load_hooks'):
            func.load_hooks = {}
        if self.hook_name not in func.load_hooks:
            func.load_hooks[self.hook_name] = []
        func.load_hooks[self.hook_name] = self.priority

        return func
