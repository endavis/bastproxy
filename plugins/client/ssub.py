"""
This plugin is a simple substition plugin
"""
import os

from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.persistentdict import PersistentDict

#these 5 are required
NAME = 'Simple Substitute'
SNAME = 'ssub'
PURPOSE = 'simple substitution of strings'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

# This keeps the plugin from being autoloaded if set to False
REQUIRED = True


class Plugin(BasePlugin):
  """
  a plugin to do simple substitution
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.savesubfile = os.path.join(self.save_directory, 'subs.txt')
    self._substitutes = PersistentDict(self.savesubfile, 'c')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='add a simple substitute')
    parser.add_argument('original',
                        help='the output to substitute',
                        default='',
                        nargs='?')
    parser.add_argument('replacement',
                        help='the string to replace it with',
                        default='',
                        nargs='?')
    self.api('commands.add')('add',
                             self.cmd_add,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='remove a substitute')
    parser.add_argument('substitute',
                        help='the substitute to remove',
                        default='',
                        nargs='?')
    self.api('commands.add')('remove',
                             self.cmd_remove,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list substitutes')
    parser.add_argument('match',
                        help='list only substitutes that have this argument in them',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='clear all substitutes')
    self.api('commands.add')('clear',
                             self.cmd_clear,
                             parser=parser)

    self.api('commands.default')('list')
    self.api('events.register')('from_mud_event', self.findsub)

    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

  def findsub(self, args):
    """
    this function finds subs in mud data
    """
    data = args['original']
    dtype = args['dtype']
    if dtype != 'fromproxy':
      for mem in self._substitutes.keys():
        if mem in data:
          ndata = data.replace(mem,
                               self.api('colors.convertcolors')(
                                   self._substitutes[mem]['sub']))
          if ndata != data:
            args['trace']['changes'].append({'flag':'Modify',
                                             'data':'changed "%s" to "%s"' % \
                                                 (data, ndata),
                                             'plugin':self.short_name,
                                             'eventname':args['eventname']})
            data = ndata
      args['original'] = data
      return args

  def cmd_add(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Add a substitute
      @CUsage@w: add @Y<originalstring>@w @M<replacementstring>@w
        @Yoriginalstring@w    = The original string to be replaced
        @Mreplacementstring@w = The new string
    """
    tmsg = []
    if args['original'] and args['replacement']:
      tmsg.append("@GAdding substitute@w : '%s' will be replaced by '%s'" % \
                                      (args['original'], args['replacement']))
      self.addsub(args['original'], args['replacement'])
      return True, tmsg

    tmsg.append("@RPlease specify all arguments@w")
    return False, tmsg

  def cmd_remove(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Remove a substitute
      @CUsage@w: rem @Y<originalstring>@w
        @Yoriginalstring@w    = The original string
    """
    tmsg = []
    if args['substitute']:
      tmsg.append("@GRemoving substitute@w : '%s'" % (args['substitute']))
      self.removesub(args['substitute'])
      return True, tmsg

    return False, tmsg

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List substitutes
      @CUsage@w: list
    """
    tmsg = self.listsubs(args['match'])
    return True, tmsg

  def cmd_clear(self, args):
    # pylint: disable=unused-argument
    """
    @G%(name)s@w - @B%(cmdname)s@w
      List substitutes
      @CUsage@w: list"""
    self.clearsubs()
    return True, ['Substitutes cleared']

  def addsub(self, item, sub):
    """
    internally add a substitute
    """
    self._substitutes[item] = {'sub':sub}
    self._substitutes.sync()

  def removesub(self, item):
    """
    internally remove a substitute
    """
    if item in self._substitutes:
      del self._substitutes[item]
      self._substitutes.sync()

  def listsubs(self, match):
    """
    return a table of strings that list subs
    """
    tmsg = []
    for item in self._substitutes:
      if not match or match in item:
        tmsg.append("%-35s : %s@w" % (item, self._substitutes[item]['sub']))
    if not tmsg:
      tmsg = ['None']
    return tmsg

  def clearsubs(self):
    """
    clear all subs
    """
    self._substitutes.clear()
    self._substitutes.sync()

  def reset(self):
    """
    reset the plugin
    """
    BasePlugin.reset(self)
    self.clearsubs()

  def _savestate(self, _=None):
    """
    save states
    """
    self._substitutes.sync()
