"""
This plugin handles internal triggers for the proxy

#TODO: add api to register to a trigger that uses events internally
look for triggers defined in this plugin first, then look for triggers otherwise
   beall
   empytyline
   all

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
    self.latest_regex_id = 0

    self.beall_id = self.create_trigger_id('beall', self.plugin_id)
    self.all_id = self.create_trigger_id('all', self.plugin_id)
    self.emptyline_id = self.create_trigger_id('emptyline', self.plugin_id)

    # The dictionary of triggers
    # This will likely get moved into the source plugin
    # key: trigger_id
    self.triggers = {}

    # The dictionary of trigger groups
    # key is group name
    # value is a list of trigger_names
    self.trigger_groups = {}

    # The dictionary of unique regexes
    # This will replace regex_lookup
    # key is regex_id
    # value is a dictionary including regex, a list of triggers, hit count, and the compiled without groups
    self.regexes = {}
    # lookup for regex to regex_id
    self.regex_lookup_to_id = {}

    # The compiled regex
    self.created_regex = {}
    self.created_regex['created_regex'] = ""
    self.created_regex['created_regex_compiled'] = ""

    # new api format
    self.api('libs.api:add')('trigger:add', self._api_trigger_add)
    self.api('libs.api:add')('trigger:remove', self._api_trigger_remove)
    self.api('libs.api:add')('trigger:toggle:enable', self._api_trigger_toggle_enable)
    self.api('libs.api:add')('trigger:toggle:omit', self._api_trigger_toggle_omit)
    self.api('libs.api:add')('trigger:update', self._api_trigger_update)
    self.api('libs.api:add')('trigger:get', self._api_trigger_get)
    self.api('libs.api:add')('trigger:register', self._api_trigger_register)
    self.api('libs.api:add')('trigger:unregister', self._api_trigger_unregister)
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

    self.api('core.triggers:trigger:add')('beall', None, self.plugin_id, enabled=False)
    self.api('core.triggers:trigger:add')('all', None, self.plugin_id, enabled=False)
    self.api('core.triggers:trigger:add')('emptyline', None, self.plugin_id, enabled=False)

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
    created_regex_list = []
    for regex in self.regexes.values():
      if regex['triggers']:
        created_regex_list.append("(?P<%s>%s)" % (regex['regex_id'], regex['regex']))

    if created_regex_list:
      self.created_regex['created_regex'] = "|".join(created_regex_list)
      try:
        self.created_regex['created_regex_compiled'] = re.compile(self.created_regex['created_regex'])
      except re.error:
        self.api('libs.io:send:traceback')('Could not compile created regex')
        print(self.created_regex['created_regex'])
    else:
      self.created_regex['created_regex'] = ""
      self.created_regex['created_regex_compiled'] = ""

  @staticmethod
  def create_trigger_id(name, plugin_id):
    """
    get a unique name for a trigger
    """
    return "t_" + plugin_id + '_' + name

  def create_regex_id(self):
    """
    get an id for a regex
    """
    self.latest_regex_id = self.latest_regex_id + 1
    return 'reg_%s' % self.latest_regex_id

  def _api_trigger_register(self, trigger_name, function, **kwargs):
    """
    register a function to a trigger
    """
    if trigger_name not in self.triggers:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
      trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    return self.api('core.events:register:to:event')(self.triggers[trigger_id]['eventname'],
                                                     function, *kwargs)

  def _api_trigger_unregister(self, trigger_name, function):
    """
    unregister a function from a trigger
    """
    if trigger_name not in self.triggers:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
      trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    return self.api('core.events:unregister:from:event')(self.triggers[trigger_id]['eventname'],
                                                         function)

  def _api_trigger_update(self, trigger_name, trigger_data):
    """
    update a trigger without deleting it
    """
    plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])
    trigger_id = self.create_trigger_id(trigger_name, plugin_id)

    if trigger_id not in self.triggers:
      self.api('libs.io:send:msg')('triggers.update could not find trigger %s (maybe plugin %s)' %
                                   (trigger_name, plugin_id))
      return False

    if 'enabled' in trigger_data:
      trigger_enabled = trigger_data['enabled']
    else:
      trigger_enabled = self.triggers[trigger_id]['enabled']

    for key in trigger_data:
      old_value = self.triggers[trigger_id][key]
      new_value = trigger_data[key]
      if old_value == new_value:
        continue
      self.triggers[trigger_id][key] = new_value
      if key == 'regex':
        orig_regex = new_value
        regex = re.sub(r"\?P\<.*?\>", "", orig_regex)

        old_regex_id = self.triggers[trigger_id]['regex_id']
        new_regex_id = self.find_regex_id(regex)

        self.triggers[trigger_id]['original_regex'] = orig_regex
        try:
          self.triggers[trigger_id]['original_regex_compiled'] = re.compile(orig_regex)
        except Exception:  # pylint: disable=broad-except
          self.api('libs.io:send:traceback')(
              'Could not compile regex for trigger: %s : %s' % \
                  (trigger_name, orig_regex))
          return False

        self.api('libs.io:send:msg')('converted %s to %s' % (orig_regex, regex))

        if trigger_id in self.regexes[old_regex_id]['triggers']:
          self.regexes[old_regex_id]['triggers'].remove(trigger_id)
        if trigger_enabled:
          self.regexes[new_regex_id]['triggers'].append(trigger_id)

        self.rebuild_regexes()

      if key == 'group':
        self.trigger_groups[old_value].remove(trigger_name)
        if self.triggers[trigger_name]['group'] not in self.trigger_groups:
          self.trigger_groups[self.triggers[trigger_name]['group']] = []
        self.trigger_groups[self.triggers[trigger_name]['group']].append(trigger_name)

  def find_regex_id(self, regex):
    """
    look for a regex, if not create one
    """
    regex_id = None
    if regex not in self.regex_lookup_to_id:
      regex_id = self.create_regex_id()
      self.regexes[regex_id] = {}
      self.regexes[regex_id]['regex'] = regex
      self.regexes[regex_id]['regex_id'] = regex_id
      self.regexes[regex_id]['triggers'] = []
      self.regexes[regex_id]['hits'] = 0
      self.regex_lookup_to_id[regex] = regex_id
    else:
      regex_id = self.regex_lookup_to_id[regex]

    return regex_id

  # add a trigger
  def _api_trigger_add(self, trigger_name, regex, plugin_id=None, **kwargs): # pylint: disable=too-many-branches
    """  add a trigger
    @Ytrigger_name@w   = The trigger name
    @Yregex@w    = the regular expression that matches this trigger
    @Yplugin_id@w   = the id for the plugin this comes from, added
          automatically if using the api through BaseClass
    @Ykeyword@w arguments:
      @Yenabled@w  = (optional) whether the trigger is enabled (default: True)
      @Ygroup@w    = (optional) the group the trigger is a member of
      @Yomit@w     = (optional) True to omit the line from the client,
                              False otherwise
      @Yargtypes@w = (optional) a dict of keywords in the regex and their type
      @Ypriority@w = (optional) the priority of the trigger, default is 100
      @Ymatchcolor@w = (optional) match with color
      @Ystopevaluating@w = (optional) True to stop trigger evauluation if this
                              trigger is matched

    this function returns no values"""
    if not plugin_id:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    if not plugin_id:
      print('could not add a plugin_id for trigger name', trigger_name)
      return False

    trigger_id = self.create_trigger_id(trigger_name, plugin_id)

    if trigger_id in self.triggers:
      self.api('libs.io:send:error')(
          'trigger %s already exists in plugin: %s' % \
              (trigger_name, self.triggers[trigger_id]['plugin_id']), secondary=plugin_id)
      return False

    args = kwargs.copy()

    args['regex'] = None
    args['regex_id'] = None
    args['original_regex'] = None

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
    if 'matchcolor' not in args:
      args['matchcolor'] = False
    args['plugin_id'] = plugin_id
    args['hits'] = 0
    args['trigger_id'] = trigger_id
    args['trigger_name'] = trigger_name
    args['eventname'] = 'ev_core.triggers_' + trigger_id

    if regex:
      orig_regex = regex
      regex = re.sub(r"\?P\<.*?\>", "", orig_regex)

      regex_id = self.find_regex_id(regex)
      args['regex'] = regex
      args['regex_id'] = regex_id
      args['original_regex'] = orig_regex

      try:
        args['original_regex_compiled'] = re.compile(args['original_regex'])
      except Exception:  # pylint: disable=broad-except
        self.api('libs.io:send:traceback')(
            'Could not compile regex for trigger: %s : %s' % \
                (trigger_name, args['original_regex']))
        return False

      self.api('libs.io:send:msg')('converted %s to %s' % (args['original_regex'], args['regex']))

      need_rebuild = False
      if args['enabled']:
        need_rebuild = True
        if trigger_id not in self.regexes[regex_id]['triggers']:
          self.regexes[regex_id]['triggers'].append(trigger_id)
        else:
          self.api('libs.io:send:error')(
              'trigger %s (%s) already exists in regex: %s' % \
                      (trigger_name, plugin_id,
                        regex), secondary=plugin_id)

      if need_rebuild:
        self.rebuild_regexes()

    if args['group']:
      if args['group'] not in self.trigger_groups:
        self.trigger_groups[args['group']] = []
      self.trigger_groups[args['group']].append(trigger_id)

    self.triggers[trigger_id] = args

    # go through and rebuild the regexes

    self.api('libs.io:send:msg')(
        'added trigger %s (unique name: %s) for plugin %s' % \
            (trigger_name, trigger_id, plugin_id), secondary=plugin_id)

    return True, args['eventname']

  # remove a trigger
  def _api_trigger_remove(self, trigger_name, force=False, plugin_id=None):
    """  remove a trigger
    @Ytrigger_name@w   = The trigger name
    @Yforce@w         = True to remove it even if other functions
                              are registered
       (default: False)

    this function returns True if the trigger was removed,
                              False if it wasn't"""
    if not plugin_id:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    if not plugin_id:
      self.api('libs.io:send:msg')('deletetrigger: could not find plugin for trigger %s' % \
                        trigger_name)
      return False

    trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    if trigger_id not in self.triggers:
      self.api('libs.io:send:msg')('deletetrigger: trigger %s (maybe plugin %s) does not exist' % \
                        (trigger_name, plugin_id))
      return False

    event = self.api('core.events:get:event')(self.triggers[trigger_id]['eventname'])
    if event:
      if not event.isempty() and not force:
        self.api('libs.io:send:msg')(
            'deletetrigger: trigger %s for plugin %s has functions registered' % (trigger_name, plugin_id),
            secondary=plugin_id)
        return False

    regex = self.regexes[self.triggers[trigger_id]['regex_id']]
    need_rebuild = False
    if trigger_id in regex['triggers']:
      print('removing trigger %s from %s' % (trigger_name, regex['regex_id)']))
      need_rebuild = True
      regex['triggers'].remove(trigger_id)

    if trigger_id in self.triggers:
      del self.triggers[trigger_id]

    self.api('libs.io:send:msg')('removed trigger %s for plugin %s' % (trigger_name, plugin_id),
                                 secondary=plugin_id)

    # go through and rebuild the regexes
    if need_rebuild:
      self.rebuild_regexes()

    return True

  # get a trigger
  def _api_trigger_get(self, trigger_name, plugin_id=None):
    """get a trigger
    @Ytrigger_name@w   = The trigger name
    """
    if not plugin_id:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    if trigger_id in self.triggers:
      return self.triggers[trigger_id]

    return None

  # remove all triggers related to a plugin
  def _api_remove_triggers_for_plugin(self, plugin_id):
    """  remove all triggers related to a plugin
    @Yplugin_id@w   = The plugin id

    this function returns no values"""
    self.api('libs.io:send:msg')('removing triggers for plugin %s' % plugin_id,
                                 secondary=plugin_id)
    for trigger in self.triggers.values():
      if trigger['plugin_id'] == plugin_id:
        self.api('core.triggers:trigger:remove')(trigger['trigger_name'], plugin_id=plugin_id)

  # toggle a trigger
  def _api_trigger_toggle_enable(self, trigger_name, flag, plugin_id=None):
    """  toggle a trigger
    @Ytrigger_name@w = The trigger name
    @Yflag@w        = (optional) True to enable, False otherwise

    this function returns no values"""
    if not plugin_id:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    if trigger_id in self.triggers:
      needs_rebuild = False
      regex = self.regexes[self.triggers[trigger_id]['regex_id']]
      if flag:
        if trigger_id not in regex['triggers']:
          regex['triggers'].append(trigger_id)
          needs_rebuild = True
      else:
        if trigger_id in regex['triggers']:
          regex['triggers'].remove(trigger_id)
          needs_rebuild = True

      if needs_rebuild:
        self.rebuild_regexes()
    else:
      self.api('libs.io:send:msg')('toggletrigger: trigger %s (maybe plugin %s) does not exist' % \
        (trigger_name, plugin_id))

  # toggle the omit flag for a trigger
  def _api_trigger_toggle_omit(self, trigger_name, flag, plugin_id=None):
    """  toggle a trigger
    @Ytrigger_name@w = The trigger name
    @Yflag@w        = (optional) True to omit the line, False otherwise

    this function returns no values"""
    if not plugin_id:
      plugin_id = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=[self.plugin_id])

    trigger_id = self.create_trigger_id(trigger_name, plugin_id)
    if trigger_id in self.triggers:
      self.triggers[trigger_id]['omit'] = flag
    else:
      self.api('libs.io:send:msg')('toggletriggeromit: trigger %s (maybe plugin %s) does not exist' % \
        (trigger_name, plugin_id))

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

    self.raisetrigger(self.beall_id,
                      {'line':data, 'trigger_name':'trigger_all'},
                      args)

    if data == '': # pylint: disable=too-many-nested-blocks
      self.raisetrigger(self.emptyline_id,
                        {'line':'', 'trigger_name':'trigger_emptyline'},
                        args)
    else:
      if self.created_regex['created_regex_compiled']:
        match_data = self.created_regex['created_regex_compiled'].match(data)
      else:
        match_data = None

      if match_data:
        match_groups = {k: v for k, v in match_data.groupdict().items() if v is not None}
      else:
        match_groups = {}

      # build a set of match trigger names
      regex_match_data = match_groups.keys()

      if regex_match_data:
        self.api('libs.io:send:msg')('line %s matched the following regexes %s' % \
                              (data, regex_match_data))
        for regex_id in regex_match_data:
          match = None
          if regex_id not in self.regexes:
            self.api('libs.io:send:msg')('regex_id %s not found in check_trigger' % \
                              regex_id)
            continue

          self.regexes[regex_id]['hits'] = self.regexes[regex_id]['hits'] + 1
          for trigger_id in self.regexes[regex_id]['triggers']:
            if not self.triggers[trigger_id]['enabled']:
              continue
            if self.triggers[trigger_id]['matchcolor']:
              match = self.triggers[trigger_id]['original_regex_compiled'].match(colored_data)
            else:
              match = self.triggers[trigger_id]['original_regex_compiled'].match(data)
            if match:
              group_dict = match.groupdict()
              if 'argtypes' in self.triggers[trigger_id]:
                for arg in self.triggers[trigger_id]['argtypes']:
                  if arg in group_dict:
                    group_dict[arg] = self.triggers[trigger_id]['argtypes'][arg](group_dict[arg])
              group_dict['line'] = data
              group_dict['colorline'] = colored_data
              group_dict['trigger_name'] = self.triggers[trigger_id]['trigger_name']
              group_dict['trigger_id'] = self.triggers[trigger_id]['trigger_id']
              self.triggers[trigger_id]['hits'] = self.triggers[trigger_id]['hits'] + 1
              args = self.raisetrigger(group_dict['trigger_id'], group_dict, args)
              if self.triggers[trigger_id]['stopevaluating']:
                break

      else:
        self.api('libs.io:send:msg')('no triggers matched for %s' % \
                              (data))


    self.raisetrigger(self.all_id, {'line':data, 'triggername':'trigger_all'}, args)
    return args

  def raisetrigger(self, trigger_id, args, origargs):
    """
    raise a trigger event
    """
    event_name = self.triggers[trigger_id]['eventname']
    if trigger_id in self.triggers and self.triggers[trigger_id]['omit']:
      origargs['omit'] = True

    data_returned = self.api('core.events:raise:event')(event_name, args)
    self.api('libs.io:send:msg')('trigger raiseevent returned: %s' % data_returned)
    if data_returned and 'newline' in data_returned:
      self.api('libs.io:send:msg')('changing line from trigger')
      new_data = self.api('core.colors:colorcode:to:ansicode')(data_returned['newline'])
      origargs['trace']['changes'].append({'flag':'Modify',
                                           'data':'trigger "%s" added by plugin %s changed "%s" to "%s"' % \
                                              (trigger_id, self.triggers[trigger_id]['plugin_id'],
                                               origargs['original'], new_data),
                                           'plugin_id':self.plugin_id})
      origargs['original'] = new_data

    if (data_returned and 'omit' in data_returned and data_returned['omit']) or \
       (trigger_id in self.triggers and self.triggers[trigger_id]['omit']):
      plugin_id = self.plugin_id
      if trigger_id in self.triggers:
        plugin_id = self.triggers[plugin_id]['plugin_id']
      origargs['trace']['changes'].append(
          {'flag':'Omit',
           'data':'trigger "%s" added by plugin "%s"' % \
              (trigger_id, plugin_id),
           'plugin_id':self.plugin_id})
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
    trigger_ids = self.triggers.keys()
    trigger_ids.sort()
    match = args['match']

    message.append('%-25s : %-30s %-9s %-5s %s' % ('Name', 'Defined in',
                                                   'Enabled', 'Hits', 'Id'))
    message.append('@B' + '-' * 60 + '@w')
    for trigger_id in trigger_ids:
      trigger = self.triggers[trigger_id]
      if not match or match in trigger_id or trigger['plugin_id'] == match:
        message.append('%-25s : %-30s %-9s %-5s %s' % \
          (trigger['trigger_name'], trigger['plugin_id'], trigger['enabled'],
           trigger['hits'], trigger_id))

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

    regex_hits = sum(regex['hits'] for regex in self.regexes.values() if regex)

    stats['Triggers'] = {}
    stats['Triggers']['showorder'] = ['Total Triggers', 'Enabled Triggers', 'Disabled Triggers',
                                      'Overall Trigger Hits', 'Triggers Memory Usage',
                                      'Total Regexes', 'Total Regex Hits', 'Regexes Memory Usage']
    stats['Triggers']['Total Triggers'] = len(self.triggers)
    stats['Triggers']['Enabled Triggers'] = total_enabled_triggers
    stats['Triggers']['Disabled Triggers'] = total_disabled_triggers
    stats['Triggers']['Overall Trigger Hits'] = overall_hit_count
    stats['Triggers']['Triggers Memory Usage'] = sys.getsizeof(self.triggers)
    stats['Triggers']['Total Regexes'] = len(self.regexes.keys())
    stats['Triggers']['Total Regex Hits'] = regex_hits
    stats['Triggers']['Regex Memory Usage'] = sys.getsizeof(self.regexes)
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
          message.append('%-24s : %s' % ('Name', self.triggers[trigger]['trigger_name']))
          message.append('%-24s : %s' % ('Internal Id', self.triggers[trigger]['trigger_id']))
          message.append('%-24s : %s' % ('Defined in',
                                         self.triggers[trigger]['plugin_id']))
          message.append('%-24s : %s' % ('Enabled',
                                         self.triggers[trigger]['enabled']))
          message.append('%-24s : %s' % ('Regex',
                                         self.triggers[trigger]['original_regex']))
          message.append('%-24s : %s' % ('Regex (w/o Groups)',
                                         self.triggers[trigger]['regex']))
          message.append('%-24s : %s' % ('Regex ID',
                                         self.triggers[trigger]['regex_id']))
          if self.triggers[trigger]['matchcolor']:
            message.append('%-24s : %s' % ('Match Color', 'True'))
          message.append('%-24s : %s' % ('Group',
                                         self.triggers[trigger]['group']))
          if self.triggers[trigger]['argtypes']:
            message.append('%-24s : %s' % ('Argument Types',
                                           self.triggers[trigger]['argtypes']))
          message.append('%-24s : %s' % ('Priority', self.triggers[trigger]['priority']))
          message.append('%-24s : %s' % ('Omit', self.triggers[trigger]['omit']))
          message.append('%-24s : %s' % ('Hits', self.triggers[trigger]['hits']))
          message.append('%-24s : %s' % ('Stop Evaluating', self.triggers[trigger]['stopevaluating']))
          message.extend(event_details)
        else:
          message.append('trigger %s does not exist' % trigger)
    else:
      message.append('Please provide a trigger name')

    return True, message
