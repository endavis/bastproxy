"""
this module is for saving settings that should not appear in memory
the setting is saved to a file with read only permissions for the user
the proxy is running under

## Using
See the source for [net.proxy](/bastproxy/plugins/net/proxy.html)
for an example of using this plugin

'''python
    ssc = self.plugin.api('core.ssc:baseclass:get')()
    self.plugin.apikey = ssc('somepassword', self, desc='Password for something')
'''
"""
import os
import stat

import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Secret Setting Class'
SNAME = 'ssc'
PURPOSE = 'Class to save settings that should not stay in memory'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class SSC(object):
  """
  a class to manage settings
  """
  def __init__(self, name, plugin, **kwargs):
    """
    initialize the class
    """
    self.name = name
    self.plugin = plugin

    if 'default' in kwargs:
      self.default = kwargs['default']
    else:
      self.default = ''

    if 'desc' in kwargs:
      self.desc = kwargs['desc']
    else:
      self.desc = 'setting'

    self.plugin.api('libs.api:add')('ssc:%s' % self.name, self.getss)

    parser = argp.ArgumentParser(add_help=False,
                                 description='set the %s' % self.desc)
    parser.add_argument('value',
                        help=self.desc,
                        default='',
                        nargs='?')
    self.plugin.api('core.commands:command:add')(self.name,
                                                 self.cmd_setssc,
                                                 showinhistory=False,
                                                 parser=parser)


  # read the secret from a file
  def getss(self):
    """
    read the secret from a file
    """
    first_line = ''
    file_name = os.path.join(self.plugin.save_directory, self.name)
    try:
      with open(file_name, 'r') as fileo:
        first_line = fileo.readline()

      return first_line.strip()
    except IOError:
      self.plugin.api('send:error')('Please set the %s with %s.%s.%s' % \
                             (self.desc,
                              self.plugin.api('core.commands:get:command:prefix')(),
                              self.plugin.plugin_id,
                              self.name))

    return self.default

  def cmd_setssc(self, args):
    """
    set the secret
    """
    if args['value']:
      file_name = os.path.join(self.plugin.save_directory, self.name)
      data_file = open(file_name, 'w')
      data_file.write(args['value'])
      os.chmod(file_name, stat.S_IRUSR | stat.S_IWUSR)
      return True, ['%s saved' % self.desc]

    return True, ['Please enter the %s' % self.desc]

class Plugin(BasePlugin):
  """
  a plugin to handle secret settings
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.reload_dependents_f = True

    self.api('libs.api:add')('baseclass:get', self.api_baseclass)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

  # return the secret setting baseclass
  def api_baseclass(self):
    # pylint: disable=no-self-use
    """
    return the sql baseclass
    """
    return SSC
