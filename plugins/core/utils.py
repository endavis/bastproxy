"""
This plugin handles utility functions
"""
import re
import datetime
import math
import time
import fnmatch
from plugins._baseplugin import BasePlugin

NAME = 'Utility functions'
SNAME = 'utils'
PURPOSE = 'Utility Functions'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 12

REQUIRED = True

TIMELENGTH_REGEXP = re.compile(r"^(?P<days>((\d*\.\d+)|\d+)+d)?" \
                               r":?(?P<hours>((\d*\.\d+)|\d+)+h)?" \
                               r":?(?P<minutes>((\d*\.\d+)|\d+)+m)?" \
                               r":?(?P<seconds>\d+s)?$")


class Plugin(BasePlugin):
  """
  a plugin to handle ansi colors
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the plugin
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('api.add')('timedeltatostring', self.api_timedeltatostring)
    self.api('api.add')('readablenumber', self.api_readablenumber)
    self.api('api.add')('secondstodhms', self.api_secondstodhms)
    self.api('api.add')('formattime', self.api_formattime)
    self.api('api.add')('center', self.api_center)
    self.api('api.add')('checklistformatch', self.api_checklistformatch)
    self.api('api.add')('timelengthtosecs', self.api_timelengthtosecs)
    self.api('api.add')('verify', self.api_verify)
    self.api('api.add')('listtocolumns', self.listtocolumns)

    self.dependencies = ['core.colors']

  def initialize(self):
    """
    load the plugin
    """
    BasePlugin.initialize(self)

  @staticmethod
  def listtocolumns(obj, cols=4, columnwise=True, gap=4):
    """
    Print the given list in evenly-spaced columns.

    Parameters
    ----------
    obj : list
        The list to be printed.
    cols : int
        The number of columns in which the list should be printed.
    columnwise : bool, default=True
        If True, the items in the list will be printed column-wise.
        If False the items in the list will be printed row-wise.
    gap : int
        The number of spaces that should separate the longest column
        item/s from the next column. This is the effective spacing
        between columns based on the maximum len() of the list items.
    """

    sobj = [str(item) for item in obj]
    if cols > len(sobj):
      cols = len(sobj)
    max_len = max([len(item) for item in sobj])
    if columnwise:
      cols = int(math.ceil(float(len(sobj)) / float(cols)))
    plist = [sobj[i: i+cols] for i in range(0, len(sobj), cols)]
    if columnwise:
      if not len(plist[-1]) == cols:
        plist[-1].extend(['']*(len(sobj) - len(plist[-1])))
      plist = zip(*plist)
    printer = '\n'.join(
        [''.join([c.ljust(max_len + gap) for c in p]) for p in plist])
    return printer

  # return the difference of two times
  def api_timedeltatostring(self, stime, etime, fmin=False, colorn='',
                            colors='', nosec=False):
    # pylint: disable=no-self-use,too-many-arguments
    """
    take two times and return a string of the difference
    in the form ##d:##h:##m:##s
    """
    if isinstance(stime, time.struct_time):
      stime = time.mktime(stime)
    if isinstance(etime, time.struct_time):
      etime = time.mktime(etime)
    delay = datetime.timedelta(seconds=abs(etime - stime))
    if delay.days > 0:
      tstr = str(delay)
      tstr = tstr.replace(" day, ", ":")
      out = tstr.replace(" days, ", ":")
    else:
      out = "0:" + str(delay)
    outar = out.split(':')
    outar = [(int(float(x))) for x in outar]
    tmsg = []
    days, hours = False, False
    if outar[0] != 0:
      days = True
      tmsg.append('%s%02d%sd' % (colorn, outar[0], colors))
    if outar[1] != 0 or days:
      hours = True
      tmsg.append('%s%02d%sh' % (colorn, outar[1], colors))
    if outar[2] != 0 or days or hours or fmin:
      tmsg.append('%s%02d%sm' % (colorn, outar[2], colors))
    if not nosec:
      tmsg.append('%s%02d%ss' % (colorn, outar[3], colors))

    out = ":".join(tmsg)
    return out

  # convert a number to a shorter readable number
  def api_readablenumber(self, num, places=2):
    # pylint: disable=no-self-use
    """
    convert a number to a shorter readable number
    """
    ret = ''
    nform = "%%00.0%sf" % places
    if not num:
      return 0
    elif num >= 1000000000000:
      ret = nform % (num / 1000000000000.0) + " T" # trillion
    elif num >= 1000000000:
      ret = nform % (num / 1000000000.0) + " B" # billion
    elif num >= 1000000:
      ret = nform % (num / 1000000.0) + " M" # million
    elif num >= 1000:
      ret = nform % (num / 1000.0) + " K" # thousand
    else:
      ret = num # hundreds
    return ret

  # convert seconds to years, days, hours, mins, secs
  def api_secondstodhms(self, sseconds):
    # pylint: disable=no-self-use
    """
    convert seconds to years, days, hours, mins, secs
    """
    nseconds = int(sseconds)
    dtime = {
        'years' : 0,
        'days' : 0,
        'hours' : 0,
        'mins': 0,
        'secs': 0
        }
    if nseconds == 0:
      return dtime

    dtime['years'] = int(math.floor(nseconds/(3600 * 24 * 365)))
    nseconds = nseconds - (dtime['years'] * 3600 * 24 * 365)
    dtime['days'] = int(math.floor(nseconds/(3600 * 24)))
    nseconds = nseconds - (dtime['days'] * 3600 * 24)
    dtime['hours'] = int(math.floor(nseconds/3600))
    nseconds = nseconds - (dtime['hours'] * 3600)
    dtime['mins'] = int(math.floor(nseconds/60))
    nseconds = nseconds - (dtime['mins'] * 60)
    dtime['secs'] = int(nseconds % 60)
    return dtime

  # format a length of time into a string
  def api_formattime(self, length, nosec=False):
    """
    format a length of time into a string
    """
    msg = []
    dtime = self.api('utils.secondstodhms')(length)
    years = False
    days = False
    hours = False
    mins = False
    if dtime['years'] > 0:
      years = True
      msg.append('%dy' % (dtime['years'] or 0))
    if dtime['days'] > 0:
      if years:
        msg.append(':')
      days = True
      msg.append('%02dd' % (dtime['days'] or 0))
    if dtime['hours']:
      if years or days:
        msg.append(':')
      hours = True
      msg.append('%02dh' % (dtime['hours'] or 0))
    if dtime['mins'] > 0:
      if years or days or hours:
        msg.append(':')
      mins = True
      msg.append('%02dm' % (dtime['mins'] or 0))
    if (dtime['secs'] > 0 or not msg) and not nosec:
      if years or days or hours or mins:
        msg.append(':')
      msg.append('%02ds' % (dtime['secs'] or 0))

    return ''.join(msg)

  # verify a value to be a boolean
  def verify_bool(self, val):
    # pylint: disable=no-self-use
    """
    convert a value to a bool, also converts some string and numbers
    """
    if val == 0 or val == '0':
      return False
    elif val == 1 or val == '1':
      return True
    elif isinstance(val, basestring):
      val = val.lower()
      if val == 'false' or val == 'no':
        return False
      elif val == 'true' or val == 'yes':
        return True

    return bool(val)

  # verify a value to contain an @ color
  def verify_color(self, val):
    """
    verify an @ color
    """
    if self.api('colors.iscolor')(val):
      return val

    raise ValueError

  # verify a time to be military
  def verify_miltime(self, mtime):
    # pylint: disable=no-self-use
    """
    verify a time like 0830 or 1850
    """
    try:
      time.strptime(mtime, '%H%M')
    except:
      raise ValueError

    return mtime

  # verfiy a time to be valid
  def verify_timelength(self, usertime):
    """
    verify a user time length
    """
    ttime = None

    try:
      ttime = int(usertime)
    except ValueError:
      ttime = self.api('utils.timelengthtosecs')(usertime)

    if ttime != 0 and not ttime:
      raise ValueError

    return ttime

  # verify different types
  def api_verify(self, val, vtype):
    """
    verify values
    """
    vtab = {}
    vtab[bool] = self.verify_bool
    vtab['color'] = self.verify_color
    vtab['miltime'] = self.verify_miltime
    vtab['timelength'] = self.verify_timelength

    if vtype in vtab:
      return vtab[vtype](val)

    return vtype(val)

  # center a string with color codes
  def api_center(self, tstr, fillerc, length):
    """
    center a string with color codes
    """
    convertcolors = self.api('colors.convertcolors')(tstr)
    nocolor = self.api('colors.stripansi')(convertcolors)

    tlen = len(nocolor) + 4
    tdiff = length - tlen

    thalf = tdiff / 2
    tstr = "{filler}  {lstring}  {filler}".format(
        filler=fillerc * thalf,
        lstring=tstr)

    newl = (thalf * 2) + tlen

    if newl < length:
      tstr = tstr + '-' * (length - newl)

    return tstr

  # check a list for a match
  def api_checklistformatch(self, arg, tlist):
    # pylint: disable=no-self-use
    """
    check a list for a match of arg
    """
    sarg = str(arg)
    tdict = {}
    match = sarg + '*'
    tdict['part'] = []
    tdict['front'] = []

    if arg in tlist or sarg in tlist:
      return [arg]

    for i in tlist:
      if fnmatch.fnmatch(i, match):
        tdict['front'].append(i)
      elif isinstance(i, basestring) and sarg in i:
        tdict['part'].append(i)

    if tdict['front']:
      return tdict['front']

    return tdict['part']

  # convert a time length to seconds
  def api_timelengthtosecs(self, timel):
    # pylint: disable=no-self-use
    """
    converts a time length to seconds

    Format is 1d:2h:30m:40s, any part can be missing
    """
    tmatch = TIMELENGTH_REGEXP.match(timel)

    if not tmatch:
      return None

    timem = tmatch.groupdict()

    if not timem["days"] and not timem["hours"] and not timem["minutes"] \
            and not timem["seconds"]:
      return None

    days = timem["days"]
    if not days:
      days = 0
    elif days.endswith("d"):
      days = float(days[:-1])

    hours = timem["hours"]
    if not hours:
      hours = 0
    elif hours.endswith("h"):
      hours = float(hours[:-1])

    minutes = timem["minutes"]
    if not minutes:
      minutes = 0
    elif minutes.endswith("m"):
      minutes = float(minutes[:-1])

    seconds = timem["seconds"]
    if not seconds:
      seconds = 0
    elif seconds.endswith("s"):
      seconds = int(seconds[:-1])

    return days * 24 * 60 * 60 + hours * 60 * 60 + minutes * 60 + seconds
