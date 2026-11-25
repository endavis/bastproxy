# Project: bastproxy
# Filename: libs/persistentdict.py
#
# File Description: persistent dictionary stored as a JSON file
#
# By: Bast
"""Module for managing a persistent dictionary with delayed disk writes.

This module provides the `PersistentDict` class, which allows for the creation of
a dictionary that persists its data to disk. The dictionary operations are performed
in memory for speed, and the data is written to disk only when explicitly requested.
The data is stored as JSON, in a file only the owner can read and write (0600).

Key Components:
    - PersistentDict: A class that extends the built-in dict to provide persistence.
    - Utility functions for converting data types and keys.

Features:
    - Delayed disk writes for improved performance.
    - JSON serialization, written atomically with permissions 0600.
    - Keys that look like integers are stored as integers (``"007"`` -> 7).
    - Tuples are refused with a ``TypeError`` because JSON would turn them into lists.
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
import shutil
import stat
from pathlib import Path
from types import TracebackType
from typing import Any, Self

# Third Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.logger import log_to


def convert(tinput: Any) -> Any:
    """Convert input data to appropriate types.

    This function recursively converts input data to appropriate types based on
    its content. Dictionaries and lists are rebuilt with converted contents; every
    other value, including bytes, is returned unchanged.

    Args:
        tinput: The input data to convert.

    Returns:
        The converted data.

    Raises:
        TypeError: If a tuple is found at any depth, since JSON would store it
            as a list and a reload would not give back what was saved.

    """
    if isinstance(tinput, dict):
        return {convert(key): convert(value) for key, value in tinput.items()}
    if isinstance(tinput, list):
        return [convert(element) for element in tinput]
    if isinstance(tinput, tuple):
        msg = "tuples are not supported, use a list instead"
        raise TypeError(msg)

    return tinput


def convert_keys_to_int(tdict: dict) -> dict[Any, Any]:
    """Convert dictionary keys to integers where possible.

    This function takes a dictionary and attempts to convert its keys to integers.
    If a key cannot be converted to an integer (``ValueError`` or ``TypeError``), it
    is left unchanged. Existing files are stored with string keys, so this restores
    integer keys on load. The function is applied recursively to nested dictionaries.

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
        with contextlib.suppress(ValueError, TypeError):
            nkey = int(i)
        converted_ndata = convert_keys_to_int(ndata) if isinstance(ndata, dict) else ndata
        new[nkey] = converted_ndata
    return new


def check_serializable(key: Any, value: Any) -> None:
    """Check that a value can be written as JSON.

    Args:
        key: The key the value would be stored under, used in the message.
        value: The value to check.

    Raises:
        TypeError: If the value cannot be serialized.

    """
    try:
        json.dumps(convert(value), skipkeys=True)
    except (TypeError, ValueError) as err:
        msg = f"Value for key {key!r} of type {type(value).__name__} cannot be saved as json: {err}"
        raise TypeError(msg) from err


class PersistentDict(dict):
    """Persistent dictionary with an API compatible with shelve and anydbm.

    The dict is kept in memory, so the dictionary operations run as fast as
    a regular dictionary.

    Write to disk is delayed until close or sync (similar to gdbm's fast mode).

    The file is JSON, written atomically with permissions 0600.

    `sync` skips the write when nothing changed since the last write or load.
    Two checks decide that: a dirty flag set by every mutating method, and a
    comparison of the serialized text with the text last written or loaded, which
    catches values mutated in place (for example appending to a nested list).

    """

    _dirty: bool = False
    _last_saved: str | None = None

    def __init__(
        self,
        owner_id: str,
        file_name: "Path",
        flag: str = "c",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the PersistentDict.

        This method initializes the PersistentDict with the given parameters,
        setting up the owner ID and file name.
        It also loads the existing data from the file if available.

        Args:
            owner_id: The ID of the owner of the dictionary.
            file_name: The name of the file where the dictionary data is stored.
            flag: The mode in which to open the file.
            *args: Additional positional arguments to pass to the dict constructor.
            **kwargs: Additional keyword arguments to pass to the dict constructor.

        Returns:
            None

        Raises:
            TypeError: If the removed ``tformat`` or ``mode`` argument is passed.
                JSON is the only format and the file mode is always 0600.

        """
        for removed in ("tformat", "mode"):
            if removed in kwargs:
                msg = (
                    f"PersistentDict no longer accepts the {removed!r} argument: "
                    "JSON is the only format and files are always 0600"
                )
                raise TypeError(msg)
        self.owner_id = owner_id
        self._dump_shallow_attrs = ["api"]
        self.api = API(owner_id=f"{self.owner_id}:libs.persistentdict:{file_name}")

        # r=readonly, c=create, or n=new
        self.flag = flag

        # the file is only readable and writable by its owner (0600)
        self.mode: int = stat.S_IWUSR | stat.S_IRUSR

        self.file_name = file_name
        self._dirty = False
        self._last_saved = None
        self.load()
        super().__init__(*args, **kwargs)
        if args or kwargs:
            self._dirty = True

    def sync(self) -> None:
        """Synchronize the in-memory dictionary with the file on disk.

        This method writes the current state of the in-memory dictionary to the
        file on disk. It first writes the data to a temporary file and then
        atomically moves it to the target file to ensure data integrity. If the
        dictionary is opened in read-only mode, this method does nothing.

        The write is also skipped, with no file I/O, when the dictionary is not
        marked dirty, the file exists and the serialized dictionary equals the text
        last written or loaded. Values mutated in place are detected by that
        comparison.

        Returns:
            None

        Raises:
            Exception: The original exception from `dump()` propagates unchanged
                if writing the temporary file fails. The temporary file is
                removed and the target file is left untouched.

        """
        if self.flag == "r":
            return
        text = self._serialize()
        if (
            not self._dirty
            and self._last_saved is not None
            and text == self._last_saved
            and self.file_name.exists()
        ):
            return
        temp_name = self.file_name.with_suffix(".tmp")

        try:
            self.dump(temp_name, text)
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
        Path(self.file_name).chmod(self.mode)
        self._last_saved = text
        self._dirty = False

    def _serialize(self) -> str:
        """Serialize the dictionary as the JSON text written to disk.

        Returns:
            The JSON text.

        """
        return json.dumps(self, separators=(",", ":"), skipkeys=True, indent=2)

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

    def dump(self, file_object: "Path", text: str | None = None) -> None:
        """Dump the dictionary to a file.

        This method serializes the in-memory dictionary as JSON and writes it to
        the specified file, flushing and fsyncing before it returns. `sync` calls it
        with a temporary file and atomically moves that onto the target file.

        Args:
            file_object: The file to which the dictionary data will be written.
            text: The already serialized JSON text. Serialized here if omitted.

        Returns:
            None

        Raises:
            None

        """
        with file_object.open(mode="w", encoding="utf-8") as f:
            f.write(self._serialize() if text is None else text)
            f.flush()
            os.fsync(f.fileno())

    def load(self) -> None:
        """Load the dictionary data from the file.

        This method reads the JSON file, converts the keys to integers where
        possible and updates the in-memory dictionary with the loaded data. If the
        file does not exist, is not readable, or the flag is ``"n"``, the method
        does nothing. If the file cannot be loaded, the error is logged,
        the file is renamed to ``<name>.corrupt-<YYYYmmdd-HHMMSS>`` (a counter is
        added if that name exists), and the dictionary stays empty, so the next
        sync writes a fresh file and the bad one is kept for inspection.

        Returns:
            None

        Raises:
            None

        """
        if (
            self.flag == "n"
            or not self.file_name.exists()
            or not os.access(self.file_name, os.R_OK)
        ):
            return None
        try:
            with self.file_name.open("r", encoding="utf-8") as tfile:
                tstuff = json.load(tfile)

            nstuff = convert_keys_to_int(tstuff)
            self.update(nstuff)
            # what was loaded is what is on disk, so nothing needs writing
            self._dirty = False
            self._last_saved = self._serialize()
            return None

        except Exception:  # pylint: disable=broad-except
            sources = [__name__]
            if self.owner_id:
                sources.append(self.owner_id)
            log_to(
                sources,
                logging.ERROR,
                "Error when loading json from %s",
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
        """Check that a value can be written as JSON.

        The dictionary is not modified.

        Args:
            key: The key the value would be stored under.
            value: The value to check.

        Raises:
            TypeError: If the value cannot be serialized.

        """
        check_serializable(key, value)

    def __setitem__(self, key: Any, val: Any) -> None:
        """Set the value for a given key in the dictionary.

        This method overrides the default `__setitem__` behavior to ensure that
        keys and values are converted to appropriate types before being stored
        in the dictionary. It attempts to convert the key to an integer (a key
        that cannot be converted, such as ``None``, is stored as is) and the
        value to a suitable type using the `convert` function.

        Args:
            key: The key for the dictionary entry. It can be a string or integer.
            val: The value to associate with the key. It can be of any type.

        Returns:
            None

        Raises:
            TypeError: If the key or value contains a tuple.

        """
        try:
            key = int(key)
        except (ValueError, TypeError):
            key = convert(key)
        val = convert(val)
        super().__setitem__(key, val)
        self._dirty = True

    def __delitem__(self, key: Any) -> None:
        """Delete a key and mark the dictionary as changed.

        Args:
            key: The key to delete.

        Raises:
            KeyError: If the key is not in the dictionary.

        """
        super().__delitem__(key)
        self._dirty = True

    def pop(self, key: Any, *args: Any) -> Any:
        """Remove a key and return its value, marking the dictionary changed.

        Args:
            key: The key to remove.
            *args: An optional default returned when the key is missing.

        Returns:
            The removed value, or the default.

        Raises:
            KeyError: If the key is missing and no default is given.

        """
        present = key in self
        value = super().pop(key, *args)
        if present:
            self._dirty = True
        return value

    def popitem(self) -> tuple[Any, Any]:
        """Remove and return the last item, marking the dictionary changed.

        Returns:
            The removed ``(key, value)`` pair.

        Raises:
            KeyError: If the dictionary is empty.

        """
        item = super().popitem()
        self._dirty = True
        return item

    def clear(self) -> None:
        """Remove all items, marking the dictionary changed if there were any."""
        if self:
            self._dirty = True
        super().clear()

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """Return the value for a key, inserting the default if it is missing.

        The default is stored as given (not converted), so callers can mutate the
        returned object in place. The dictionary is marked changed only when the
        key was inserted.

        Args:
            key: The key to look up.
            default: The value stored when the key is missing.

        Returns:
            The existing value or the default.

        """
        size = len(self)
        value = super().setdefault(key, default)
        if len(self) != size:
            self._dirty = True
        return value

    def __ior__(self, other: Any) -> Self:  # type: ignore[misc]  # dict.__or__ is overloaded for dict only; update() takes any mapping or pairs
        """Merge ``other`` in place through `update`, so values are converted.

        Args:
            other: A mapping or iterable of key-value pairs.

        Returns:
            The dictionary itself.

        """
        self.update(other)
        return self

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
            TypeError: If a key or value contains a tuple.

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
