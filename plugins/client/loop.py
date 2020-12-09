"""
This plugin loops commands for a specified number of times

## Example
 * ```#bp.loop.cmd -c 10 "get all ${num}.corpse"```
   will get all from 1.corpse, 2.corpse, 3.corpse, etc.

"""
from string import Template
import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Loop'
SNAME = 'loop'
PURPOSE = 'loop a command multiple times'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True


class Plugin(BasePlugin):
  """
  a plugin to handle looping of commands
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
                                 description='loop a command')
    parser.add_argument('cmd',
                        help='the command to run',
                        default='',
                        nargs='?')
    parser.add_argument('-c',
                        "--count",
                        help="how many times to execute the command",
                        default=1)
    self.api('core.commands:command:add')('cmd',
                                          self.cmd_loop,
                                          parser=parser)

    # self.api('commands.default')('cmd')

  def cmd_loop(self, args):
    """
    loop a command count times
    """
    tmsg = []
    count = int(args['count'])
    if count < 1 or count > 50:
      return True, ['Count has to be between 1 and 50']

    if args['cmd']:
      templ = Template(args['cmd'])
      for i in xrange(1, count + 1):
        datan = templ.safe_substitute({'num':i, 'count':i})
        self.api('libs.io:send:msg')('sending cmd: %s' % datan)
        self.api('libs.io:send:execute')(datan)
      return True, ['"%s" was sent %s times' % (args['cmd'], count)]

    tmsg.append("@RPlease include all arguments@w")
    return False, tmsg
