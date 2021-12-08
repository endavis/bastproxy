"""
This is an example plugin about how to use triggers

## Using
### Add the regex
 * ```self.api('core.triggers:trigger:add')('testtrig', "^some test$")```
### Register a function to the event
 * ```self.api('core.events:register:to:event')('ev_core.triggers_testtrig', somefunc)```
"""
from plugins._baseplugin import BasePlugin

NAME = 'Trigger Example'
SNAME = 'triggerex'
PURPOSE = 'examples for using triggers'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(BasePlugin):
  """
  a plugin to show how to use triggers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('core.triggers')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('core.triggers:trigger:add')(
        'example_trigger',
        r"^(?P<name>.*) flicks a (?P<insect>.*) off his bar\.$")
    self.api('core.triggers:trigger:register')('example_trigger', self.testtrigger)

  def testtrigger(self, args):
    """
    show that the trigger fired
    """
    self.api('libs.io:send:client')('Trigger fired: args returned %s' % args)
