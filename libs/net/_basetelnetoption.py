"""
This module holds the base class for a Telnet Option
"""
from libs.api import API

class BaseTelnetOption(object):
  """
  a base class for a telnet object
  """
  # plugin_id, option_name, option_class, option_num
  def __init__(self, telnet_object, option_name, option_number, plugin_id):
    """
    initalize the instance
    """
    tapi = API()
    self.telnet_object = telnet_object
    self.option_name = option_name
    self.option_number = option_number
    self.option_string = chr(self.option_number)

    self.telnet_object.option_handlers[self.option_number] = self
    self.plugin = tapi('core.plugins:get:plugin:instance')(plugin_id)
    #self.telnet_object.debug_types.append(self.option_number)

  def onconnect(self):
    """
    a method for when an option connects
    """
    self.telnet_object.msg('onconnect for option: %s' % self.option_number,
                           mtype='option')

  def handleopt(self, command, sbdata):
    """
    handle an option
    """
    self.telnet_object.msg('handleopt for option: %s, command: %s, sbdata: %s' % \
                        (self.option_number, command, sbdata), mtype='option')

  def reset(self, onclose=False): # pylint: disable=unused-argument
    """
    reset and option
    """
    self.telnet_object.msg('reset for option: %s' % self.option_number, mtype='option')
    self.telnet_object.options[self.option_number] = False
