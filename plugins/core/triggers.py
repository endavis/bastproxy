# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/apihelp.py
#
# File Description: a plugin to handle internal triggers
#
# By: Bast
"""
This plugin handles internal triggers for the proxy
"""
# Standard Library
import sys

# 3rd Party
try:
    import regex as re
except ImportError:
    print('Please install required libraries. regex is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
import libs.argp as argp
from libs.api import API
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'triggers'
SNAME = 'triggers'
PURPOSE = 'handle triggers'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class TriggerItem:
    def __init__(self, owner_id, trigger_name, regex, regex_id, original_regex, enabled=True,
                 group=None, omit=False, priority=100, stopevaluating=False, argtypes=None,
                 matchcolor=False, trigger_id=None, eventname=None,
                 original_regex_compiled=None) -> None:
        """
        initialize the instance
        """
        self.api = API(owner_id=f"{owner_id}:{trigger_name}")
        self.enabled = enabled
        self.owner_id = owner_id
        self.trigger_name = trigger_name
        self.regex = regex
        self.regex_id = regex_id
        self.original_regex = original_regex
        self.original_regex_compiled = original_regex_compiled
        self.group = group
        self.omit = omit
        self.priority = priority
        self.stopevaluating = stopevaluating
        self.argtypes = argtypes
        self.matchcolor = matchcolor
        self.hits = 0
        self.trigger_id = trigger_id
        self.event_name = eventname

    def raisetrigger(self, args):
        """
        raise an event for this trigger

        # Any updates of data should be done to the ToClientRecord in args['ToClientRecord']
        """
        if self.omit:
            args['ToClientRecord'].set_send_to_clients(False, f"Trigger {self.trigger_id}, plugin {self.owner_id}")

        args = self.api('plugins.core.events:raise.event')(self.event_name, args)
        LogRecord(f"raisetrigger - trigger {self.trigger_id} raised event {self.event_name} with args {args} and returned {args['ToClientRecord'].data}",
                  level='debug', sources=[self.owner_id, __name__]).send()

        return args


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
        self.created_regex['created_regex'] = ''
        self.created_regex['created_regex_compiled'] = ''

        # new api format
        self.api('libs.api:add')(self.plugin_id, 'trigger.add', self._api_trigger_add)
        self.api('libs.api:add')(self.plugin_id, 'trigger.remove', self._api_trigger_remove)
        self.api('libs.api:add')(self.plugin_id, 'trigger.toggle.enable', self._api_trigger_toggle_enable)
        self.api('libs.api:add')(self.plugin_id, 'trigger.toggle.omit', self._api_trigger_toggle_omit)
        self.api('libs.api:add')(self.plugin_id, 'trigger.update', self._api_trigger_update)
        self.api('libs.api:add')(self.plugin_id, 'trigger.get', self._api_trigger_get)
        self.api('libs.api:add')(self.plugin_id, 'trigger.register', self._api_trigger_register)
        self.api('libs.api:add')(self.plugin_id, 'trigger.unregister', self._api_trigger_unregister)
        self.api('libs.api:add')(self.plugin_id, 'group.toggle.enable', self._api_group_toggle_enable)
        self.api('libs.api:add')(self.plugin_id, 'remove.data.for.owner', self._api_remove_triggers_for_owner)

        self.api(f"{self.plugin_id}:setting.add")('enabled', 'True', bool,
                                'enable triggers')

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description='get details of a trigger')
        parser.add_argument('trigger',
                            help='the trigger to detail',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command.add')('detail',
                                              self.cmd_detail,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list triggers')
        parser.add_argument('match',
                            help='list only triggers that have this argument in them',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('list',
                                              self.cmd_list,
                                              parser=parser)

        self.api('plugins.core.events:register.to.event')('ev_plugins.core.pluginm_plugin_uninitialized',
                                                          self.evc_plugin_uninitialized)
        self.api('plugins.core.events:register.to.event')('ev_to_client_data_modify',
                                                  self.evc_check_trigger, prio=1)
        self.api('plugins.core.events:register.to.event')(f"ev_{self.plugin_id}_var_enabled_modified", self.evc_enabled_modify)

        self.api('plugins.core.triggers:trigger.add')('beall', None, self.plugin_id, enabled=False)
        self.api('plugins.core.triggers:trigger.add')('all', None, self.plugin_id, enabled=False)
        self.api('plugins.core.triggers:trigger.add')('emptyline', None, self.plugin_id, enabled=False)


    def evc_enabled_modify(self):
        """
        setup the plugin on setting change
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            change = event_record['newvalue']
            if change:
                self.api('plugins.core.events:register.to.event')('ev_libs.net.mud_from_mud_event',
                                                        self.evc_check_trigger, prio=1)
            else:
                self.api('plugins.core.events:unregister.from.event')('ev_libs.net.mud_from_mud_event',
                                                            self.evc_check_trigger)

    def evc_plugin_uninitialized(self):
        """
        a plugin was uninitialized
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            self.api(f'{self.plugin_id}:remove.data.for.owner')(event_record['plugin_id'])

    def rebuild_regexes(self):
        """
        rebuild a regex for priority

        will need a colored and a noncolored regex for each priority
        """
        created_regex_list = []
        for regex in self.regexes.values():
            if regex['triggers']:
                created_regex_list.append(f"(?P<{regex['regex_id']}>{regex['regex']})")

        if created_regex_list:
            self.created_regex['created_regex'] = '|'.join(created_regex_list)
            try:
                self.created_regex['created_regex_compiled'] = re.compile(self.created_regex['created_regex'])
            except re.error:
                LogRecord('Could not compile created regex', level='error', sources=[self.plugin_id], exc_info=True).send()
                print(self.created_regex['created_regex'])
        else:
            self.created_regex['created_regex'] = ''
            self.created_regex['created_regex_compiled'] = ''

    @staticmethod
    def create_trigger_id(name, owner_id):
        """
        get a unique name for a trigger
        """
        return 't_' + owner_id + '_' + name

    def create_regex_id(self):
        """
        get an id for a regex
        """
        self.latest_regex_id = self.latest_regex_id + 1
        return f"reg_{self.latest_regex_id}"

    def _api_trigger_register(self, trigger_name, function, **kwargs):
        """
        register a function to a trigger
        """
        if trigger_name not in self.triggers:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
            trigger_name = self.create_trigger_id(trigger_name, owner_id)
        return self.api('plugins.core.events:register.to.event')(self.triggers[trigger_name].eventname,
                                                         function, *kwargs)

    def _api_trigger_unregister(self, trigger_name, function):
        """
        unregister a function from a trigger
        """
        if trigger_name not in self.triggers:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
            trigger_name = self.create_trigger_id(trigger_name, owner_id)
        return self.api('plugins.core.events:unregister.from.event')(self.triggers[trigger_name].eventname,
                                                             function)

    def _api_trigger_update(self, trigger_name, trigger_data):
        """
        update a trigger without deleting it
        """
        owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
        trigger_id = self.create_trigger_id(trigger_name, owner_id)

        if trigger_id not in self.triggers:
            LogRecord(f"_api_trigger_update - could not find trigger {trigger_name} (maybe {owner_id})",
                      level='error', sources=[self.plugin_id, owner_id]).send()
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
            setattr(self.triggers[trigger_id], key, new_value)
            if key == 'regex':
                orig_regex = new_value
                regex = re.sub(r"\?P\<.*?\>", '', orig_regex)

                old_regex_id = self.triggers[trigger_id].regex_id
                new_regex_id = self.find_regex_id(regex)

                self.triggers[trigger_id].original_regex = orig_regex
                try:
                    self.triggers[trigger_id].original_regex_compiled = re.compile(orig_regex)
                except Exception:  # pylint: disable=broad-except
                    LogRecord(f"Could not compile regex for trigger: {trigger_name} : {orig_regex}",
                              level='error', sources=[self.plugin_id], exc_info=True).send()
                    return False

                LogRecord(f"_api_trigger_update - converted {orig_regex} to {regex}",
                          level='debug', sources=[self.plugin_id]).send()

                if trigger_id in self.regexes[old_regex_id]['triggers']:
                    self.regexes[old_regex_id]['triggers'].remove(trigger_id)
                if trigger_enabled:
                    self.regexes[new_regex_id]['triggers'].append(trigger_id)

                self.rebuild_regexes()

            if key == 'group':
                self.trigger_groups[old_value].remove(trigger_name)
                if self.triggers[trigger_name].group not in self.trigger_groups:
                    self.trigger_groups[self.triggers[trigger_name].group] = []
                self.trigger_groups[self.triggers[trigger_name].group].append(trigger_name)

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
    def _api_trigger_add(self, trigger_name, regex, owner_id=None, **kwargs): # pylint: disable=too-many-branches
        """  add a trigger
        @Ytrigger_name@w   = The trigger name
        @Yregex@w    = the regular expression that matches this trigger
        @Yowner_id@w   = the id for the owner this comes from, added
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
        if not owner_id:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        if not owner_id:
            print('could not add a owner for trigger name', trigger_name)
            return False

        trigger_id = self.create_trigger_id(trigger_name, owner_id)

        if trigger_id in self.triggers:
            LogRecord(f"_api_trigger_add - trigger {trigger_name} already exists in plugin: {self.triggers[trigger_id]['owner_id']}",
                      level='error', sources=[self.plugin_id, owner_id]).send()
            return False

        args = kwargs.copy()

        regex_id = None
        original_regex = None

        args['trigger_id'] = trigger_id
        args['eventname'] = 'ev_core.triggers_' + trigger_id

        if regex:
            original_regex = regex
            regex = re.sub(r"\?P\<.*?\>", '', original_regex)

            regex_id = self.find_regex_id(regex)

            try:
                args['original_regex_compiled'] = re.compile(args['original_regex'])
            except Exception:  # pylint: disable=broad-except
                LogRecord(f"_api_trigger_add - Could not compile regex for trigger: {trigger_name} : {args['original_regex']}",
                          level='error', sources=[self.plugin_id, owner_id], exc_info=True).send()
                return False

            LogRecord(f"_api_trigger_add - converted {args['original_regex']} to {args['regex']}",
                      level='debug', sources=[self.plugin_id, owner_id]).send()

            need_rebuild = False
            if 'enabled' in args and args['enabled']:
                need_rebuild = True
                if trigger_id not in self.regexes[regex_id]['triggers']:
                    self.regexes[regex_id]['triggers'].append(trigger_id)
                else:
                    LogRecord(f"_api_trigger_add - trigger {trigger_name} already exists in regex: {regex}",
                              level='error', sources=[self.plugin_id, owner_id]).send()

            # go through and rebuild the regexes
            if need_rebuild:
                self.rebuild_regexes()

        if 'group' in args and args['group']:
            if args['group'] not in self.trigger_groups:
                self.trigger_groups[args['group']] = []
            self.trigger_groups[args['group']].append(trigger_id)

        self.triggers[trigger_id] = TriggerItem( owner_id, trigger_name, regex, regex_id, original_regex, **args)

        LogRecord(f"_api_trigger_add - added trigger {trigger_name} (unique name: {trigger_id}) for {owner_id}",
                  level='debug', sources=[self.plugin_id, owner_id]).send()

        return True, args['eventname']

    # remove a trigger
    def _api_trigger_remove(self, trigger_name, force=False, owner_id=None):
        """  remove a trigger
        @Ytrigger_name@w   = The trigger name
        @Yforce@w         = True to remove it even if other functions
                                  are registered
           (default: False)

        this function returns True if the trigger was removed,
                                  False if it wasn't"""
        if not owner_id:
            owner_id = self.api('libs.api:get:caller:owner')(ignore_owner_list=[self.plugin_id])

        if not owner_id:
            LogRecord(f"_api_trigger_remove - could not find owner for trigger {trigger_name}",
                      level='error', sources=[self.plugin_id]).send()
            return False

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id not in self.triggers:
            LogRecord(f"_api_trigger_remove - trigger {trigger_name} (maybe {owner_id}) does not exist",
                      level='error', sources=[self.plugin_id, owner_id]).send()
            return False

        event = self.api('plugins.core.events:get.event')(self.triggers[trigger_id].eventname)
        if event:
            if not event.isempty() and not force:
                LogRecord(f"_api_trigger_remove - trigger {trigger_name} for {owner_id} has functions registered",
                          level='error', sources=[self.plugin_id, owner_id]).send()
                return False

        regex = self.regexes[self.triggers[trigger_id].regex_id]
        need_rebuild = False
        if trigger_id in regex['triggers']:
            LogRecord(f"_api_trigger_remove - removing trigger {trigger_name} from {regex['regex_id']}",
                      level='debug', sources=[self.plugin_id, owner_id]).send()
            need_rebuild = True
            regex['triggers'].remove(trigger_id)

        if trigger_id in self.triggers:
            del self.triggers[trigger_id]

        LogRecord(f"_api_trigger_remove - removed trigger {trigger_name} for {owner_id}",
                  level='debug', sources=[self.plugin_id, owner_id]).send()

        # go through and rebuild the regexes
        if need_rebuild:
            self.rebuild_regexes()

        return True

    # get a trigger
    def _api_trigger_get(self, trigger_name, owner_id=None):
        """get a trigger
        @Ytrigger_name@w   = The trigger name
        """
        if not owner_id:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id in self.triggers:
            return self.triggers[trigger_id]

        return None

    # remove all triggers related to a plugin
    def _api_remove_triggers_for_owner(self, owner_id):
        """  remove all triggers related to a owner
        @Yowner_id@w   = The owner id

        this function returns no values"""
        LogRecord(f"_api_remove_triggers_for_owner - removing triggers for {owner_id}",
                  level='debug', sources=[self.plugin_id, owner_id]).send()
        for trigger in self.triggers.values():
            if trigger.owner_id == owner_id:
                self.api('plugins.core.triggers:trigger.remove')(trigger['trigger_name'], owner_id=owner_id)

    # toggle a trigger
    def _api_trigger_toggle_enable(self, trigger_name, flag, owner_id=None):
        """  toggle a trigger
        @Ytrigger_name@w = The trigger name
        @Yflag@w        = (optional) True to enable, False otherwise

        this function returns no values"""
        if not owner_id:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
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
            LogRecord(f"toggletrigger - trigger {trigger_name} (maybe {owner_id}) does not exist",
                      level='error', sources=[self.plugin_id, owner_id]).send()

    # toggle the omit flag for a trigger
    def _api_trigger_toggle_omit(self, trigger_name, flag, owner_id=None):
        """  toggle a trigger
        @Ytrigger_name@w = The trigger name
        @Yflag@w        = (optional) True to omit the line, False otherwise

        this function returns no values"""
        if not owner_id:
            owner_id = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        trigger_id = self.create_trigger_id(trigger_name, owner_id)
        if trigger_id in self.triggers:
            self.triggers[trigger_id].omit = flag
        else:
            LogRecord(f"toggletriggeromit - trigger {trigger_name} (maybe {owner_id}) does not exist",
                      level='error', sources=[self.plugin_id, owner_id]).send()

    # toggle a trigger group
    def _api_group_toggle_enable(self, trigger_group, flag):
        """  toggle a trigger group
        @Ytrigger_group@w = The triggergroup name
        @Yflag@w        = (optional) True to enable, False otherwise

        this function returns no values"""
        LogRecord(f"toggletriggergroup - toggling trigger group {trigger_group} to {flag}",
                  level='debug', sources=[self.plugin_id]).send()
        if trigger_group in self.trigger_groups:
            for i in self.trigger_groups[trigger_group]:
                self.api(f"{self.plugin_id}:trigger.toggle.enable")(i, flag)

    def evc_check_trigger(self): # pylint: disable=too-many-branches
        """
        check a line of text from the mud to see if it matches any triggers
        """
        if not (event_record := self.api('plugins.core.events:get.current.event.record')()):
            return

        toclientrecord = event_record['ToClientRecord']

        # don't check internal data
        if toclientrecord.internal:
            return

        data = toclientrecord.noansi
        colored_data = toclientrecord.color

        self.triggers[self.beall_id].raisetrigger({'line':data, 'trigger_name':self.triggers[self.beall_id].trigger_name}, event_record)


        if data == '': # pylint: disable=too-many-nested-blocks
            self.triggers[self.emptyline_id].raisetrigger({'line':data, 'trigger_name':self.triggers[self.emptyline_id].trigger_name}, event_record)
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
                LogRecord(f"evc_check_trigger - line {data} matched the following regexes {regex_match_data}",
                          level='debug', sources=[self.plugin_id]).send()
                for regex_id in regex_match_data:
                    match = None
                    if regex_id not in self.regexes:
                        LogRecord(f"evc_check_trigger - regex_id {regex_id} not found in evc_check_trigger",
                                  level='error', sources=[self.plugin_id]).send()
                        continue

                    self.regexes[regex_id]['hits'] = self.regexes[regex_id]['hits'] + 1
                    for trigger_id in self.regexes[regex_id]['triggers']:
                        if not self.triggers[trigger_id].enabled:
                            continue
                        if self.triggers[trigger_id].matchcolor:
                            match = self.triggers[trigger_id].original_regex_compiled.match(colored_data)
                        else:
                            match = self.triggers[trigger_id].original_regex_compiled.match(data)
                        if match:
                            group_dict = match.groupdict()
                            if self.triggers[trigger_id].argtypes:
                                for arg in self.triggers[trigger_id].argtypes:
                                    if arg in group_dict:
                                        group_dict[arg] = self.triggers[trigger_id].argtypes[arg](group_dict[arg])
                            group_dict['line'] = data
                            group_dict['colorline'] = colored_data
                            group_dict['trigger_name'] = self.triggers[trigger_id]['trigger_name']
                            group_dict['trigger_id'] = self.triggers[trigger_id]['trigger_id']
                            args = self.triggers[trigger_id].raiseevent(group_dict, event_record)
                            if self.triggers[trigger_id].stopevaluating:
                                break

            else:
                LogRecord(f"evc_check_trigger - line {data} did not match any regexes",
                          level='debug', sources=[self.plugin_id]).send()

        self.raisetrigger(self.all_id, {'line':data, 'trigger_name':self.triggers[self.all_id]['trigger_name']}, event_record)

    def raisetrigger(self, trigger_id, args, origargs):
        """
        raise a trigger event
        """
        event_name = self.triggers[trigger_id].eventname
        if trigger_id in self.triggers and self.triggers[trigger_id]['omit']:
            origargs['omit'] = True

        data_returned = self.api('plugins.core.events:raise.event')(event_name, args)
        LogRecord(f"raisetrigger - trigger {trigger_id} raised event {event_name} with args {args} and returned {data_returned}",
                  level='debug', sources=[self.plugin_id, self.triggers[trigger_id]['owner_id']]).send()
        if data_returned and 'newline' in data_returned:
            LogRecord(f"raisetrigger - trigger {trigger_id} returned a modified line {data_returned['newline']}",
                      level='debug', sources=[self.plugin_id, self.triggers[trigger_id]['owner_id']]).send()
            new_data = self.api('plugins.core.colors:colorcode.to.ansicode')(data_returned['newline'])
            origargs['trace']['changes'].append({'flag':'Modify',
                                                 'info':f"trigger '{trigger_id}' added by plugin {self.triggers[trigger_id]['owner_id']}",
                                                 'original_data':origargs['original'],
                                                 'new_data':new_data,
                                                 'owner_id':self.plugin_id})
            origargs['original'] = new_data

        if (data_returned and 'omit' in data_returned and data_returned['omit']) or \
           (trigger_id in self.triggers and self.triggers[trigger_id]['omit']):
            owner_id = self.plugin_id
            if trigger_id in self.triggers:
                owner_id = self.triggers[owner_id]['owner_id']
            origargs['trace']['changes'].append(
                {'flag':'Omit',
                 'data':f"trigger '{trigger_id}' added by '{owner_id}'",
                 'owner_id':self.plugin_id})
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
        trigger_ids = sorted(trigger_ids)
        match = args['match']

        template = '%-25s : %-30s %-9s %-5s %s'

        message.append(template % ('Name', 'Defined in',
                                                       'Enabled', 'Hits', 'Id'))
        message.append('@B' + '-' * 60 + '@w')
        for trigger_id in trigger_ids:
            trigger = self.triggers[trigger_id]
            if not match or match in trigger_id or trigger['owner_id'] == match:
                message.append(template % \
                  (trigger['trigger_name'], trigger['owner_id'], trigger['enabled'],
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
        stats['Triggers']['Regexes Memory Usage'] = sys.getsizeof(self.regexes)
        return stats

    def cmd_detail(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the details of a trigger
          @CUsage@w: detail
        """
        message = []
        columnwidth = 24

        if args['trigger']:
            for trigger in args['trigger']:
                if trigger in self.triggers:
                    event_name = self.triggers[trigger].eventname
                    event_details = self.api('plugins.core.events:get.event.detail')(event_name)
                    message.append(f"{'Name':<{columnwidth}} : {self.triggers[trigger]['trigger_name']}")
                    message.append(f"{'Internal Id':<{columnwidth}} : {self.triggers[trigger]['trigger_id']}")
                    message.append(f"{'Defined in':<{columnwidth}} : {self.triggers[trigger]['owner_id']}")
                    message.append(f"{'Enabled':<{columnwidth}} : {self.triggers[trigger]['enabled']}")
                    message.append(f"{'Regex':<{columnwidth}} : {self.triggers[trigger]['original_regex']}")
                    message.append(f"{'Regex (w/o Groups)':<{columnwidth}} : {self.triggers[trigger]['regex']}")
                    message.append(f"{'Regex ID':<{columnwidth}} : {self.triggers[trigger]['regex_id']}")
                    message.append(f"{'Match Color':<{columnwidth}} : {self.triggers[trigger]['matchcolor']}")
                    message.append(f"{'Group':<{columnwidth}} : {self.triggers[trigger]['group']}")
                    if self.triggers[trigger]['argtypes']:
                        message.append(f"{'Argument Types':<{columnwidth}} : {self.triggers[trigger]['argtypes']}")
                    message.append(f"{'Priority':<{columnwidth}} : {self.triggers[trigger]['priority']}")
                    message.append(f"{'Omit':<{columnwidth}} : {self.triggers[trigger]['omit']}")
                    message.append(f"{'Hits':<{columnwidth}} : {self.triggers[trigger]['hits']}")
                    message.append(f"{'Stop Evaluating':<{columnwidth}} : {self.triggers[trigger]['stopevaluating']}")
                    message.extend(event_details)
                else:
                    message.append(f"trigger {trigger} does not exist")
        else:
            message.append('Please provide a trigger name')

        return True, message
