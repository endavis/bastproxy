# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/commands.py
#
# File Description: holds command utilities
#
# By: Bast
"""
This plugin hold command utilities

All 3 decorators are not required.
if any one of the decorators are used, the command plugin will
mark this for command creation and use defaults for any missing
variables.

To apply a command to a plugin method, use the following decorator:
    from libs.commands import AddCommand, AddParser, AddArgument

    # see the arguments for plugins.core.commands.Command.__init__ kwargs
    # There are a couple of special keywords that can be used:
    #   dynamic_name - will make the command plugin
    #       format the given string with the input as func.__self__.__dict__
    #       and use that for the command name
    #   autoadd - if False, the command will not be adding automatically
    #        It can be added later, see plugins._baseplugin.BasePlugin._add_commands
    @AddCommand(show_in_history=False)
    # passed directly to ArgumentParser
    @AddParser(description='list functions in the API')
    # passed directly to ArgumentParser.add_argument
    @AddArgument('toplevel',
                    help='the top level api to show (optional)',
                    default='', nargs='?')
    @AddArgument('-np',
                    '--noplugin',
                    help="use an API that is not from a plugin",
                    action='store_true')
    def _command_list(self):
        \"""
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        \"""
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []

        api = self.api
        if args['noplugin']:
            api = API(owner_id=f"{self.plugin_id}:_command_list")

        if apilist := api('libs.api:list')(args['toplevel']):
            tmsg.extend(apilist)
        else:
            tmsg.append(f"{args['toplevel']} does not exist in the api")
        return True, tmsg
"""
# Standard Library

# 3rd Party

# Project

commands_at_startup = {}

class CommandFuncData:
    def __init__(self):
        self.command = {'dynamic_name': False,
                        'autoadd': True,
                        'kwargs': {}}
        self.argparse = {'kwargs': {'add_help': False},
                         'args': []}
        self.arguments = []

class AddCommand:
    """
    a class to decorate a function with command data
    """
    def __init__(self, *args, **kwargs):
        self.dynamic_name = False
        if 'dynamic_name' in  kwargs:
            self.dynamic_name = kwargs['dynamic_name']
            del kwargs['dynamic_name']
        self.autoadd = True
        if 'autoadd' in  kwargs:
            self.autoadd = kwargs['autoadd']
            del kwargs['autoadd']
        self.command_kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, 'command_data'):
            func.command_data  = CommandFuncData()
        func.command_data.command['kwargs'].update(self.command_kwargs)
        func.command_data.command['dynamic_name'] = self.dynamic_name
        func.command_data.command['autoadd'] = self.autoadd

        return func

class AddParser:
    """
    a class to decorate a function with argparse data
    """
    def __init__(self, *args, **kwargs):
        self.argparse_args = args
        self.argparse_kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, 'command_data'):
            func.command_data = CommandFuncData()
        func.command_data.argparse['args'] = self.argparse_args
        func.command_data.argparse['kwargs'].update(self.argparse_kwargs)

        return func

class AddArgument:
    """
    a class to decorate a function with argument data
    """
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, 'command_data'):
            func.command_data = CommandFuncData()

        # insert at 0 because decorators are applied in bottom->top order,
        # so the last decorator applied will be the first
        # make it so the order can be exactly like using an argparse object
        func.command_data.arguments.insert(0, {'args': self.args, 'kwargs': self.kwargs})

        return func
