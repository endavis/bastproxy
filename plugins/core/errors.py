"""
This plugin shows and clears errors seen during plugin execution
"""
import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Error Plugin'
SNAME = 'errors'
PURPOSE = 'show and manage errors'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 2

REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to handle errors
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.errors = []

    self.api('api.add')('add', self.api_adderror)
    self.api('api.add')('gete', self.api_geterrors)
    self.api('api.add')('clear', self.api_clearerrors)

    self.dependencies = []

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='show errors')
    parser.add_argument('number',
                        help='list the last <number> errors',
                        default='-1',
                        nargs='?')
    self.api('commands.add')('show',
                             self.cmd_show,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='clear errors')
    self.api('commands.add')('clear',
                             self.cmd_clear,
                             parser=parser)

    self.api('events.register')('proxy_ready', self.proxy_ready)

  # show all errors that happened during startup
  def proxy_ready(self, _=None):
    """
    show all errors that happened during startup
    """
    errors = self.api('errors.gete')()

    msg = ['The following errors happened during startup:']
    if errors:
      for i in errors:
        msg.append('')
        msg.append('Time: %s' % i['timestamp'])
        msg.append('Error: %s' % i['msg'])

      self.api('send.error')('\n'.join(msg))


  # add an error to the list
  def api_adderror(self, timestamp, error):
    """add an error

    this function adds an error to the list
    """
    self.errors.append({'timestamp':timestamp,
                        'msg':error})

  # get the errors that have been seen
  def api_geterrors(self):
    """ get errors

    this function has no arguments

    this function returns the list of errors
    """
    return self.errors

  # clear errors
  def api_clearerrors(self):
    """ clear errors

    this function has no arguments

    this function returns no values
    """
    self.errors = []

  def cmd_show(self, args=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      show the error queue
      @CUsage@w: show
    """
    msg = []
    try:
      number = int(args['number'])
    except ValueError:
      msg.append('Please specify a number')
      return False, msg

    errors = self.api('errors.gete')()

    if not errors:
      msg.append('There are no errors')
    else:
      if args and number > 0:
        for i in errors[-int(number):]:
          msg.append('')
          msg.append('Time: %s' % i['timestamp'])
          msg.append('Error: %s' % i['msg'])

      else:
        for i in errors:
          msg.append('')
          msg.append('Time: %s' % i['timestamp'])
          msg.append('Error: %s' % i['msg'])

    return True, msg

  def cmd_clear(self, args=None):
    # pylint: disable=unused-argument
    """
    clear errors
    """
    self.api('errors.clear')()

    return True, ['Errors cleared']
