"""
This plugins handles TCP option 201, GMCP (aardwolf implementation)

see the [Aardwolf Wiki](http://www.aardwolf.com/wiki/index.php/Clients/GMCP)
"""
import pprint
import libs.argp as argp
from libs.net._basetelnetoption import BaseTelnetOption
from libs.net.telnetlib import WILL, DO, IAC, SE, SB, CODES
from libs.persistentdict import convert
from plugins._baseplugin import BasePlugin

NAME = 'GMCP'
SNAME = 'GMCP'
PURPOSE = 'Handle telnet option 201, GMCP'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

REQUIRED = True

GMCP = chr(201)

CODES[201] = '<GMCP>'

# Plugin
class Plugin(BasePlugin):
  """
  a plugin to handle gmcp
  """
  def __init__(self, *args, **kwargs):
    """
    Iniitialize the class

    self.gmcpcache - the cache of values for different GMCP modules
    self.modstates - the current counter for what modules have been enabled
    self.gmcpqueue - the queue of gmcp commands that the client sent
              before connected to the server
    self.gmcpmodqueue - the queue of gmcp modules that were enabled by
              the client before connected to the server
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.gmcpcache = {}
    self.modstates = {}
    self.gmcpqueue = []
    self.gmcpmodqueue = []

    self.reconnecting = False

    self.api('dependency.add')('net.options')

    self.api('api.add')('sendmud', self.api_sendmud)
    self.api('api.add')('sendmodule', self.api_sendmodule)
    self.api('api.add')('togglemodule', self.api_togglemodule)
    self.api('api.add')('getv', self.api_getv)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('events.register')('GMCP_raw', self.gmcpfromserver)
    self.api('events.register')('GMCP_from_client', self.gmcpfromclient)
    self.api('events.register')('GMCP:server-enabled', self.gmcprequest)
    self.api('events.register')('muddisconnect', self.gmcpdisconnect)

    self.api('options.addserveroption')(self.short_name, SERVER)
    self.api('options.addclientoption')(self.short_name, CLIENT)

    parser = argp.ArgumentParser(add_help=False,
                                 description='send something through GMCP')
    parser.add_argument('stuff',
                        help='the item to send through GCMP',
                        default='',
                        nargs='?')
    self.api('commands.add')('send',
                             self.cmd_send,
                             showinhistory=False,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='show an item in the cache')
    parser.add_argument('item',
                        help='the item to show',
                        default='',
                        nargs='?')
    self.api('commands.add')('cache',
                             self.cmd_cache,
                             showinhistory=False,
                             parser=parser)

  def cmd_cache(self, args):
    """
    see the cache
    """
    tmsg = []
    if args['item'] == '':
      tmsg.append('Full cache')
      tmsg.append('--------------------------------------------')
      tmsg.append(pprint.pformat(self.gmcpcache))
    else:
      tmsg.append(args['item'])
      tmsg.append('--------------------------------------------')
      tmsg.append(pprint.pformat(self.api('GMCP.getv')(args['item'])))

    return True, tmsg

  def cmd_send(self, args):
    """
    send a gmcp packet
    """
    tmsg = []
    if not args['stuff']:
      tmsg.append('Please supply a command')
    else:
      command = args['stuff']
      self.api('GMCP.sendmud')(command)
      tmsg.append('Send "%s" to GMCP' % command)

    return True, tmsg

  # send a GMCP packet
  def api_sendmud(self, message):
    """  send a GMCP packet
    @Ymessage@w  = the message to send

    this function returns no values

    Format: IAC SB GMCP <gmcp message text> IAC SE"""
    self.api('send.mud')('%s%s%s%s%s%s' % \
                (IAC, SB, GMCP, message.replace(IAC, IAC+IAC), IAC, SE),
                         raw=True, dtype=GMCP)

  def gmcpdisconnect(self, _=None):
    """
    disconnect
    """
    self.api('send.msg')('setting reconnect to true')
    self.reconnecting = True

  # toggle a GMCP module
  def api_togglemodule(self, modname, mstate):
    """  toggle a GMCP module
    @Ymodname@w  = the GMCP module to toggle
    @Ymstate@w  = the state, either True or False

    this function returns no values"""
    if modname not in self.modstates:
      self.modstates[modname] = 0

    if mstate:
      if self.modstates[modname] == 0:
        self.api('send.msg')('Enabling GMCP module: %s' % modname)
        cmd = 'Core.Supports.Set [ "%s %s" ]' % (modname, 1)
        self.api('GMCP.sendmud')(cmd)
      self.modstates[modname] = self.modstates[modname] + 1

    else:
      self.modstates[modname] = self.modstates[modname] - 1
      if self.modstates[modname] == 0:
        self.api('send.msg')('Disabling GMCP module: %s' % modname)
        cmd = 'Core.Supports.Set [ "%s %s" ]' % (modname, 0)
        self.api('GMCP.sendmud')(cmd)

  # get a GMCP value/module from the cache
  def api_getv(self, module):
    """  get a GMCP value/module from the cache
    @Ymodule@w  = the module to get

    this function returns a table or value depending on what is requested"""
    mods = module.split('.')
    mods = [x.lower() for x in mods]
    tlen = len(mods)

    currenttable = self.gmcpcache

    for i in range(0, tlen):
      if mods[i] not in currenttable:
        return None

      #previoustable = currenttable
      currenttable = currenttable[mods[i]]

    return currenttable

  # send a GMCP module to all clients that support GMCP
  def api_sendmodule(self, modname):
    """  send a GMCP module to clients that support GMCP
    @Ymodname@w  = the module to send to clients

    this function returns no values"""
    data = self.api('GMCP.getv')(modname)
    if data:
      import json
      tdata = json.dumps(data)
      tpack = '%s %s' % (modname, tdata)
      self.api('send.client')('%s%s%s%s%s%s' % \
                 (IAC, SB, GMCP, tpack.replace(IAC, IAC+IAC), IAC, SE),
                              raw=True, dtype=GMCP)

  def gmcpfromserver(self, args):
    """
    handle gmcp data from the server
    """
    modname = args['module'].lower()
    mods = modname.split('.')
    mods = [x.lower() for x in mods]

    if modname != 'room.wrongdir':
      tlen = len(mods)

      currenttable = self.gmcpcache
      previoustable = {}
      for i in range(0, tlen):
        if mods[i] not in currenttable:
          currenttable[mods[i]] = {}

        previoustable = currenttable
        currenttable = currenttable[mods[i]]

      previoustable[mods[tlen - 1]] = {}
      datatable = previoustable[mods[tlen - 1]]

      for i in args['data']:
        try:
          datatable[i] = args['data'][i]
        except TypeError:
          msg = []
          msg.append("TypeError: string indices must be integers")
          msg.append('i: %s' % i)
          msg.append('datatable: %s' % datatable)
          msg.append('args: %s' % args)
          msg.append('args[data]: %s' % args['data'])
          self.api('send.traceback')('\n'.join(msg))

    self.api('send.msg')('%s : %s' % (args['module'], args['data']))
    self.api('events.eraise')('GMCP', args)
    self.api('events.eraise')('GMCP:%s' % modname, args)
    self.api('events.eraise')('GMCP:%s' % mods[0], args)

  def gmcprequest(self, _=None):
    """
    handle a gmcp request
    """
    if not self.reconnecting:
      for i in self.gmcpmodqueue:
        self.api('GMCP.togglemodule')(i['modname'], i['toggle'])
      self.gmcpmodqueue = []
    else:
      self.reconnecting = False
      for i in self.modstates:
        tnum = self.modstates[i]
        if tnum > 0:
          self.api('send.msg')('Re-Enabling GMCP module %s' % i)
          cmd = 'Core.Supports.Set [ "%s %s" ]' % (i, 1)
          self.api('GMCP.sendmud')(cmd)

    for i in self.gmcpqueue:
      self.api('GMCP.sendmud')(i)
    self.gmcpqueue = []

  def gmcpfromclient(self, args):
    """
    handle gmcp data from the client
    """
    mud = self.api('managers.getm')('mud')
    data = args['data']
    if 'core.supports.set' in data.lower():
      mods = data[data.find("[")+1:data.find("]")].split(',')
      for i in mods:
        tmod = i.strip()
        tmod = tmod[1:-1]
        modname, toggle = tmod.split()

        toggle = bool(toggle)

        if not mud.connected:
          self.gmcpmodqueue.append({'modname':modname, 'toggle':toggle})
        else:
          self.api('GMCP.togglemodule')(modname, toggle)
    elif 'rawcolor' in data.lower() or 'group' in data.lower():
      # we only support "rawcolor on" right now, the json parser doesn't like
      # ascii codes, we also turn on group and leave it on
      return
    else:
      if not mud.connected:
        if data not in self.gmcpqueue:
          self.gmcpqueue.append(data)
      else:
        self.api('GMCP.sendmud')(data)

# Server
class SERVER(BaseTelnetOption):
  """
  a class to handle gmcp data from the server
  """
  def __init__(self, telnetobj):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnetobj, GMCP, SNAME)

    #self.telnetobj.debug_types.append('GMCP')

  def handleopt(self, command, sbdata):
    """
    handle the gmcp option
    """
    self.telnet_object.msg('CMD: %s - in handleopt' % self.telnet_object.ccode(command),
                           level=2, mtype='GMCP')
    self.telnet_object.msg('DATA: "%s"- in handleopt' % (sbdata),
                           level=2, mtype='GMCP')

    # yes, I support GMCP
    if command == WILL:
      self.telnet_object.msg('sending IAC DO GMCP', level=2, mtype='GMCP')
      self.telnet_object.send("".join([IAC, DO, GMCP]))
      self.telnet_object.options[ord(GMCP)] = True
      self.plugin.api('events.eraise')('GMCP:server-enabled', {})

    # GMCP data
    elif command in [SE, SB]:
      if not self.telnet_object.options[ord(GMCP)]:
        # somehow we missed negotiation, so enable GMCP
        self.telnet_object.msg('##BUG: Enabling GMCP, missed negotiation',
                               level=2, mtype='GMCP')
        self.telnet_object.options[ord(GMCP)] = True
        self.plugin.api('events.eraise')('GMCP:server-enabled', {})

      data = sbdata
      # split it for further use
      modname, data = data.split(" ", 1)
      try:
        import json
        newdata = json.loads(data.decode('utf-8', 'ignore'),
                             object_hook=convert)
      except (UnicodeDecodeError, ValueError):
        newdata = {}
        self.plugin.api('send.traceback')('Could not decode: %s' % data)
      self.telnet_object.msg("mod: %s, data: '%s'" % (modname, data), level=2, mtype='GMCP')
      self.telnet_object.msg("modtype: %s, data %s" % (type(newdata), newdata),
                             level=2, mtype='GMCP')
      tdata = {}
      tdata['data'] = newdata
      tdata['module'] = modname
      tdata['server'] = self.telnet_object

      # pass it through to the client
      self.plugin.api('send.client')('%s%s%s%s%s%s' % \
                 (IAC, SB, GMCP, sbdata.replace(IAC, IAC+IAC), IAC, SE),
                                     raw=True, dtype=GMCP)

      # raise it for internal use
      self.plugin.api('events.eraise')('GMCP_raw', tdata)

# Client
class CLIENT(BaseTelnetOption):
  """
  a class to handle gmcp data from a client
  """
  def __init__(self, telnet_object):
    """
    initalize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, GMCP, SNAME)
    #self.telnet_object.debug_types.append('GMCP')
    self.telnet_object.msg('sending IAC WILL GMCP', mtype='GMCP')
    self.telnet_object.addtooutbuffer("".join([IAC, WILL, GMCP]), True)

  def handleopt(self, command, sbdata):
    """
    handle gmcp data from a client
    """
    self.telnet_object.msg('%s - in handleopt' % self.telnet_object.ccode(command), mtype='GMCP')
    if command == DO:
      self.telnet_object.msg('setting options["GMCP"] to True',
                             mtype='GMCP')
      self.telnet_object.options[ord(GMCP)] = True
    elif command in [SE, SB]:
      self.plugin.api('events.eraise')('GMCP_from_client',
                                       {'data': sbdata, 'client':self.telnet_object})
