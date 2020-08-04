"""
a module that holds a persistent dictionary implementation
it saves the dict to a file
"""
import pickle
import json
import csv
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
    return {convert(key): convert(value) for key, value in tinput.iteritems()}
  elif isinstance(tinput, list):
    return [convert(element) for element in tinput]
  elif isinstance(tinput, unicode):
    return tinput.encode('utf-8')

  return tinput

def convert_keys_to_int(tdict):
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
      ndata = convert_keys_to_int(tdict[i])
    new[nkey] = ndata
  return new

class PersistentDict(dict):
  ''' Persistent dictionary with an API compatible with shelve and anydbm.

  The dict is kept in memory, so the dictionary operations run as fast as
  a regular dictionary.

  Write to disk is delayed until close or sync (similar to gdbm's fast mode).

  Input file format is automatically discovered.
  Output file format is selectable between pickle, json, and csv.
  All three serialization formats are backed by fast C implementations.

  '''
  def __init__(self, file_name, flag='c', mode=None,
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

    # 'csv', 'json', or 'pickle'
    self.format = tformat
    self.file_name = file_name
    self.pload()
    dict.__init__(self, *args, **kwds)

  def sync(self):
    """
    write data to disk
    """
    if self.flag == 'r':
      return
    file_name = self.file_name
    temp_name = file_name + '.tmp'
    file_object = open(temp_name, 'wb' if self.format == 'pickle' else 'w')
    try:
      self.dump(file_object)
    except Exception:
      os.remove(temp_name)
      raise
    finally:
      file_object.close()
    shutil.move(temp_name, self.file_name)    # atomic commit
    if self.mode is not None:
      os.chmod(self.file_name, self.mode)

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

  def dump(self, file_object):
    """
    dump the file
    """
    if self.format == 'csv':
      csv.writer(file_object).writerows(self.items())
    elif self.format == 'json':
      try:
        json.dump(self, file_object, separators=(',', ':'), skipkeys=True)
      except TypeError:
        self.api('send.traceback')('Could not save object')
    elif self.format == 'pickle':
      pickle.dump(dict(self), file_object, 2)
    else:
      raise NotImplementedError('Unknown format: ' + repr(self.format))

  def pload(self):
    """
    load from file
    """
    # try formats from most restrictive to least restrictive
    if os.path.exists(self.file_name):
      if self.flag != 'n' and os.access(self.file_name, os.R_OK):
        self.load()

  def load(self):
    """
    load the dictionary
    """
    tstuff = {}
    if not os.path.exists(self.file_name):
      return
    try:
      if self.format == 'pickle':
        with open(self.file_name, 'rb') as tfile:
          tstuff = pickle.load(tfile)
      elif self.format == 'json':
        with open(self.file_name, 'r') as tfile:
          tstuff = json.load(tfile, object_hook=convert)

      nstuff = convert_keys_to_int(tstuff)
      return self.update(nstuff)

    except Exception:  # pylint: disable=broad-except
      #if 'log' not in self.file_name:
      self.api('send.traceback')("Error when loading %s from %s" % \
                                    (self.format, self.file_name))
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
    for k, val in dict(*args, **kwargs).iteritems():
      self[k] = val

  def __deepcopy__(self, memo):
    return self

class PersistentDictEvent(PersistentDict):
  """
  a class to send events when a dictionary object is set
  """
  def __init__(self, plugin, file_name, *args, **kwds):
    """
    init the class
    """
    self.plugin = plugin
    PersistentDict.__init__(self, file_name, *args, **kwds)

  def __setitem__(self, key, val):
    """
    override setitem
    """
    key = convert(key)
    val = convert(val)
    old_value = None
    if key in self:
      old_value = self.plugin.api('setting.gets')(key)
    if old_value != val:
      dict.__setitem__(self, key, val)

      event_name = 'var_%s_%s' % (self.plugin.short_name, key)
      if not self.plugin.reset_f and key != '_version':
        self.plugin.api('events.eraise')(event_name,
                                         {'var':key,
                                          'newvalue':self.plugin.api('setting.gets')(key),
                                          'oldvalue':old_value})

  def raiseall(self):
    """
    go through and raise a var_<plugin>_<variable> for each variable
    """
    for i in self:
      event_name = 'var_%s_%s' % (self.plugin.short_name, i)
      if not self.plugin.reset_f and i != '_version':
        self.plugin.api('events.eraise')(event_name,
                                         {'var':i,
                                          'newvalue':self.plugin.api('setting.gets')(i),
                                          'oldvalue':'__init__'})

  def sync(self):
    """
    always put plugin version in here
    """
    self['_version'] = self.plugin.version

    PersistentDict.sync(self)
