# Project: bastproxy
# Filename: libs/persistentdict.py
#
# File Description: setup logging with some customizations
#
# By: Bast
"""Module for managing a persistent dictionary with delayed disk writes.

This module provides the `PersistentDict` class, which allows for the creation of
a dictionary that persists its data to disk. The dictionary operations are performed
in memory for speed, and the data is written to disk only when explicitly requested.
The module supports both JSON and pickle formats for serialization.

Key Components:
    - PersistentDict: A class that extends the built-in dict to provide persistence.
    - Utility functions for converting data types and keys.

Features:
    - Delayed disk writes for improved performance.
    - Support for JSON and pickle serialization formats.
    - Automatic conversion of input data to appropriate types.
    - Context manager support for automatic resource management.

Usage:
    - Instantiate PersistentDict to create a persistent dictionary.
    - Use standard dictionary methods to manipulate the data.
    - Call `sync` or `close` to write data to disk.
    - Use the context manager interface to ensure data is written on exit.

Classes:
    - `PersistentDict`: Represents a dictionary that persists its data to disk.

"""

# Standard Library
import contextlib
import datetime
import json
import logging
import os
import pickle
import shutil
import stat
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

# Third Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.logger import log_to

if TYPE_CHECKING:
    pass


def convert(tinput: Any) -> Any:
    """Convert input data to appropriate types.

    This function recursively converts input data to appropriate types based on
    its content. It handles dictionaries, lists, strings, and bytes, converting
    them as necessary.

    Args:
        tinput: The input data to convert. It can be a dictionary, list, string,
            or bytes.

    Returns:
        The converted data, with types adjusted as necessary.

    Raises:
        None

    """
    if isinstance(tinput, dict):
        return {convert(key): convert(value) for key, value in tinput.items()}
    if isinstance(tinput, list):
        return [convert(element) for element in tinput]
    if isinstance(tinput, str):
        return tinput
    if isinstance(tinput, bytes):
        return str(tinput)

    return tinput


def convert_keys_to_int(tdict: dict) -> dict[Any, Any]:
    """Convert dictionary keys to integers where possible.

    This function takes a dictionary and attempts to convert its keys to integers.
    If a key cannot be converted to an integer, it is left unchanged. The function
    is applied recursively to nested dictionaries.

    Args:
        tdict: The dictionary whose keys are to be converted.

    Returns:
        A new dictionary with keys converted to integers where possible.

    Raises:
        None

    """
    new = {}
    for i, ndata in tdict.items():
        nkey = i
        with contextlib.suppress(ValueError):
            nkey = int(i)
        converted_ndata = convert_keys_to_int(ndata) if isinstance(ndata, dict) else ndata
        new[nkey] = converted_ndata
    return new


def check_serializable(key: Any, value: Any, tformat: str = "json") -> None:
    """Check that a value can be written in the given format.

    Args:
        key: The key the value would be stored under, used in the message.
        value: The value to check.
        tformat: The serialization format ('json' or 'pickle').

    Raises:
        TypeError: If the value cannot be serialized.

    """
    try:
        if tformat == "pickle":
            pickle.dumps(value, 2)
        else:
            json.dumps(convert(value), skipkeys=True)
    except (TypeError, ValueError, pickle.PicklingError, AttributeError) as err:
        msg = (
            f"Value for key {key!r} of type {type(value).__name__} "
            f"cannot be saved as {tformat}: {err}"
        )
        raise TypeError(msg) from err


class PersistentDict(dict):
    """Persistent dictionary with an API compatible with shelve and anydbm.

    The dict is kept in memory, so the dictionary operations run as fast as
    a regular dictionary.

    Write to disk is delayed until close or sync (similar to gdbm's fast mode).

    Input file format is automatically discovered.
    Output file format is selectable between pickle and json
    All three serialization formats are backed by fast C implementations.

    """

    def __init__(
        self,
        owner_id: str,
        file_name: "Path",
        flag: str = "c",
        mode: str | None = None,
        tformat: str = "json",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the PersistentDict.

        This method initializes the PersistentDict with the given parameters,
        setting up the owner ID, file name, file mode, and serialization format.
        It also loads the existing data from the file if available.

        Args:
            owner_id: The ID of the owner of the dictionary.
            file_name: The name of the file where the dictionary data is stored.
            flag: The mode in which to open the file.
            mode: The file mode to use when creating the file.
            tformat: The serialization format to use ('json' or 'pickle').
            *args: Additional positional arguments to pass to the dict constructor.
            **kwargs: Additional keyword arguments to pass to the dict constructor.

        Returns:
            None

        Raises:
            None

        """
        self.owner_id = owner_id
        self._dump_shallow_attrs = ["api"]
        self.api = API(owner_id=f"{self.owner_id}:libs.persistentdict:{file_name}")

        # r=readonly, c=create, or n=new
        self.flag = flag

        # None or an octal triple like 0644
        self.mode: int | None = (
            stat.S_IWUSR | stat.S_IRUSR
        )  # always set; the ``mode`` argument is unused

        # json', or 'pickle'
        self.format = tformat
        self.file_name = file_name
        self.pload()
        super().__init__(*args, **kwargs)

    def sync(self) -> None:
        """Synchronize the in-memory dictionary with the file on disk.

        This method writes the current state of the in-memory dictionary to the
        file on disk. It first writes the data to a temporary file and then
        atomically moves it to the target file to ensure data integrity. If the
        dictionary is opened in read-only mode, this method does nothing.

        Returns:
            None

        Raises:
            Exception: The original exception from `dump()` propagates unchanged
                if writing the temporary file fails. The temporary file is
                removed and the target file is left untouched.

        """
        if self.flag == "r":
            return
        temp_name = self.file_name.with_suffix(".tmp")

        try:
            self.dump(temp_name)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
        shutil.move(temp_name, self.file_name)  # atomic commit
        with contextlib.suppress(OSError):
            dir_fd = os.open(self.file_name.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        if self.mode is not None:
            Path(self.file_name).chmod(self.mode)

    def close(self) -> None:
        """Close the dictionary and synchronize with the file on disk.

        This method ensures that any changes made to the in-memory dictionary
        are written to the file on disk by calling the `sync` method. It is
        typically used when the dictionary is no longer needed, and its state
        should be persisted.

        Returns:
            None

        Raises:
            Exception: If an error occurs during the synchronization process.

        """
        self.sync()

    def __enter__(self) -> Any:
        """Enter the runtime context related to this object.

        This method is called when the runtime context is entered using the
        `with` statement. It returns the PersistentDict instance itself, allowing
        the dictionary to be used within the context.

        Returns:
            PersistentDict: The instance of the PersistentDict.

        Raises:
            None

        """
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Exit the runtime context related to this object.

        This method is called when the runtime context is exited using the
        `with` statement. It ensures that any changes made to the in-memory
        dictionary are written to the file on disk by calling the `close` method.

        Args:
            _exc_type: The type of exception raised, if any.
            _exc_val: The exception instance raised, if any.
            _exc_tb: The traceback object for the exception, if any.

        Returns:
            None

        Raises:
            None

        """
        self.close()

    def dump(self, file_object: "Path") -> None:
        """Dump the dictionary to a file.

        This method serializes the in-memory dictionary and writes it to the specified
        file object. The serialization format is determined by the `format` attribute,
        which can be either 'json' or 'pickle'. The data is written to a temporary file
        and then atomically moved to the target file to ensure data integrity.

        Args:
            file_object: The file object to which the dictionary data will be written.

        Returns:
            None

        Raises:
            NotImplementedError: If the specified format is not supported.

        """
        if self.format == "json":
            with file_object.open(mode="w", encoding="utf-8") as f:
                json.dump(self, f, separators=(",", ":"), skipkeys=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
        elif self.format == "pickle":
            with file_object.open(mode="wb") as f:
                pickle.dump(dict(self), f, 2)
                f.flush()
                os.fsync(f.fileno())
        else:
            msg = f"Unknown format: {self.format!r}"
            raise NotImplementedError(msg)

    def pload(self) -> None:
        """Load the dictionary from the file on disk.

        This method loads the dictionary data from the file on disk. It attempts to
        read the data using the specified serialization format (either 'json' or
        'pickle'). If the file does not exist or is not readable, the method does
        nothing. If the file cannot be loaded it is moved aside (see `load`) and
        the dictionary stays empty.

        Returns:
            None

        Raises:
            None

        """
        # try formats from most restrictive to least restrictive
        if self.file_name.exists() and self.flag != "n" and os.access(self.file_name, os.R_OK):
            self.load()

    def load(self) -> None:
        """Load the dictionary data from the file.

        This method reads the dictionary data from the file on disk using the
        specified serialization format (either 'json' or 'pickle'). It converts
        the keys to integers where possible and updates the in-memory dictionary
        with the loaded data. If the file does not exist or is not readable, the
        method does nothing. If the file cannot be loaded, the error is logged,
        the file is renamed to ``<name>.corrupt-<YYYYmmdd-HHMMSS>`` (a counter is
        added if that name exists), and the dictionary stays empty, so the next
        sync writes a fresh file and the bad one is kept for inspection.

        Returns:
            None

        Raises:
            None

        """
        tstuff = {}

        if not self.file_name.exists():
            return None
        try:
            if self.format == "pickle":
                with self.file_name.open(mode="rb") as tfile:
                    tstuff = pickle.load(tfile)
            elif self.format == "json":
                with self.file_name.open("r", encoding="utf-8") as tfile:
                    tstuff = json.load(tfile, object_hook=convert)

            nstuff = convert_keys_to_int(tstuff)
            return self.update(nstuff)

        except Exception:  # pylint: disable=broad-except
            sources = [__name__]
            if self.owner_id:
                sources.append(self.owner_id)
            log_to(
                sources,
                logging.ERROR,
                "Error when loading %s from %s",
                self.format,
                self.file_name,
                exc_info=True,
            )

        self._move_corrupt_aside(sources)
        return None

    def _move_corrupt_aside(self, sources: list[str]) -> None:
        """Rename an unloadable file to ``<name>.corrupt-<timestamp>``."""
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{self.file_name.name}.corrupt-{stamp}"
        target = self.file_name.with_name(base)
        counter = 1
        while target.exists():
            target = self.file_name.with_name(f"{base}-{counter}")
            counter += 1
        try:
            self.file_name.rename(target)
        except OSError:
            log_to(
                sources,
                logging.ERROR,
                "Could not move corrupt file %s aside",
                self.file_name,
                exc_info=True,
            )
            return
        log_to(sources, logging.ERROR, "Moved corrupt file %s to %s", self.file_name, target)

    def check_serializable(self, key: Any, value: Any) -> None:
        """Check that a value can be written in this dict's format.

        The dictionary is not modified.

        Args:
            key: The key the value would be stored under.
            value: The value to check.

        Raises:
            TypeError: If the value cannot be serialized.

        """
        check_serializable(key, value, self.format)

    def __setitem__(self, key: Any, val: Any) -> None:
        """Set the value for a given key in the dictionary.

        This method overrides the default `__setitem__` behavior to ensure that
        keys and values are converted to appropriate types before being stored
        in the dictionary. It attempts to convert the key to an integer and the
        value to a suitable type using the `convert` function.

        Args:
            key: The key for the dictionary entry. It can be a string or integer.
            val: The value to associate with the key. It can be of any type.

        Returns:
            None

        Raises:
            None

        """
        try:
            key = int(key)
        except ValueError:
            key = convert(key)
        val = convert(val)
        super().__setitem__(key, val)

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Update the dictionary with the provided key-value pairs.

        This method updates the dictionary with the key-value pairs provided
        as arguments. It converts the keys and values to appropriate types
        before storing them in the dictionary.

        Args:
            *args: Positional arguments containing key-value pairs to update
                the dictionary with.
            **kwargs: Keyword arguments containing key-value pairs to update
                the dictionary with.

        Returns:
            None

        Raises:
            None

        """
        for k, val in dict(*args, **kwargs).items():
            self[k] = val

    def __deepcopy__(self, _: dict[int, Any]) -> Self:
        """Provide a custom deep copy implementation that returns the original object.

        This method overrides the default deep copy behavior by returning the same
        object instance instead of creating a new copy. It effectively creates a
        shallow reference to the original object.

        Args:
            _: Memo dictionary used by deepcopy mechanism, which is ignored in this
                implementation.

        Returns:
            The original object instance without creating a new copy.

        Raises:
            None

        """
        return self
