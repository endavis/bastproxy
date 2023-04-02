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
import libs.argp as argp
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin

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

        # new api format
        self.api('libs.api:add')('watch:add', self._api_watch_add)
        self.api('libs.api:add')('watch:remove', self._api_watch_remove)
        self.api('libs.api:add')('remove:all:data:for:plugin', self._api_remove_all_data_for_plugin)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:register:to:event')('ev_libs.io_execute', self.checkcmd)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list watches')
        parser.add_argument('match',
                            help='list only watches that have this argument in them',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('list',
                                              self.cmd_list,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='get details of a watch')
        parser.add_argument('watch',
                            help='the trigger to detail',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command:add')('detail',
                                              self.cmd_detail,
                                              parser=parser)

        self.api('plugins.core.events:register:to:event')('ev_plugins.core.plugins_plugin_uninitialized',
                                                          self.event_plugin_uninitialized)

    def event_plugin_uninitialized(self, args):
        """
        a plugin was uninitialized
        """
        LogRecord(f"event_plugin_unitialized - removing watches for plugin {args['plugin_id']}",
                  level='debug', sources=[self.plugin_id, args['plugin_id']]).send()
        self.api(f"{self.plugin_id}:remove:all:data:for:plugin")(args['plugin_id'])

    def cmd_list(self, args):
        """
        list watches
        """
        message = []
        watches = self.watch_data.keys()
        watches.sort()
        match = args['match']

        template = '%-25s : %-13s %s'

        message.append(template % ('Name', 'Defined in',
                                             'Hits'))
        message.append('@B' + '-' * 60 + '@w')
        for watch_name in watches:
            watch = self.watch_data[watch_name]
            if not match or match in watch_name or watch['owner'] == match:
                message.append(template % (watch_name, watch['owner'],
                                                     watch['hits']))

        return True, message

    def cmd_detail(self, args):
        """
        list the details of a watch
        """
        message = []
        columnwidth = 13
        if args['watch']:
            for watch in args['watch']:
                if watch in self.watch_data:
                    event_name = self.watch_data[watch]['event_name']
                    watch_event = self.api('plugins.core.events:get:event:detail')(event_name)
                    message.append(f"{'Name':<{columnwidth}} : {watch}")
                    message.append(f"{'Defined in':<{columnwidth}} : {self.watch_data[watch]['owner']}")
                    message.append(f"{'Regex':<{columnwidth}} : {self.watch_data[watch]['regex']}")
                    message.append(f"{'Hits':<{columnwidth}} : {self.watch_data[watch]['hits']}")
                    message.extend(watch_event)
                else:
                    message.append(f"watch {watch} does not exist")
        else:
            message.append('Please provide a watch name')

        return True, message

    # add a command watch
    def _api_watch_add(self, watch_name, regex, owner=None, **kwargs):
        """  add a command watch
        @Ywatch_name@w   = name
        @Yregex@w    = the regular expression that matches this command
        @Yplugin@w   = the plugin this comes from
        @Ykeyword args@w arguments:
          None as of now

        this function returns no values"""
        if not owner:
            owner = self.api('libs.api:get:caller:owner')(ignore_owner_list=[self.plugin_id])

        if not owner:
            LogRecord(f"_api_watch_add: no plugin could be found to add {watch_name}",
                      level='error', sources=[self.plugin_id]).send()
            return

        if regex in self.regex_lookup:
            LogRecord(f"_api_watch_add: watch {watch_name} tried to add a regex that already existed for {self.regex_lookup[regex]}",
                      level='debug', sources=[self.plugin_id, owner]).send()
            return
        watch_args = kwargs.copy()
        watch_args['regex'] = regex
        watch_args['owner'] = owner
        watch_args['eventname'] = 'watch_' + watch_name
        try:
            self.watch_data[watch_name] = watch_args
            self.watch_data[watch_name]['hits'] = 0
            self.watch_data[watch_name]['compiled'] = re.compile(watch_args['regex'])
            self.regex_lookup[watch_args['regex']] = watch_name
            LogRecord(f"_api_watch_add: watch {watch_name} added for {owner}",
                      level='debug', sources=[self.plugin_id, owner]).send()
        except Exception: # pylint: disable=broad-except
            LogRecord(f"_api_watch_add: watch {watch_name} failed to compile regex {regex}",
                      level='error', sources=[self.plugin_id, owner], exc_info=True).send()

        # add the event so it can be tracked
        self.api('plugins.core.events:add:event')(watch_args['eventname'], watch_args['owner'],
                                                  description = f"event for {watch_name} for {watch_args['regex']}",
                                                  arg_descriptions = { 'matched' : 'The matched arguments from the regex',
                                                                       'cmdname' : 'The command name that was matched',
                                                                       'data'    : 'The data that was matched'})

    # remove a command watch
    def _api_watch_remove(self, watch_name, force=False):
        """  remove a command watch
        @Ywatch_name@w   = The watch name
        @Yforce@w       = force removal if functions are registered

        this function returns no values"""
        if watch_name in self.watch_data:
            event = self.api('plugins.core.events:get:event')(self.watch_data[watch_name]['eventname'])
            plugin = self.watch_data[watch_name]['owner']
            if event:
                if not event.isempty() and not force:
                    LogRecord(f"_api_watch_remove: watch {watch_name} for plugin {plugin} has functions registered",
                              level='error', sources=[self.plugin_id, plugin]).send()
                    return False
            del self.regex_lookup[self.watch_data[watch_name]['regex']]
            del self.watch_data[watch_name]
            LogRecord(f"_api_watch_remove: watch {watch_name} for plugin {plugin} removed",
                      level='debug', sources=[self.plugin_id, plugin]).send()
        else:
            LogRecord(f"_api_watch_remove: watch {watch_name} does not exist",
                      level='error', sources=[self.plugin_id]).send()

    # remove all watches related to a plugin
    def _api_remove_all_data_for_plugin(self, plugin):
        """  remove all watches related to a plugin
        @Yplugin@w   = The plugin

        this function returns no values"""
        LogRecord(f"_api_remove_all_data_for_plugin: removing watches for plugin {plugin}",
                  level='debug', sources=[self.plugin_id, plugin]).send()
        watches = self.watch_data.keys()
        for i in watches:
            if self.watch_data[i]['owner'] == plugin:
                self.api('%s:watch:remove' % self.plugin_id)(i)

    def checkcmd(self, data):
        """
        check input from the client and see if we are watching for it
        """
        client_data = data['fromdata'].strip()
        for watch_name in self.watch_data:
            cmdre = self.watch_data[watch_name]['compiled']
            match_data = cmdre.match(client_data)
            if match_data:
                self.watch_data[watch_name]['hits'] = self.watch_data[watch_name]['hits'] + 1
                match_args = {}
                match_args['matched'] = match_data.groupdict()
                match_args['cmdname'] = 'cmd_' + watch_name
                match_args['data'] = client_data
                LogRecord(f"checkcmd: watch {watch_name} matched {client_data}, raising {match_args['cmdname']}",
                          level='debug', sources=[self.plugin_id]).send()
                event_data = self.api('plugins.core.events:raise:event')(self.watch_data[watch_name]['eventname'], match_args)
                # Since this is an EventArgRecord, we can check to see if it was changed
                if 'changed' in event_data:
                    self.api('libs.io:trace:add:execute')(self.plugin_id, 'Modify',
                                                          original_data=client_data,
                                                          new_data=event_data['changed'])
                    data['nfromdata'] = event_data['changed']

        if 'nfromdata' in data:
            data['fromdata'] = data['nfromdata']
        return data
