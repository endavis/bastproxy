"""
$Id$

This plugin is an alias plugin

Two types of aliases:
#bp.alias.add 'oa' 'open all'
  This type of alias will just replace the oa with open all

#bp.alias.add 'port (.*)' 'get {1} $portbag|wear {1}|enter|wear amulet|put {1} portbag'
  This alias can be used with numbered positions from the words following after the alias
"""
import os
import re
import shlex
import argparse

from string import Template
from plugins._baseplugin import BasePlugin
from libs.persistentdict import PersistentDict
from libs.color import strip_ansi

#these 5 are required
NAME = 'Alias'
SNAME = 'alias'
PURPOSE = 'create aliases'
AUTHOR = 'Bast'
VERSION = 2
PRIORITY = 25

# This keeps the plugin from being autoloaded if set to False
AUTOLOAD = True


class Plugin(BasePlugin):
  """
  a plugin to do simple substitution
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.aliasfile = os.path.join(self.savedir, 'aliases.txt')
    self._aliases = PersistentDict(self.aliasfile, 'c', format='json')

    self.sessionhits = {}

  def load(self):
    """
    load the plugins
    """
    BasePlugin.load(self)

    self.api.get('setting.add')('nextnum', 0, int,
                                'the number of the next alias addded',
                                readonly=True)

    parser = argparse.ArgumentParser(add_help=False,
                 description='add an alias')
    parser.add_argument('original', help='the input to replace', default='', nargs='?')
    parser.add_argument('replacement', help='the string to replace it with', default='', nargs='?')
    parser.add_argument('-d', "--disable", help="disable the alias", action="store_true")
    self.api.get('commands.add')('add', self.cmd_add,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                 description='remove an alias')
    parser.add_argument('alias', help='the alias to remove', default='', nargs='?')
    self.api.get('commands.add')('remove', self.cmd_remove,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                 description='list aliases')
    parser.add_argument('match', help='list only aliases that have this argument in them', default='', nargs='?')
    self.api.get('commands.add')('list', self.cmd_list,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                 description='toggle enabled flag')
    parser.add_argument('alias', help='the alias to toggle', default='', nargs='?')
    self.api.get('commands.add')('toggle', self.cmd_toggle,
                                 parser=parser)

    parser = argparse.ArgumentParser(add_help=False,
                 description='toggle enabled flag')
    parser.add_argument('alias', help='the alias to get details for', default='', nargs='?')
    self.api.get('commands.add')('detail', self.cmd_detail,
                                 parser=parser)

    self.api.get('commands.default')('list')
    self.api.get('events.register')('from_client_event', self.checkalias, prio=5)

  def checkalias(self, args):
    """
    this function finds aliases in client input
    """
    data = args['fromdata'].strip()

    if not data:
      return args

    for mem in self._aliases.keys():
      if self._aliases[mem]['enabled']:
        datan = data
        if '(.*)' in mem:
          if re.match(mem, data):
            self.api.get('send.msg')('matched input on %s' % mem)
            tlist = shlex.split(data)
            tlistn = ['"%s"' % i for i in tlist]
            self.api.get('send.msg')('args: %s' % tlistn)
            try:
              datan = self._aliases[mem]['alias'].format(*tlistn)
            except:
              self.api.get('send.traceback')('alias %s had an issue' % (mem))
        else:
          p = re.compile('^%s' % mem)
          datan = p.sub(self._aliases[mem]['alias'], data)
        if datan != data:
          if not 'hits' in self._aliases[mem]:
            self._aliases[mem]['hits'] = 0
          if not mem in self.sessionhits:
            self.sessionhits[mem] = 0
          self.api.get('send.msg')('incrementing hits for %s' % mem)
          self._aliases[mem]['hits'] = self._aliases[mem]['hits'] + 1
          self.sessionhits[mem] = self.sessionhits[mem] + 1
          self.api.get('send.msg')('replacing "%s" with "%s"' % (data.strip(), datan.strip()))
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
    if args.original and args.replacement:
      tmsg.append("@GAdding alias@w : '%s' will be replaced by '%s'" % \
                                              (args.original, args.replacement))
      self.addalias(args.original, args.replacement, args.disable)
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
    if args.alias:
      retval = self.removealias(args.alias)
      if retval:
        tmsg.append("@GRemoving alias@w : '%s'" % (retval))
      else:
        tmsg.append("@GCould not remove alias@w : '%s'" % (args.alias))

      return True, tmsg
    else:
      return False, ['@RPlease include an alias to remove@w']

  def cmd_toggle(self, args):
    """
    toggle the enabled flag
    """
    tmsg = []
    if args.alias:
      retval = self.togglealias(args.alias)
      if retval:
        if self._aliases[retval]['enabled']:
          tmsg.append("@GEnabled alias@w : '%s'" % (retval))
        else:
          tmsg.append("@GDisabled alias@w : '%s'" % (retval))
      else:
        tmsg.append("@GDoes not exist@w : '%s'" % (args.alias))
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
    if args.alias:
      alias = self.lookup_alias(args.alias)
      if alias:
        if not ('hits' in self._aliases[alias]):
          self._aliases[alias]['hits'] = 0
        if not (alias in self.sessionhits):
          self.sessionhits[alias] = 0
        tmsg.append('%-12s : %d' % ('Num', self._aliases[alias]['num']))
        tmsg.append('%-12s : %s' % ('Enabled', 'Y' if self._aliases[alias]['enabled'] else 'N'))
        tmsg.append('%-12s : %d' % ('Total Hits', self._aliases[alias]['hits']))
        tmsg.append('%-12s : %d' % ('Session Hits', self.sessionhits[alias]))
        tmsg.append('%-12s : %s' % ('Alias', alias))
        tmsg.append('%-12s : %s' % ('Replacement', self._aliases[alias]['alias']))
      else:
        return True, ['@RAlias does not exits@w : \'%s\'' % (args.alias)]

      return True, tmsg
    else:
      return False, ['@RPlease include all arguments@w']

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List aliases
      @CUsage@w: list
    """
    tmsg = self.listaliases(args.match)
    return True, tmsg

  def addalias(self, item, alias, disabled):
    """
    internally add a alias
    """
    num = self.api.get('setting.gets')('nextnum')
    self._aliases[item] = {'alias':alias, 'enabled':not disabled, 'num':num}
    self._aliases.sync()
    self.api.get('setting.change')('nextnum', num + 1)

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
    alias = self.lookup_alias(item)
    if alias:
      self._aliases[alias]['enabled'] = not self._aliases[alias]['enabled']

    return alias

  def listaliases(self, match):
    """
    return a table of strings that list aliases
    """
    tmsg = []
    for s in sorted(self._aliases.iteritems(), key=lambda (x, y): y['num']):
      item = s[0]
      if not match or match in item:
        lalias = strip_ansi(self._aliases[item]['alias'])
        if len(lalias) > 30:
          lalias = lalias[:27] + '...'
        tmsg.append("%4s %2s  %-20s : %s@w" % (self._aliases[item]['num'],
                      'Y' if self._aliases[item]['enabled'] else 'N',
                      item,
                      lalias))
    if len(tmsg) == 0:
      tmsg = ['None']
    else:
      tmsg.insert(0, "%4s %2s  %-20s : %s@w" % ('#', 'E', 'Alias', 'Replacement'))
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

  def savestate(self):
    """
    save states
    """
    BasePlugin.savestate(self)
    self._aliases.sync()
