"""
TELNET client class.

Based on RFC 854: TELNET Protocol Specification, by J. Postel and
J. Reynolds
"""

from __future__ import print_function

import asyncore
import socket

from libs.api import API

__all__ = ["Telnet"]

# Tunable parameters
# 1 = a lot of debug
# ..
# 5 = less
DEBUGLEVEL = 3

# Telnet protocol defaults
TELNET_PORT = 23

# Telnet protocol characters (don't change)
IAC = chr(255) # "Interpret As Command"
DONT = chr(254)
DO = chr(253)
WONT = chr(252)
WILL = chr(251)
THENULL = chr(0)

SE = chr(240)  # Subnegotiation End
NOP = chr(241)  # No Operation
DM = chr(242)  # Data Mark
BRK = chr(243)  # Break
IP = chr(244)  # Interrupt process
AO = chr(245)  # Abort output
AYT = chr(246)  # Are You There
EC = chr(247)  # Erase Character
EL = chr(248)  # Erase Line
GA = chr(249)  # Go Ahead
SB = chr(250)  # Subnegotiation Begin


# Telnet protocol options code (don't change)
# These ones all come from arpa/telnet.h
BINARY = chr(0) # 8-bit data path
ECHO = chr(1) # echo
RCP = chr(2) # prepare to reconnect
SGA = chr(3) # suppress go ahead
NAMS = chr(4) # approximate message size
STATUS = chr(5) # give status
TM = chr(6) # timing mark
RCTE = chr(7) # remote controlled transmission and echo
NAOL = chr(8) # negotiate about output line width
NAOP = chr(9) # negotiate about output page size
NAOCRD = chr(10) # negotiate about CR disposition
NAOHTS = chr(11) # negotiate about horizontal tabstops
NAOHTD = chr(12) # negotiate about horizontal tab disposition
NAOFFD = chr(13) # negotiate about formfeed disposition
NAOVTS = chr(14) # negotiate about vertical tab stops
NAOVTD = chr(15) # negotiate about vertical tab disposition
NAOLFD = chr(16) # negotiate about output LF disposition
XASCII = chr(17) # extended ascii character set
LOGOUT = chr(18) # force logout
BM = chr(19) # byte macro
DET = chr(20) # data entry terminal
SUPDUP = chr(21) # supdup protocol
SUPDUPOUTPUT = chr(22) # supdup output
SNDLOC = chr(23) # send location
TTYPE = chr(24) # terminal type
EOR = chr(25) # end or record
TUID = chr(26) # TACACS user identification
OUTMRK = chr(27) # output marking
TTYLOC = chr(28) # terminal location number
VT3270REGIME = chr(29) # 3270 regime
X3PAD = chr(30) # X.3 PAD
NAWS = chr(31) # window size
TSPEED = chr(32) # terminal speed
LFLOW = chr(33) # remote flow control
LINEMODE = chr(34) # Linemode option
XDISPLOC = chr(35) # X Display Location
OLD_ENVIRON = chr(36) # Old - Environment variables
AUTHENTICATION = chr(37) # Authenticate
ENCRYPT = chr(38) # Encryption option
NEW_ENVIRON = chr(39) # New - Environment variables
# the following ones come from
# http://www.iana.org/assignments/telnet-options
# Unfortunately, that document does not assign identifiers
# to all of them, so we are making them up
TN3270E = chr(40) # TN3270E
XAUTH = chr(41) # XAUTH
CHARSET = chr(42) # CHARSET
RSP = chr(43) # Telnet Remote Serial Port
COM_PORT_OPTION = chr(44) # Com Port Control Option
SUPPRESS_LOCAL_ECHO = chr(45) # Telnet Suppress Local Echo
TLS = chr(46) # Telnet Start TLS
KERMIT = chr(47) # KERMIT
SEND_URL = chr(48) # SEND-URL
FORWARD_X = chr(49) # FORWARD_X
PRAGMA_LOGON = chr(138) # TELOPT PRAGMA LOGON
SSPI_LOGON = chr(139) # TELOPT SSPI LOGON
PRAGMA_HEARTBEAT = chr(140) # TELOPT PRAGMA HEARTBEAT
EXOPL = chr(255) # Extended-Options-List

NOOPT = chr(0)
IS = chr(0)

# reverse lookup allowing us to see what's going on more easily
# when we're debugging.
# for a list of telnet options: http://www.freesoft.org/CIE/RFC/1700/10.htm
CODES = {255: "IAC",
         254: "DON'T",
         253: "DO",
         252: "WON'T",
         251: "WILL",
         250: "SB",
         249: "GA",
         240: "SE",
         239: "TELOPT_EOR",
         0:   "<IS>",
         1:   "[<ECHO> or <SEND/MODE>]",
         3:   "<SGA>",
         5:   "STATUS",
         25:  "<EOR>",
         31:  "<NegoWindoSize>",
         32:  "<TERMSPEED>",
         34:  "<Linemode>",
         35:  "<XDISPLAY>",
         36:  "<ENV>",
         39:  "<NewENV>",
        }


def addcode(code, codestr):
  """
  add a code into the CODE table
  """
  CODES[code] = codestr


class Telnet(asyncore.dispatcher):
  # have to keep up with a lot of things, so disabling pylint warning
  # pylint: disable=too-many-instance-attributes
  """
  Telnet interface class.

  read_sb_data()
      Reads available data between SB ... SE sequence. Don't block.

  set_option_negotiation_callback(callback)
      Each time a telnet option is read on the input flow, this callback
      (if set) is called with the following parameters :
      callback(command, option)
          option will be chr(0) when there is no option.
      No other action is done afterwards by telnetlib.
  """
  def __init__(self, host=None, port=0, sock=None):
    """
    Constructor.

    When called without arguments, create an unconnected instance.
    With a hostname argument, it connects the instance; port number
    and timeout are optional.
    """
    if sock:
      asyncore.dispatcher.__init__(self, sock)
    else:
      asyncore.dispatcher.__init__(self)
    self.sock = sock
    self.debuglevel = DEBUGLEVEL
    self.host = host
    self.port = port
    self.rawq = ''
    self.api = API()
    self.cookedq = ''
    self.eof = 0
    self.sbdataq = ''
    self._sbdatabuffer = ''
    self.outbuffer = ''
    self.options = {}
    self.option_callback = self.handleopt
    self.option_handlers = {}
    self.connected = False
    self.connected_time = None
    self.terminal_type = 'Unknown'
    self.debug_types = []

  @staticmethod
  def ccode(newchar):
    """
    convert a char to a string if in CODES lookup table
    """
    tchar = ord(newchar)
    if tchar in CODES:
      return CODES[tchar]

    return tchar

  def handleopt(self, command, option):
    """
    handle an option
    """
    cmdstr = self.ccode(command)
    optstr = self.ccode(option)

    self.msg('Command %s with option: %s' % (cmdstr, optstr), mtype='OPTION')
    data = self.read_sb_data()

    if ord(option) in self.option_handlers:
      self.msg('calling handleopt for: %s' % optstr, mtype='OPTION')
      self.option_handlers[ord(option)].handleopt(command, data)
    elif command == WILL:
      self.msg('Sending IAC WONT %s' % optstr, mtype='OPTION')
      self.send("".join([IAC, WONT, option]))
    elif command == DO:
      self.msg('Sending IAC DONT %s' % optstr, mtype='OPTION')
      self.send("".join([IAC, DONT, option]))
    elif command == DONT or command == WONT:
      pass
    else:
      self.msg('Fallthrough: %s with option %s'  % (cmdstr, optstr), mtype='OPTION')
      if command == SE:
        self.msg('sbdataq: %r' % self.sbdataq, mtype='OPTION')

      self.msg('length of sbdataq: %s' % len(self.sbdataq), mtype='OPTION')
      if len(self.sbdataq) == 1:
        self.msg('should look at the sbdataq: %s' % self.ccode(self.sbdataq),
                 mtype='OPTION')
      else:
        self.msg('should look at the sbdataq: %s' % self.sbdataq, mtype='OPTION')

  def readdatafromsocket(self):
    """
    read 1024 bytes from the socket
    """
    try:
      buf = self.recv(1024)
      self.msg("recv %r" % buf)
      return buf
    except:  # pylint: disable=bare-except
      return None

  def __del__(self):
    """
    Destructor -- close the connection.
    """
    self.close()

  def msg(self, msg, **kwargs):
    """
    Print a debug message, when the debug level is > 0.

    If extra arguments are present, they are substituted in the
    message using the standard string formatting operator.

    """
    mtype = 'net'
    if 'level' not in kwargs:
      kwargs['level'] = 1
    if 'mtype' in kwargs:
      mtype = kwargs['mtype']
    if kwargs['level'] >= self.debuglevel or mtype in self.debug_types:
      print('Telnet(%-15s - %-5s %-7s %-5s): %s' % \
                          (self.host, self.port, self.terminal_type, mtype, msg))

  def set_debuglevel(self, debuglevel):
    """
    Set the debug level.

    The higher it is, the more debug output you get (on sys.stdout).

    """
    self.debuglevel = debuglevel

  def doconnect(self, hostname, hostport):
    """
    connect to a host and port
    """
    self.host = hostname
    self.port = hostport
    self.msg('doconnect')
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.set_reuse_addr()
    self.connect((self.host, self.port))
    self.connected = True
    for i in self.option_handlers:
      self.option_handlers[i].onconnect()

  def handle_close(self):
    """
    Close the connection.
    """
    self.msg('closing connection')
    self.connected = False
    self.close()
    self.options = {}
    self.eof = 1

  def handle_write(self):
    """
    write to a connection
    """
    self.msg('Handle_write: %s' % self.outbuffer)
    sent = self.send(self.outbuffer)
    self.outbuffer = self.outbuffer[sent:]

  def addtooutbuffer(self, data, raw=False):
    """
    Write a string to the socket, doubling any IAC characters.

    Can block if the connection is blocked.  May raise
    socket.error if the connection is closed.
    """
    self.msg('adding to output buffer - raw: %s, data: %s' % (raw, data))
    if not raw and IAC in data:
      data = data.replace(IAC, IAC+IAC)

    data = self.convert_outdata(data)

    self.outbuffer = "".join([self.outbuffer, data])

  def convert_outdata(self, outbuffer):
    """
    override this to convert something from the outbuffer
    """
    # this function can be overridden so disabling pylint warning
    # pylint: disable=no-self-use
    return outbuffer

  def writable(self):
    """
    find out if the connection has data to write
    """
    #self.msg( 'writable', self.terminal_type, len(self.outbuffer) > 0)
    return len(self.outbuffer) > 0

  def handle_error(self):
    """
    handle an error
    """
    self.api('libs.io:send:traceback')("Telnet error: %s" % self.terminal_type)

  def handle_read(self):
    """
    Read readily available data.

    Raise EOFError if connection closed and no cooked data
    available.  Return '' if no cooked data available otherwise.
    Don't block unless in the midst of an IAC sequence.
    """
    try:
      self.rawq_get()
    except EOFError:
      self.sbdataq = ""
      self._sbdatabuffer = ""
      return

    while self.rawq:
      self.process_rawq()

  def getdata(self):
    """
    Return any data available in the cooked queue.

    Raise EOFError if connection closed and no data available.
    Return '' if no cooked data available otherwise.  Don't block.
    """
    if not self.connected:
      return None
    buf = self.cookedq
    self.cookedq = ''
    return buf

  def read_sb_data(self):
    """
    Return any data available in the SB ... SE queue.

    Return '' if no SB ... SE available. Should only be called
    after seeing a SB or SE command. When a new SB command is
    found, old unread SB data will be discarded. Don't block.
    """
    buf = self.sbdataq
    self.sbdataq = ''
    return buf

  def set_option_negotiation_callback(self, callback):
    """
    Provide a callback function called after each receipt of a telnet option.
    """
    self.option_callback = callback

  def handle_subdata(self, data): # pylint: disable=too-many-branches,too-many-statements
    """
    handle data that has an IAC in it
    """
    marker = -1

    self.msg('handle_subdata with data: "%s"' % data, mtype='OPTION')
    self.msg('# of IACS: %s' % (data.count(IAC)), mtype="OPTION")

    if self._sbdatabuffer:
      self.msg('had previous sb data: "%s"' % self._sbdatabuffer, mtype='OPTION')
      data = "".join([self._sbdatabuffer, data])
      self.msg('data now: "%s"' % data, mtype='OPTION')
      self._sbdatabuffer = ''

    i = data.find(IAC)

    while i != -1:
      if i + 1 >= len(data):
        marker = i
        break

      if i != 0:
        # put everything before the IAC on the cookedq
        self.msg('i != 0: everything goes into cooked queue that is before it',
                 mtype="OPTION")
        self.msg('i != 0: cooked q was "%s"' % self.cookedq,
                 mtype="OPTION")
        self.cookedq = "".join([self.cookedq, data[:i]])
        self.msg('i != 0: cooked q is now "%s"' % self.cookedq,
                 mtype="OPTION")
        data = data[i:]
        self.msg('i != 0: data changed to "%s"' % data,
                 mtype="OPTION")
        i = data.find(IAC)

      if data[i+1] == NOP:
        self.msg('received IAC NOP', mtype='OPTION')
        data = "".join([data[:i], data[i+2:]])

      elif data[i+1] == IAC:
        self.msg('received IAC IAC', mtype='OPTION')
        data = "".join([data[:i], data[i+1:]])
        i = i + 1

      else:
        if i + 2 >= len(data):
          self.msg('not enough data to figure out IAC sequence', mtype='OPTION')
          marker = i
          break

        # handles DO/DONT/WILL/WONT
        if data[i+1] in [DO, DONT, WILL, WONT]:
          self.msg('DDWW: got a do, dont, will, or wont', mtype='OPTION')
          cmd = data[i+1]
          optionnum = data[i+2]
          self.sbdataq = ""
          self.option_callback(cmd, optionnum)

          data = "".join([data[:i], data[i+3:]])
          self.msg('DDWW: data was changed to: "%s"' % data, mtype='OPTION')


        # handles SB...SE stuff
        elif data[i+1] == SB:
          self.msg('SBSE - data: "%s"' % data, mtype="OPTION")
          optionnum = data[i+2]
          cmd = SB
          sei = data.find(SE, i)
          self.msg('SBSE - Found: SB: %s, SE: %s' % (i, sei), mtype="OPTION")
          if sei == -1:
            marker = i
            break

          #self.logControl("receive: " + _cc(option))
          self.sbdataq = data[i+3:sei-1]
          self.msg('SBSE: sbdataq "%s"' % self.sbdataq, mtype="OPTION")

          # before each option, put the remaining data back on
          # the rawq, make the callback and then let things settle
          self.rawq = "".join([data[:i], data[sei+1:]])
          self.msg('SBSE - setting rawq to "%s"' % self.rawq, mtype="OPTION")
          self.msg('SBSE - calling option_callback', mtype="OPTION")
          self.option_callback(cmd, optionnum)

          return ""

        # in case they passed us something weird we remove the IAC and
        # move on
        else:
          data = "".join([data[:i], data[i+1:]])
          self.msg('Weird IAC sequence: data was changed to: "%s"' % data, mtype='OPTION')

      i = data.find(IAC, i)

    if marker != -1:
      self.msg('MARKER - not 1 with data %s' % data, mtype='OPTION')
      self._sbdatabuffer = data[marker:]
      self.msg('MARKER - _sbdatabuffer: "%s"' % self._sbdatabuffer, mtype='OPTION')
      data = data[:marker]
      self.msg('MARKER - data changed to "%s"' % self._sbdatabuffer, mtype='OPTION')

    return data

  def process_rawq(self):
    """
    Transfer from raw queue to cooked queue.

    Set self.eof when connection is closed.  Don't block unless in
    the midst of an IAC sequence.
    """
    self.msg('PROCESS_RAWQ: rawq "%s"' % self.rawq, mtype='OPTION')
    newdata = self.rawq
    self.rawq = ''
    if IAC in newdata:
      parseddata = self.handle_subdata(newdata)
    else:
      parseddata = newdata

    self.msg('PROCESS_RAWQ: parseddata "%s"' % parseddata, mtype='OPTION')

    self.cookedq = "".join([self.cookedq, parseddata])

  def rawq_get(self):
    """
    Get next char from raw queue.

    Block if no data is immediately available.  Raise EOFError
    when connection is closed.
    """
    if not self.rawq:
      self.fill_rawq()
      if self.eof:
        raise EOFError

  def fill_rawq(self):
    """
    Fill raw queue from exactly one recv() system call.

    Block if no data is immediately available.  Set self.eof when
    connection is closed.
    """
    buf = self.readdatafromsocket()
    self.eof = (not buf)
    self.rawq = "".join([self.rawq, buf])
    self.msg('rawq: %s' % self.rawq)
    return buf
