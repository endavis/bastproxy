"""
This plugin sends messages through the pushbullet api

## Usage
 * You must install [pushbullet.py](https://pypi.python.org/pypi/pushbullet.py)
 * Enter your api key with the apikey command

"""
try:
  import pushbullet
except ImportError:
  pushbullet = None

import libs.argp as argp
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Pushbullet'
SNAME = 'pb'
PURPOSE = 'send info through Pushbullet'
AUTHOR = 'Bast'
VERSION = 1

class Plugin(BasePlugin):
  """
  a plugin to send email
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)
    self.api('dependency.add')('core.ssc')

    self.apikey = None

    self.api('api.add')('note', self.api_note)
    self.api('api.add')('link', self.api_link)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting.add')('channel', '', str,
                            'the channel to send to')

    parser = argp.ArgumentParser(add_help=False,
                                 description='send a note')
    parser.add_argument('title',
                        help='the title of the note',
                        default='Pushbullet note from bastproxy',
                        nargs='?')
    parser.add_argument('body',
                        help='the body of the note',
                        default='A Pushbullet note sent through bastproxy',
                        nargs='?')
    parser.add_argument('-c', "--channel",
                        help="the pushbullet channel to send to",
                        default='')
    self.api('commands.add')('note', self.cmd_note,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='send a link')
    parser.add_argument('title',
                        help='the title of the link',
                        default='Pushbullet link from bastproxy',
                        nargs='?')
    parser.add_argument('url',
                        help='the url of the link',
                        default='https://github.com/endavis/bastproxy',
                        nargs='?')
    parser.add_argument('-c', "--channel",
                        help="the pushbullet channel to send to",
                        default='')
    self.api('commands.add')('link', self.cmd_link,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='show channels associated with pb')
    self.api('commands.add')('channels', self.cmd_channels,
                             parser=parser)

    ssc = self.api('ssc.baseclass')()
    self.apikey = ssc('apikey', self, desc='Pushbullet API key')

    self.import_pushbullet()

  def import_pushbullet(self):
    """
    import pushbullet module
    """
    global pushbullet # pylint: disable=global-statement,invalid-name
    if not pushbullet:
      try:
        import pushbullet # pylint: disable=redefined-outer-name
      except ImportError:
        self.api('send.error')(
            'Please install pushbullet.py with "pip(2) install pushbullet.py"')
        return False

    return True

  # send a note through pushbullet
  def api_note(self, title, body, channel=None):
    """ send a note through pushbullet

    @Ytitle@w     = the title of the note
    @Ybody@w      = the body of the note
    @Ychannel@w   = the pushbullet channel to send to

    this function returns True if sent, False otherwise"""
    apikey = self.api('%s.apikey' % self.short_name)()

    if not apikey:
      self.api('send.error')('pushbullet apikey not set')
      return False

    if not pushbullet:
      if not self.import_pushbullet():
        return False

    pbc = pushbullet.Pushbullet(apikey)

    rval = {}
    found = False
    nchannel = channel or self.api('setting.gets')('channel')
    if nchannel:
      for i in pbc.channels:
        if str(i.channel_tag) == nchannel:
          found = True
          rval = i.push_note(title, body)
          break

      if not found:
        self.api('send.error')('There was no channel %s' % nchannel)
        return False

    else:
      rval = pbc.push_note(title, body)

    pbc._session.close() # pylint: disable=protected-access

    if 'error' in rval:
      self.api('send.error')('Pushbullet send failed with %s' % rval)
      return False

    self.api('send.msg')('pb returned %s' % rval)
    return True

  # send a url through pushbullet
  def api_link(self, title, url, channel=None):
    """ send a link through pushbullet

    @Ytitle@w  = the title of the note
    @Yurl@w      = the body of the note
    @Ychannel@w   = the pushbullet channel to send to

    this function returns True if sent, False otherwise"""
    apikey = self.api('%s.apikey' % self.short_name)()

    if not apikey:
      self.api('send.error')('pushbullet apikey not set')
      return False

    if not pushbullet:
      if not self.import_pushbullet():
        return False

    pbc = pushbullet.Pushbullet(apikey)

    rval = {}
    nchannel = channel or self.api('setting.gets')('channel')
    if nchannel:
      for i in pbc.channels:
        if str(i.channel_tag) == nchannel:
          found = True
          rval = i.push_link(title, url)
          break

      if not found:
        self.api('send.error')('There was no channel %s' % nchannel)
        return False

    else:
      rval = pbc.push_link(title, url)

    pbc._session.close() # pylint: disable=protected-access

    if 'error' in rval:
      self.api('send.error')('Pushbullet send failed with %s' % rval)
      return False

    self.api('send.msg')('pb returned %s' % rval)
    return True

  def cmd_channels(self, _):
    """
    list the channels
    """
    tmsg = []
    apikey = self.api('%s.apikey' % self.short_name)()

    if not apikey:
      self.api('send.error')('pushbullet apikey not set')
      return False

    if not pushbullet:
      if not self.import_pushbullet():
        return False

    pbc = pushbullet.Pushbullet(apikey)

    for i in pbc.channels:
      tmsg.append(str(i.channel_tag))

    return True, tmsg

  def cmd_note(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    Send a note
    @CUsage@w: @B%(cmdname)s@w @Ytitle@x @Ybody@x
      @Ytitle@w   = the title of the note
      @Ybody@w    = the body of the note
      @Ychannel@w    = the channel the note should be sent to
    """
    title = args['title']
    body = args['body']
    channel = args['channel']
    if self.api('pb.note')(title, body, channel):
      return True, ['Pushbullet note sent']

    return True, ['Attempt failed, please see error message']

  def cmd_link(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    Send a link
    @CUsage@w: @B%(cmdname)s@w @Ytitle@x @Ybody@x
      @Ytitle@w   = the title of the link
      @Yurl@w    = the url of the link
      @Ychannel@w    = the channel the note should be sent to
    """
    title = args['title']
    body = args['url']
    channel = args['channel']
    if self.api('pb.link')(title, body, channel):
      return True, ['Pushbullet link sent']

    return True, ['Attempt failed, please see error message']
