# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/inspect/_plugin.py
#
# File Description: a plugin to inspect plugin internals
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.records import RMANAGER
from libs.commands import AddParser, AddArgument

class InspectPlugin(BasePlugin):
    """
    a plugin to show connection information
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.api(f"{self.plugin_id}:setting.add")('showLogRecords', False, bool,
                                '1 to show LogRecords in detail command')

    @AddParser(description='return the list of record types')
    def _command_types(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        tmsg = ['Record Types:']
        tmsg.extend(f"{rtype:<25} - {count}" for rtype, count in RMANAGER.get_types())
        return True, tmsg

    @AddParser(description='get a list of a specific type of record')
    @AddArgument('recordtype',
                    help='the type of record to list',
                    default='')
    @AddArgument('-n',
                    '--number',
                    help='the # of items to return (default 10)',
                    default=10,
                    nargs='?',
                    type=int)
    def _command_list(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        if not args['recordtype']:
            return True, [f'Please enter a record type of {", ".join(RMANAGER.get_types())}']
        tmsg = [f"Last {args['number']} records of type {args['recordtype']}:"]

        if records := RMANAGER.get_records(args['recordtype'], count=args['number']):
            tmsg.extend([f"{record.uuid} - {record.original_data[0].strip()} ..." for record in records])
        else:
            tmsg.append('No records found')

        return True, tmsg

    @AddParser(description='get details of a specific record')
    @AddArgument('uid', help='the uid of the record',
                    default='', nargs='?')
    @AddArgument('-u',
                    '--update',
                    help='the update uuid',
                    default='')
    @AddArgument('-dls',
                    '--data_lines_to_show',
                    help='the # of lines of data to show, -1 for all data',
                    default=10,
                    type=int)
    @AddArgument('-sd',
                    '--show_data',
                    help='show data in updates',
                    action='store_false',
                    default=True)
    @AddArgument('-ss',
                    '--show_stack',
                    help='show stack in updates',
                    action='store_false',
                    default=True)
    @AddArgument('-sfr',
                    '--full_related_records',
                    help='show the full related record (without updates)',
                    action='store_true',
                    default=False)
    @AddArgument('-iu',
                    '--include_updates',
                    help='include_updates in the detail',
                    action='store_false',
                    default=True)
    def _command_detail(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        detail a function in the api
          @CUsage@w: detail @Y<api>@w
          @Yapi@w = (optional) the api to detail
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []

        if not args['uid']:
            tmsg.append('No record id provided')
            return True, tmsg

        record = RMANAGER.get_record(args['uid'])

        # Records are list and can be empty, so check is None
        if record is None:
            tmsg.append(f"record {args['uid']} not found")

        elif args['update']:
            if update := record.get_update(args['update']):
                tmsg.extend(update.format_detailed())
            else:
                tmsg.append(f"update {args['update']} in record {args['uid']} not found")

        else:
            showlogrecords = self.api(f"{self.plugin_id}:setting.get")('showLogRecords')
            update_filter = [] if showlogrecords else ['LogRecord']
            tmsg.extend(record.get_formatted_details(update_filter=update_filter,
                                                     full_related_records=args['full_related_records'],
                                                     include_updates=args['include_updates']))

        return True, tmsg

    @AddParser(description='inspect a plugin')
    @AddArgument('plugin',
                    help='the plugin to inspect',
                    default='')
    @AddArgument('-o',
                    '--object',
                    help='show an object of the plugin, can be method or variable',
                    default='')
    @AddArgument('-s',
                    '--simple',
                    help='show a simple output',
                    action='store_true')
    def _command_plugin(self):
        """
        inspect another plugin
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        if not args['plugin']:
            return False, ['Please enter a plugin name']

        if not self.api('plugins.core.pluginm:is.plugin.id')(args['plugin']):
            return True, [f'Plugin {args["plugin"]} not found']

        return True, self.api(f"{args['plugin']}:dump")(args['object'], args['simple'])[1]
