"""
This plugin adds the ability to do user defined actions when text is
seen from the mud

## Example
 * ```#bp.actions.add "test (?P<something>.*)" "gt just got a test $something"```
  * The match can use regular expresssions: see
  [Python Regular Expression HOWTO](https://docs.python.org/2/howto/regex.html)
  * The action can use trigger groups
"""
import re
import argparse
import os
from string import Template

from plugins._baseplugin import BasePlugin
from libs.timing import timeit
from libs.persistentdict import PersistentDict

#these 5 are required
NAME = 'Actions'
SNAME = 'actions'
PURPOSE = 'handle user actions'
AUTHOR = 'Bast'
VERSION = 1

# This keeps the plugin from being autoloaded if set to False
AUTOLOAD = True

class Plugin(BasePlugin):
  """
  a plugin for user actions
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.canreload = True

    self.regexlookup = {}
    self.actiongroups = {}
    self.compiledregex = {}
    self.sessionhits = {}

    self.saveactionsfile = os.path.join(self.savedir, 'actions.txt')
    self.actions = PersistentDict(self.saveactionsfile, 'c')

  def load(self):
    """
    load the plugin
    """
    BasePlugin.load(self)

    self.api('setting.add')('nextnum', 0, int,
                                'the number of the next action added',
                                readonly=True)

    parser = argparse.ArgumentParser(add_help=False,
                                     description='add a action')
    parser.add_argument('regex',
                        help='the regex to match',
                        default='',
                        nargs='?')
    parser.add_argument('action',
                        help='the action to take',
                        default='',
                        nargs='?')
    parser.add_argument('send',
                        help='where to send the action',
                        default='execute',
                        nargs='?',
                        choices=self.api('apichildren')('send'))
    parser.add_argument('-c',
                        "--color",
                        help="match colors (@@colors)",
                        action="store_true")
    parser.add_argument('-d',
                        "--disable",
                        help="disable the action",
                        action="store_true")
    parser.add_argument('-g',
                        "--group",
                        help="the action group",
                        default="")
    parser.add_argument('-o',
                        "--overwrite",
                        help="overwrite an action if it already exists",
                        action="store_true")
    self.api('commands.add')('add',
                                 self.cmd_add,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                                     description='list actions')
    parser.add_argument('match',
                        help='list only actions that have this argument in them',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                                 self.cmd_list,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                                     description='remove an action')
    parser.add_argument('action',
                        help='the action to remove',
                        default='',
                        nargs='?')
    self.api('commands.add')('remove',
                                 self.cmd_remove,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                                     description='toggle enabled flag')
    parser.add_argument('action',
                        help='the action to toggle',
                        default='',
                        nargs='?')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('-t', '--toggle', action='store_const',
                        dest='togact', const='toggle',
                        default='toggle', help='toggle the action')
    action.add_argument('-d', '--disable', action='store_const',
                        dest='togact', const='disable',
                        help='disable the action')
    action.add_argument('-e', '--enable', action='store_const',
                        dest='togact', const='enable',
                        help='enable the action')
    self.api('commands.add')('toggle',
                                 self.cmd_toggle,
                                 parser=parser)


    parser = argparse.ArgumentParser(add_help=False,
                                     description='get detail for an action')
    parser.add_argument('action',
                        help='the action to get details for',
                        default='',
                        nargs='?')
    self.api('commands.add')('detail',
                                 self.cmd_detail,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                                     description='toggle all actions in a group')
    parser.add_argument('group',
                        help='the group to toggle',
                        default='',
                        nargs='?')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('-t', '--toggle', action='store_const',
                        dest='togact', const='toggle',
                        default='toggle', help='toggle the action')
    action.add_argument('-d', '--disable', action='store_const',
                        dest='togact', const='disable',
                        help='disable the action')
    action.add_argument('-e', '--enable', action='store_const',
                        dest='togact', const='enable',
                        help='enable the action')
    self.api('commands.add')('groupt',
                                 self.cmd_grouptoggle,
                                 parser=parser)

    for action in self.actions.values():
      self.register_action(action)

#    self.api('events.register')('plugin_stats', self.getpluginstats)

  def register_action(self, action):
    """
    register an action as a trigger
    """
    if 'triggername' not in action:
      action['triggername'] = "action_%s" % action['num']
    self.api('triggers.add')(action['triggername'],
                    action['regex'])
    self.api('events.register')('trigger_%s' % action['triggername'],
                                    self.action_matched)

  def unregister_action(self, action):
    """
    unregister an action
    """
    self.api('events.unregister')('trigger_%s' % action['triggername'],
                                     self.action_matched)
    self.api('triggers.remove')(action['triggername'])

  def action_matched(self, args):
    """
    do something when an action is matched
    """
    actionnum = int(args['triggername'].split('_')[-1])
    action = self.lookup_action(actionnum)
    if action:
      akey = action['regex']
      if akey not in self.sessionhits:
        self.sessionhits[akey] = 0
      self.sessionhits[akey] = self.sessionhits[akey] + 1
      action['hits'] = action['hits'] + 1
      self.api('send.msg')('matched line: %s to action %s' % (args['line'],
                                                                  akey))
      templ = Template(action['action'])
      newaction = templ.safe_substitute(args)
      sendtype = 'send.' + action['send']
      self.api('send.msg')('sent %s to %s' % (newaction, sendtype))
      self.api(sendtype)(newaction)
    else:
      self.api('send.error')("Bug: could not find action for trigger %s" % \
                              args['triggername'])

  def lookup_action(self, action):
    """
    lookup an action by number or name
    """
    nitem = None
    try:
      num = int(action)
      nitem = None
      for titem in self.actions.keys():
        if num == self.actions[titem]['num']:
          nitem = self.actions[titem]
          break

    except ValueError:
      if action in self.actions:
        nitem = action

    return nitem

  def cmd_add(self, args):
    """
    add user defined actions
    """
    if not args['regex']:
      return False, ['Please include a regex']
    if not args['action']:
      return False, ['Please include an action']

    if not args['overwrite'] and args['regex'] in self.actions:
      return True, ['Action: %s already exists.' % args['regex']]
    else:
      num = 0

      if args['regex'] in self.actions:
        num = self.actions[args['regex']]['num']
      else:
        num = self.api('setting.gets')('nextnum')
        self.api('setting.change')('nextnum', num + 1)

      self.actions[args['regex']] = {
          'num':num,
          'hits':0,
          'regex': args['regex'],
          'action':args['action'],
          'send':args['send'],
          'matchcolor':args['color'],
          'enabled':not args['disable'],
          'group':args['group'],
          'triggername':"action_%s" % num
      }
      self.actions.sync()

      self.register_action(self.actions[args['regex']])

      return True, ['added action %s - regex: %s' % (num, args['regex'])]

    return False, ['You should never see this']

  def cmd_remove(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Remove an action
      @CUsage@w: rem @Y<originalstring>@w
        @Yoriginalstring@w    = The original string
    """
    tmsg = []
    if args['action']:
      retval = self.removeaction(args['action'])
      if retval:
        tmsg.append("@GRemoving action@w : '%s'" % (retval))
      else:
        tmsg.append("@GCould not remove action@w : '%s'" % (args['action']))

      return True, tmsg
    else:
      return False, ['@RPlease include an action to remove@w']

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List actiones
      @CUsage@w: list
    """
    tmsg = self.listactions(args['match'])
    return True, tmsg

  def cmd_toggle(self, args):
    """
    toggle the enabled flag
    """
    tmsg = []

    if args['togact'] == 'disable':
      state = False
    elif args['togact'] == 'enable':
      state = True
    else:
      state = "toggle"
    if args['action']:
      action = self.toggleaction(args['action'], flag=state)
      if action:
        if action['enabled']:
          tmsg.append("@GEnabled action@w : '%s'" % (action['num']))
        else:
          tmsg.append("@GDisabled action@w : '%s'" % (action['num']))
      else:
        tmsg.append("@GDoes not exist@w : '%s'" % (args['action']))
      return True, tmsg

    else:
      return False, ['@RPlease include an action to toggle@w']

  def cmd_grouptoggle(self, args):
    """
    toggle all actions in a group
    """
    tmsg = []
    togglea = []
    if args['togact'] == 'disable':
      state = False
    elif args['togact'] == 'enable':
      state = True
    else:
      state = "toggle"
    if args['group']:
      for i in self.actions:
        if self.actions[i]['group'] == args['group']:
          action = self.toggleaction(self.actions[i]['num'], flag=state)
          togglea.append('%s' % self.actions[i]['num'])

      if togglea:
        tmsg.append('The following actions were %s: %s' % \
              ('enabled' if state else 'disabled',
               ','.join(togglea)))
      else:
        tmsg.append('No actions were modified')

      return True, tmsg
    else:
      return False, ['@RPlease include a group to toggle@w']

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      get details of an action
      @CUsage@w: detail 1
        @Yaction@w    = the action to get details, either the number or regex
    """
    tmsg = []
    if args['action']:
      action = self.lookup_action(args['action'])
      if action:
        if 'hits' not in action:
          action['hits'] = 0
        if action['regex'] not in self.sessionhits:
          self.sessionhits[action['regex']] = 0
        tmsg.append('%-12s : %d' % ('Num', action['num']))
        tmsg.append('%-12s : %s' % \
            ('Enabled', 'Y' if action['enabled'] else 'N'))
        tmsg.append('%-12s : %d' % ('Total Hits',
                                    action['hits']))
        tmsg.append('%-12s : %d' % ('Session Hits',
                                    self.sessionhits[action['regex']]))
        tmsg.append('%-12s : %s' % ('Regex', action['regex']))
        tmsg.append('%-12s : %s' % ('Action', action['action']))
        tmsg.append('%-12s : %s' % ('Group', action['group']))
        tmsg.append('%-12s : %s' % ('Match Color',
                                    action['matchcolor']))
        tmsg.append('%-12s : %s' % ('Trigger Name',
                                    action['triggername']))
      else:
        return True, ['@RAction does not exist@w : \'%s\'' % (args['action'])]

      return True, tmsg
    else:
      return False, ['@RPlease include all arguments@w']

  def listactions(self, match):
    """
    return a table of strings that list actions
    """
    tmsg = []
    for action in sorted(self.actions.keys()):
      item = self.actions[action]
      if not match or match in item:
        regex = self.api('colors.stripansi')(item['regex'])
        if len(regex) > 30:
          regex = regex[:27] + '...'
        action = self.api('colors.stripansi')(item['action'])
        if len(action) > 30:
          action = action[:27] + '...'
        tmsg.append("%4s %2s  %-10s %-32s : %s@w" % \
                     (item['num'],
                      'Y' if item['enabled'] else 'N',
                      item['group'],
                      regex,
                      action))
    if len(tmsg) == 0:
      tmsg = ['None']
    else:
      tmsg.insert(0, "%4s %2s  %-10s %-32s : %s@w" % ('#', 'E', 'Group',
                                                      'Regex', 'Action'))
      tmsg.insert(1, '@B' + '-' * 60 + '@w')

    return tmsg

  def removeaction(self, item):
    """
    internally remove a action
    """
    action = self.lookup_action(item)

    if action and action['regex'] in self.actions:
      self.unregister_action(action)
      del self.actions[action['regex']]
      self.actions.sync()

    return action

  def toggleaction(self, item, flag="toggle"):
    """
    toggle an action
    """
    action = self.lookup_action(item)
    if action:
      if flag == "toggle":
        action['enabled'] = not action['enabled']
      else:
        action['enabled'] = bool(flag)
      if action['enabled']:
        self.register_action(action)
      else:
        self.unregister_action(action)

    return action

  def clearactions(self):
    """
    clear all actiones
    """
    for action in self.actions.values():
      self.unregister_action(action)

    self.actions.clear()
    self.actions.sync()

  def reset(self):
    """
    reset the plugin
    """
    BasePlugin.reset(self)
    self.clearactions()

  def savestate(self):
    """
    save states
    """
    BasePlugin.savestate(self)
    self.actions.sync()
