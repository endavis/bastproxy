"""
This plugin is an alias plugin

Two types of aliases:

 * `#bp.alias.add 'oa' 'open all'`
  * This type of alias will just replace the oa with open all

 * `#bp.alias.add 'port (.*)'
          'get {1} $portbag|wear {1}|enter|wear amulet|put {1} portbag'`
  * This alias can be used with numbered positions
"""
import os
import re

from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.persistentdict import PersistentDict

#these 5 are required
NAME = 'Alias'
SNAME = 'alias'
PURPOSE = 'create aliases'
AUTHOR = 'Bast'
VERSION = 2
PRIORITY = 25

REQUIRED = True


class Plugin(BasePlugin):
  """
  a plugin to handle user aliases
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.aliasfile = os.path.join(self.save_directory, 'aliases.txt')
    self._aliases = PersistentDict(self.aliasfile, 'c')

    self.sessionhits = {}

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting.add')('nextnum', 0, int,
                            'the number of the next alias added',
                            readonly=True)

    parser = argp.ArgumentParser(add_help=False,
                                 description='add an alias')
    parser.add_argument('original',
                        help='the input to replace',
                        default='',
                        nargs='?')
    parser.add_argument('replacement',
                        help='the string to replace it with',
                        default='',
                        nargs='?')
    parser.add_argument('-o',
                        "--overwrite",
                        help="overwrite an alias if it already exists",
                        action="store_true")
    parser.add_argument('-d', "--disable",
                        help="disable the alias",
                        action="store_true")
    parser.add_argument('-g',
                        "--group",
                        help="the alias group",
                        default="")
    self.api('commands.add')('add',
                             self.cmd_add,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='remove an alias')
    parser.add_argument('alias',
                        help='the alias to remove',
                        default='',
                        nargs='?')
    self.api('commands.add')('remove',
                             self.cmd_remove,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list aliases')
    parser.add_argument('match',
                        help='list only aliases that have this argument in them',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='toggle enabled flag')
    parser.add_argument('alias',
                        help='the alias to toggle',
                        default='',
                        nargs='?')
    self.api('commands.add')('toggle',
                             self.cmd_toggle,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='toggle all aliases in a group')
    parser.add_argument('group',
                        help='the group to toggle',
                        default='',
                        nargs='?')
    parser.add_argument('-d',
                        "--disable",
                        help="disable the group",
                        action="store_true")
    self.api('commands.add')('groupt',
                             self.cmd_grouptoggle,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='get detail for an alias')
    parser.add_argument('alias',
                        help='the alias to get details for',
                        default='',
                        nargs='?')
    self.api('commands.add')('detail',
                             self.cmd_detail,
                             parser=parser)

    self.api('commands.default')('list')
    self.api('events.register')('io_execute_event', self.checkalias,
                                prio=2)
    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

  def checkalias(self, args): # pylint: disable=too-many-branches
    """
    this function finds aliases in client input
    """
    data = args['fromdata'].strip()

    if not data:
      return args

    for mem in self._aliases.keys():
      if self._aliases[mem]['enabled']:
        datan = data
        matchd = re.match(mem, data)
        if matchd:
          self.api('send.msg')('matched input on %s' % mem)
          tlistn = [data]
          for i in xrange(1, len(matchd.groups()) + 1):
            tlistn.append(matchd.group(i))
          self.api('send.msg')('args: %s' % tlistn)
          try:
            datan = self._aliases[mem]['alias'].format(*tlistn)
          except Exception: # pylint: disable=broad-except
            self.api('send.traceback')('alias %s had an issue' % (mem))
        else:
          cre = re.compile('^%s' % mem)
          datan = cre.sub(self._aliases[mem]['alias'], data)
        if datan != data:
          if 'trace' in args:
            args['trace']['changes'].append({'flag':'Modify',
                                             'data':'changed "%s" to "%s"' % \
                                                (data, datan),
                                             'plugin':self.short_name})
          if not 'hits' in self._aliases[mem]:
            self._aliases[mem]['hits'] = 0
          if not mem in self.sessionhits:
            self.sessionhits[mem] = 0
          self.api('send.msg')('incrementing hits for %s' % mem)
          self._aliases[mem]['hits'] = self._aliases[mem]['hits'] + 1
          self.sessionhits[mem] = self.sessionhits[mem] + 1
          self.api('send.msg')('replacing "%s" with "%s"' % \
                                          (data.strip(), datan.strip()))
          if datan[0:3] == '#bp':
            self.api('send.execute')(datan, showinhistory=False, fromclient=False)
            args['fromdata'] = ''
            args['history'] = False
          else:
            args['history'] = False
            args['fromclient'] = False
            args['fromdata'] = datan

    return args

  def lookup_alias(self, alias):
    """
    lookup an alias by number or name
    """
    nitem = None
    try:
      num = int(alias)
      nitem = None
      for titem in self._aliases.keys():
        if num == self._aliases[titem]['num']:
          nitem = titem
          break

    except ValueError:
      if alias in self._aliases:
        nitem = alias

    return nitem

  def cmd_add(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Add a alias
      @CUsage@w: add @Y<originalstring>@w @M<replacementstring>@w
        @Yoriginalstring@w    = The original string to be replaced
        @Mreplacementstring@w = The new string
    """
    tmsg = []
    if args['original'] and args['replacement']:
      if args['original'] in self._aliases and not args['overwrite']:
        return True, ['Alias: %s already exists.' % args['original']]
      else:
        tmsg.append("@GAdding alias@w : '%s' will be replaced by '%s'" % \
                                      (args['original'], args['replacement']))
        self.addalias(args['original'], args['replacement'],
                      args['disable'], args['group'])
      return True, tmsg
    else:
      return False, ['@RPlease include all arguments@w']

  def cmd_remove(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Remove a alias
      @CUsage@w: rem @Y<originalstring>@w
        @Yoriginalstring@w    = The original string
    """
    tmsg = []
    if args['alias']:
      retval = self.removealias(args['alias'])
      if retval:
        tmsg.append("@GRemoving alias@w : '%s'" % (retval))
      else:
        tmsg.append("@GCould not remove alias@w : '%s'" % (args['alias']))

      return True, tmsg
    else:
      return False, ['@RPlease include an alias to remove@w']

  def cmd_toggle(self, args):
    """
    toggle the enabled flag
    """
    tmsg = []
    if args['alias']:
      retval = self.togglealias(args['alias'])
      if retval:
        if self._aliases[retval]['enabled']:
          tmsg.append("@GEnabled alias@w : '%s'" % (retval))
        else:
          tmsg.append("@GDisabled alias@w : '%s'" % (retval))
      else:
        tmsg.append("@GDoes not exist@w : '%s'" % (args['alias']))
      return True, tmsg

    else:
      return False, ['@RPlease include an alias to toggle@w']

  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Add a alias
      @CUsage@w: add @Y<originalstring>@w @M<replacementstring>@w
        @Yoriginalstring@w    = The original string to be replaced
        @Mreplacementstring@w = The new string
    """
    tmsg = []
    if args['alias']:
      alias = self.lookup_alias(args['alias'])
      if alias:
        if 'hits' not in self._aliases[alias]:
          self._aliases[alias]['hits'] = 0
        if alias not in self.sessionhits:
          self.sessionhits[alias] = 0
        tmsg.append('%-12s : %d' % ('Num', self._aliases[alias]['num']))
        tmsg.append('%-12s : %s' % \
            ('Enabled', 'Y' if self._aliases[alias]['enabled'] else 'N'))
        tmsg.append('%-12s : %d' % ('Total Hits',
                                    self._aliases[alias]['hits']))
        tmsg.append('%-12s : %d' % ('Session Hits', self.sessionhits[alias]))
        tmsg.append('%-12s : %s' % ('Alias', alias))
        tmsg.append('%-12s : %s' % ('Replacement',
                                    self._aliases[alias]['alias']))
        tmsg.append('%-12s : %s' % ('Group', self._aliases[alias]['group']))
      else:
        return True, ['@RAlias does not exits@w : \'%s\'' % (args['alias'])]

      return True, tmsg
    else:
      return False, ['@RPlease include all arguments@w']

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List aliases
      @CUsage@w: list
    """
    tmsg = self.listaliases(args['match'])
    return True, tmsg

  def cmd_grouptoggle(self, args):
    """
    toggle all aliases in a group
    """
    tmsg = []
    togglea = []
    state = not args['disable']
    if args['group']:
      for i in self._aliases:
        if 'group' not in self._aliases[i]:
          self._aliases[i]['group'] = ''

        if self._aliases[i]['group'] == args['group']:
          self._aliases[i]['enabled'] = state
          togglea.append('%s' % self._aliases[i]['num'])

      if togglea:
        tmsg.append('The following aliases were %s: %s' % \
              ('enabled' if state else 'disabled',
               ','.join(togglea)))
      else:
        tmsg.append('No aliases were modified')

      return True, tmsg
    else:
      return False, ['@RPlease include a group to toggle@w']

  def addalias(self, item, alias, disabled, group):
    """
    internally add a alias
    """
    num = self.api('setting.gets')('nextnum')
    self._aliases[item] = {'alias':alias, 'enabled':not disabled,
                           'num':num, 'group':group}
    self._aliases.sync()
    self.api('setting.change')('nextnum', num + 1)

  def removealias(self, item):
    """
    internally remove a alias
    """
    alias = self.lookup_alias(item)
    if alias:
      del self._aliases[alias]
      self._aliases.sync()

    return alias

  def togglealias(self, item):
    """
    toggle an alias
    """
    alias = self.lookup_alias(item)
    if alias:
      self._aliases[alias]['enabled'] = not self._aliases[alias]['enabled']

    return alias

  def listaliases(self, match):
    """
    return a table of strings that list aliases
    """
    tmsg = []
    for alias in sorted(self._aliases.iteritems(),
                        key=lambda (x, y): y['num']):
      item = alias[0]
      if not match or match in item:
        lalias = self.api('colors.stripansi')(self._aliases[item]['alias'])
        if len(lalias) > 30:
          lalias = lalias[:27] + '...'
        tmsg.append("%4s %2s  %-10s %-20s : %s@w" % \
                     (self._aliases[item]['num'],
                      'Y' if self._aliases[item]['enabled'] else 'N',
                      self._aliases[item]['group'],
                      item,
                      lalias))
    if not tmsg:
      tmsg = ['None']
    else:
      tmsg.insert(0, "%4s %2s  %-10s %-20s : %s@w" % ('#', 'E', 'Group',
                                                      'Alias', 'Replacement'))
      tmsg.insert(1, '@B' + '-' * 60 + '@w')

    return tmsg

  def clearaliases(self):
    """
    clear all aliases
    """
    self._aliases.clear()
    self._aliases.sync()

  def reset(self):
    """
    reset the plugin
    """
    BasePlugin.reset(self)
    self.clearaliases()

  def _savestate(self, _=None):
    """
    save states
    """
    self._aliases.sync()
