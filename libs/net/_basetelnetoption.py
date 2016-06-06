"""
This module holds the base class for a Telnet Option
"""
from libs.api import API

class BaseTelnetOption(object):
  """
  a base class for a telnet object
  """
  def __init__(self, telnetobj, option):
    """
    initalize the instance
    """
    self.api = API()
    self.telnetobj = telnetobj
    self.option = option
    self.telnetobj.option_handlers[ord(self.option)] = self
    #self.telnetobj.debug_types.append(self.option)

  def onconnect(self):
    """
    a method for when an option connects
    """
    self.telnetobj.msg('onconnect for option', ord(self.option),
                       mtype='option')

  def handleopt(self, command, sbdata):
    """
    handle an option
    """
    self.telnetobj.msg('handleopt for option', ord(self.option),
                       command, sbdata, mtype='option')

  def reset(self, onclose=False):
    """
    reset and option
    """
    self.telnetobj.msg('reset for option', ord(self.option), mtype='option')
    self.telnetobj.options[ord(self.option)] = False
