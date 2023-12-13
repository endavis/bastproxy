# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/records/_records.py
#
# File Description: a plugin to inspect records
#
# By: Bast

# Standard Library

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from libs.records import RMANAGER
from plugins.core.commands import AddParser, AddArgument

class RecordPlugin(BasePlugin):
    """
    a plugin to inspect records
    """
    @RegisterPluginHook('initialize')
    def _phook_initialize(self):
        """
        initialize the instance
        """
        self.api('plugins.core.settings:add')(self.plugin_id, 'showLogRecords', False, bool,
                                '1 to show LogRecords in detail command')

    @AddParser(description='return the list of record types')
    def _command_types(self):
        """
        List the types of records
        """
        tmsg = ['Record Types:']
        tmsg.extend(f"{rtype:<25} - {count}" for rtype, count in RMANAGER.get_types())
        return True, tmsg

    @AddParser(description='get a list of a specific type of record')
    @AddArgument('recordtype',
                    help='the type of record to list',
                    default='')
    @AddArgument('-c',
                    '--count',
                    help='the # of items to return (default 10)',
                    default=10,
                    nargs='?',
                    type=int)
    def _command_list(self):
        """
        List records of a specific type
        """
        line_length = self.api('plugins.core.commands:get.output.line.length')()
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        args = self.api('plugins.core.commands:get.current.command.args')()
        rtypes = [rtype for rtype, _ in RMANAGER.get_types()]
        if not args['recordtype'] or args['recordtype'] not in rtypes:
            return True, ["Valid Types:", *[f"    {rtype}" for rtype in rtypes]]
        tmsg = [f"Last {args['count']} records of type {args['recordtype']}:",
                header_color + line_length * '-' + '@w']
        if records := RMANAGER.get_records(args['recordtype'], count=args['count']):
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
        get the details of a specific record
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
            showlogrecords = self.api('plugins.core.settings:get')(self.plugin_id, 'showLogRecords')
            update_filter = [] if showlogrecords else ['LogRecord']
            tmsg.extend(record.get_formatted_details(update_filter=update_filter,
                                                     full_related_records=args['full_related_records'],
                                                     include_updates=args['include_updates']))

        return True, tmsg
