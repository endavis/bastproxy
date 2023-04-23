# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""
This plugin will show api functions and details
"""
# Standard Library

# 3rd Party

# Project
import libs.argp as argp
from plugins._baseplugin import BasePlugin
from libs.records import RMANAGER

#these 5 are required
NAME = 'Inspect Proxy Internals'
PURPOSE = 'see info about records and other internal proxy functions'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class Plugin(BasePlugin):
    """
    a plugin to show connection information
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description='return the list of record types')
        self.api('plugins.core.commands:command.add')('types', self.cmd_types,
                                              parser=parser)


        parser = argp.ArgumentParser(add_help=False,
                                     description='get a list of a specific type of record')
        parser.add_argument('recordtype',
                            help='the type of record to list',
                            default='')
        parser.add_argument('-n',
                            '--number',
                            help='the # of items to return (default 10)',
                            default=10,
                            nargs='?',
                            type=int)
        self.api('plugins.core.commands:command.add')('list', self.cmd_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='details a specific record')
        parser.add_argument('uid', help='the uid of the record',
                            default='', nargs='?')
        self.api('plugins.core.commands:command.add')('detail', self.cmd_detail,
                                              parser=parser)

    def cmd_types(self, _):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        tmsg = ['Record Types:']
        tmsg.extend(iter(RMANAGER.get_types()))
        return True, tmsg

    def cmd_list(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        List functions in the api
          @CUsage@w: list @Y<apiname>@w
          @Yapiname@w = (optional) the toplevel api to show
        """
        tmsg = [f"Last {args['number']} records of type {args['recordtype']}:"]

        if records := RMANAGER.get_records(args['recordtype'], count=args['number']):
            tmsg.extend([f"{record.uuid} - {record.original_data[0].strip()} ..." for record in records])
        else:
            tmsg.append('No records found')

        return True, tmsg


    def cmd_detail(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
        detail a function in the api
          @CUsage@w: detail @Y<api>@w
          @Yapi@w = (optional) the api to detail
        """
        tmsg = []

        if not args['uid']:
            tmsg.append('No record id provided')
            return True, tmsg

        record = RMANAGER.get_record(args['uid'])

        # Records are list and can be empty, so check is None
        if record is not None:
            tmsg.extend(record.get_formatted_details())
        else:
            tmsg.append(f"record {args['uid']} not found")

        return True, tmsg
