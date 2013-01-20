
"""
This module handles all things GMCP

SERVER handles all GMCP communication to and from the MUD
CLIENT handles all GMCP communication to and from a client

GMCP_MANAGER takes GMCP data, caches it and then creates three events
GMCP
GMCP:<base module name>
GMCP:<full module name>

The args for the event will look like
{'data': {u'clan': u'', u'name': u'Bast', u'perlevel': 6000, 
          u'remorts': 1, u'subclass': u'Ninja', u'race': u'Shadow', 
          u'tier': 6, u'class': u'Thief', u'redos': u'0', u'pretitle': u''}, 
 'module': 'char.base'}

It adds the following functions to exported
#TODO Test These
gmcp.getgmcp(module) - get data that is in cache for the specified gmcp module
gmcp.sendgmcppacket(what) - send a gmcp packet to the mud with the specified contents
gmcp.togglegmcpmodule(modname, mstate) - toggle the gmcp module with modname, mstate should be True or False

To get GMCP data:
1: Save the data from the event
2: Use exported.getgmcp(module)

"""

from libs.net.options._option import TelnetOption
from libs.net.telnetlib import WILL, DO, IAC, SE, SB
from libs import exported

GMCP = chr(201)
GMCPMAN = None
canreload = True

class dotdict(dict):
    def __getattr__(self, attr):
      return self.get(attr, dotdict())
    __setattr__= dict.__setitem__
    __delattr__= dict.__delitem__
    
    
#IAC SB GMCP <atcp message text> IAC SE
def sendgmcppacket(what):
  exported.processevent('to_mud_event', {'data':'%s%s%s%s%s%s' % (IAC, SB, GMCP, what.replace(IAC, IAC+IAC), IAC, SE), 'raw':True, 'dtype':GMCP})  
    
    
# Server
class SERVER(TelnetOption):
  def __init__(self, telnetobj):
    TelnetOption.__init__(self, telnetobj, GMCP)
    self.telnetobj.debug_types.append('GMCP')

  def handleopt(self, command, sbdata):
    self.telnetobj.msg('GMCP:', ord(command), '- in handleopt', level=2, mtype='GMCP')
    if command == WILL:
      self.telnetobj.msg('GMCP: sending IAC DO GMCP', level=2, mtype='GMCP')
      self.telnetobj.send(IAC + DO + GMCP)
      
    elif command == SE:
      self.telnetobj.options[ord(GMCP)] = True        
      data = sbdata
      modname, data = data.split(" ", 1)
      import json
      newdata = json.loads(data)
      self.telnetobj.msg(modname, data, level=2, mtype='GMCP')
      self.telnetobj.msg(type(newdata), newdata, level=2, mtype='GMCP')
      tdata = {}
      tdata['data'] = newdata
      tdata['module'] = modname
      exported.processevent('to_user_event', {'todata':'%s%s%s%s%s%s' % (IAC, SB, GMCP, sbdata.replace(IAC, IAC+IAC), IAC, SE), 'raw':True, 'dtype':GMCP})      
      exported.processevent('GMCP_raw', tdata)


# Client
class CLIENT(TelnetOption):
  def __init__(self, telnetobj):
    TelnetOption.__init__(self, telnetobj, GMCP)
    self.telnetobj.msg('GMCP: sending IAC WILL GMCP', mtype='GMCP')    
    self.telnetobj.addtooutbuffer(IAC + WILL + GMCP, True)
    self.cmdqueue = []
    
  def handleopt(self, command, sbdata):
    self.telnetobj.msg('GMCP:', ord(command), '- in handleopt', mtype='GMCP')
    if command == DO:
      self.telnetobj.msg('GMCP:setting options["GMCP"] to True', mtype='GMCP')    
      self.telnetobj.options[ord(GMCP)] = True        
    elif command == SE:
      exported.processevent('GMCP_from_client', {'data': sbdata})
      
      
# Manager
class GMCP_MANAGER:
  def __init__(self):
    """
    Iniitilaize the class
    
    self.gmcpcache - the cache of values for different GMCP modules
    self.modstates - the current counter for what modules have been enabled
    self.gmcpqueue - the queue of gmcp commands that the client sent before connected to the server
    self.gmcpmodqueue - the queue of gmcp modules that were enabled by the client before connected to the server
    """
    self.name = 'GMCP'

    self.gmcpcache = {}
    self.modstates = {}
    self.gmcpqueue = []
    self.gmcpmodqueue = []   
    
    self.reconnecting = False   

  def disconnect(self, args):
    exported.debug('setting reconnect to true')
    self.reconnecting = True    

  def togglegmcpmodule(self, modname, mstate):
      
    if not (modname in self.modstates):
      self.modstates[modname] = 0
    
    if mstate:
      if self.modstates[modname] == 0:
        exported.debug('Enabling GMCP module', modname)
        cmd = 'Core.Supports.Set [ "%s %s" ]' % (modname, 1)
        sendgmcppacket(cmd)
      self.modstates[modname] = self.modstates[modname] + 1
      
    else:
      self.modstates[modname] = self.modstates[modname] - 1
      if self.modstates[modname] == 0:
        exported.debug('Disabling GMCP module', modname)
        cmd = 'Core.Supports.Set [ "%s %s" ]' % (modname, 0)
        sendgmcppacket(cmd)       
    
  def getgmcp(self, module):
    mods = module.split('.')  
    mods = [x.lower() for x in mods]
    tlen = len(mods)
      
    currenttable = self.gmcpcache
    previoustable = dotdict()
    for i in range(0,tlen):
      if not (mods[i] in currenttable):
        return None
      
      previoustable = currenttable
      currenttable = currenttable[mods[i]]
      
    return currenttable
    
  def gmcpraw(self, args):
    modname = args['module'].lower()

    mods = modname.split('.')  
    mods = [x.lower() for x in mods]    
    tlen = len(mods)
      
    currenttable = self.gmcpcache
    previoustable = dotdict()
    for i in range(0,tlen):
      if not (mods[i] in currenttable):
        currenttable[mods[i]] = dotdict()
      
      previoustable = currenttable
      currenttable = currenttable[mods[i]]
      
    previoustable[mods[tlen - 1]] = dotdict(args['data'])
    
    exported.processevent('GMCP', args)
    exported.processevent('GMCP:%s' % modname, args)
    exported.processevent('GMCP:%s' % mods[0], args)
    
  def requestgmcp(self, args):
    exported.debug('cleaning gmcp queues')
    if not self.reconnecting:
      print(self.gmcpmodqueue)
      for i in self.gmcpmodqueue:
        self.togglegmcpmodule(i['modname'],i['toggle'])
    else:
      reconnecting = False
      for i in self.modstates:
        v = self.modstates[i]
        if v > 0:
          exported.debug('Re-Enabling GMCP module',i)
          cmd = 'Core.Supports.Set [ "%s %s" ]' % (i, 1)
          sendgmcppacket(cmd)        
        
    for i in self.gmcpqueue:
      sendgmcppacket(i)    
  
  def clientgmcp(self, args):
    data = args['data']
    if 'core.supports.set' in data.lower():
      mods = data[data.find("[")+1:data.find("]")].split(',')
      for i in mods:
        tmod = i.strip()
        tmod = tmod[1:-1]
        modname, toggle = tmod.split()
        if int(toggle) == 1:
          toggle = True
        else:
          toggle = False
            
        if not exported.connected:
          self.gmcpmodqueue.append({'modname':modname, 'toggle':toggle})
        else:
          self.togglegmcpmodule(modname, toggle)
    else:
      if not exported.connected:
        self.gmcpqueue.append(data)
      else:
        sendgmcppacket(data)  
  
  def load(self):
    exported.registerevent('GMCP_raw', self.gmcpraw)
    exported.registerevent('GMCP_from_client', self.clientgmcp)
    exported.registerevent('mudconnect', self.requestgmcp)
    exported.registerevent('muddisconnect', self.disconnect)
    exported.gmcp = dotdict()
    exported.gmcp['getgmcp'] = self.getgmcp
    exported.gmcp['sendgmcppacket'] = sendgmcppacket
    exported.gmcp['togglegmcpmodule'] = self.togglegmcpmodule    
    
  def unload(self):
    exported.unregisterevent('GMCP_raw', self.gmcpraw)
    exported.unregisterevent('GMCP_from_client', self.clientgmcp)
    exported.unregisterevent('mudconnect', self.requestgmcp)
    exported.unregisterevent('muddisconnect', self.disconnect)
    export.gmcp = None  
  
    
def load():
  GMCPMAN = GMCP_MANAGER()
  GMCPMAN.load()


def unload():
  GMCPMAN.unload()
