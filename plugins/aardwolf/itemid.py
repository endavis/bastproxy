"""
This plugin reads and parses id and invdetails from Aardwolf
"""
import textwrap
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Item Identification'
SNAME = 'itemid'
PURPOSE = 'Parse invdetails and id'
AUTHOR = 'Bast'
VERSION = 1



class InvdetailsCmd(object):
  """
  a class to manipulate containers
  """
  def __init__(self, plugin):
    """
    init the class
    """
    ## cmd = command to send to get data
    ## cmdregex = regex that matches command
    ## startregex = the line to match to start collecting data
    ## endregex = the line to match to end collecting data
    self.cid = "invdetails"
    self.cmd = "invdetails"
    self.cmdregex = r"^invdetails (?P<item>.*)$"
    self.startregex = r"^\{invdetails\}$"
    self.endregex = r"^\{/invdetails\}$"
    self.plugin = plugin
    self.api = self.plugin.api
    self.currentitem = {}

    self._dump_shallow_attrs = ['plugin', 'api']

    self.api('cmdq.addcmdtype')(self.cid, self.cmd, self.cmdregex,
                                beforef=self.databefore, afterf=self.dataafter)

    self.api('triggers.add')('cmd_%s_start' % self.cid,
                             self.startregex,
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

    self.api('triggers.add')('cmd_%s_end' % self.cid,
                             self.endregex,
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

    self.api('triggers.add')('cmd_%s_line' % self.cid,
                             r"^\{(?P<header>.*)\}(?P<data>.+)$",
                             group='cmd_%s' % self.cid, enabled=False, omit=True)

  def databefore(self):
    """
    this will be called before the command
    """
    self.api('events.register')('trigger_cmd_%s_start' % self.cid, self.datastart)

    self.api('events.register')('trigger_cmd_%s_line' % self.cid,
                                self.invdetailsline)

    self.api('triggers.togglegroup')('cmd_%s' % self.cid, True)

  def datastart(self, args=None): # pylint: disable=unused-argument
    """
    found beginning of data for slist
    """
    self.api('send.msg')('CMD - %s: found start %s' % (self.cid, self.startregex))
    self.api('cmdq.cmdstart')(self.cid)
    self.api('events.register')('trigger_cmd_%s_end' % self.cid, self.dataend)

  def invdetailsline(self, args):
    """
    parse a line of invdetails
    """
    self.api('send.msg')('invdetailsline args: %s' % args)
    header = args['header']
    data = args['data']
    self.api('send.msg')('match: %s - %s' % (header,
                                             data))
    titem = self.api('itemu.dataparse')(data,
                                        header)
    if header == 'invheader':
      self.currentitem = titem
    elif header in ['statmod', 'resistmod', 'skillmod']:
      self.addmod(header, titem)
    elif header == 'enchant':
      if 'enchant' not in self.currentitem:
        self.currentitem['enchant'] = []
      self.currentitem['enchant'].append(titem)
    else:
      self.currentitem[header] = titem
    self.api('send.msg')('invdetails parsed item: %s' % titem)

  def dataend(self, args): #pylint: disable=unused-argument
    """
    found end of data for the slist command
    """
    self.api('send.msg')('CMD - %s: found end %s' % (self.cid, self.endregex))

    self.api('events.unregister')('trigger_cmd_%s_start' % self.cid, self.datastart)
    self.api('events.unregister')('trigger_cmd_%s_end' % self.cid, self.dataend)

    self.api('events.unregister')('trigger_cmd_%s_line' % self.cid,
                                  self.invdetailsline)

    self.api('triggers.togglegroup')('cmd_%s' % self.cid, False)

    self.api('cmdq.cmdfinish')(self.cid)

  def dataafter(self):
    """
    this will be called after the command
    """
    self.plugin.currentitem = self.currentitem

  def addmod(self, ltype, mod):
    """
    add a mod to an item (stat, skills, resist, etc)
    """
    if ltype not in self.currentitem:
      self.currentitem[ltype] = {}

    if ltype == 'tempmod':
      if mod['type'] not in self.currentitem[ltype]:
        self.currentitem[ltype][mod['type']] = []
      self.currentitem[ltype][mod['type']].append(mod)
    else:
      self.currentitem[ltype][mod['name']] = int(mod['value'])

class IdentifyCmd(object):
  """
  a class to manipulate containers
  """
  def __init__(self, plugin):
    """
    init the class
    """
    ## cmd = command to send to get data
    ## cmdregex = regex that matches command
    ## startregex = the line to match to start collecting data
    ## endregex = the line to match to end collecting data
    self.cid = "identify"
    self.cmd = "identify"
    self.cmdregex = r"^identify (?P<item>.*)$"
    self.startregex = r"\+-*\+"
    self.endregex = r""
    self.plugin = plugin
    self.api = self.plugin.api

    self._dump_shallow_attrs = ['plugin', 'api']

    self.api('cmdq.addcmdtype')(self.cid, self.cmd, self.cmdregex,
                                beforef=self.databefore, afterf=self.dataafter)

    self.currentitem = None

    self.dividercount = 0
    self.pastkeywords = False
    self.currentidsection = ''
    self.putevent = ''

    self.idinfoneeded = ['keywords', 'foundat', 'material', 'leadsto',
                         'affectmod', 'reward']
    self.idinfoskip = ['name', 'id', 'itype', 'worth', 'wearable', 'score',
                       'flags', 'ownedby', 'statmods', 'resistmods',
                       'weapontype', 'inflicts', 'specials', 'capacity',
                       'holding', 'totweight', 'clanitem', 'spells', 'healrate',
                       'duration', 'serial']

    self.api('triggers.add')('cmd_%s_divider' % self.cid,
                             r"\+-*\+",
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

    self.api('triggers.add')('cmd_%s_line' % self.cid,
                             r'^\|(?P<data>.*)\|$',
                             enabled=False, group='cmd_%s' % self.cid,
                             omit=True)

  def databefore(self):
    """
    this will be called before the command
    """
    self.currentitem = self.plugin.currentitem
    self.api('events.register')('trigger_cmd_%s_divider' % self.cid, self.datadivider)

    self.api('events.register')('trigger_cmd_%s_line' % self.cid,
                                self.dataline)

    self.api('triggers.togglegroup')('cmd_%s' % self.cid, True)

  def datadivider(self, args=None): # pylint: disable=unused-argument
    """
    found a divider for identify
    """
    self.api('send.msg')('CMD - %s: found start %s' % (self.cid, self.startregex))
    self.api('cmdq.cmdstart')(self.cid)

    self.dividercount = self.dividercount + 1
    if self.dividercount == 1:
      self.api('send.msg')('found identify')
      self.api('triggers.togglegroup')('cmd_%s' % self.cid, True)
      self.api('events.register')('trigger_emptyline', self.dataend)
    elif self.dividercount == 2:
      self.pastkeywords = True
    self.currentidsection = ''

  def dataline(self, args): # pylint: disable=too-many-branches
    """
    parse an identify line, we only want a couple of things that don't
    appear in invdetails: Keywords, Found, Material, Leads to, Affect Mods and
    any item notes
    """
    data = args['data']

    # Find the current id section
    if ':' in data and data[1] != ' ':
      tdata = data.replace('|', '')
      section = tdata.split(':')[0].strip().lower().replace(' ', '')
      if section == 'reward.....':
        section = 'reward'
      if section == 'type':
        section = 'itype'
      if section == 'id':
        section = 'serial'
      if section == 'affectmods':
        section = 'affectmod'
      if section:
        self.currentidsection = section

    if self.currentidsection not in self.idinfoneeded \
        and self.currentidsection not in self.currentitem \
        and self.currentidsection not in self.idinfoskip:
      self.api('send.msg')('found unknown data in identify: %s' % \
                                self.currentidsection)

    # Save the info if we can't get it from invdetails
    if self.currentidsection in self.idinfoneeded:
      item = data.split(': ')[1]
      item = item.replace('@W', '')
      item = item.replace('@w', '')
      if self.currentidsection in self.idinfoneeded and \
        self.currentidsection not in self.currentitem:
        self.currentitem[self.currentidsection] = item.strip()
      else:
        self.currentitem[self.currentidsection] = \
          self.currentitem[self.currentidsection] + ' ' + item.strip()
      return

    # Anything that doesn't have a section is Notes
    if not self.currentidsection:
      if 'notes' not in self.currentitem:
        self.currentitem['notes'] = []
      tdat = args['colorline'][1:-1]
      self.currentitem['notes'].append(tdat.strip())

  def dataend(self, _=None):
    """
    found end of identify data, clean up triggers and events
    """
    self.api('send.msg')('CMD - %s: found end' % (self.cid))
    self.api('events.unregister')('trigger_cmd_%s_divider' % self.cid, self.datadivider)
    self.api('events.unregister')('trigger_cmd_%s_line' % self.cid,
                                  self.dataline)
    self.api('events.unregister')('trigger_emptyline', self.dataend)
    self.api('triggers.togglegroup')('cmd_%s' % self.cid, False)
    self.api('cmdq.cmdfinish')(self.cid)

  def dataafter(self):
    """
    this will be called after the command
    """
    self.pastkeywords = False
    self.dividercount = 0
    self.currentidsection = ''

    self.api('send.msg')('identify item' % self.currentitem)

    # split the keywords
    keyw = self.currentitem['keywords'].strip()
    newkey = keyw.split(' ')
    self.currentitem['keywords'] = newkey

    # split the flags
    flagw = self.currentitem['flags'].strip()
    newflag = flagw.split(', ')
    self.currentitem['flags'] = newflag

    # fix reward
    if 'reward'in self.currentitem:
      self.currentitem['reward'] = {'rtext':self.currentitem['reward']}

    # fix notes
    if 'notes'in self.currentitem:
      self.currentitem['notes'] = {'ntext':" ".join(self.currentitem['notes'])}

    # split affectmods
    if 'affectmod' in self.currentitem:
      affw = self.currentitem['affectmod'].strip()
      newflag = affw.split(', ')
      self.currentitem['affectmod'] = newflag


    if self.currentitem['serial'] in self.plugin.waitingforid:
      del self.plugin.waitingforid[int(self.currentitem['serial'])]
    self.api('eq.addidentify')(self.currentitem['serial'], self.currentitem)

    titem = self.api('eq.getitem')(self.currentitem['serial'])

    if titem.origcontainer and titem.origcontainer.cid != 'Inventory':
      self.api('eq.put')(titem.serial)
      self.putevent = 'eq_put_%s_%s' % (self.currentitem['serial'],
                                        titem.origcontainer.cid)
      self.api('send.msg')('waiting for event: %s' % self.putevent)
      self.api('events.register')(self.putevent, self.event_put)
    else:
      self.raiseid()

  def event_put(self, args):
    """
    wait for the put event
    """
    self.api('send.msg')('identify got put event')
    self.api('events.unregister')(args['eventname'], self.event_put)
    self.raiseid()

  def raiseid(self):
    """
    raise an event for id finished
    """
    titem = self.api('eq.getitem')(self.currentitem['serial'])
    self.api('send.client')('raiseid item: %s' % titem)
    self.api('send.msg')('raising id event for %s' % titem.serial)
    self.api('events.eraise')('itemid_%s' % titem.serial, {'item':titem})
    self.api('events.eraise')('itemid_all', {'item':titem})

class Plugin(AardwolfBasePlugin): # pylint: disable=too-many-public-methods
  """
  a plugin to handle equipment identification, id and invdetails
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.invdetailscmd = None
    self.identifycmd = None

    self.waitingforid = {}
    self.showid = {}
    self.fulllinelength = 68
    self.linelength = 64

    self.currentitem = {}

    self.api('dependency.add')('aardwolf.itemu')
    self.api('dependency.add')('core.cmdq')

    self.api('api.add')('identify', self.api_identify)
    self.api('api.add')('format', self.api_formatitem)
    self.api('api.add')('show', self.api_showitem)

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.invdetailscmd = InvdetailsCmd(self)
    self.identifycmd = IdentifyCmd(self)

    self.api('setting.add')('idcmd', True, str,
                            'identify')

    parser = argp.ArgumentParser(add_help=False,
                                 description='id an item')
    parser.add_argument('serial', help='the item to id', default='', nargs='?')
    parser.add_argument('-f', "--force",
                        help="force an id of the item",
                        action="store_true",
                        default=False)
    parser.add_argument('-d', "--database",
                        help="get the item from the database",
                        action="store_true",
                        default=False)
    self.api('commands.add')('id', self.cmd_id,
                             parser=parser)

  # identify an item
  def api_identify(self, serial, force=False):
    """  identify an item
    @Yserial@w    = the serial # if the item to identify

    this function returns None if the identify data has to gathered,
    or the item if is in the cache"""
    titem = self.api('eq.getitem')(serial)
    if titem.hasbeenided and not force:
      return titem
    else:
      self.waitingforid[serial] = True
      if titem.curcontainer and titem.curcontainer.cid != 'Inventory':
        self.api('eq.get')(serial)
      self.api('cmdq.addtoqueue')('invdetails', serial)
      self.api('cmdq.addtoqueue')('identify', serial)
      return None

  def event_showitem(self, args):
    """
    this function is for showing an item when using the id command,
    it registers with itemid_<serial>
    """
    self.api('events.unregister')(args['eventname'], self.event_showitem)
    self.api('%s.show' % self.short_name)(args['item'].serial)

  def cmd_id(self, args):
    """
    do an id
    """
    msg = []
    if args['serial']:
      #try:
      serial = int(args['serial'])
      titem = self.api('eq.getitem')(serial)
      if not titem:
        msg.append('Could not find %s' % serial)
      else:
        if titem.hasbeenided and not args['force'] and not args['database']:
          self.api('send.msg')('cmd_id item.hasbeenided')
          self.api('%s.show' % self.short_name)(serial)
        elif args['database']:
          self.api('send.msg')('getting %s from the database' % serial)
          self.api('%s.show' % self.short_name)(serial, database=True)
        elif not titem.hasbeenided or args['force']:
          self.api('send.msg')('identifying %s' % serial)
          self.api('events.register')('itemid_%s' % serial,
                                      self.event_showitem)
          self.api('%s.identify' % self.short_name)(serial, force=args['force'])
      #except ValueError:
        #msg.append('%s is not a serial number' % args['serial'])
    else:
      msg.append('Please supply a serial #')

    return True, msg

  # show an item to the client
  def api_showitem(self, serial, database=False):
    """  show an item to the client
    @Yserial@w    = the serial # of the item to show

    if the serial isn't in the cache, then it is identified through the id
    command

    this function returns nothing"""
    if database:
      itemc = self.api('eq.itemclass')()
      item = itemc(serial, self, loadfromdb=True)
    else:
      item = self.api('eq.getitem')(serial)
    if item:
      if item.hasbeenided:
        self.api('send.msg')('api_showitem item.hasbeenided')
        tstuff = self.api('%s.format' % self.short_name)(item)
        self.api('send.client')('\n'.join(tstuff))
      else:
        self.api('send.execute')('%s.%s.id' % (self.api('commands.prefix')(), self.short_name, serial))

  def formatsingleline(self, linename, linecolour, data, datacolor=None):
    """
    format a single data line
     | Keywords   : aylorian dagger thin blade dirk                    |
    """
    if not datacolor:
      datacolor = '@W'

    data = str(data)

    printstring = '| %s%-11s@w: %s%s'
    ttext = printstring % (linecolour, linename, datacolor, data)
    newnum = 66 - len(self.api('colors.stripcolor')(ttext))
    tstring = "%" + str(newnum) + "s@w|"
    ttext = ttext + tstring % ""

    return ttext


  def formatdoubleline(self, linename, linecolour, data, # pylint: disable=too-many-arguments
                       linename2, data2):
    """
    format a double data line
     | Worth      : 20                       Weight : 4                |
    """
    if not linecolour:
      linecolour = '@W'

    data = str(data)
    data2 = str(data2)

    adddata = 24 + self.api('colors.lengthdiff')(data)
    adddata2 = 17 + self.api('colors.lengthdiff')(data2)

    printstring = '| %s%-11s@w: @W%-' + str(adddata) + 's %s%-7s@w: @W%-' + \
            str(adddata2) + 's@w|'

    return printstring % (linecolour, linename, data,
                          linecolour, linename2, data2)

  def formatspecialline(self, linename, linecolour, data, # pylint: disable=too-many-arguments
                        linename2='', data2=''):
    """
    format a special text line
     | Skill Mods : Modifies Dagger by +2                              |
    """
    if not linecolour:
      linecolour = '@W'

    data = str(data)
    data2 = str(data2)

    adddata = 20 + self.api('colors.lengthdiff')(data)

    printstring = '| %s%-11s@w: @W%-' + str(adddata) + 's'

    ttext = printstring % (linecolour, linename, data)

    if linename2:
      adddata2 = 14 + self.api('colors.lengthdiff')(data2)
      printstring2 = ' %s%-13s:  @W%-' + str(adddata2) + 's@w|'
      ttext = ttext + printstring2 % (linecolour, linename2, data2)
    else:
      newnum = 66 - len(self.api('colors.stripcolor')(ttext))
      tstring = "%" + str(newnum) + "s@w|"
      ttext = ttext + tstring % ""

    return ttext

  @staticmethod
  def formatstatsheader():
    """
    format the stats header
     |     DR   HR    Str Int Wis Dex Con Luc   Sav   HP   MN   MV     |
    """
    return '|     @w%-4s %-4s  %-3s %-3s %-3s ' \
                  '%-3s %-3s %-3s   %-3s   %-4s %-4s %-4s   |' % (
                      'DR', 'HR', 'Str', 'Int', 'Wis',
                      'Dex', 'Con', 'Luc', 'Sav', 'HP', 'MN', 'MV')

  @staticmethod
  def formatstats(stats):
    """
    format all stats
     |     -    2     -   -   -   -   -   -     -     -    -    -      |
    """
    colors = {}
    for i in stats:
      if int(stats[i]) > 0:
        colors[i] = '@G'
      else:
        colors[i] = '@R'

    allstats = ['Damage roll', 'Hit roll', 'Strength', 'Intelligence',
                'Wisdom', 'Dexterity', 'Constitution', 'Luck', 'Saves',
                'Hit points', 'Mana', 'Moves']

    for i in allstats:
      if i in stats:
        if int(stats[i]) > 0:
          colors[i] = '@G'
        elif int(stats[i]) < 0:
          colors[i] = '@R'
        else:
          colors[i] = '@w'

      else:
        stats[i] = 0
        colors[i] = '@w'

    return '|     %s%-4s@w %s%-4s@w  %s%-3s@w %s%-3s@w ' \
            '%s%-3s@w %s%-3s@w %s%-3s@w %s%-3s@w   ' \
            '%s%-3s@w   %s%-4s@w %s%-4s@w %s%-4s@w   |' % (
                colors['Damage roll'], stats['Damage roll'] or '-',
                colors['Hit roll'], stats['Hit roll'] or '-',
                colors['Strength'], stats['Strength'] or '-',
                colors['Intelligence'], stats['Intelligence'] or '-',
                colors['Wisdom'], stats['Wisdom'] or '-',
                colors['Dexterity'], stats['Dexterity'] or '-',
                colors['Constitution'], stats['Constitution'] or '-',
                colors['Luck'], stats['Luck'] or '-',
                colors['Saves'], stats['Saves'] or '-',
                colors['Hit points'], stats['Hit points'] or '-',
                colors['Mana'], stats['Mana'] or '-',
                colors['Moves'], stats['Moves'] or '-')

  @staticmethod
  def formatresist(resists, divider):
    """
    format resists

      |     Bash  Pierce  Slash    All Phys  All Mag   Diss  Poisn      |
      |      -      -       -         13       -        -     -         |
      +-----------------------------------------------------------------+
      |     Acid   Air   Cold  Earth   Eltrc   Enrgy   Fire    Holy     |
      |     100    100   100   100     100     100     100     100      |
      |     Light  Magic Mntl  Ngtv    Shdw    Sonic   Water            |
      |     100    100   100   100     100     100     100              |
    """
    colors = {}
    ttext = []
    foundfirst = False
    foundsecond = False

    firstline = ['Bash', 'Pierce', 'Slash', 'All physical',
                 'All magic', 'Disease', 'Poison']

    secondline = ['Acid', 'Air', 'Cold', 'Earth', 'Electric', 'Energy',
                  'Fire', 'Holy', 'Light', 'Magic', 'Mental', 'Negative', 'Shadow',
                  'Sonic', 'Water']

    allresists = firstline + secondline

    for i in allresists:
      if i in resists:
        if not foundfirst and i in firstline:
          foundfirst = True
        if not foundsecond and i in secondline and resists[i] > 0:
          foundsecond = True

        if int(resists[i]) > 0:
          colors[i] = '@G'
        elif int(resists[i]) < 0:
          colors[i] = '@R'
        else:
          colors[i] = '@w'
      else:
        resists[i] = 0
        colors[i] = '@w'

    if foundfirst:
      ttext.append('|%5s@w%-8s  %-8s  %-5s %-7s %-7s  %-5s %-5s %5s|' % (
          '', 'All Phys', 'All Mag', 'Bash', 'Pierce', 'Slash',
          'Diss', 'Poisn', ''))
      ttext.append(
          '|%6s %s%-8s  %s%-8s  %s%-5s %s%-7s %s%-7s  %s%-5s %s%-5s@w%4s|' % (
              '',
              colors['All physical'], resists['All physical'] or '-',
              colors['All magic'], resists['All magic'] or '-',
              colors['Bash'], resists['Bash'] or '-',
              colors['Pierce'], resists['Pierce'] or '-',
              colors['Slash'], resists['Slash'] or '-',
              colors['Disease'], resists['Disease'] or '-',
              colors['Poison'], resists['Poison'] or '-',
              ''))

    if foundsecond:
      ttext.append(divider)
      ttext.append('|%5s%-5s  %-5s %-5s %-5s   %-5s   ' \
                    '%-5s   %-5s   %-5s@w %3s|' % (
                        '', 'Acid', 'Air', 'Cold', 'Earth',
                        'Eltrc', 'Enrgy', 'Fire', 'Holy', ''))

      ttext.append('|%5s%s%-5s  %s%-5s %s%-5s %s%-5s   ' \
                        '%s%-5s   %s%-5s   %s%-5s   %s%-5s@w %3s|' % (
                            '',
                            colors['Acid'], resists['Acid'] or '-',
                            colors['Air'], resists['Air'] or '-',
                            colors['Cold'], resists['Cold'] or '-',
                            colors['Earth'], resists['Earth'] or '-',
                            colors['Electric'], resists['Electric'] or '-',
                            colors['Energy'], resists['Energy'] or '-',
                            colors['Fire'], resists['Fire'] or '-',
                            colors['Holy'], resists['Holy'] or '-',
                            ''))

      ttext.append(
          '|%4s %-5s  %-5s %-5s %-5s   %-5s   %-5s   %-5s @w %10s|' % (
              '', 'Light', 'Magic', 'Mntl', 'Ngtv',
              'Shdw', 'Sonic', 'Water', ''))

      ttext.append('|%4s %s%-5s  %s%-5s %s%-5s %s%-5s   %s%-5s   ' \
                            '%s%-5s   %s%-5s@w %11s|' % (
                                '',
                                colors['Light'], resists['Light'] or '-',
                                colors['Magic'], resists['Magic'] or '-',
                                colors['Mental'], resists['Mental'] or '-',
                                colors['Negative'], resists['Negative'] or '-',
                                colors['Shadow'], resists['Shadow'] or '-',
                                colors['Sonic'], resists['Sonic'] or '-',
                                colors['Water'], resists['Water'] or '-',
                                ''))

    return ttext

  # format an item
  def api_formatitem(self, item): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """  format an item
    @Yserial@w    = the serial # if the item to identify

    this function returns a list of strings that are the formatted item"""
    divider = '+' + '-' * 65 + '+'
    linelen = 50

    iteml = [divider]

    self.api('send.msg')('formatting item: %s' % item)

    if item.checkattr('keywords'):
      keywordline = " ".join(item.keywords)
      tstuff = textwrap.wrap(keywordline, linelen, break_on_hyphens=False)
      header = 'Keywords'
      for i in tstuff:
        iteml.append(self.formatsingleline(header, '@R', i))
        header = ''

    # do identifiers here

    if item.checkattr('cname'):
      iteml.append(self.formatsingleline('Name', '@R', '@w' + item.cname))

    iteml.append(self.formatsingleline('Id', '@R', '@w%s' % item.serial))

    if item.checkattr('curcontainer') and item.curcontainer:
      if item.curcontainer.cid == 'Worn':
        wearlocs = self.api('itemu.wearlocs')()
        iteml.append(self.formatsingleline('Location', '@R',
                                           'Worn - %s' % wearlocs[item.wearslot]))
      else:
        iteml.append(self.formatsingleline('Location', '@R',
                                           item.curcontainer.cid))

    if item.checkattr('itype') and item.checkattr('level'):
      ntype = item.itype.capitalize()
      iteml.append(self.formatdoubleline('Type', '@c', ntype,
                                         'Level', item.level))
    elif item.checkattr('level'):
      iteml.append(self.formatsingleline('Level', '@c', item.level))

    if item.checkattr('worth') and item.checkattr('weight'):
      iteml.append(self.formatdoubleline('Worth', '@c', "{:,}".format(item.worth),
                                         'Weight', item.weight))

    if item.itype == 'Light' and not item.checkattr('light'):
      iteml.append(self.formatsingleline('Duration', '@c',
                                         'permanent'))

    if item.checkattr('light'):
      iteml.append(self.formatsingleline('Duration', '@c',
                                         '%s minutes' % item.light['duration']))

    if item.checkattr('wearable'):
      iteml.append(self.formatsingleline('Wearable', '@c',
                                         item.wearable))

    if item.checkattr('score'):
      iteml.append(self.formatsingleline('Score', '@c', item.score,
                                         datacolor='@Y'))

    if item.checkattr('material'):
      iteml.append(self.formatsingleline('Material', '@c', item.material))

    if item.checkattr('flags'):
      flags = ", ".join(item.flags)
      tlist = textwrap.wrap(flags, linelen, break_on_hyphens=False)
      header = 'Flags'
      for i in tlist:
        i = i.replace('precious', '@Yprecious@w')
        i = i.replace('noshare', '@Rnoshare@w')
        iteml.append(self.formatsingleline(header, '@c', i.rstrip()))
        header = ''

    if item.checkattr('owner'):
      iteml.append(self.formatsingleline('Owned by', '@c', item.owner))

    if item.checkattr('fromclan'):
      iteml.append(self.formatsingleline('Clan Item', '@G', item.fromclan,
                                         datacolor='@M'))

    if item.checkattr('foundat'):
      iteml.append(self.formatsingleline('Found at', '@G', item.foundat,
                                         datacolor='@M'))

    if item.checkattr('leadsto'):
      iteml.append(self.formatsingleline('Leads to', '@G', item.leadsto,
                                         datacolor='@M'))

    if item.checkattr('notes'):
      iteml.append(divider)
      tlist = textwrap.wrap(item.notes['ntext'], linelen)
      header = 'Notes'
      for i in tlist:
        iteml.append(self.formatsingleline(header, '@W', i, '@w'))
        header = ''

    if item.checkattr('affectmod'):
      iteml.append(divider)
      tlist = textwrap.wrap(', '.join(item.affectmod), linelen)
      header = 'Affects'
      for i in tlist:
        iteml.append(self.formatsingleline(header, '@g', i, '@w'))
        header = ''

    if item.checkattr('container'):
      iteml.append(divider)
      iteml.append(self.formatspecialline('Capacity', '@c',
                                          item.container['capacity'], 'Heaviest Item',
                                          item.container['heaviestitem']))
      iteml.append(self.formatspecialline('Holding', '@c',
                                          item.container['holding'], 'Items Inside',
                                          item.container['itemsinside']))
      iteml.append(self.formatspecialline('Tot Weight', '@c',
                                          item.container['totalweight'], 'Item Burden',
                                          item.container['itemburden']))
      iteml.append(self.formatspecialline(
          '', '@c',
          '@wItems inside weigh @Y%d@w%%@w of their usual weight' % \
          item.container['itemweightpercent']))

    if item.checkattr('weapon'):
      iteml.append(divider)
      iteml.append(self.formatspecialline('Weapon Type', '@c',
                                          item.weapon['wtype'], 'Average Dam',
                                          item.weapon['avedam']))
      iteml.append(self.formatspecialline('Inflicts', '@c',
                                          item.weapon['inflicts'], 'Damage Type',
                                          item.weapon['damtype']))
      if 'special' in item.weapon and item.weapon['special']:
        iteml.append(self.formatspecialline('Specials', '@c',
                                            item.weapon['special']))

    if item.itype == 'Portal':
      if item.checkattr('portal'):
        iteml.append(divider)
        iteml.append(self.formatsingleline('Portal', '@R',
                                           '@Y%s@w uses remaining.' % \
                                              item.portal['uses']))

    if item.checkattr('statmod'):
      iteml.append(divider)
      iteml.append(self.formatstatsheader())
      iteml.append(self.formatstats(item.statmod))

    if item.checkattr('resistmod'):
      iteml.append(divider)
      if item.resistmod:
        for i in self.formatresist(item.resistmod, divider):
          iteml.append(i)

    if item.checkattr('skillmod'):
      iteml.append(divider)
      header = 'Skill Mods'
      for i in item.skillmod:
        spell = self.api('skills.gets')(i)
        color = '@R'
        if int(item.skillmod[i]) > 0:
          color = '@G'
        iteml.append(self.formatspecialline(header, '@c',
                                            'Modifies @g%s@w by %s%+d@w' % \
                                              (str(spell['name']).capitalize(),
                                               color, int(item.skillmod[i]))))
        header = ''

    if item.checkattr('enchant'):
      if item.enchant:
        iteml.append(divider)
        iteml.append(self.formatspecialline('Enchants', '@c', ''))
        for enchant in item.enchant:
          lline = '@W%s @G%+d@w' % (enchant['stat'], enchant['mod'])
          if enchant['removable'] == 'E':
            tline = "%-26s     (removable by enchanter)" % lline
          else:
            tline = lline
          iteml.append(self.formatsingleline(enchant['spell'], '@g',
                                             tline))

    if item.checkattr('spells'):
      iteml.append(divider)

      header = 'Spells'
      for i in xrange(1, 5):
        key = 'sn%s' % i
        if item.spells[key] and item.spells[key] != 0:
          spell = self.api('skills.gets')(item.spells[key])
          plural = ''
          if int(item.spells['uses']) > 1:
            plural = 's'
          iteml.append(self.formatspecialline(header, '@c',
                                              "%d use%s of level %d '@g%s@w'" % (
                                                  item.spells['uses'], plural,
                                                  item.spells['level'],
                                                  spell['name'].lower())))
          header = ''

    if item.checkattr('food'):
      iteml.append(divider)
      header = 'Food'
      iteml.append(self.formatspecialline(header, '@c',
                                          "Will replenish hunger by %d%%" % \
                                            (item.food['percent'])))

    if item.checkattr('reward'):
      iteml.append(divider)
      header = 'Reward'
      iteml.append(self.formatspecialline(header, '@Y',
                                          item.reward['rtext']))

    if item.checkattr('drink'):
      iteml.append(divider)
      iteml.append(self.formatspecialline('Drink', '@c',
                                          "@w%d servings of %s. Max: %d" % \
                                            (item.drink['servings'],
                                             item.drink['liquid'],
                                             item.drink['liquidmax']/20 or 1)))
      iteml.append(self.formatspecialline('', '@c',
                                          "@wEach serving replenishes thirst by %d%%" % \
                                           item.drink['thirstpercent']))
      iteml.append(self.formatspecialline('', '@c',
                                          "@wEach serving replenishes hunger by %d%%" % \
                                           item.drink['hungerpercent']))

    if item.checkattr('furniture'):
      iteml.append(divider)
      iteml.append(self.formatspecialline('Heal Rate', '@c',
                                          "Health @w[@Y%d@w]    @WMagic @w[@Y%d@w]" % \
                                           (item.furniture['hpregen'],
                                            item.furniture['manaregen'])))

    iteml.append(divider)

    return iteml
