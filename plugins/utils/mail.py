"""
This plugin sends mail
"""
import smtplib
import os
import signal
from datetime import datetime
import libs.argp as argp
from plugins._baseplugin import BasePlugin


#these 5 are required
NAME = 'Mail'
SNAME = 'mail'
PURPOSE = 'setup and send mail'
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
    self.password = ''
    self.api('libs.api:add')('send', self.api_send)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('core.events:register:to:event')('ev_libs.net.client_client_connected', self.checkpassword)

    parser = argp.ArgumentParser(add_help=False,
                                 description='set the password for the mail account')
    parser.add_argument('password',
                        help='the top level api to show (optional)',
                        default='', nargs='?')
    self.api('core.commands:command:add')('password', self.cmd_pw,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='send a test email')
    parser.add_argument('subject',
                        help='the subject of the test email (optional)',
                        default='Test subject from bastproxy', nargs='?')
    parser.add_argument('message',
                        help='the message of the test email (optional)',
                        default='Msg from bastproxy', nargs='?')
    self.api('core.commands:command:add')('test', self.cmd_test,
                                          parser=parser)

    parser = argp.ArgumentParser(
        add_help=False,
        description='check to make sure all settings are applied')
    self.api('core.commands:command:add')('check', self.cmd_check,
                                          parser=parser)

    self.api('setting:add')('server', '', str,
                            'the smtp server to send mail through')
    self.api('setting:add')('port', '', int,
                            'the port to use when sending mail')
    self.api('setting:add')('username', '', str,
                            'the username to connect as',
                            nocolor=True)
    self.api('setting:add')('to', '', str, 'the address to send mail to',
                            nocolor=True)
    self.api('setting:add')('from', '', str,
                            'the address to send mail from',
                            nocolor=True)
    self.api('setting:add')('ssl', '', bool,
                            'set this to True if the connection will use ssl')

    if self.api('setting:get')('username') != '':
      self.api('libs.io:send:client')('Please set the mail password')

  def check(self):
    """
    check to make sure all data need to send mail is available
    """
    self.api('setting:get')('server')
    if not self.api('setting:get')('server') or \
       not self.api('setting:get')('port') or \
       not self.api('setting:get')('username') or \
       not self.password or \
       not self.api('setting:get')('from') or \
       not self.api('setting:get')('to'):
      return False

    return True

  # send an email
  def api_send(self, subject, msg, mailto=None):
    """  send an email
    @Ysubject@w  = the subject of the message
    @Ymsg@w      = the msg to send
    @Ymailto@w   = the email address to send to (default: the to
      setting of the mail plugin)

    this function returns no values"""
    if self.check():
      senddate = datetime.strftime(datetime.now(), '%Y-%m-%d')
      if not mailto:
        mailto = self.api('setting:get')('to')
      mhead = """Date: %s
From: %s
To: %s
Subject: %s
X-Mailer: My-Mail

%s""" % (senddate,
         self.api('setting:get')('from'), mailto, subject, msg)

      oldchild = signal.getsignal(signal.SIGCHLD)

      try:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

        pid = os.fork()
        if pid == 0:
          server = '%s:%s' % (self.api('setting:get')('server'),
                              self.api('setting:get')('port'))
          server = smtplib.SMTP(server)
          if self.api('setting:get')('ssl'):
            server.starttls()
          server.login(self.api('setting:get')('username'), self.password)
          server.sendmail(self.api('setting:get')('from'), mailto, mhead)
          server.quit()
          os._exit(os.EX_OK) # pylint: disable=protected-access

      except:
        server = '%s:%s' % (self.api('setting:get')('server'),
                            self.api('setting:get')('port'))
        server = smtplib.SMTP(server)
        if self.api('setting:get')('ssl'):
          server.starttls()
        server.login(self.api('setting:get')('username'), self.password)
        server.sendmail(self.api('setting:get')('from'), mailto, mhead)
        server.quit()

    if signal.getsignal(signal.SIGCHLD) != oldchild:
      signal.signal(signal.SIGCHLD, oldchild)

  def checkpassword(self, _):
    """
    check the password
    """
    if self.api('setting:get')('username'):
      if not self.password:
        self.api('libs.io:send:client')(
            '@CPlease set the email password for account: @M%s@w' \
                % self.api('setting:get')('username').replace('@', '@@'))

  def cmd_pw(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    Set the password for the smtp server
    @CUsage@w: pw @Y<password>@w
      @Ypassword@w    = the password for the smtp server
    """
    if args['password']:
      self.password = args['password']
      return True, ['Password is set']

    return False, ['@RPlease specify a password@x']

  def cmd_check(self, _=None):
    """
    check for all settings to be correct
    """
    msg = []
    items = []
    if not self.api('setting:get')('server'):
      items.append('server')
    if not self.api('setting:get')('port'):
      items.append('port')
    if not self.api('setting:get')('username'):
      items.append('username')
    if not self.password:
      items.append('password')
    if not self.api('setting:get')('from'):
      items.append('from')
    if not self.api('setting:get')('to'):
      items.append('to')
    if items:
      msg.append('Please set the following:')
      msg.append(', '.join(items))
    else:
      msg.append('Everything is ready to send a test email')
    return True, msg

  def cmd_test(self, args):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    Send a test email
    @CUsage@w: test @YSubject@x @Ymessage@x
      @Ysubject@w    = the subject of the email
      @Ymessage@w    = the message to put in the email
    """
    subject = args['subject']
    msg = args['message']
    if self.check():
      self.api('send')(subject, msg)
      return True, ['Attempted to send test message',
                    'Please check your email']

    msg = []
    msg.append('There is not enough information to send mail')
    msg.append('Please check all info')
    return True, msg
