# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/persistentdict.py
#
# File Description: setup logging with some customizations
#
# By: Bast
"""
a module that holds a persistent dictionary implementation
it saves the dict to a file
"""

# Standard Library
import pickle
import json
import os
import shutil
import stat
import contextlib

# Third Party

# Project
from libs.api import API
from libs.records import LogRecord

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

def convert_keys_to_int(tdict):
    """
    convert all keys in int if they are numbers
    """
    new = {}
    for i in tdict:
        nkey = i
        with contextlib.suppress(ValueError):
            nkey = int(i)
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
    Output file format is selectable between pickle and json
    All three serialization formats are backed by fast C implementations.

    '''
    def __init__(self, owner_id, file_name, flag='c', mode=None,
                 tformat='json', *args, **kwargs):
        """
        initialize the instance
        """
        self.owner_id = owner_id
        self._dump_shallow_attrs = ['api']
        self.api = API(owner_id=f"{self.owner_id}:{__name__}:{file_name}")

        # r=readonly, c=create, or n=new
        self.flag = flag

        # None or an octal triple like 0644
        self.mode = (stat.S_IWUSR | stat.S_IRUSR) or mode

        # json', or 'pickle'
        self.format = tformat
        self.file_name = file_name
        self.pload()
        super().__init__(*args, **kwargs)

    def sync(self):
        """
        write data to disk
        """
        if self.flag == 'r':
            return
        temp_name = self.file_name.with_suffix('.tmp')

        try:
            self.dump(temp_name)
        except Exception:
            os.remove(temp_name)
            raise
        finally:
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

    def __exit__(self, _):
        """
        close the file
        """
        self.close()

    def dump(self, file_object):
        """
        dump the file
        """
        if self.format == 'json':
            with file_object.open(mode='w', encoding='utf-8') as f:
                json.dump(self, f, separators=(',', ':'), skipkeys=True, indent=2)
        elif self.format == 'pickle':
            with file_object.open(mode='wb') as f:
                pickle.dump(dict(self), f, 2)
        else:
            raise NotImplementedError(f'Unknown format: {repr(self.format)}')

    def pload(self):
        """
        load from file
        """
        # try formats from most restrictive to least restrictive
        if (
            self.file_name.exists()
            and self.flag != 'n'
            and os.access(self.file_name, os.R_OK)
        ):
            self.load()

    def load(self):
        """
        load the dictionary
        """
        tstuff = {}

        if not self.file_name.exists():
            return
        try:
            if self.format == 'pickle':
                with self.file_name.open(mode='rb') as tfile:
                    tstuff = pickle.load(tfile)
            elif self.format == 'json':
                with self.file_name.open('r', encoding='utf-8') as tfile:
                    tstuff = json.load(tfile, object_hook=convert)

            nstuff = convert_keys_to_int(tstuff)
            return self.update(nstuff)

        except Exception:  # pylint: disable=broad-except
            sources = [__name__]
            if getattr(self, 'owner_id'):
                sources.append(self.owner_id)
            LogRecord(f"Error when loading {self.format} from {self.file_name}",
                               level='error', sources=sources, exc_info=True)()

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
        super().__setitem__(key, val)

    def update(self, *args, **kwargs):
        """
        override update
        """
        for k, val in dict(*args, **kwargs).items():
            self[k] = val

    def __deepcopy__(self, _):
        return self

class PluginPersistentDict(PersistentDict):
    """
    a class to send events when a dictionary object is set
    """
    def __init__(self, owner_id, file_name, *args, **kwds):
        """
        init the class
        """
        super().__init__(owner_id, file_name, *args, **kwds)
        self.event_setup = False

    def add_events(self):
        """
        add events for each setting
        """
        if not self.event_setup and self.api('libs.api:has')(
            'plugins.core.events:add.event'
        ):
            self.event_setup = True
            for i in self:
                if not self.api(f"{self.owner_id}:setting.is.hidden")(i):
                    event_name = f"ev_{self.owner_id}_var_{i}_modified"
                    self.api('plugins.core.events:add.event')(event_name, self.owner_id,
                                        description=[f"An event raised when {i} is modified in {self.owner_id}"],
                                        arg_descriptions={'var':'The variable that was modified',
                                        'newvalue':'the new value of the variable',
                                        'oldvalue':'the old value of the variable, will be "__init__" if the variable was not set before'})

    def __setitem__(self, key, val):
        """
        override setitem
        """
        key = convert(key)
        val = convert(val)
        old_value = None
        try:
            plugin_instance = self.api('libs.pluginloader:get.plugin.instance')(self.owner_id)
        except AttributeError:
            plugin_instance = None
        if key in self and plugin_instance:
            old_value =  self.api(f"{plugin_instance.plugin_id}:setting.get")(key)
        if old_value != val:
            dict.__setitem__(self, key, val)

            if plugin_instance and \
                (plugin_instance.reset_f
                 or plugin_instance.initializing_f
                 or self.api(f"{plugin_instance.plugin_id}:setting.is.hidden")(key)):
                return
            if self.api.startup:
                return

            if plugin_instance:
                new_value =  self.api(f"{plugin_instance.plugin_id}:setting.get")(key)
            else:
                new_value = val

            event_name = f"ev_{self.owner_id}_var_{key}_modified"
            old_value = old_value

            if self.api('libs.api:has')('plugins.core.events:raise.event'):
                    self.api('plugins.core.events:raise.event')(
                        event_name,
                        {'var':key,
                        'newvalue':new_value,
                        'oldvalue':old_value})

    def raiseall(self):
        """
        go through and raise a ev_<plugin>_var_<setting>_modified event for each setting
        """
        self.add_events()
        plugin_instance = self.api('libs.pluginloader:get.plugin.instance')(self.owner_id)
        old_value = '__init__'
        for i in self:
            if plugin_instance:
                if self.api(f"{plugin_instance.plugin_id}:setting.is.hidden")(i):
                    continue
                event_name = f"ev_{self.owner_id}_var_{i}_modified"
                new_value = self.api(f"{plugin_instance.plugin_id}:setting.get")(i)
            else:
                event_name = f"ev_{self.owner_id}_var_{i}_modified"
                new_value = self[i]

            self.api('plugins.core.events:raise.event')(
                event_name,
                {'var':i,
                'newvalue':new_value,
                'oldvalue':old_value})

