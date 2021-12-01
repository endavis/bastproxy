"""
This plugin parses whois data from Aardwolf
"""
import os
import copy
from libs.persistentdict import PersistentDict
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Whois'
SNAME = 'whois'
PURPOSE = 'Gather whois data'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)
    self.savewhoisfile = os.path.join(self.save_directory, 'whois.txt')
    self.whois = PersistentDict(self.savewhoisfile, 'c')

    self.api('dependency:add')('core.triggers')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('core.watch:watch:add')('whois', '^(whoi|whois)$')

    self.api('core.triggers:trigger:add')('whoisheader',
                                          r"^\[.*\]\s+.*\s*\((?P<sex>\w+)\s+\w+\)$",
                                          enabled=False,
                                          group='whois')
    self.api('core.triggers:trigger:add')('whoisclasses',
                                          r"^\[Multiclass Player: (?P<classes>.*) \]$",
                                          enabled=False,
                                          group='whois')
    self.api('core.triggers:trigger:add')(
        'whois1',
        r"^(?P<name1>[\w\s]*)\s*:\s*\[\s*(?P<val1>[\w\d\s]*)\s*\]\s*$",
        enabled=False,
        group='whois')
    self.api('core.triggers:trigger:add')(
        'whois2',
        r"^(?P<name1>[\w\s]*)\s*:\s*\[\s*(?P<val1>[\w\d\s]*)\s*\]" \
          r"\s*(?P<name2>[\w\s]*)\s*:\s*\[\s*(?P<val2>[\w\d\s]*)\s*\]\s*$",
        enabled=False,
        group='whois')
    self.api('core.triggers:trigger:add')(
        'whois3',
        r"^(?P<name1>[\w\s]*)\s*:\s*\[\s*(?P<val1>[\w\d\s]*)\s*\]" \
          r"\s*(?P<name2>[\w\s]*)\s*:\s*\[\s*(?P<val2>[\w\d\s]*)\s*\]" \
          r"\s*(?P<name3>[\w\s]*)\s*:\s*\[\s*(?P<val3>[\w\d\s]*)\s*\]\s*$",
        enabled=False,
        group='whois')
    self.api('core.triggers:trigger:add')(
        'whoispowerup',
        r"^(?P<name1>[\w\s]*)\s*:\s*\[\s*(?P<val1>[\w\d\s]*)\s*\]" \
          r"\s*([\w\s]*)\s*:\s*\[\s*(?P<pval1>[\w\d\s]*)\s*\]\s*\[\s*" \
          r"(?P<pval2>[\w\d\s]*)\s*\]\s*$",
        enabled=False,
        group='whois')
    self.api('core.triggers:trigger:add')('whoisend',
                                          r"^-{74,74}$",
                                          enabled=False)

    self.api('core.events:register:to:event')('watch_whois', self._whois)
    self.api('core.events:register:to:event')('trigger_whoisheader', self._whoisheader)
    self.api('core.events:register:to:event')('trigger_whoisclasses', self._whoisclasses)
    self.api('core.events:register:to:event')('trigger_whois1', self._whoisstats)
    self.api('core.events:register:to:event')('trigger_whois2', self._whoisstats)
    self.api('core.events:register:to:event')('trigger_whois3', self._whoisstats)
    self.api('core.events:register:to:event')('trigger_whoispowerup', self._whoisstats)
    self.api('core.events:register:to:event')('trigger_whoisend', self._whoisend)
    self.api('core.events:register:to:event')('ev_{0.plugin_id}_savestate'.format(self), self._savestate)

  def _whois(self, args=None):
    """
    reset the whois info when a "whois" command is sent
    """
    self.whois.clear()
    self.api('core.triggers:group:toggle:enable')('whois', True)
    return args

  def _whoisstats(self, args=None):
    """
    parse a whois line
    """
    for i in range(1, 4):
      akey = 'name%s' % i
      aval = 'val%s' % i

      if akey in args:
        kname = args[akey].lower().strip()
        kname = kname.replace(' ', '')
        kval = args[aval].strip()

        self.whois[kname] = kval

    if 'pval1' in args:
      self.whois['powerupsall'] = args['pval1']
    if 'pval2' in args:
      self.whois['powerupsmort'] = args['pval2']

  def _whoisheader(self, args=None):
    """
    do stuff when we see the whois header
    """
    self.whois["name"] = self.api('net.GMCP:value:get')('char.base.name')
    self.whois['level'] = self.api('net.GMCP:value:get')('char.status.level')
    self.whois['tiers'] = self.api('net.GMCP:value:get')('char.base.tier')
    self.whois['redos'] = int(self.api('net.GMCP:value:get')('char.base.redos'))
    self.whois['race'] = self.api('net.GMCP:value:get')('char.base.race').lower()
    self.whois['sex'] = args['sex'].lower()
    self.whois['subclass'] = self.api('net.GMCP:value:get')(
        'char.base.subclass').lower()
    self.whois['powerupsall'] = 0
    self.whois['powerupsmort'] = 0
    self.whois['remorts'] = self.api('net.GMCP:value:get')('char.base.remorts')
    if self.whois['remorts'] == 1:
      classabs = self.api('aardwolf.aardu:classabb')()
      self.whois['classes'] = []
      self.whois['classes'].append({'remort':1,
                                    'class':classabs[self.api('net.GMCP:value:get')(
                                        'char.base.class').lower()]})

    self.api('core.triggers:trigger:toggle:enable')('whoisend', True)

  def _whoisclasses(self, args):
    """
    add classes
    """
    classabs = self.api('aardwolf.aardu:classabb')()
    tlist = args['classes'].split("/")
    remorts = len(tlist)
    self.whois['classes'] = []
    for i in range(remorts):
      tclass = tlist[i].strip().lower()
      self.whois['classes'].append({'remort':i + 1,
                                    'class':classabs[tclass.lower()]})

    self.whois['remorts'] = remorts

  def _whoisend(self, _=None):
    """
    send a whois
    """
    self.whois['totallevels'] = self.api('aardwolf.aardu:getactuallevel')(
        self.whois['level'], self.whois['remorts'],
        self.whois['tiers'], self.whois['redos'])
    self.whois.sync()
    self.api('core.triggers:group:toggle:enable')('whois', False)
    self.api('core.triggers:trigger:toggle:enable')('whoisend', False)
    self.api('core.events:raise:event')('aard_whois', copy.deepcopy(self.whois))
    self.api('libs.io:send:msg')('whois: %s' % self.whois)

  def _savestate(self, _=None):
    """
    save states
    """
    self.whois.sync()
