# Project: bastproxy
# Filename: plugins/_baseplugin/libs/_pluginhooks.py
#
# File Description: holds the RegisterPluginHook decorator
#
# By: Bast
"""plugin hooks are for plugins to register functions to be called at certain.

points in the plugins lifecycle.
"""
# Standard Library

# 3rd Party

# Project

VALID_HOOK_NAMES: tuple[str, ...] = ("__init__", "after_load", "save", "uninitialize")


def validate_hook_name(hook_name: str) -> None:
    """Raise ValueError unless hook_name is one of VALID_HOOK_NAMES.

    A misspelled name used to register and never run (#446).
    """
    if hook_name in VALID_HOOK_NAMES:
        return
    message = (
        f"unknown plugin hook name {hook_name!r}; valid hooks are: {', '.join(VALID_HOOK_NAMES)}"
    )
    if hook_name == "initialize":
        message += " ('initialize' was renamed to 'after_load', #423)"
    raise ValueError(message)


class RegisterPluginHook:
    def __init__(self, hook_name, priority=50):
        """'__init__' - invoked for __init__ at the end of baseplugin.__init__.

        'after_load' - invoked when the initialize method is ran
        'save' - invoked when saving the plugin
        'uninitialize' - invoked when the unitialize method is ran.

        hook_name: the hook to register to
        priority: the priority to register the function with (default: 50)

        Raises ValueError for a hook name not in VALID_HOOK_NAMES.
        """
        validate_hook_name(hook_name)
        self.hook_name = hook_name
        self.priority = priority

    def __call__(self, func):
        if not hasattr(func, "plugin_hooks"):
            func.plugin_hooks = {}
        func.plugin_hooks[self.hook_name] = self.priority

        return func
