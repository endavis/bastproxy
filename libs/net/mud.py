"""
This file holds the class that connects to the mud
"""
import time
from libs.net.telnetlib import Telnet


class Mud(Telnet):
  """
  This class is for the proxy that connects to the mud
  """
  def __init__(self):
    """
    init the class
    """
    Telnet.__init__(self)

    self.lastmsg = ''
    self.ttype = 'BastProxy'
    self.connectedtime = None
    self.api('events.register')('to_mud_event', self.addtooutbuffer,
                                prio=99)
    self.api('options.prepareserver')(self)
    self.api('managers.add')('mud', self)
    self.api('log.adddtype')('rawmud')

  def handle_read(self):
    """
    handle a read
    """
    Telnet.handle_read(self)

    data = self.getdata()
    if data:
      ndata = "".join([self.lastmsg, data])

      # don't care about \r
      alldata = ndata.replace("\r", "")

      # split on \n
      ndatal = alldata.split('\n')
      self.lastmsg = ndatal[-1]
      for i in ndatal[:-1]:
        tosend = i
        try:
          tnoansi = self.api('colors.stripansi')(tosend)
        except AttributeError:
          tnoansi = tosend
        try:
          tconvertansi = self.api('colors.convertansi')(tosend)
        except AttributeError:
          tconvertansi = tosend
        if tosend != tconvertansi:
          self.api('send.msg')('converted %s to %s' % (repr(tosend),
                                                       tconvertansi),
                               'ansi')
        trace = {}
        trace['dtype'] = 'frommud'
        trace['original'] = tosend
        trace['changes'] = []

        data = {'original':tosend,
                'data':tosend,
                'dtype':'frommud',
                'noansi':tnoansi,
                'convertansi':tconvertansi,
                'trace':trace}

        self.api('events.eraise')('muddata_trace_started', data,
                                  calledfrom='proxy')

        # this event can be used to transform the data
        newdata = self.api('events.eraise')('from_mud_event',
                                            data,
                                            calledfrom="mud")

        self.api('events.eraise')('muddata_trace_finished', data,
                                  calledfrom='proxy')

        # use the original key in the returned dictionary
        # TODO: make this so that it uses a key just named data
        if 'original' in newdata:
          tosend = newdata['original']

        # omit the data if it has been flagged
        if 'omit' in newdata and newdata['omit']:
          tosend = None

        if tosend != None:
          #data cannot be transformed here, it goes straight to the client
          if self.api('api.has')('colors.stripansi'):
            tnoansi = self.api('colors.stripansi')(tosend)
          else:
            tnoansi = tosend
          if self.api('api.has')('colors.convertansi'):
            tconvertansi = self.api('colors.convertansi')(tosend)
          else:
            tconvertansi = tosend
          self.api('send.client')(tosend, dtype='frommud')

  def connectmud(self, mudhost, mudport):
    """
    connect to the mud
    """
    if self.connected:
      return
    self.outbuffer = ''
    self.doconnect(mudhost, mudport)
    self.connectedtime = time.localtime()
    self.api('send.msg')('Connected to mud', 'net')
    self.api('events.eraise')('mudconnect', {}, calledfrom="mud")

  def handle_close(self):
    """
    hand closing the connection
    """
    self.api('send.msg')('Disconnected from mud', 'net')
    self.api('send.client')(self.api('colors.convertcolors')(
        '%s%s@w: The mud closed the connection' % (self.api('proxy.preambleerrorcolor')(),
                                                    self.api('proxy.preamble')())))
    self.api('options.resetoptions')(self, True)
    Telnet.handle_close(self)
    self.connectedtime = None
    self.api('events.eraise')('muddisconnect', {}, calledfrom="mud")

  def addtooutbuffer(self, data, raw=False):
    """
    add to the outbuffer

    required:
      data - a string
             or a dictionary that contains a data key and a raw key

    optional:
      raw - set a raw flag, which means IAC will not be doubled
    """
    dtype = 'fromclient'
    datastr = ""
    trace = None
    if isinstance(data, dict):
      datastr = data['data']
      dtype = data['dtype']
      if 'raw' in data:
        raw = data['raw']
      if 'trace' in data:
        trace = data['trace']
    else:
      datastr = data

    if len(dtype) == 1 and ord(dtype) in self.options:
      if trace:
        trace['changes'].append({'flag':'Sent',
                                 'data':'"%s" to mud with raw: %s and datatype: %s' %
                                        (repr(datastr.strip()), raw, dtype),
                                 'plugin':'proxy',
                                 'callstack':self.api('api.callstack')()})
      Telnet.addtooutbuffer(self, datastr, raw)
    elif dtype == 'fromclient':
      if trace:
        trace['changes'].append({'flag':'Sent',
                                 'data':'"%s" to mud with raw: %s and datatype: %s' %
                                        (datastr.strip(), raw, dtype),
                                 'plugin':'proxy',
                                 'callstack':self.api('api.callstack')()})
      Telnet.addtooutbuffer(self, datastr, raw)

  def fill_rawq(self):
    """
    Fill raw queue from exactly one recv() system call.

    Block if no data is immediately available.  Set self.eof when
    connection is closed.
    """
    buf = Telnet.fill_rawq(self)
    self.api('log.writefile')('rawmud', buf)
    return buf
