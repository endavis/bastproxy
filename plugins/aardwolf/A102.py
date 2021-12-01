"""
This plugin handles Aardwolf 102 telnet options

see the [Aardwolf Wiki](http://www.aardwolf.com/wiki/index.php/Help/Telopts)
"""
from plugins._baseplugin import BasePlugin
from libs.net.telnetlib import WILL, DO, IAC, SE, SB, CODES
from libs.net._basetelnetoption import BaseTelnetOption

NAME = 'A102'
SNAME = 'A102'
PURPOSE = 'Handle telnet option 102, Aardwolf specific'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35



AOPTIONS = {}
AOPTIONS['STATMON'] = 1
AOPTIONS['BIGMAPTAGS'] = 2
AOPTIONS['HELPTAGS'] = 3
AOPTIONS['MAPTAGS'] = 4
AOPTIONS['CHANNELTAGS'] = 5
AOPTIONS['TELLTAGS'] = 6
AOPTIONS['SPELLUPTAGS'] = 7
AOPTIONS['SKILLGAINTAGS'] = 8
AOPTIONS['SAYTAGS'] = 9
AOPTIONS['SCORETAGS'] = 11
AOPTIONS['ROOMNAME'] = 12
AOPTIONS['EXITS'] = 14
AOPTIONS['EDITORTAGS'] = 15
AOPTIONS['EQTAGS'] = 16
AOPTIONS['INVTAGS'] = 17
AOPTIONS['ROOMDESCTAGS'] = 18
AOPTIONS['ROOMNAMETAGS'] = 19
AOPTIONS['REPOPTAGS'] = 21

AOPTIONS['QUIETTAGS'] = 50
AOPTIONS['AUTOTICK'] = 51
AOPTIONS['PROMPT'] = 52
AOPTIONS['PAGING'] = 53
AOPTIONS['AUTOMAP'] = 54
AOPTIONS['SHORTMAP'] = 55

AOPTIONREV = {}
for optionn in AOPTIONS:
  AOPTIONREV[AOPTIONS[optionn]] = optionn

ON = chr(1)
OFF = chr(2)

# Plugin
class Plugin(BasePlugin):
  """
  the plugin to handle external a102 stuff
  """
  def __init__(self, *args, **kwargs):
    """
    Initialize the class

    self.optionstates - the current counter for what
                            options have been enabled
    self.a102optionqueue - the queue of a102 options
                            that were enabled by the client before
                             connected to the server
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.optionstates = {}
    self.a102optionqueue = []
    self.option_name = 'A102'
    self.option_num = 102
    self.option_string = chr(self.option_num)
    self.option_code = '<%s>' % self.option_name

    CODES[self.option_num] = self.option_code

    self.reconnecting = False

    self.api('dependency:add')('net.options')

    self.api('libs.api:add')('sendmud', self.api_sendmud)
    self.api('libs.api:add')('toggle', self.api_toggle)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('core.events:register:to:event')('A102_from_server', self.a102fromserver)
    self.api('core.events:register:to:event')('A102_from_client', self.a102fromclient)
    self.api('core.events:register:to:event')('A102:server-enabled', self.a102request)
    self.api('core.events:register:to:event')('ev_libs.net.mud_muddisconnect', self.a102disconnect)

    self.api('net.options:server:option:add')(self.plugin_id, self.option_name, self.option_num, SERVER)
    self.api('net.options:client:option:add')(self.plugin_id, self.option_name, self.option_num, SERVER)

  # Send an A102 packet
  def api_sendmud(self, message):
    """  send an A102 packet
    @Ymessage@w  = the message to send

    Format: IAC SB A102 <atcp message text> IAC SE

    this function returns no values"""
    self.api('libs.io:send:mud')('%s%s%s%s%s%s' % \
                              (IAC, SB, self.option_string, message.replace(IAC, IAC+IAC),
                               IAC, SE),
                                 raw=True, dtype=self.option_string)

  def a102disconnect(self, _=None):
    """
    this function is registered with the muddisconnect hook
    """
    self.api('libs.io:send:msg')('setting reconnect to true')
    self.reconnecting = True

  # toggle an a102 option
  def api_toggle(self, aoption, mstate):
    """  toggle an A102 option
    @Yaoption@w  = the A102 option to toggle
    @Ymstate@w  = the state, either True or False

    this function True if the option was toggled, False if it didn't
    exist"""
    if aoption in AOPTIONS:
      self.a102toggleoption(AOPTIONS[aoption], mstate)
      return True

    return False

  def a102toggleoption(self, aoption, mstate):
    """
    toggle an a102 option
    """
    if aoption not in self.optionstates:
      if mstate:
        self.optionstates[aoption] = 0
      else:
        self.optionstates[aoption] = 1

    if mstate:
      mstate = 1
      if self.optionstates[aoption] == 0:
        self.api('libs.io:send:msg')('Enabling A102 option: %s' % \
                                              AOPTIONREV[aoption])
        cmd = '%s%s' % (chr(aoption), ON)
        self.api('sendmud')(cmd)
      self.optionstates[aoption] = self.optionstates[aoption] + 1

    else:
      mstate = 2
      self.optionstates[aoption] = self.optionstates[aoption] - 1
      if self.optionstates[aoption] == 0:
        self.api('libs.io:send:msg')('Disabling A102 option: %s' % \
                                              AOPTIONREV[aoption])
        cmd = '%s%s' % (chr(aoption), OFF)
        self.api('sendmud')(cmd)

  def a102fromserver(self, args):
    """
    handle stuff from the server
    """
    self.api('core.events:raise:event')(self.option_name, args)
    self.api('core.events:raise:event')('%s:%s' % (self.option_name, args['option']), args)

  def a102request(self, _=None):
    """
    this function is called when the a102 option is enabled
    """
    self.api('libs.io:send:msg')('cleaning a102 queues')
    if not self.reconnecting:
      for i in self.a102optionqueue:
        self.a102toggleoption(i['option'], i['toggle'])
    else:
      self.reconnecting = False
      for i in self.optionstates:
        tnum = self.optionstates[i]
        if tnum > 0:
          self.api('libs.io:send:msg')('Re-Enabling A102 option: %s' % \
                                                    AOPTIONREV[i])
          cmd = '%s%s' % (i, 1)
          self.api('sendmud')(cmd)
        else:
          self.api('libs.io:send:msg')('Re-Disabling A102 option: %s' % \
                                                    AOPTIONREV[i])
          cmd = '%s%s' % (i, 2)
          self.api('sendmud')(cmd)

  def a102fromclient(self, args):
    """
    this function is called when we receive an a102 option from the client
    """
    mud = self.api('managers:get')('mud')
    data = args['data']
    option = ord(data[0])
    mstate = ord(data[1])
    mstate = bool(mstate)
    if not mud.connected:
      self.a102optionqueue.append({'option':option, 'toggle':mstate})
    else:
      self.a102toggleoption(option, mstate)

# Server
class SERVER(BaseTelnetOption):
  """
  a class to handle aard102 for the server
  """
  def __init__(self, telnet_object, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_number, plugin_id)

  def handleopt(self, command, sbdata):
    """
    handle the a102 option from the server
    """
    self.telnet_object.msg('%s - in handleopt' % self.telnet_object.ccode(command),
                           level=2, mtype=self.option_name)
    if command == WILL:
      self.telnet_object.msg('sending IAC DO A102', level=2, mtype=self.option_name)
      self.telnet_object.send(IAC + DO + self.option_string)
      self.telnet_object.options[ord(self.option_string)] = True
      self.plugin.api('core.events:raise:event')('A102:server-enabled', {})

    elif command in [SB, SE]:
      if not self.telnet_object.options[ord(self.option_string)]:
        print '##BUG: Enabling A102, missed negotiation'
        self.telnet_object.options[ord(self.option_string)] = True
        self.plugin.api('core.events:raise:event')('A102:server-enabled', {})

      tdata = {}
      tdata['option'] = ord(sbdata[0])
      tdata['flag'] = ord(sbdata[1])
      tdata['server'] = self.telnet_object
      self.telnet_object.msg('got %s,%s from server' % \
              (tdata['option'], tdata['flag']), level=2, mtype=self.option_name)
      self.plugin.api('libs.io:send:client')('%s%s%s%s%s%s' % \
                                  (IAC, SB, self.option_string,
                                   sbdata.replace(IAC, IAC+IAC), IAC, SE),
                                             raw=True, dtype=self.option_string)
      self.plugin.api('core.events:raise:event')('A102_from_server', tdata)

# Client
class CLIENT(BaseTelnetOption):
  """
  a class to handle a102 options from the client
  """
  def __init__(self, telnet_object, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_number, plugin_id)
    self.telnet_object.msg('sending IAC WILL A102', mtype=self.option_name)
    self.telnet_object.addtooutbuffer(IAC + WILL + self.option_string, True)

  def handleopt(self, command, sbdata):
    """
    handle the a102 option for the client
    """
    self.telnet_object.msg('%s - in handleopt' % self.telnet_object.ccode(command), mtype=self.option_name)
    if command == DO:
      self.telnet_object.msg('setting options[A102] to True', mtype=self.option_name)
      self.telnet_object.options[ord(self.option_string)] = True
    elif command in [SB, SE]:
      self.plugin.api('core.events:raise:event')('A102_from_client',
                                                 {'data': sbdata,
                                                  'client':self.telnet_object})
