"""
This plugin will handle watching for commands coming from the client
"""
import re
import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Command Watch'
SNAME = 'watch'
PURPOSE = 'watch for specific commands from clients'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

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

    #self.api('core.commands:command:add')('detail', self.cmd_detail,
                                 #shelp='details of an event')

    self.api('core.events:register:to:event')('io_execute_event', self.checkcmd)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list watches')
    parser.add_argument('match',
                        help='list only watches that have this argument in them',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('list',
                                          self.cmd_list,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details of a watch')
    parser.add_argument('watch',
                        help='the trigger to detail',
                        default=[],
                        nargs='*')
    self.api('core.commands:command:add')('detail',
                                          self.cmd_detail,
                                          parser=parser)

    self.api('core.events:register:to:event')('core.plugins_plugin_uninitialized', self.event_plugin_uninitialized)

  def event_plugin_uninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('libs.io:send:msg')('removing watches for plugin %s' % args['plugin_id'],
                                 secondary=args['plugin_id'])
    self.api('%s:remove:all:data:for:plugin' % self.plugin_id)(args['plugin_id'])

  def cmd_list(self, args):
    """
    list watches
    """
    message = []
    watches = self.watch_data.keys()
    watches.sort()
    match = args['match']

    message.append('%-25s : %-13s %s' % ('Name', 'Defined in',
                                         'Hits'))
    message.append('@B' + '-' * 60 + '@w')
    for watch_name in watches:
      watch = self.watch_data[watch_name]
      if not match or match in watch_name or watch['plugin'] == match:
        message.append('%-25s : %-13s %s' % (watch_name, watch['plugin'],
                                             watch['hits']))

    return True, message

  def cmd_detail(self, args):
    """
    list the details of a watch
    """
    message = []
    if args['watch']:
      for watch in args['watch']:
        if watch in self.watch_data:
          event_name = self.watch_data[watch]['event_name']
          watch_event = self.api('core.events:get:event:detail')(event_name)
          message.append('%-13s : %s' % ('Name', watch))
          message.append('%-13s : %s' % ('Defined in',
                                         self.watch_data[watch]['plugin']))
          message.append('%-13s : %s' % ('Regex',
                                         self.watch_data[watch]['regex']))
          message.append('%-13s : %s' % ('Hits', self.watch_data[watch]['hits']))
          message.extend(watch_event)
        else:
          message.append('trigger %s does not exist' % watch)
    else:
      message.append('Please provide a watch name')

    return True, message

  # add a command watch
  def _api_watch_add(self, watch_name, regex, plugin=None, **kwargs):
    """  add a command watch
    @Ywatch_name@w   = name
    @Yregex@w    = the regular expression that matches this command
    @Yplugin@w   = the plugin this comes from
    @Ykeyword args@w arguments:
      None as of now

    this function returns no values"""
    if not plugin:
      plugin = self.api('libs.api:get:caller:plugin')()

    if not plugin:
      print 'could not add a watch for watchname', watch_name
      return

    if regex in self.regex_lookup:
      self.api('libs.io:send:msg')(
          'watch %s tried to add a regex that already existed for %s' % \
                      (watch_name, self.regex_lookup[regex]), secondary=plugin)
      return
    watch_args = kwargs.copy()
    watch_args['regex'] = regex
    watch_args['plugin'] = plugin
    watch_args['eventname'] = 'watch_' + watch_name
    try:
      self.watch_data[watch_name] = watch_args
      self.watch_data[watch_name]['hits'] = 0
      self.watch_data[watch_name]['compiled'] = re.compile(watch_args['regex'])
      self.regex_lookup[watch_args['regex']] = watch_name
      self.api('libs.io:send:msg')(
          'added watch %s for plugin %s' % \
                      (watch_name, plugin), secondary=plugin)
    except Exception: # pylint: disable=broad-except
      self.api('libs.io:send:traceback')(
          'Could not compile regex for cmd watch: %s : %s' % \
                (watch_name, regex))

  # remove a command watch
  def _api_watch_remove(self, watch_name, force=False):
    """  remove a command watch
    @Ywatch_name@w   = The watch name
    @Yforce@w       = force removal if functions are registered

    this function returns no values"""
    if watch_name in self.watch_data:
      event = self.api('core.events:get:event')(self.watch_data[watch_name]['eventname'])
      plugin = self.watch_data[watch_name]['plugin']
      if event:
        if not event.isempty() and not force:
          self.api('libs.io:send:msg')(
              'removewatch: watch %s for plugin %s has functions registered' % \
                      (watch_name, plugin), secondary=plugin)
          return False
      del self.regex_lookup[self.watch_data[watch_name]['regex']]
      del self.watch_data[watch_name]
      self.api('libs.io:send:msg')('removed watch %s' % watch_name,
                                   secondary=plugin)
    else:
      self.api('libs.io:send:msg')('removewatch: watch %s does not exist' % \
                                            watch_name)

  # remove all watches related to a plugin
  def _api_remove_all_data_for_plugin(self, plugin):
    """  remove all watches related to a plugin
    @Yplugin@w   = The plugin

    this function returns no values"""
    self.api('libs.io:send:msg')('removing watches for plugin %s' % plugin,
                                 secondary=plugin)
    watches = self.watch_data.keys()
    for i in watches:
      if self.watch_data[i]['plugin'] == plugin:
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
        match_args = match_data.groupdict()
        match_args['cmdname'] = 'cmd_' + watch_name
        match_args['data'] = client_data
        self.api('libs.io:send:msg')('raising %s' % match_args['cmdname'])
        event_data = self.api('core.events:raise:event')('watch_' + watch_name, match_args)
        if 'changed' in event_data:
          if 'trace' in data:
            data['trace']['changes'].append({'cmd':client_data,
                                             'flag':'modify',
                                             'newcmd':event_data['changed'],
                                             'plugin':self.plugin_id})
          data['nfromdata'] = event_data['changed']

    if 'nfromdata' in data:
      data['fromdata'] = data['nfromdata']
    return data
