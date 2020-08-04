"""
This plugin handles internal triggers for the proxy
"""
from __future__ import print_function
import sys
try:
  import regex as re
except ImportError:
  print("Please install the regex library: pip install regex")
  sys.exit(1)

import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'triggers'
SNAME = 'triggers'
PURPOSE = 'handle triggers'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

# This keeps the plugin from being autoloaded if set to False
REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to handle internal triggers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.triggers = {}
    self.regexlookup = {}
    self.triggergroups = {}
    self.uniquelookup = {}

    self.regex = {}
    self.regex['color'] = ""
    self.regex['noncolor'] = ""

    self.api('api.add')('add', self.api_addtrigger)
    self.api('api.add')('remove', self.api_remove)
    self.api('api.add')('toggle', self.api_toggle)
    self.api('api.add')('gett', self.api_gett)
    self.api('api.add')('togglegroup', self.api_togglegroup)
    self.api('api.add')('toggleomit', self.api_toggleomit)
    self.api('api.add')('removeplugin', self.api_removeplugin)
    self.api('api.add')('update', self.api_update)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting.add')('enabled', 'True', bool,
                            'enable triggers')
    self.api('events.register')('var_%s_echo' % self.short_name, self.enablechange)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details of a trigger')
    parser.add_argument('trigger',
                        help='the trigger to detail',
                        default=[],
                        nargs='*')
    self.api('commands.add')('detail',
                             self.cmd_detail,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list triggers')
    parser.add_argument('match',
                        help='list only triggers that have this argument in them',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    self.api('events.register')('plugin_unloaded', self.pluginunloaded)

    self.api('events.register')('from_mud_event',
                                self.checktrigger, prio=1)

  def enablechange(self, args):
    """
    setup the plugin on setting change
    """
    change = args['newvalue']
    if change:
      self.api('events.register')('from_mud_event',
                                  self.checktrigger, prio=1)
    else:
      self.api('events.unregister')('from_mud_event',
                                    self.checktrigger)

  def pluginunloaded(self, args):
    """
    a plugin was unloaded
    """
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  def rebuildregexes(self):
    """
    rebuild a regex for priority

    will need a colored and a noncolored regex for each priority
    """
    colorres = []
    noncolorres = []
    for trig in self.uniquelookup.values():
      if trig['enabled']:
        if 'matchcolor' in trig \
            and trig['matchcolor']:
          colorres.append("(?P<%s>%s)" % (trig['unique'], trig['nonamedgroups']))
        else:
          noncolorres.append("(?P<%s>%s)" % (trig['unique'], trig['nonamedgroups']))

    try:
      self.regex['color'] = re.compile("|".join(colorres))
    except re.error:
      self.api('send.traceback')('Could not compile color regex')

    try:
      # print("|".join(noncolorres))
      self.regex['noncolor'] = re.compile("|".join(noncolorres))
      # print(self.regex['noncolor'])
    except re.error:
      self.api('send.traceback')('Could not compile regex')

  @staticmethod
  def getuniquename(name):
    """
    get a unique name for a trigger
    """
    return "t_" + name

  def api_update(self, triggername, trigger):
    """
    update a trigger without deleting it
    """
    if triggername not in self.triggers:
      self.api('send.msg')('triggers.update could not find triggger %s' % trigger)
      return False

    for i in trigger:
      oldval = self.triggers[triggername][i]
      newval = trigger[i]
      self.triggers[triggername][i] = newval
      if i == 'regex':
        try:
          self.triggers[triggername]['compiled'] = re.compile(
              self.triggers[triggername]['regex'])
        except Exception:  # pylint: disable=broad-except
          self.api('send.traceback')(
              'Could not compile regex for trigger: %s : %s' % \
                  (triggername, self.triggers[triggername]['regex']))
          return False

        self.triggers[triggername]['nonamedgroups'] = \
                    re.sub(r"\?P\<.*?\>", "",
                           self.triggers[triggername]['regex'])
        self.api('send.msg')('converted %s to %s' % \
                                (self.triggers[triggername]['regex'],
                                 self.triggers[triggername]['nonamedgroups']))

        del self.regexlookup[oldval]
        self.regexlookup[self.triggers[triggername]['regex']] = triggername

        self.rebuildregexes()

      if i == 'group':
        self.triggergroups[oldval].remove(triggername)
        if self.triggers[triggername]['group'] not in self.triggergroups:
          self.triggergroups[self.triggers[triggername]['group']] = []
        self.triggergroups[self.triggers[triggername]['group']].append(triggername)

  # add a trigger
  def api_addtrigger(self, triggername, regex, plugin=None, **kwargs): # pylint: disable=too-many-branches
    """  add a trigger
    @Ytriggername@w   = The trigger name
    @Yregex@w    = the regular expression that matches this trigger
    @Yplugin@w   = the plugin this comes from, added
          automatically if using the api through BaseClass
    @Ykeyword@w arguments:
      @Yenabled@w  = (optional) whether the trigger is enabled (default: True)
      @Ygroup@w    = (optional) the group the trigger is a member of
      @Yomit@w     = (optional) True to omit the line from the client,
                              False otherwise
      @Yargtypes@w = (optional) a dict of keywords in the regex and their type
      @Ypriority@w = (optional) the priority of the trigger, default is 100
      @Ystopevaluating@w = (optional) True to stop trigger evauluation if this
                              trigger is matched

    this function returns no values"""
    if not plugin:
      plugin = self.api('api.callerplugin')(skipplugin=[self.short_name])

    if not plugin:
      print('could not add a trigger for triggername', triggername)
      return False

    uniquetriggername = self.getuniquename(triggername)

    if triggername in self.triggers:
      self.api('send.error')(
          'trigger %s already exists in plugin: %s' % \
              (triggername, self.triggers[triggername]['plugin']), secondary=plugin)
      return False

    if regex in self.regexlookup:
      self.api('send.error')(
          'trigger %s tried to add a regex that already existed for %s' % \
              (triggername, self.regexlookup[regex]), secondary=plugin)
      return False
    args = kwargs.copy()
    args['regex'] = regex
    if 'enabled' not in args:
      args['enabled'] = True
    if 'group' not in args:
      args['group'] = None
    if 'omit' not in args:
      args['omit'] = False
    if 'priority' not in args:
      args['priority'] = 100
    if 'stopevaluating' not in args:
      args['stopevaluating'] = False
    if 'argtypes' not in args:
      args['argtypes'] = {}
    args['plugin'] = plugin
    args['hits'] = 0
    args['name'] = triggername
    args['unique'] = uniquetriggername
    args['eventname'] = 'trigger_' + triggername

    try:
      args['compiled'] = re.compile(args['regex'])
    except Exception:  # pylint: disable=broad-except
      self.api('send.traceback')(
          'Could not compile regex for trigger: %s : %s' % \
              (triggername, args['regex']))
      return False

    args['nonamedgroups'] = re.sub(r"\?P\<.*?\>", "", args['regex'])
    self.api('send.msg')('converted %s to %s' % (args['regex'], args['nonamedgroups']))

    self.regexlookup[args['regex']] = triggername

    if args['group']:
      if args['group'] not in self.triggergroups:
        self.triggergroups[args['group']] = []
      self.triggergroups[args['group']].append(triggername)

    self.triggers[triggername] = args
    self.uniquelookup[args['unique']] = args

    # go through and rebuild the regexes
    self.rebuildregexes()

    self.api('send.msg')(
        'added trigger %s for plugin %s' % \
            (triggername, plugin), secondary=plugin)

    return True

  # remove a trigger
  def api_remove(self, triggername, force=False):
    """  remove a trigger
    @Ytriggername@w   = The trigger name
    @Yforce@w         = True to remove it even if other functions
                              are registered
       (default: False)

    this function returns True if the trigger was removed,
                              False if it wasn't"""
    plugin = None
    if triggername in self.triggers:
      event = self.api('events.gete')(
          self.triggers[triggername]['eventname'])
      plugin = self.triggers[triggername]['plugin']
      if event:
        if not event.isempty() and not force:
          self.api('send.msg')(
              'deletetrigger: trigger %s has functions registered' % triggername,
              secondary=plugin)
          return False
      plugin = self.triggers[triggername]['plugin']
      del self.regexlookup[self.triggers[triggername]['regex']]

      uniquename = self.triggers[triggername]['unique']
      if uniquename in self.uniquelookup:
        del self.uniquelookup[uniquename]

      del self.triggers[triggername]
      self.api('send.msg')('removed trigger %s' % triggername,
                           secondary=plugin)

      # go through and rebuild the regexes
      self.rebuildregexes()

      return True
    else:
      if not plugin:
        plugin = self.api('api.callerplugin')(skipplugin=[self.short_name])
      self.api('send.msg')('deletetrigger: trigger %s does not exist' % \
                        triggername, secondary=plugin)
      return False

  # get a trigger
  def api_gett(self, triggername):
    """get a trigger
    @Ytriggername@w   = The trigger name
    """
    if triggername in self.triggers:
      return self.triggers[triggername]

    return None

  # remove all triggers related to a plugin
  def api_removeplugin(self, plugin):
    """  remove all triggers related to a plugin
    @Yplugin@w   = The plugin name

    this function returns no values"""
    self.api('send.msg')('removing triggers for plugin %s' % plugin,
                         secondary=plugin)
    for trig in self.triggers.values():
      if trig['plugin'] == plugin:
        self.api('triggers.remove')(trig['name'])

  # toggle a trigger
  def api_toggle(self, triggername, flag):
    """  toggle a trigger
    @Ytriggername@w = The trigger name
    @Yflag@w        = (optional) True to enable, False otherwise

    this function returns no values"""
    if triggername in self.triggers:
      self.triggers[triggername]['enabled'] = flag
      self.rebuildregexes()
    else:
      self.api('send.msg')('toggletrigger: trigger %s does not exist' % \
        triggername)

  # toggle the omit flag for a trigger
  def api_toggleomit(self, triggername, flag):
    """  toggle a trigger
    @Ytriggername@w = The trigger name
    @Yflag@w        = (optional) True to omit the line, False otherwise

    this function returns no values"""
    if triggername in self.triggers:
      self.triggers[triggername]['omit'] = flag
    else:
      self.api('send.msg')('toggletriggeromit: trigger %s does not exist' % \
        triggername)

  # toggle a trigger group
  def api_togglegroup(self, triggroup, flag):
    """  toggle a trigger group
    @Ytriggername@w = The triggergroup name
    @Yflag@w        = (optional) True to enable, False otherwise

    this function returns no values"""
    self.api('send.msg')('toggletriggergroup: %s to %s' % \
                                                (triggroup, flag))
    if triggroup in self.triggergroups:
      for i in self.triggergroups[triggroup]:
        self.api('triggers.toggle')(i, flag)

  def checktrigger(self, args): # pylint: disable=too-many-branches
    """
    check a line of text from the mud to see if it matches any triggers
    called whenever the from_mud_event is raised
    """
    data = args['noansi']
    colordata = args['convertansi']

    self.raisetrigger('beall',
                      {'line':data, 'triggername':'all'},
                      args)

    if data == '': # pylint: disable=too-many-nested-blocks
      self.raisetrigger('emptyline',
                        {'line':'', 'triggername':'emptyline'},
                        args)
    else:
      if self.regex['color']:
        colormatch = self.regex['color'].match(colordata)
      else:
        colormatch = None
      if self.regex['noncolor']:
        noncolormatch = self.regex['noncolor'].match(data)
      else:
        noncolormatch = None
      if colormatch:
        colormatchg = {k: v for k, v in colormatch.groupdict().items() if v is not None}
      else:
        colormatchg = {}
      if noncolormatch:
        noncolormatchg = {k: v for k, v in noncolormatch.groupdict().items() \
                                  if v is not None}
      else:
        noncolormatchg = {}

      # build a set of match trigger names
      trigsmatch = set(colormatchg.keys()) | set(noncolormatchg.keys())

      if trigsmatch:
        self.api('send.msg')('line %s matched the following triggers %s' % \
                              (data, trigsmatch))
        for trig in trigsmatch:
          match = None
          if trig not in self.uniquelookup or \
              not self.uniquelookup[trig]['enabled']:
            continue
          if trig in colormatchg:
            self.api('send.msg')('color matched line %s to trigger %s' % (colordata,
                                                                          trig))
            match = self.uniquelookup[trig]['compiled'].match(colordata)
          elif trig in noncolormatchg:
            self.api('send.msg')('noncolor matched line %s to trigger %s' % (data,
                                                                            trig))
            match = self.uniquelookup[trig]['compiled'].match(data)
          if match:
            targs = match.groupdict()
            if 'argtypes' in self.uniquelookup[trig]:
              for arg in self.uniquelookup[trig]['argtypes']:
                if arg in targs:
                  targs[arg] = self.uniquelookup[trig]['argtypes'][arg](targs[arg])
            targs['line'] = data
            targs['colorline'] = colordata
            targs['triggername'] = self.uniquelookup[trig]['name']
            self.uniquelookup[trig]['hits'] = self.uniquelookup[trig]['hits'] + 1
            args = self.raisetrigger(targs['triggername'], targs, args)
            if trig in self.uniquelookup:
              if self.uniquelookup[trig]['stopevaluating']:
                break

          if len(trigsmatch) > 1:
            self.api('send.error')('line %s matched multiple triggers %s' % \
                                      (data, trigsmatch))

      else:
        self.api('send.msg')('no triggers matched for %s' % \
                              (data))


    self.raisetrigger('all', {'line':data, 'triggername':'all'}, args)
    return args

  def raisetrigger(self, triggername, args, origargs):
    """
    raise a trigger event
    """
    try:
      eventname = self.triggers[triggername]['eventname']
    except KeyError:
      eventname = 'trigger_' + triggername
    if triggername in self.triggers and self.triggers[triggername]['omit']:
      origargs['omit'] = True

    tdat = self.api('events.eraise')(eventname, args)
    self.api('send.msg')('trigger raiseevent returned: %s' % tdat)
    if tdat and 'newline' in tdat:
      self.api('send.msg')('changing line from trigger')
      ndata = self.api('colors.convertcolors')(tdat['newline'])
      origargs['trace']['changes'].append({'flag':'Modify',
                                           'data':'trigger "%s" changed "%s" to "%s"' % \
                                              (triggername, origargs['original'], ndata),
                                           'plugin':self.short_name})
      origargs['original'] = ndata

    if (tdat and 'omit' in tdat and tdat['omit']) or \
       (triggername in self.triggers and self.triggers[triggername]['omit']):
      plugin = self.short_name
      if triggername in self.triggers:
        plugin = self.triggers[triggername]['plugin']
      origargs['trace']['changes'].append(
          {'flag':'Omit',
           'data':'by trigger "%s" added by plugin "%s"' % \
              (triggername, plugin),
           'plugin':self.short_name,})
      origargs['original'] = ""
      origargs['omit'] = True

    return origargs

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list triggers and the plugins they are defined in
      @CUsage@w: list
    """
    tmsg = []
    tkeys = self.triggers.keys()
    tkeys.sort()
    match = args['match']

    tmsg.append('%-25s : %-13s %-9s %s' % ('Name', 'Defined in',
                                           'Enabled', 'Hits'))
    tmsg.append('@B' + '-' * 60 + '@w')
    for i in tkeys:
      trigger = self.triggers[i]
      if not match or match in i or trigger['plugin'] == match:
        tmsg.append('%-25s : %-13s %-9s %s' % \
          (trigger['name'], trigger['plugin'], trigger['enabled'], trigger['hits']))

    return True, tmsg

  def get_stats(self):
    """
    return stats for this plugin
    """
    stats = BasePlugin.get_stats(self)

    totalhits = 0
    totalenabled = 0
    totaldisabled = 0
    for trigger in self.triggers:
      totalhits = totalhits + self.triggers[trigger]['hits']
      if self.triggers[trigger]['enabled']:
        totalenabled = totalenabled + 1
      else:
        totaldisabled = totaldisabled + 1

    totaltriggers = len(self.triggers)

    stats['Triggers'] = {}
    stats['Triggers']['showorder'] = ['Total', 'Enabled', 'Disabled',
                                      'Total Hits', 'Memory Usage']
    stats['Triggers']['Total'] = totaltriggers
    stats['Triggers']['Enabled'] = totalenabled
    stats['Triggers']['Disabled'] = totaldisabled
    stats['Triggers']['Total Hits'] = totalhits
    stats['Triggers']['Memory Usage'] = sys.getsizeof(self.triggers)
    return stats

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list the details of a trigger
      @CUsage@w: detail
    """
    tmsg = []
    if args['trigger']:
      for trigger in args['trigger']:
        if trigger in self.triggers:
          eventname = self.triggers[trigger]['eventname']
          eventstuff = self.api('events.detail')(eventname)
          tmsg.append('%-13s : %s' % ('Name', self.triggers[trigger]['name']))
          tmsg.append('%-13s : %s' % ('Defined in',
                                      self.triggers[trigger]['plugin']))
          tmsg.append('%-13s : %s' % ('Regex',
                                      self.triggers[trigger]['regex']))
          tmsg.append('%-13s : %s' % ('No groups',
                                      self.triggers[trigger]['nonamedgroups']))
          tmsg.append('%-13s : %s' % ('Group',
                                      self.triggers[trigger]['group']))
          tmsg.append('%-13s : %s' % ('Omit', self.triggers[trigger]['omit']))
          tmsg.append('%-13s : %s' % ('Hits', self.triggers[trigger]['hits']))
          tmsg.append('%-13s : %s' % ('Enabled',
                                      self.triggers[trigger]['enabled']))
          tmsg.extend(eventstuff)
        else:
          tmsg.append('trigger %s does not exist' % trigger)
    else:
      tmsg.append('Please provide a trigger name')

    return True, tmsg
