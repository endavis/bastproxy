"""
a module that holds a persistent dictionary implementation
it saves the dict to a file
"""
import pickle
import json
import os
import shutil
import stat
from libs.api import API
#api = API()

def convert(tinput):
  """
  converts input to ascii (utf-8)
  """
  if isinstance(tinput, dict):
    return {convert(key): convert(value) for key, value in tinput.items()}
  elif isinstance(tinput, list):
    return [convert(element) for element in tinput]
  elif isinstance(tinput, str):
    return tinput
  elif isinstance(tinput, bytes):
    return str(tinput)

  return tinput

def convertkeystoint(tdict):
  """
  convert all keys in int if they are numbers
  """
  new = {}
  for i in tdict:
    nkey = i
    try:
      nkey = int(i)
    except ValueError:
      pass
    ndata = tdict[i]
    if isinstance(tdict[i], dict):
      ndata = convertkeystoint(tdict[i])
    new[nkey] = ndata
  return new

class PersistentDict(dict):
  ''' Persistent dictionary with an API compatible with shelve and anydbm.

  The dict is kept in memory, so the dictionary operations run as fast as
  a regular dictionary.

  Write to disk is delayed until close or sync (similar to gdbm's fast mode).

  Input file format is automatically discovered.
  Output file format is selectable between pickle and json
  All three serialization formats are backed by fast C implementations.

  '''
  def __init__(self, filename, flag='c', mode=None,
               tformat='json', *args, **kwds):
    """
    initialize the instance
    """
    self._dump_shallow_attrs = ['api']
    self.api = API()

    # r=readonly, c=create, or n=new
    self.flag = flag

    # None or an octal triple like 0644
    self.mode = (stat.S_IWUSR | stat.S_IRUSR) or mode

    # json', or 'pickle'
    self.format = tformat
    self.filename = filename
    self.pload()
    dict.__init__(self, *args, **kwds)

  def sync(self):
    """
    write data to disk
    """
    if self.flag == 'r':
      return
    filename = self.filename
    tempname = filename + '.tmp'
    try:
      self.dump(tempname)
    except Exception:
      os.remove(tempname)
      raise
    finally:
      shutil.move(tempname, self.filename)    # atomic commit
    if self.mode is not None:
      os.chmod(self.filename, self.mode)

  def close(self):
    """
    close the file
    """
    self.sync()

  def __enter__(self):
    """
    ????
    """
    return self

  def __exit__(self, *exc_info):
    """
    close the file
    """
    self.close()

  def dump(self, filename):
    """
    dump the file
    """
    if self.format == 'json':
      with open(filename, mode='w', encoding='utf-8') as f:
        json.dump(self, f, separators=(',', ':'), skipkeys=True, indent=2)
    elif self.format == 'pickle':
      with open(filename, 'wb') as f:
        pickle.dump(dict(self), f, 2)
    else:
      raise NotImplementedError('Unknown format: ' + repr(self.format))

  def pload(self):
    """
    load from file
    """
    # try formats from most restrictive to least restrictive
    if self.flag != 'n' and os.access(self.filename, os.R_OK):
      self.load()

  def load(self):
    """
    load the dictionary
    """
    tstuff = {}
    if not os.path.exists(self.filename):
      return
    try:
      if self.format == 'pickle':
        with open(self.filename, 'rb') as f:
          tstuff = pickle.load(f)
      elif self.format == 'json':
        with open(self.filename, 'r', encoding='utf-8') as f:
          tstuff = json.load(f, object_hook=convert)

      nstuff = convertkeystoint(tstuff)
      return self.update(nstuff)

    except Exception:  # pylint: disable=broad-except
      #if 'log' not in self.filename:
      self.api('send.traceback')("Error when loading %s" % loader)
      #else:
      #  pass

    raise ValueError('File not in a supported format')

  def __setitem__(self, key, val):
    """
    override setitem
    """
    try:
      key = int(key)
    except ValueError:
      key = convert(key)
    val = convert(val)
    dict.__setitem__(self, key, val)

  def update(self, *args, **kwargs):
    """
    override update
    """
    for k, val in dict(*args, **kwargs).items():
      self[k] = val

  def __deepcopy__(self, memo):
    return self

class PersistentDictEvent(PersistentDict):
  """
  a class to send events when a dictionary object is set
  """
  def __init__(self, plugin, filename, *args, **kwds):
    """
    init the class
    """
    self.plugin = plugin
    PersistentDict.__init__(self, filename, *args, **kwds)

  def __setitem__(self, key, val):
    """
    override setitem
    """
    key = convert(key)
    val = convert(val)
    if key in self:
      oldvalue = self.plugin.api('setting.gets')(key)
    else:
      oldvalue = None
    if oldvalue != val:
      dict.__setitem__(self, key, val)

      eventname = 'var_%s_%s' % (self.plugin.sname, key)
      if not self.plugin.resetflag and key != '_version':
        self.plugin.api('events.eraise')(eventname,
                                         {'var':key,
                                          'newvalue':self.plugin.api('setting.gets')(key),
                                          'oldvalue':oldvalue})

  def raiseall(self):
    """
    go through and raise a var_<plugin>_<variable> for each variable
    """
    for i in self:
      eventname = 'var_%s_%s' % (self.plugin.sname, i)
      if not self.plugin.resetflag and i != '_version':
        self.plugin.api('events.eraise')(eventname,
                                         {'var':i,
                                          'newvalue':self.plugin.api('setting.gets')(i),
                                          'oldvalue':'__init__'})

  def sync(self):
    """
    always put plugin version in here
    """
    self['_version'] = self.plugin.version

    PersistentDict.sync(self)
