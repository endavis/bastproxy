"""
This plugin will show api functions and details
"""
import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'API help'
SNAME = 'apihelp'
PURPOSE = 'show info about the api'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True


class Plugin(BasePlugin):
  """
  a plugin to show connection information
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list functions in the api')
    parser.add_argument('toplevel',
                        help='the top level api to show (optional)',
                        default='', nargs='?')
    self.api('commands.add')('list', self.cmd_list,
                             parser=parser)
    parser = argp.ArgumentParser(add_help=False,
                                 description='detail a function in the api')
    parser.add_argument('api', help='the api to detail (optional)',
                        default='', nargs='?')
    self.api('commands.add')('detail', self.cmd_detail,
                             parser=parser)


  def cmd_detail(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    detail a function in the api
      @CUsage@w: detail @Y<api>@w
      @Yapi@w = (optional) the api to detail
    """
    tmsg = []
    if args['api']:
      tmsg.extend(self.api('api.detail')(args['api']))

    else: # args <= 0
      tmsg.append('Please provide an api to detail')

    return True, tmsg

  def cmd_list(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    List functions in the api
      @CUsage@w: list @Y<apiname>@w
      @Yapiname@w = (optional) the toplevel api to show
    """
    tmsg = []
    apilist = self.api('api.list')(args['toplevel'])
    if not apilist:
      tmsg.append('%s does not exist in the api' % args['toplevel'])
    else:
      tmsg.extend(apilist)

    return True, tmsg
