"""
This plugin holds a plugin to check garbage collection
"""
import gc
import pprint
from plugins._baseplugin import BasePlugin
import libs.argp as argp

NAME = 'Garbage Collection'
PURPOSE = 'check garbage collection for objects'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to test command parsing
  """
  def __init__(self, *args, **kwargs):
    """
    init the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.dependencies = []


  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='send a link')
    parser.add_argument('plugin_id',
                        help='the title of the link',
                        default='net.clients',
                        nargs='?')
    self.api('core.commands:command:add')('show',
                                          self.cmd_plugin,
                                          shelp='list plugin object references',
                                          parser=parser)

  def cmd_plugin(self, args=None): # pylint: disable=unused-argument
    """
    find plugins and their references
    """
    parser = argp.ArgumentParser(add_help=False,
                                 description='send a note')
    parser.add_argument('title',
                        help='the title of the note',
                        default='Pushbullet note from bastproxy',
                        nargs='?')

    plugin_id = args['plugin_id']

    test_plugin = self.api('core.plugins:get:plugin:instance')(plugin_id)
    if not test_plugin:
      return True, ['Plugin %s does not exist' % plugin_id]

    referrals = gc.get_referrers(test_plugin)

    msg = []
    for item in referrals:
      msg.append('item:\n  %s'% pprint.pformat(item, indent=4))
      print('item:\n', pprint.pformat(item))

    return True, msg
