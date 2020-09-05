"""
This module holds the base class for a Telnet Option
"""
from libs.api import API

class BaseTelnetOption(object):
  """
  a base class for a telnet object
  """
  def __init__(self, telnet_object, option, plugin):
    """
    initalize the instance
    """
    tapi = API()
    self.telnet_object = telnet_object
    self.option = option
    self.telnet_object.option_handlers[ord(self.option)] = self
    self.plugin = tapi('core.plugins:get:plugin:instance')(plugin)
    #self.telnet_object.debug_types.append(self.option)

  def onconnect(self):
    """
    a method for when an option connects
    """
    self.telnet_object.msg('onconnect for option: %s' % ord(self.option),
                           mtype='option')

  def handleopt(self, command, sbdata):
    """
    handle an option
    """
    self.telnet_object.msg('handleopt for option: %s, command: %s, sbdata: %s' % \
                        (ord(self.option), command, sbdata), mtype='option')

  def reset(self, onclose=False): # pylint: disable=unused-argument
    """
    reset and option
    """
    self.telnet_object.msg('reset for option: %s' % ord(self.option), mtype='option')
    self.telnet_object.options[ord(self.option)] = False
