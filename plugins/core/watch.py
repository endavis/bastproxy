# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/watch.py
#
# File Description: a plugin to watch for commands from the client
#
# By: Bast
"""
This plugin will handle watching for commands coming from the client
"""
# Standard Library
import re

# 3rd Party

# Project
from libs.records import LogRecord, EventArgsRecord
from plugins._baseplugin import BasePlugin
from libs.commands import AddParser, AddArgument
from libs.event import RegisterToEvent
from libs.api import AddAPI

#these 5 are required
NAME = 'Command Watch'
SNAME = 'watch'
PURPOSE = 'watch for specific commands from clients'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class Plugin(BasePlugin):
    """
    a plugin to watch for commands coming from the client
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.can_reload_f = False

        self.regex_lookup = {}
        self.watch_data = {}

    @RegisterToEvent(event_name='ev_plugins.core.pluginm_plugin_uninitialized')
    def _eventcb_plugin_uninitialized(self):
        """
        a plugin was uninitialized
        """
        event_record = self.api('plugins.core.events:get.current.event.record')()
        LogRecord(f"event_plugin_unitialized - removing watches for plugin {event_record['plugin_id']}",
                  level='debug', sources=[self.plugin_id, event_record['plugin_id']])()
        self.api(f"{self.plugin_id}:remove.all.data.for.plugin")(event_record['plugin_id'])

    @AddParser(description='list watches')
    @AddArgument('match',
                        help='list only watches that have this argument in them',
                        default='',
                        nargs='?')
    def _command_list(self):
        """
        list watches
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        watches = self.watch_data.keys()
        watches = sorted(watches)
        match = args['match']

        template = '%-25s : %-13s %s'

        message = [
            template % ('Name', 'Defined in', 'Hits'),
            '@B' + '-' * 60 + '@w',
        ]
        for watch_name in watches:
            watch = self.watch_data[watch_name]
            if not match or match in watch_name or watch['owner'] == match:
                message.append(template % (watch_name, watch['owner'],
                                                     watch['hits']))

        return True, message

    @AddParser(description='get details of a watch')
    @AddArgument('watch',
                    help='the trigger to detail',
                    default=[],
                    nargs='*')
    def _command_detail(self):
        """
        list the details of a watch
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        if args['watch']:
            columnwidth = 13
            for watch in args['watch']:
                if watch in self.watch_data:
                    event_name = self.watch_data[watch]['event_name']
                    watch_event = self.api('plugins.core.events:get.event.detail')(event_name)
                    message.extend(
                        (
                            f"{'Name':<{columnwidth}} : {watch}",
                            f"{'Defined in':<{columnwidth}} : {self.watch_data[watch]['owner']}",
                            f"{'Regex':<{columnwidth}} : {self.watch_data[watch]['regex']}",
                            f"{'Hits':<{columnwidth}} : {self.watch_data[watch]['hits']}",
                        )
                    )
                    message.extend(watch_event)
                else:
                    message.append(f"watch {watch} does not exist")
        else:
            message.append('Please provide a watch name')

        return True, message

    @AddAPI('watch.add', description='add a watch')
    def _api_watch_add(self, watch_name, regex, owner=None, **kwargs):
        """  add a command watch
        @Ywatch_name@w   = name
        @Yregex@w    = the regular expression that matches this command
        @Yplugin@w   = the plugin this comes from
        @Ykeyword args@w arguments:
          None as of now

        this function returns no values"""
        if not owner:
            owner = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        if not owner:
            LogRecord(f"_api_watch_add: no plugin could be found to add {watch_name}",
                      level='error', sources=[self.plugin_id])()
            return

        if regex in self.regex_lookup:
            LogRecord(f"_api_watch_add: watch {watch_name} tried to add a regex that already existed for {self.regex_lookup[regex]}",
                      level='debug', sources=[self.plugin_id, owner])()
            return
        watch_args = kwargs.copy()
        watch_args['regex'] = regex
        watch_args['owner'] = owner
        watch_args['eventname'] = f'watch_{watch_name}'
        try:
            self.watch_data[watch_name] = watch_args
            self.watch_data[watch_name]['hits'] = 0
            self.watch_data[watch_name]['compiled'] = re.compile(watch_args['regex'])
            self.regex_lookup[watch_args['regex']] = watch_name
            LogRecord(f"_api_watch_add: watch {watch_name} added for {owner}",
                      level='debug', sources=[self.plugin_id, owner])()
        except Exception: # pylint: disable=broad-except
            LogRecord(f"_api_watch_add: watch {watch_name} failed to compile regex {regex}",
                      level='error', sources=[self.plugin_id, owner], exc_info=True)()

        # add the event so it can be tracked
        self.api('plugins.core.events:add.event')(watch_args['eventname'], watch_args['owner'],
                                                  description = f"event for {watch_name} for {watch_args['regex']}",
                                                  arg_descriptions = { 'matched' : 'The matched arguments from the regex',
                                                                       'cmdname' : 'The command name that was matched',
                                                                       'data'    : 'The data that was matched'})

    @AddAPI('watch.remove', description='remove a watch')
    def _api_watch_remove(self, watch_name, force=False):
        """  remove a command watch
        @Ywatch_name@w   = The watch name
        @Yforce@w       = force removal if functions are registered

        this function returns no values"""
        if watch_name in self.watch_data:
            event = self.api('plugins.core.events:get.event')(self.watch_data[watch_name]['eventname'])
            plugin = self.watch_data[watch_name]['owner']
            if event and not event.isempty() and not force:
                LogRecord(f"_api_watch_remove: watch {watch_name} for plugin {plugin} has functions registered",
                          level='error', sources=[self.plugin_id, plugin])()
                return False
            del self.regex_lookup[self.watch_data[watch_name]['regex']]
            del self.watch_data[watch_name]
            LogRecord(f"_api_watch_remove: watch {watch_name} for plugin {plugin} removed",
                      level='debug', sources=[self.plugin_id, plugin])()
        else:
            LogRecord(f"_api_watch_remove: watch {watch_name} does not exist",
                      level='error', sources=[self.plugin_id])()

    @AddAPI('remove.all.data.for.plugin', description='remove all watches for a plugin')
    def _api_remove_all_data_for_plugin(self, plugin):
        """  remove all watches related to a plugin
        @Yplugin@w   = The plugin

        this function returns no values"""
        LogRecord(f"_api_remove_all_data_for_plugin: removing watches for plugin {plugin}",
                  level='debug', sources=[self.plugin_id, plugin])()
        watches = self.watch_data.keys()
        for i in watches:
            if self.watch_data[i]['owner'] == plugin:
                self.api(f'{self.plugin_id}:watch.remove')(i)

    @RegisterToEvent(event_name='ev_to_mud_data_modify')
    def _eventcb_check_command(self):
        """
        check input from the client and see if we are watching for it
        """
        if not (
            event_record := self.api(
                'plugins.core.events:get.current.event.record'
            )()
        ):
            return
        client_data = event_record['line']
        for watch_name in self.watch_data:
            cmdre = self.watch_data[watch_name]['compiled']
            if match_data := cmdre.match(client_data):
                self.watch_data[watch_name]['hits'] = self.watch_data[watch_name]['hits'] + 1
                match_args = {
                    'matched': match_data.groupdict(),
                    'cmdname': f'cmd_{watch_name}',
                }
                match_args['data'] = client_data
                LogRecord(f"_eventcb_check_command: watch {watch_name} matched {client_data}, raising {match_args['cmdname']}",
                        level='debug', sources=[self.plugin_id])()
                self.api('plugins.core.events:raise.event')(self.watch_data[watch_name]['eventname'], match_args)
