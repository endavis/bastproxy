# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/debug/api/_patch_base.py
#
# File Description: holds the api command to patch into all plugins
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from libs.api import API
from plugins.core.commands import AddCommand, AddParser, AddArgument

CANRELOAD = False

@AddCommand(group='Debug/Info', name='api')
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
def _command_apihelp_plugin_detail(self):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    detail a function in the api
        @CUsage@w: detail @Y<api>@w
        @Yapi@w = (optional) the api to detail
    """
    args = self.api('plugins.core.commands:get.current.command.args')()
    api = self.api
    if args['noplugin']:
        api = API(owner_id=f"{self.plugin_id}:_command_detail")

    if not args['api']:
        return True, self.api('libs.api:list')(self.plugin_id)

    api_to_find = args['api']
    if ':' not in args['api']:
        api_to_find = f"{self.plugin_id}:{args['api']}"
    return True, api('libs.api:detail')(api_to_find, stats_by_plugin=args['stats'], stats_by_caller=args['statsdetail'],
                                        show_function_code=args['show_code'])
