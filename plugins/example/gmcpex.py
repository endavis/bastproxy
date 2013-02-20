"""
$Id$
"""

from libs import exported
from plugins import BasePlugin

name = 'GMCP Test'
sname = 'gmcpex'
purpose = 'examples for using the gmcp plugin'
author = 'Bast'
version = 1

autoload = False

class Plugin(BasePlugin):
  def __init__(self, name, sname, filename, directory, importloc):
    BasePlugin.__init__(self, name, sname, filename, directory, importloc) 
    self.events.append({'event':'GMCP', 'func':self.test})
    self.events.append({'event':'GMCP:char', 'func':self.testchar})
    self.events.append({'event':'GMCP:char.status', 'func':self.testcharstatus})
    self.cmds['get'] = {'func':self.cmd_get, 'shelp':'print what is in the gmcp cache'}
    self.defaultcmd = 'get'
    
  def cmd_get(self, args):
    """---------------------------------------------------------------
@G%(name)s@w - @B%(cmdname)s@w
  print an item from the gmcpcache
  @CUsage@w: rem @Y<gmcpmod>@w
    @Ygmcpmod@w    = The gmcp module to print, such as char.status
---------------------------------------------------------------"""    
    if len(args) > 0:
      exported.sendtoclient()
      return True, ['%s' % exported.gmcp.getv(args[0])]
    
    return False

  def test(self, args):
    exported.sendtoclient('@x52@z192 Event @w- @GGMCP@w: @B%s@w : %s' % (args['module'], args['data']))

  def testchar(self, args):
    msg = []
    msg.append('testchar --------------------------')
    tchar = exported.gmcp.getv('char')
    msg.append(tchar)
    if tchar and tchar.status:
      msg.append('char.status.state from tchar')
      msg.append(tchar.status.state)
    else:
      msg.append('Do not have status')
    msg.append('char.status.state with getting full')
    cstate = exported.gmcp.getv('char.status.state')
    if cstate:
      msg.append('Got state: %s' % cstate)
    else:
      msg.append('did not get state')
    msg.append('getting a module that doesn\'t exist')
    msg.append(exported.gmcp.getv('char.test'))
    msg.append('getting a variable that doesn\'t exist')
    msg.append(exported.gmcp.getv('char.status.test'))
    self.msg('\n'.join(msg))
    
    exported.sendtoclient('@CEvent@w - @GGMCP:char@w: %s' % args['module'])

  def testcharstatus(self, args):
    exported.sendtoclient('@CEvent@w - @GGMCP:char.status@w')

  
