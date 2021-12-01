"""
This plugin handles internal triggers for the proxy
"""
from __future__ import print_function
import sys
try:
  import regex as re
except ImportError:
  print("Please install the regex library: pip(2) install regex")
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
    self.regex_lookup = {}
    self.trigger_groups = {}
    self.unique_trigger_lookup = {}

    self.regex = {}
    self.regex['color'] = ""
    self.regex['noncolor'] = ""

    # new api format
    self.api('libs.api:add')('trigger:add', self._api_trigger_add)
    self.api('libs.api:add')('trigger:remove', self._api_trigger_remove)
    self.api('libs.api:add')('trigger:toggle:enable', self._api_trigger_toggle_enable)
    self.api('libs.api:add')('trigger:toggle:omit', self._api_trigger_toggle_omit)
    self.api('libs.api:add')('trigger:update', self._api_trigger_update)
    self.api('libs.api:add')('trigger:get', self._api_trigger_get)
    self.api('libs.api:add')('group:toggle:enable', self._api_group_toggle_enable)
    self.api('libs.api:add')('remove:data:for:plugin', self._api_remove_triggers_for_plugin)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting:add')('enabled', 'True', bool,
                            'enable triggers')
    self.api('core.events:register:to:event')('ev_%s_var_enabled_modified' % self.plugin_id, self.enablechange)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get details of a trigger')
    parser.add_argument('trigger',
                        help='the trigger to detail',
                        default=[],
                        nargs='*')
    self.api('core.commands:command:add')('detail',
                                          self.cmd_detail,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list triggers')
    parser.add_argument('match',
                        help='list only triggers that have this argument in them',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('list',
                                          self.cmd_list,
                                          parser=parser)

    self.api('core.events:register:to:event')('ev_core.plugins_plugin_uninitialized', self.event_plugin_uninitialized)

    self.api('core.events:register:to:event')('ev_libs.net.mud_from_mud_event',
                                              self.check_trigger, prio=1)

  def enablechange(self, args):
    """
    setup the plugin on setting change
    """
    change = args['newvalue']
    if change:
      self.api('core.events:register:to:event')('ev_libs.net.mud_from_mud_event',
                                                self.check_trigger, prio=1)
    else:
      self.api('core.events:unregister:from:event')('ev_libs.net.mud_from_mud_event',
                                                    self.check_trigger)

  def event_plugin_uninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('%s:remove:data:for:plugin' % self.plugin_id)(args['plugin_id'])

  def rebuild_regexes(self):
    """
    rebuild a regex for priority

    will need a colored and a noncolored regex for each priority
    """
    color_regex_list = []
    nocolor_regex_list = []
    for trigger in self.unique_trigger_lookup.values():
      if trigger['enabled']:
        if 'matchcolor' in trigger \
            and trigger['matchcolor']:
          color_regex_list.append("(?P<%s>%s)" % (trigger['unique'], trigger['nonamedgroups']))
        else:
          nocolor_regex_list.append("(?P<%s>%s)" % (trigger['unique'], trigger['nonamedgroups']))

    if color_regex_list:
      try:
        self.regex['color'] = re.compile("|".join(color_regex_list))
      except re.error:
        self.api('libs.io:send:traceback')('Could not compile color regex')
    else:
      self.regex['color'] = ""

    if nocolor_regex_list:
      try:
        self.regex['noncolor'] = re.compile("|".join(nocolor_regex_list))
      except re.error:
        self.api('libs.io:send:traceback')('Could not compile regex')
    else:
      self.regex['nocolor'] = ""

  @staticmethod
  def getuniquename(name):
    """
    get a unique name for a trigger
    """
    return "t_" + name

  def _api_trigger_update(self, trigger_name, trigger_data):
    """
    update a trigger without deleting it
    """
    if trigger_name not in self.triggers:
      self.api('libs.io:send:msg')('triggers.update could not find trigger %s' % trigger_name)
      return False

    for key in trigger_data:
      old_value = self.triggers[trigger_name][key]
      new_value = trigger_data[key]
      self.triggers[trigger_name][key] = new_value
      if key == 'regex':
        try:
          self.triggers[trigger_name]['compiled'] = re.compile(
              self.triggers[trigger_name]['regex'])
        except Exception:  # pylint: disable=broad-except
          self.api('libs.io:send:traceback')(
              'Could not compile regex for trigger: %s : %s' % \
                  (trigger_name, self.triggers[trigger_name]['regex']))
          return False

        self.triggers[trigger_name]['nonamedgroups'] = \
                    re.sub(r"\?P\<.*?\>", "",
                           self.triggers[trigger_name]['regex'])
        self.api('libs.io:send:msg')('converted %s to %s' % \
                                (self.triggers[trigger_name]['regex'],
                                 self.triggers[trigger_name]['nonamedgroups']))

        del self.regex_lookup[old_value]
        self.regex_lookup[self.triggers[trigger_name]['regex']] = trigger_name

        self.rebuild_regexes()

      if key == 'group':
        self.trigger_groups[old_value].remove(trigger_name)
        if self.triggers[trigger_name]['group'] not in self.trigger_groups:
          self.trigger_groups[self.triggers[trigger_name]['group']] = []
        self.trigger_groups[self.triggers[trigger_name]['group']].append(trigger_name)

  # add a trigger
  def _api_trigger_add(self, trigger_name, regex, plugin=None, **kwargs): # pylint: disable=too-many-branches
    """  add a trigger
    @Ytrigger_name@w   = The trigger name
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
      plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    if not plugin:
      print('could not add a trigger for trigger name', trigger_name)
      return False

    unique_trigger_name = self.getuniquename(trigger_name)

    if trigger_name in self.triggers:
      self.api('libs.io:send:error')(
          'trigger %s already exists in plugin: %s' % \
              (trigger_name, self.triggers[trigger_name]['plugin']), secondary=plugin)
      return False

    if regex in self.regex_lookup:
      self.api('libs.io:send:error')(
          'trigger %s tried to add a regex that already existed for %s' % \
              (trigger_name, self.regex_lookup[regex]), secondary=plugin)
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
    args['name'] = trigger_name
    args['unique'] = unique_trigger_name
    args['eventname'] = 'trigger_' + trigger_name

    try:
      args['compiled'] = re.compile(args['regex'])
    except Exception:  # pylint: disable=broad-except
      self.api('libs.io:send:traceback')(
          'Could not compile regex for trigger: %s : %s' % \
              (trigger_name, args['regex']))
      return False

    args['nonamedgroups'] = re.sub(r"\?P\<.*?\>", "", args['regex'])
    self.api('libs.io:send:msg')('converted %s to %s' % (args['regex'], args['nonamedgroups']))

    self.regex_lookup[args['regex']] = trigger_name

    if args['group']:
      if args['group'] not in self.trigger_groups:
        self.trigger_groups[args['group']] = []
      self.trigger_groups[args['group']].append(trigger_name)

    self.triggers[trigger_name] = args
    self.unique_trigger_lookup[args['unique']] = args

    # go through and rebuild the regexes
    self.rebuild_regexes()

    self.api('libs.io:send:msg')(
        'added trigger %s for plugin %s' % \
            (trigger_name, plugin), secondary=plugin)

    return True

  # remove a trigger
  def _api_trigger_remove(self, trigger_name, force=False):
    """  remove a trigger
    @Ytrigger_name@w   = The trigger name
    @Yforce@w         = True to remove it even if other functions
                              are registered
       (default: False)

    this function returns True if the trigger was removed,
                              False if it wasn't"""
    plugin = None
    if trigger_name in self.triggers:
      event = self.api('core.events:get:event')(
          self.triggers[trigger_name]['eventname'])
      plugin = self.triggers[trigger_name]['plugin']
      if event:
        if not event.isempty() and not force:
          self.api('libs.io:send:msg')(
              'deletetrigger: trigger %s has functions registered' % trigger_name,
              secondary=plugin)
          return False
      del self.regex_lookup[self.triggers[trigger_name]['regex']]

      unique_name = self.triggers[trigger_name]['unique']
      if unique_name in self.unique_trigger_lookup:
        del self.unique_trigger_lookup[unique_name]

      del self.triggers[trigger_name]
      self.api('libs.io:send:msg')('removed trigger %s' % trigger_name,
                                   secondary=plugin)

      # go through and rebuild the regexes
      self.rebuild_regexes()

      return True
    else:
      if not plugin:
        plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
      self.api('libs.io:send:msg')('deletetrigger: trigger %s does not exist' % \
                        trigger_name, secondary=plugin)
      return False

  # get a trigger
  def _api_trigger_get(self, trigger_name):
    """get a trigger
    @Ytrigger_name@w   = The trigger name
    """
    if trigger_name in self.triggers:
      return self.triggers[trigger_name]

    return None

  # remove all triggers related to a plugin
  def _api_remove_triggers_for_plugin(self, plugin):
    """  remove all triggers related to a plugin
    @Yplugin@w   = The plugin name

    this function returns no values"""
    self.api('libs.io:send:msg')('removing triggers for plugin %s' % plugin,
                                 secondary=plugin)
    for trigger in self.triggers.values():
      if trigger['plugin'] == plugin:
        self.api('core.triggers:remove:all:triggers:for:plugin')(trigger['name'])

  # toggle a trigger
  def _api_trigger_toggle_enable(self, trigger_name, flag):
    """  toggle a trigger
    @Ytrigger_name@w = The trigger name
    @Yflag@w        = (optional) True to enable, False otherwise

    this function returns no values"""
    if trigger_name in self.triggers:
      self.triggers[trigger_name]['enabled'] = flag
      self.rebuild_regexes()
    else:
      self.api('libs.io:send:msg')('toggletrigger: trigger %s does not exist' % \
        trigger_name)

  # toggle the omit flag for a trigger
  def _api_trigger_toggle_omit(self, trigger_name, flag):
    """  toggle a trigger
    @Ytrigger_name@w = The trigger name
    @Yflag@w        = (optional) True to omit the line, False otherwise

    this function returns no values"""
    if trigger_name in self.triggers:
      self.triggers[trigger_name]['omit'] = flag
    else:
      self.api('libs.io:send:msg')('toggletriggeromit: trigger %s does not exist' % \
        trigger_name)

  # toggle a trigger group
  def _api_group_toggle_enable(self, trigger_group, flag):
    """  toggle a trigger group
    @Ytrigger_group@w = The triggergroup name
    @Yflag@w        = (optional) True to enable, False otherwise

    this function returns no values"""
    self.api('libs.io:send:msg')('toggletriggergroup: %s to %s' % \
                                                (trigger_group, flag))
    if trigger_group in self.trigger_groups:
      for i in self.trigger_groups[trigger_group]:
        self.api('%s:trigger:toggle:enable' % self.plugin_id)(i, flag)

  def check_trigger(self, args): # pylint: disable=too-many-branches
    """
    check a line of text from the mud to see if it matches any triggers
    called whenever the ev_libs.net.mud_from_mud_event is raised
    """
    data = args['noansi']
    colored_data = args['convertansi']

    self.raisetrigger('beall',
                      {'line':data, 'triggername':'all'},
                      args)

    if data == '': # pylint: disable=too-many-nested-blocks
      self.raisetrigger('emptyline',
                        {'line':'', 'triggername':'emptyline'},
                        args)
    else:
      if self.regex['color']:
        color_match_data = self.regex['color'].match(colored_data)
      else:
        color_match_data = None
      if self.regex['noncolor']:
        non_color_match_data = self.regex['noncolor'].match(data)
      else:
        non_color_match_data = None
      if color_match_data:
        color_match_groups = {k: v for k, v in color_match_data.groupdict().items() if v is not None}
      else:
        color_match_groups = {}
      if non_color_match_data:
        non_color_match_groups = {k: v for k, v in non_color_match_data.groupdict().items() \
                                  if v is not None}
      else:
        non_color_match_groups = {}

      # build a set of match trigger names
      trigger_match_data = set(color_match_groups.keys()) | set(non_color_match_groups.keys())

      if trigger_match_data:
        self.api('libs.io:send:msg')('line %s matched the following triggers %s' % \
                              (data, trigger_match_data))
        for trigger in trigger_match_data:
          match = None
          if trigger not in self.unique_trigger_lookup or \
              not self.unique_trigger_lookup[trigger]['enabled']:
            continue
          if trigger in color_match_groups:
            self.api('libs.io:send:msg')('color matched line %s to trigger %s' % (colored_data,
                                                                                  trigger))
            match = self.unique_trigger_lookup[trigger]['compiled'].match(colored_data)
          elif trigger in non_color_match_groups:
            self.api('libs.io:send:msg')('noncolor matched line %s to trigger %s' % (data,
                                                                                     trigger))
            match = self.unique_trigger_lookup[trigger]['compiled'].match(data)
          if match:
            group_dict = match.groupdict()
            if 'argtypes' in self.unique_trigger_lookup[trigger]:
              for arg in self.unique_trigger_lookup[trigger]['argtypes']:
                if arg in group_dict:
                  group_dict[arg] = self.unique_trigger_lookup[trigger]['argtypes'][arg](group_dict[arg])
            group_dict['line'] = data
            group_dict['colorline'] = colored_data
            group_dict['triggername'] = self.unique_trigger_lookup[trigger]['name']
            self.unique_trigger_lookup[trigger]['hits'] = self.unique_trigger_lookup[trigger]['hits'] + 1
            args = self.raisetrigger(group_dict['triggername'], group_dict, args)
            if trigger in self.unique_trigger_lookup:
              if self.unique_trigger_lookup[trigger]['stopevaluating']:
                break

          if len(trigger_match_data) > 1:
            self.api('libs.io:send:error')('line %s matched multiple triggers %s' % \
                                      (data, trigger_match_data))

      else:
        self.api('libs.io:send:msg')('no triggers matched for %s' % \
                              (data))


    self.raisetrigger('all', {'line':data, 'triggername':'all'}, args)
    return args

  def raisetrigger(self, trigger_name, args, origargs):
    """
    raise a trigger event
    """
    try:
      event_name = self.triggers[trigger_name]['eventname']
    except KeyError:
      event_name = 'trigger_' + trigger_name
    if trigger_name in self.triggers and self.triggers[trigger_name]['omit']:
      origargs['omit'] = True

    data_returned = self.api('core.events:raise:event')(event_name, args)
    self.api('libs.io:send:msg')('trigger raiseevent returned: %s' % data_returned)
    if data_returned and 'newline' in data_returned:
      self.api('libs.io:send:msg')('changing line from trigger')
      new_data = self.api('core.colors:colorcode:to:ansicode')(data_returned['newline'])
      origargs['trace']['changes'].append({'flag':'Modify',
                                           'data':'trigger "%s" changed "%s" to "%s"' % \
                                              (trigger_name, origargs['original'], new_data),
                                           'plugin':self.plugin_id})
      origargs['original'] = new_data

    if (data_returned and 'omit' in data_returned and data_returned['omit']) or \
       (trigger_name in self.triggers and self.triggers[trigger_name]['omit']):
      plugin = self.plugin_id
      if trigger_name in self.triggers:
        plugin = self.triggers[trigger_name]['plugin']
      origargs['trace']['changes'].append(
          {'flag':'Omit',
           'data':'by trigger "%s" added by plugin "%s"' % \
              (trigger_name, plugin),
           'plugin':self.plugin_id})
      origargs['original'] = ""
      origargs['omit'] = True

    return origargs

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list triggers and the plugins they are defined in
      @CUsage@w: list
    """
    message = []
    trigger_names = self.triggers.keys()
    trigger_names.sort()
    match = args['match']

    message.append('%-25s : %-13s %-9s %s' % ('Name', 'Defined in',
                                              'Enabled', 'Hits'))
    message.append('@B' + '-' * 60 + '@w')
    for trigger_name in trigger_names:
      trigger = self.triggers[trigger_name]
      if not match or match in trigger_name or trigger['plugin'] == match:
        message.append('%-25s : %-13s %-9s %s' % \
          (trigger['name'], trigger['plugin'], trigger['enabled'], trigger['hits']))

    return True, message

  def get_stats(self):
    """
    return stats for this plugin
    """
    stats = BasePlugin.get_stats(self)

    overall_hit_count = 0
    total_enabled_triggers = 0
    total_disabled_triggers = 0
    for trigger in self.triggers:
      overall_hit_count = overall_hit_count + self.triggers[trigger]['hits']
      if self.triggers[trigger]['enabled']:
        total_enabled_triggers = total_enabled_triggers + 1
      else:
        total_disabled_triggers = total_disabled_triggers + 1

    total_triggers = len(self.triggers)

    stats['Triggers'] = {}
    stats['Triggers']['showorder'] = ['Total', 'Enabled', 'Disabled',
                                      'Overall Hits', 'Memory Usage']
    stats['Triggers']['Total'] = total_triggers
    stats['Triggers']['Enabled'] = total_enabled_triggers
    stats['Triggers']['Disabled'] = total_disabled_triggers
    stats['Triggers']['Overall Hits'] = overall_hit_count
    stats['Triggers']['Memory Usage'] = sys.getsizeof(self.triggers)
    return stats

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      list the details of a trigger
      @CUsage@w: detail
    """
    message = []
    if args['trigger']:
      for trigger in args['trigger']:
        if trigger in self.triggers:
          event_name = self.triggers[trigger]['eventname']
          event_details = self.api('core.events:get:event:detail')(event_name)
          message.append('%-13s : %s' % ('Name', self.triggers[trigger]['name']))
          message.append('%-13s : %s' % ('Defined in',
                                         self.triggers[trigger]['plugin']))
          message.append('%-13s : %s' % ('Regex',
                                         self.triggers[trigger]['regex']))
          message.append('%-13s : %s' % ('No groups',
                                         self.triggers[trigger]['nonamedgroups']))
          message.append('%-13s : %s' % ('Group',
                                         self.triggers[trigger]['group']))
          message.append('%-13s : %s' % ('Omit', self.triggers[trigger]['omit']))
          message.append('%-13s : %s' % ('Hits', self.triggers[trigger]['hits']))
          message.append('%-13s : %s' % ('Enabled',
                                         self.triggers[trigger]['enabled']))
          message.extend(event_details)
        else:
          message.append('trigger %s does not exist' % trigger)
    else:
      message.append('Please provide a trigger name')

    return True, message
