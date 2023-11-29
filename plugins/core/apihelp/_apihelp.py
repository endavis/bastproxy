# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/apihelp/_apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""
this plugin can be used to inspect and call functions in the api
"""
# Standard Library

# 3rd Party

# Project
from libs.api import API
from libs.commands import AddParser, AddArgument
from plugins._baseplugin import BasePlugin

class APIHelpPlugin(BasePlugin):
    """
    a plugin to show api information
    """
    @AddParser(description='detail a function in the API')
    @AddArgument('-a',
                    '--api',
                    help='the api to detail (optional)',
                    default='', nargs='?')
    @AddArgument('-s',
                    '--stats',
                    help="add stats",
                    action='store_true')
    @AddArgument('-sd',
                    '--statsdetail',
                    help='The caller to show detailed stats for the api',
                    default='', nargs='?')
    @AddArgument('-np',
                    '--noplugin',
                    help="use an API that is not from a plugin",
                    action='store_true')
    @AddArgument('-c', '--show-code',
                    help="show the function code",
                    action='store_true')
    def _command_detail(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        detail a function in the api
          @CUsage@w: detail @Y<api>@w
          @Yapi@w = (optional) the api to detail
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        api = self.api
        if args['noplugin']:
            api = API(owner_id=f"{self.plugin_id}:_command_detail")
        if args['api']:
            tmsg.extend(api('libs.api:detail')(args['api'], stats_by_plugin=args['stats'], stats_by_caller=args['statsdetail'],
                                               show_function_code=args['show_code']))

        else: # args <= 0
            tmsg.append('Please provide an api to detail')

        return True, tmsg

    @AddParser(description='list functions in the API')
    @AddArgument('toplevel',
                    help='the top level api to show (optional)',
                    default='', nargs='?')
    @AddArgument('-np',
                    '--noplugin',
                    help="use an API that is not from a plugin",
                    action='store_true')
    def _command_list(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        api = self.api
        if args['noplugin']:
            api = API(owner_id=f"{self.plugin_id}:_command_list")
        if apilist := api('libs.api:list.data')(args['toplevel']):
            api_columns = [
                {'name': 'API', 'key': 'full_api_name', 'width': 5},
                {'name': 'Called', 'key': 'called_count', 'width': 7},
                {'name': 'Description', 'key': 'description', 'width': 10},
            ]

            tmsg.extend(self.api('plugins.core.utils:convert.data.to.output.table')('APIs', apilist, api_columns))
        else:
            tmsg.append(f"{args['toplevel']} does not exist in the api")

        return True, tmsg

    @AddParser(description='call an API')
    @AddArgument('-a',
                    '--api',
                    help='the api to detail (optional)',
                    default='', nargs='?')
    @AddArgument('arguments',
                    help='arguments to the api',
                    default='', nargs='*')
    def _command_run(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        api = args['api']
        try:
            returnstuff = self.api(api)(*args['arguments'])
            tmsg = self.dump_object_as_string(returnstuff)
            return True, ['Api returned:', '', tmsg]
        except Exception as e:
            return True, ['Api returned an error:', f'{e}']
