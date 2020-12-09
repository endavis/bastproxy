# pylint: disable=line-too-long
"""
This plugin includes a combat tracker for aardwolf

### Example Output

    @x033------------------------------------------------------------------------
    @x033-----------------  @Wthe dwarven barkeeper@x033 : @W06@x033s - @W72@x033xp  -----------------
    @x033------------------------------------------------------------------------
    @x033Dam Type             :    Hits      Damage   (  0%)   Misses    Average
    @x033------------------------------------------------------------------------
    @Wbackstab             @x033: @W    2         982     ( 37%)     1         491
    @Wcleave               @x033: @W    3         976     ( 37%)     2         325
    @Wpierce               @x033: @W    2         665     ( 25%)     0         332
    @x033------------------------------------------------------------------------
    @WTotal                @x033: @W    7         2623    (100%)     3         374
    @x033------------------------------------------------------------------------@w

"""
# pylint: enable=line-too-long
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'CombatTracker'
SNAME = 'ct'
PURPOSE = 'Show combat stats'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to show combat stats after a mob kill
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.msgs = []

    self.api('dependency:add')('aardwolf.mobk')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting:add')('statcolor', '@W', 'color', 'the stat color')
    self.api('setting:add')('infocolor', '@x33', 'color', 'the info color')

    self.api('core.events:register:to:event')('aard_mobkill', self.mobkill)

  def mobkill(self, args=None): # pylint: disable=too-many-locals
    """
    handle a mob kill
    """
    linelen = 72
    msg = []
    infocolor = self.api('setting:get')('infocolor')
    statcolor = self.api('setting:get')('statcolor')
    msg.append(infocolor + '-' * linelen)
    timestr = ''
    damages = args['damage']
    totald = sum(damages[d]['damage'] for d in damages)
    if args['finishtime'] and args['starttime']:
      timestr = '%s' % self.api('core.utils:convert:timedelta:to:string')(
          args['starttime'],
          args['finishtime'],
          colorn=statcolor,
          colors=infocolor)

    xpstr = '%s%s%sxp' % (statcolor, args['totalxp'], infocolor)

    namestr = "{statcolor}{name}{infocolor} : {time}{infocolor} - {xp}".format(
        infocolor=infocolor,
        statcolor=statcolor,
        name=args['name'],
        time=timestr,
        xp=xpstr)
    tstr = infocolor + self.api('core.utils:center:colored:string')(namestr, '-', linelen)

    msg.append(tstr)
    msg.append(infocolor + '-' * linelen)

    bstringt = "{statcolor}{dtype:<20} {infocolor}: {statcolor}{hits:^10} " \
                "{damage:^10} ({percent:4.0%}) {misses:^10} {average:^10}"

    msg.append(bstringt.format(
        statcolor=infocolor,
        infocolor=infocolor,
        dtype='Dam Type',
        hits='Hits',
        percent=0,
        damage='Damage',
        misses='Misses',
        average='Average'))
    msg.append(infocolor + '-' * linelen)
    totalm = 0
    totalh = 0
    tkeys = damages.keys()
    tkeys.sort()
    for i in tkeys:
      if i != 'enemy' and i != 'starttime' and i != 'finishtime':
        vdict = args['damage'][i]
        totalm = totalm + vdict['misses']
        totalh = totalh + vdict['hits']
        damt = i
        if i == 'backstab' and 'incombat' in vdict:
          damt = i + " (in)"

        if vdict['hits'] == 0:
          avedamage = 0
        else:
          avedamage = vdict['damage'] / vdict['hits']

        try:
          tperc = vdict['damage'] / float(totald)
        except ZeroDivisionError:
          self.api('libs.io:send:error')('totald = 0 for %s' % vdict)
          tperc = 0

        msg.append(bstringt.format(
            statcolor=statcolor,
            infocolor=infocolor,
            dtype=damt,
            hits=vdict['hits'],
            percent=tperc,
            damage=vdict['damage'],
            misses=vdict['misses'],
            average=avedamage))

    msg.append(infocolor + '-' * linelen)
    msg.append(bstringt.format(
        statcolor=statcolor,
        infocolor=infocolor,
        dtype='Total',
        hits=totalh,
        percent=1,
        damage=totald,
        misses=totalm,
        average=totald/(totalh or 1)))
    msg.append(infocolor + '-' * linelen)
    self.addmessage('\n'.join(msg))

  def addmessage(self, msg):
    """
    add a message to the out queue
    """
    self.msgs.append(msg)

    self.api('core.events:register:to:event')('trigger_emptyline', self.showmessages)

  def showmessages(self, _=None):
    """
    show a message
    """
    self.api('core.events:unregister:from:event')('trigger_emptyline', self.showmessages)
    for i in self.msgs:
      self.api('libs.io:send:client')(i, preamble=False)

    self.msgs = []
