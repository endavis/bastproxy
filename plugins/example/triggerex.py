"""
$Id$
"""
from libs import exported
from plugins import BasePlugin

NAME = 'Trigger Example'
SNAME = 'triggerex'
PURPOSE = 'examples for using triggers'
AUTHOR = 'Bast'
VERSION = 1

AUTOLOAD = False

class Plugin(BasePlugin):
  """
  a plugin to show how to use triggers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.triggers['example_trigger'] = \
            {'regex':"^(?P<name>.*) flicks a (?P<insect>.*) off his bar\.$"}
    self.event.register('trigger_example_trigger', self.testtrigger)

  def testtrigger(self, args):
    """
    show that the trigger fired
    """
    exported.sendtoclient('Trigger fired: args returned %s' % args)

