"""
This plugin is an example plugin to show how to use gmcp

## Using GMCP
 * register to the GMCP event and check which option it was
 * register to the "GMCP:[module]" event
  * example: GMCP:char

 see the [Aardwolf Wiki](http://www.aardwolf.com/wiki/index.php/Clients/GMCP)
"""
import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'GMCP Test'
SNAME = 'gmcpex'
PURPOSE = 'examples for using the gmcp plugin'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(BasePlugin):
  """
  a plugin to show gmcp usage
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency.add')('net.GMCP')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('events.register')('GMCP', self.test)
    self.api('events.register')('GMCP:char', self.testchar)
    self.api('events.register')('GMCP:char.status', self.testcharstatus)

    parser = argp.ArgumentParser(
        add_help=False,
        description='print what is in a module in the gmcp cache')
    parser.add_argument('module',
                        help='the module to show',
                        default='',
                        nargs='?')
    self.api('commands.add')('get',
                             self.cmd_get,
                             parser=parser)

  def cmd_get(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      print an item from the gmcpcache
      @CUsage@w: rem @Y<gmcpmod>@w
        @Ygmcpmod@w    = The gmcp module to print, such as char.status
    """
    if args['module']:
      return True, ['%s' % self.api('GMCP.getv')(args['module'])]

    return False

  def test(self, args):
    """
    show the gmcp event
    """
    self.api('send.client')(
        '@x52@z192 Event @w- @GGMCP@w: @B%s@w : %s' % \
                  (args['module'], args['data']))

  def testchar(self, args):
    """
    show the gmcp char event
    """
    getv = self.api('GMCP.getv')
    msg = []
    msg.append('testchar --------------------------')
    tchar = getv('char')
    msg.append('%s' % tchar)
    if tchar and tchar.status:
      msg.append('char.status.state from tchar')
      msg.append('%s' % tchar.status.state)
    else:
      msg.append('Do not have status')
    msg.append('char.status.state with getting full')
    cstate = getv('char.status.state')
    if cstate:
      msg.append('Got state: %s' % cstate)
    else:
      msg.append('did not get state')
    msg.append('getting a module that doesn\'t exist')
    msg.append('%s' % getv('char.test'))
    msg.append('getting a variable that doesn\'t exist')
    msg.append('%s' % getv('char.status.test'))

    self.api('send.msg')('\n'.join(msg))
    self.api('send.client')('@CEvent@w - @GGMCP:char@w: %s' % \
                                  args['module'])

  def testcharstatus(self, _=None):
    """
    show the gmcp char.status event
    """
    self.api('send.client')('@CEvent@w - @GGMCP:char.status@w')
