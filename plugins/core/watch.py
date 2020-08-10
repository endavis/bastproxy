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

    self.regexlookup = {}
    self.watchcmds = {}

    self.api('api.add')('add', self.api_addwatch)
    self.api('api.add')('remove', self.api_removewatch)
    self.api('api.add')('removeplugin', self.api_removeplugin)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    #self.api('commands.add')('detail', self.cmd_detail,
                                 #shelp='details of an event')

    self.api('events.register')('io_execute_event', self.checkcmd)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list watches')
    parser.add_argument('match',
                        help='list only watches that have this argument in them',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details of a watch')
    parser.add_argument('watch',
                        help='the trigger to detail',
                        default=[],
                        nargs='*')
    self.api('commands.add')('detail',
                             self.cmd_detail,
                             parser=parser)

    self.api('events.register')('plugin_uninitialized', self.pluginuninitialized)

  def pluginuninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('send.msg')('removing watches for plugin %s' % args['name'],
                         secondary=args['name'])
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  def cmd_list(self, args):
    """
    list watches
    """
    tmsg = []
    tkeys = self.watchcmds.keys()
    tkeys.sort()
    match = args['match']

    tmsg.append('%-25s : %-13s %s' % ('Name', 'Defined in',
                                      'Hits'))
    tmsg.append('@B' + '-' * 60 + '@w')
    for i in tkeys:
      watch = self.watchcmds[i]
      if not match or match in i or watch['plugin'] == match:
        tmsg.append('%-25s : %-13s %s' % (i, watch['plugin'],
                                          watch['hits']))

    return True, tmsg

  def cmd_detail(self, args):
    """
    list the details of a watch
    """
    tmsg = []
    if args['watch']:
      for watch in args['watch']:
        if watch in self.watchcmds:
          eventname = self.watchcmds[watch]['eventname']
          eventstuff = self.api('events.detail')(eventname)
          tmsg.append('%-13s : %s' % ('Name', watch))
          tmsg.append('%-13s : %s' % ('Defined in',
                                      self.watchcmds[watch]['plugin']))
          tmsg.append('%-13s : %s' % ('Regex',
                                      self.watchcmds[watch]['regex']))
          tmsg.append('%-13s : %s' % ('Hits', self.watchcmds[watch]['hits']))
          tmsg.extend(eventstuff)
        else:
          tmsg.append('trigger %s does not exist' % watch)
    else:
      tmsg.append('Please provide a watch name')

    return True, tmsg

  # add a command watch
  def api_addwatch(self, watchname, regex, plugin=None, **kwargs):
    """  add a command watch
    @Ywatchname@w   = name
    @Yregex@w    = the regular expression that matches this command
    @Yplugin@w   = the plugin this comes from
    @Ykeyword args@w arguments:
      None as of now

    this function returns no values"""
    if not plugin:
      plugin = self.api('api.callerplugin')()

    if not plugin:
      print 'could not add a watch for watchname', watchname
      return

    if regex in self.regexlookup:
      self.api('send.msg')(
          'watch %s tried to add a regex that already existed for %s' % \
                      (watchname, self.regexlookup[regex]), secondary=plugin)
      return
    args = kwargs.copy()
    args['regex'] = regex
    args['plugin'] = plugin
    args['eventname'] = 'watch_' + watchname
    try:
      self.watchcmds[watchname] = args
      self.watchcmds[watchname]['hits'] = 0
      self.watchcmds[watchname]['compiled'] = re.compile(args['regex'])
      self.regexlookup[args['regex']] = watchname
      self.api('send.msg')(
          'added watch %s for plugin %s' % \
                      (watchname, plugin), secondary=plugin)
    except Exception: # pylint: disable=broad-except
      self.api('send.traceback')(
          'Could not compile regex for cmd watch: %s : %s' % \
                (watchname, regex))

  # remove a command watch
  def api_removewatch(self, watchname, force=False):
    """  remove a command watch
    @Ywatchname@w   = The watch name
    @Yforce@w       = force removal if functions are registered

    this function returns no values"""
    if watchname in self.watchcmds:
      event = self.api('events.gete')(self.watchcmds[watchname]['eventname'])
      plugin = self.watchcmds[watchname]['plugin']
      if event:
        if not event.isempty() and not force:
          self.api('send.msg')(
              'removewatch: watch %s for plugin %s has functions registered' % \
                      (watchname, plugin), secondary=plugin)
          return False
      del self.regexlookup[self.watchcmds[watchname]['regex']]
      del self.watchcmds[watchname]
      self.api('send.msg')('removed watch %s' % watchname,
                           secondary=plugin)
    else:
      self.api('send.msg')('removewatch: watch %s does not exist' % \
                                            watchname)

  # remove all watches related to a plugin
  def api_removeplugin(self, plugin):
    """  remove all watches related to a plugin
    @Yplugin@w   = The plugin

    this function returns no values"""
    self.api('send.msg')('removing watches for plugin %s' % plugin,
                         secondary=plugin)
    tkeys = self.watchcmds.keys()
    for i in tkeys:
      if self.watchcmds[i]['plugin'] == plugin:
        self.api('watch.remove')(i)

  def checkcmd(self, data):
    """
    check input from the client and see if we are watching for it
    """
    tdat = data['fromdata'].strip()
    for i in self.watchcmds:
      cmdre = self.watchcmds[i]['compiled']
      mat = cmdre.match(tdat)
      if mat:
        self.watchcmds[i]['hits'] = self.watchcmds[i]['hits'] + 1
        targs = mat.groupdict()
        targs['cmdname'] = 'cmd_' + i
        targs['data'] = tdat
        self.api('send.msg')('raising %s' % targs['cmdname'])
        tdata = self.api('events.eraise')('watch_' + i, targs)
        if 'changed' in tdata:
          if 'trace' in data:
            data['trace']['changes'].append({'cmd':tdat,
                                             'flag':'modify',
                                             'newcmd':tdata['changed'],
                                             'plugin':self.short_name})
          data['nfromdata'] = tdata['changed']

    if 'nfromdata' in data:
      data['fromdata'] = data['nfromdata']
    return data
