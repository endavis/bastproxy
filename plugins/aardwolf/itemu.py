"""
This plugin hold utility functions for items

It includes:

 * an object types table and its reverse
 * a wear location table and its reverse
 * an item flags table
 * an item flags color table
 * an item flags name table
"""
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Item Utils'
SNAME = 'itemu'
PURPOSE = 'Aard item and inventory functions'
AUTHOR = 'Bast'
VERSION = 1



OBJECTTYPES = [
    'none',
    'light',
    'scroll',
    'wand',
    'staff',
    'weapon',
    'treasure',
    'armor',
    'potion',
    'furniture',
    'trash',
    'container',
    'drink',
    'key',
    'food',
    'boat',
    'mobcorpse',
    'corpse',
    'fountain',
    'pill',
    'portal',
    'beacon',
    'giftcard',
    'gold',
    'raw material',
    'campfire'
]
OBJECTTYPESREV = {}
for objectt in OBJECTTYPES:
  OBJECTTYPESREV[objectt] = OBJECTTYPES.index(objectt)

WEARLOCS = [
    'light',
    'head',
    'eyes',
    'lear',
    'rear',
    'neck1',
    'neck2',
    'back',
    'medal1',
    'medal2',
    'medal3',
    'medal4',
    'torso',
    'body',
    'waist',
    'arms',
    'lwrist',
    'rwrist',
    'hands',
    'lfinger',
    'rfinger',
    'legs',
    'feet',
    'shield',
    'wielded',
    'second',
    'hold',
    'float',
    'tattoo1',
    'tattoo2',
    'above',
    'portal',
    'sleeping',
]

WEARLOCSREV = {}
for wearlocs in WEARLOCS:
  WEARLOCSREV[wearlocs] = WEARLOCS.index(wearlocs)

ITEMFLAGS = ['K', 'G', 'H', 'I', 'M']

ITEMFLAGSCOLORS = {
    'K':'R',
    'M':'B',
    'G':'W',
    'H':'C',
    'I':'w',
}

ITEMFLAGSNAME = {
    'K':'kept',
    'M':'magic',
    'G':'glow',
    'H':'hum',
    'I':'invis',
}

class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf cp events
  """
  def __init__(self, *args, **kwargs):
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.api('libs.api:add')('dataparse', self.api_dataparse)
    self.api('libs.api:add')('wearlocs', self.api_wearlocs)
    self.api('libs.api:add')('objecttypes', self.api_objecttypes)
    self.api('libs.api:add')('itemflags', self.api_itemflags)
    self.api('libs.api:add')('itemflagscolors', self.api_itemflagscolors)
    self.api('libs.api:add')('itemflagshort_name', self.api_itemflagshort_name)

    self.invlayout = {}
    self.invlayout['invheader'] = ["serial", "level", "itype", "worth",
                                   "weight", "wearable", "flags", "owner",
                                   "fromclan", "timer", "u1", "u2", "u3",
                                   "score"]
    self.invlayout['container'] = ["capacity", "heaviestitem", "holding",
                                   "itemsinside", "totalweight", "itemburden",
                                   "itemweightpercent"]
    self.invlayout['statmod'] = ['name', 'value']
    self.invlayout['resistmod'] = ['name', 'value']
    self.invlayout['weapon'] = ["wtype", "avedam", "inflicts", "damtype",
                                "special"]
    self.invlayout['skillmod'] = ['name', 'value']
    self.invlayout['spells'] = ["uses", "level", "sn1", "sn2", "sn3", "sn4",
                                "u1"]
    self.invlayout['food'] = ['percent']
    self.invlayout['drink'] = ["servings", "liquid", "liquidmax", "liquidleft",
                               "thirstpercent", "hungerpercent", "u1"]
    self.invlayout['furniture'] = ["hpregen", "manaregen", "u1"]
    self.invlayout['eqdata'] = ["serial", "shortflags", "cname", "level",
                                "itype", "unique", "wearslot", "timer"]
    self.invlayout['light'] = ['duration']
    self.invlayout['portal'] = ['uses']
    self.invlayout['tempmod'] = ['sn', 'u1', 'u2', 'statmod', 'duration']
    self.invlayout['enchant'] = ['spell', 'etype', 'stat', 'mod', 'char', 'removable']

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

  @staticmethod
  # get the flags name table
  def api_itemflagshort_name():
    """  get the flags name table
    """
    return ITEMFLAGSNAME

  @staticmethod
  # get the flags table
  def api_itemflags():
    """  get the flags table
    """
    return ITEMFLAGS

  @staticmethod
  # get the flags color table
  def api_itemflagscolors():
    """  get the flags color table
    """
    return ITEMFLAGSCOLORS

  @staticmethod
  # get the wear locations table
  def api_wearlocs(rev=False):
    """  get the wear locations table
    @Yrev@w  = if True, return the reversed table
    """
    if rev:
      return WEARLOCSREV

    return WEARLOCS

  @staticmethod
  # get the object types table
  def api_objecttypes(rev=False):
    """  get the object types table
    @Yrev@w  = if True, return the reversed table
    """
    if rev:
      return OBJECTTYPESREV

    return OBJECTTYPES

  # parse a line from invitem, invdata, eqdata, invdetails
  def api_dataparse(self, line, layoutname):
    """ parse a line of data from invdetails, invdata, eqdata, invdetails
    @Yline@w       = The line to parse
    @ylayoutname@w = The layout of the line

    this function returns a dictionary"""
    tlist = [line]
    if layoutname == 'eqdata' or layoutname == 'tempmod' or layoutname == 'enchant':
      tlist = line.split(',')
    else:
      tlist = line.split('|')
    titem = {}
    if layoutname in self.invlayout:
      try:
        for i in xrange(len(self.invlayout[layoutname])):
          name = self.invlayout[layoutname][i]
          value = tlist[i]
          try:
            value = int(value)
          except ValueError:
            pass

          if layoutname == 'invheader' and name == 'type':
            try:
              value = value.lower()
            except AttributeError:
              pass

          titem[name] = value
      except:  # pylint: disable=broad-except,bare-except
        self.api('libs.io:send:traceback')('dataparse error: %s' % line)

      if layoutname == 'eqdata':
        titem['name'] = self.api('core.colors:colorcode:strip')(titem['cname'])

      return titem
    else:
      self.api('libs.io:send:msg')('layout %s not found' % layoutname)

    return None
