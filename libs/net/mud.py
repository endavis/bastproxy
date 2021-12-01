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

    self.last_data = ''
    self.terminal_type = 'BastProxy'
    self.api('core.events:register:to:event')('to_mud_event', self.addtooutbuffer,
                                              prio=99)
    self.api('net.options:server:prepare')(self)
    self.api('core.managers:add')('mud', self)
    self.api('core.log:add:datatype')('rawmud')

  def handle_read(self):
    """
    handle a read
    """
    Telnet.handle_read(self)

    data = self.getdata()
    if data:
      new_data_string = "".join([self.last_data, data])

      # don't care about \r
      all_data = new_data_string.replace("\r", "")

      # split on \n
      new_data_list_by_line = all_data.split('\n')
      self.last_data = new_data_list_by_line[-1]
      for i in new_data_list_by_line[:-1]:
        tosend = i
        try:
          tnoansi = self.api('core.colors:colorcode:strip')(tosend)
        except AttributeError:
          tnoansi = tosend
        try:
          tconvertansi = self.api('core.colors:ansicode:to:colorcode')(tosend)
        except AttributeError:
          tconvertansi = tosend
        if tosend != tconvertansi:
          self.api('libs.io:send:msg')('converted %s to %s' % (repr(tosend),
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

        self.api('core.events:raise:event')('muddata_trace_started', data,
                                            calledfrom='proxy')

        # this event can be used to transform the data
        newdata = self.api('core.events:raise:event')('from_mud_event',
                                                      data,
                                                      calledfrom="mud")

        self.api('core.events:raise:event')('muddata_trace_finished', data,
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
          if self.api('libs.api:has')('core.colors:colorcode:strip'):
            tnoansi = self.api('core.colors:colorcode:strip')(tosend)
          else:
            tnoansi = tosend
          if self.api('libs.api:has')('core.colors:ansicode:to:colorcode'):
            tconvertansi = self.api('core.colors:ansicode:to:colorcode')(tosend)
          else:
            tconvertansi = tosend
          self.api('libs.io:send:client')(tosend, dtype='frommud')

  def connectmud(self, mudhost, mudport):
    """
    connect to the mud
    """
    if self.connected:
      return
    self.outbuffer = ''
    self.doconnect(mudhost, mudport)
    self.connected_time = time.localtime()
    self.api('libs.io:send:msg')('Connected to mud', 'net')
    self.api('core.events:raise:event')('mudconnect', {}, calledfrom="mud")

  def handle_close(self):
    """
    hand closing the connection
    """
    self.api('libs.io:send:msg')('Disconnected from mud', 'net')
    self.api('libs.io:send:client')(self.api('core.colors:colorcode:to:ansicode')(
        '%s%s@w: The mud closed the connection' % (self.api('net.proxy:preamble:error:color:get')(),
                                                   self.api('net.proxy:preamble:get')())))
    self.api('net.options:options:reset')(self, True)
    Telnet.handle_close(self)
    self.connected_time = None
    self.api('core.events:raise:event')('ev_libs.net.mud_muddisconnect', {}, calledfrom="mud")

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
                                 'callstack':self.api('libs.api:get:call:stack')()})
      Telnet.addtooutbuffer(self, datastr, raw)
    elif dtype == 'fromclient':
      if trace:
        trace['changes'].append({'flag':'Sent',
                                 'data':'"%s" to mud with raw: %s and datatype: %s' %
                                        (datastr.strip(), raw, dtype),
                                 'plugin':'proxy',
                                 'callstack':self.api('libs.api:get:call:stack')()})
      Telnet.addtooutbuffer(self, datastr, raw)

  def fill_rawq(self):
    """
    Fill raw queue from exactly one recv() system call.

    Block if no data is immediately available.  Set self.eof when
    connection is closed.
    """
    buf = Telnet.fill_rawq(self)
    self.api('core.log:write:to:file')('rawmud', buf)
    return buf
