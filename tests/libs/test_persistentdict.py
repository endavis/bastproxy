# Project: bastproxy
# Filename: tests/libs/test_persistentdict.py
#
# File Description: Tests for PersistentDict
#
# By: Bast
"""Unit tests for the PersistentDict class.

This module contains tests for the persistent dictionary functionality,
including saving, loading, and context manager behavior.

"""

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs import persistentdict
from bastproxy.libs.persistentdict import (
    PersistentDict,
    check_serializable,
    convert,
    convert_keys_to_int,
)


class TestPersistentDict:
    """Test suite for PersistentDict class."""

    def test_create_empty_dict(self, temp_data_dir: Path) -> None:
        """Test creating an empty persistent dictionary.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        assert len(pd) == 0
        assert pd.file_name == filepath

    def test_basic_operations(self, temp_data_dir: Path) -> None:
        """Test basic dictionary operations.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        # Test set
        pd["key1"] = "value1"
        assert pd["key1"] == "value1"

        # Test get
        assert pd.get("key1") == "value1"
        assert pd.get("nonexistent") is None

        # Test contains
        assert "key1" in pd
        assert "key2" not in pd

    def test_persistence(self, temp_data_dir: Path) -> None:
        """Test that data persists to disk.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"

        # Create and populate dict
        pd1 = PersistentDict("test_owner", filepath)
        pd1["test_key"] = "test_value"
        pd1["number"] = 42
        pd1.sync()

        # Load in new instance
        pd2 = PersistentDict("test_owner", filepath)
        assert pd2["test_key"] == "test_value"
        assert pd2["number"] == 42

    def test_sync_method(self, temp_data_dir: Path) -> None:
        """Test manual sync saves data to disk.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"

        # Create and populate dict
        pd1 = PersistentDict("test_owner", filepath)
        pd1["manual_sync"] = True
        pd1.sync()

        # Verify data was saved
        pd2 = PersistentDict("test_owner", filepath)
        assert pd2["manual_sync"] is True

    def test_delete_operation(self, temp_data_dir: Path) -> None:
        """Test deleting keys from dictionary.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["to_delete"] = "value"
        assert "to_delete" in pd

        del pd["to_delete"]
        assert "to_delete" not in pd

    def test_update_method(self, temp_data_dir: Path) -> None:
        """Test updating dictionary with multiple values.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd.update({"key1": "val1", "key2": "val2"})
        assert pd["key1"] == "val1"
        assert pd["key2"] == "val2"

    def test_clear_method(self, temp_data_dir: Path) -> None:
        """Test clearing all items from dictionary.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["key1"] = "val1"
        pd["key2"] = "val2"
        assert len(pd) == 2

        pd.clear()
        assert len(pd) == 0

    def test_keys_values_items(self, temp_data_dir: Path) -> None:
        """Test dict view methods.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["a"] = 1
        pd["b"] = 2
        pd["c"] = 3

        assert set(pd.keys()) == {"a", "b", "c"}
        assert set(pd.values()) == {1, 2, 3}
        assert set(pd.items()) == {("a", 1), ("b", 2), ("c", 3)}

    def test_iteration(self, temp_data_dir: Path) -> None:
        """Test iterating over dictionary.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["x"] = 10
        pd["y"] = 20
        pd["z"] = 30

        keys = list(pd)
        assert set(keys) == {"x", "y", "z"}

    def test_nested_data_structures(self, temp_data_dir: Path) -> None:
        """Test storing nested dicts and lists.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["nested"] = {"inner": {"deep": "value"}}
        pd["list"] = [1, 2, {"key": "val"}]

        pd.sync()

        pd2 = PersistentDict("test_owner", filepath)
        assert pd2["nested"]["inner"]["deep"] == "value"
        assert pd2["list"][2]["key"] == "val"

    def test_pop_method(self, temp_data_dir: Path) -> None:
        """Test pop method with default value.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        pd["key"] = "value"

        popped = pd.pop("key")
        assert popped == "value"
        assert "key" not in pd

        default = pd.pop("missing", "default_val")
        assert default == "default_val"

    def test_context_manager_saves_and_exits_cleanly(self, temp_data_dir: Path) -> None:
        """Test that using PersistentDict as a context manager syncs and exits cleanly.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"

        with PersistentDict("test_owner", filepath) as pd:
            pd["context_key"] = "context_value"

        assert filepath.exists()

        pd2 = PersistentDict("test_owner", filepath)
        assert pd2["context_key"] == "context_value"

    def test_context_manager_exits_cleanly_on_exception(self, temp_data_dir: Path) -> None:
        """Test that `__exit__` still syncs data when the `with` block raises.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"

        with pytest.raises(ValueError, match="boom"), PersistentDict("test_owner", filepath) as pd:
            pd["key_before_error"] = "value"
            raise ValueError("boom")

        pd2 = PersistentDict("test_owner", filepath)
        assert pd2["key_before_error"] == "value"

    def test_setdefault_method(self, temp_data_dir: Path) -> None:
        """Test setdefault method.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)

        # Key doesn't exist, should set and return default
        val = pd.setdefault("new_key", "default")
        assert val == "default"
        assert pd["new_key"] == "default"

        # Key exists, should return existing value
        val = pd.setdefault("new_key", "other")
        assert val == "default"  # Original value preserved

    def test_sync_failure_raises_original_error_and_keeps_target(self, temp_data_dir: Path) -> None:
        """A failed dump re-raises the original error and leaves the target intact.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["good"] = "value"
        pd.sync()
        before = filepath.read_text(encoding="utf-8")

        pd["bad"] = object()
        with pytest.raises(TypeError):
            pd.sync()

        assert not filepath.with_suffix(".tmp").exists()
        assert filepath.read_text(encoding="utf-8") == before

    def test_sync_success_writes_file_and_removes_temp(self, temp_data_dir: Path) -> None:
        """A normal sync writes the file and removes the temp file.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["key"] = "value"
        pd.sync()

        assert filepath.exists()
        assert not filepath.with_suffix(".tmp").exists()

    # Windows has no POSIX permission bits: stat reports 0o666 for a file whatever chmod set (#498).
    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits; Windows uses ACLs")
    def test_sync_success_applies_mode(self, temp_data_dir: Path) -> None:
        """A normal sync sets the file's permission bits to the dict's mode.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["key"] = "value"
        pd.sync()

        assert filepath.stat().st_mode & 0o777 == pd.mode


class TestCorruptRecovery:
    """A file that cannot be loaded is moved aside, not raised (#608)."""

    def test_corrupt_json_moved_aside(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        filepath.write_text("{not json", encoding="utf-8")
        pd = PersistentDict("test_owner", filepath)
        assert len(pd) == 0
        assert not filepath.exists()
        aside = list(temp_data_dir.glob("test.json.corrupt-*"))
        assert len(aside) == 1
        assert aside[0].read_text(encoding="utf-8") == "{not json"
        pd["a"] = 1
        pd.sync()
        assert PersistentDict("test_owner", filepath)["a"] == 1
        assert len(list(temp_data_dir.glob("test.json.corrupt-*"))) == 1

    def test_empty_file_moved_aside(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        filepath.write_text("", encoding="utf-8")
        pd = PersistentDict("test_owner", filepath)
        assert len(pd) == 0
        assert len(list(temp_data_dir.glob("test.json.corrupt-*"))) == 1

    def test_second_corrupt_file_gets_counter(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        for _ in range(2):
            filepath.write_text("{bad", encoding="utf-8")
            PersistentDict("test_owner", filepath)
        assert len(list(temp_data_dir.glob("test.json.corrupt-*"))) == 2


class TestSerializable:
    """check_serializable and fsync before rename (#608)."""

    def test_rejects_set_and_leaves_dict_unchanged(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd["a"] = 1
        with pytest.raises(TypeError, match=r"'k'.*set"):
            pd.check_serializable("k", {1, 2})
        assert dict(pd) == {"a": 1}

    def test_accepts_plain_value(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd.check_serializable("k", {"a": [1, "b"]})

    def test_sync_fsyncs_before_rename(
        self, temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil

        events: list[str] = []
        real_fsync = os.fsync
        real_move = shutil.move

        def fake_fsync(fd: int) -> None:
            events.append("fsync")
            real_fsync(fd)

        def fake_move(src: Path, dst: Path) -> object:
            events.append("move")
            return real_move(src, dst)

        monkeypatch.setattr(os, "fsync", fake_fsync)
        monkeypatch.setattr(shutil, "move", fake_move)
        pd = PersistentDict("test_owner", temp_data_dir / "t.json")
        pd["a"] = 1
        pd.sync()
        assert events.index("fsync") < events.index("move")


class TestKeyConversion:
    """Keys that look like integers are stored as integers (#610)."""

    def test_int_like_keys_become_ints(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd["1_000"] = "a"
        pd["007"] = "b"
        pd[True] = "c"
        pd["abc"] = "d"
        assert pd[1000] == "a"
        assert pd[7] == "b"
        assert pd[1] == "c"
        assert pd["abc"] == "d"

    def test_none_key_is_stored_as_is(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd[None] = 1
        assert pd[None] == 1

    def test_convert_keys_to_int_handles_none_and_nested(self) -> None:
        assert convert_keys_to_int({None: 1, "2": {"3": "a"}}) == {None: 1, 2: {3: "a"}}


class TestTuplesRefused:
    """Tuples raise TypeError because JSON would store them as lists (#610)."""

    def test_setitem_top_level(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        with pytest.raises(TypeError, match="tuple"):
            pd["a"] = (1, 2)
        assert "a" not in pd

    def test_setitem_nested(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        with pytest.raises(TypeError):
            pd["a"] = {"b": [1, (2, 3)]}

    def test_tuple_key(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        with pytest.raises(TypeError):
            pd[(1, 2)] = 1

    def test_update(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        with pytest.raises(TypeError):
            pd.update({"a": (1,)})

    def test_check_serializable(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        with pytest.raises(TypeError, match="tuple"):
            pd.check_serializable("k", {"a": (1,)})
        with pytest.raises(TypeError, match="tuple"):
            check_serializable("k", (1,))


class TestRemovedOptions:
    """Pickle, `mode` and `tformat` are gone (#610)."""

    @pytest.mark.parametrize(
        ("name", "value"), [("tformat", "json"), ("tformat", "pickle"), ("mode", "0644")]
    )
    def test_removed_arguments_raise(self, temp_data_dir: Path, name: str, value: str) -> None:
        path = temp_data_dir / "removed.json"
        with pytest.raises(TypeError, match=name):
            PersistentDict("test_owner", path, **{name: value})
        assert not path.exists()

    def test_no_pickle_or_pload(self) -> None:
        assert not hasattr(persistentdict, "pickle")
        assert not hasattr(PersistentDict, "pload")

    def test_convert_leaves_bytes_alone(self) -> None:
        assert convert(b"raw") == b"raw"


class TestLoadExisting:
    """Existing files load unchanged; flag "n" ignores them (#610)."""

    def test_sample_files_load_unchanged(self, temp_data_dir: Path) -> None:
        samples = {
            "settings.json": '{"_version": 1, "name": "x", "flag": true, "items": [1, "a"]}',
            "log.json": '{"1": {"level": "info"}, "2": {"level": "debug"}}',
            "commands.json": '{"history": ["a", "b"]}',
        }
        for name, text in samples.items():
            filepath = temp_data_dir / name
            filepath.write_text(text, encoding="utf-8")
            pd = PersistentDict("test_owner", filepath)
            assert len(pd) > 0
            assert filepath.exists()
        log = PersistentDict("test_owner", temp_data_dir / "log.json")
        assert log[1] == {"level": "info"}
        assert list(temp_data_dir.glob("*.corrupt-*")) == []

    def test_flag_n_ignores_existing_file(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        filepath.write_text('{"a": 1}', encoding="utf-8")
        pd = PersistentDict("test_owner", filepath, "n")
        assert len(pd) == 0
        assert filepath.exists()


class TestSkipCleanSync:
    """sync() does no file I/O when nothing changed (#814)."""

    @pytest.fixture
    def io_calls(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Record the moves and fsyncs sync() performs."""
        calls: list[str] = []
        real_move = persistentdict.shutil.move
        real_fsync = os.fsync

        def fake_move(src: Path, dst: Path) -> object:
            calls.append("move")
            return real_move(src, dst)

        def fake_fsync(fd: int) -> None:
            calls.append("fsync")
            real_fsync(fd)

        monkeypatch.setattr(persistentdict.shutil, "move", fake_move)
        monkeypatch.setattr(persistentdict.os, "fsync", fake_fsync)
        return calls

    def test_second_sync_skipped(self, temp_data_dir: Path, io_calls: list[str]) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd["a"] = 1
        pd.sync()
        assert "move" in io_calls
        io_calls.clear()
        pd.sync()
        assert io_calls == []

    def test_loaded_clean_dict_skipped(self, temp_data_dir: Path, io_calls: list[str]) -> None:
        filepath = temp_data_dir / "test.json"
        first = PersistentDict("test_owner", filepath)
        first["a"] = {"b": [1, 2]}
        first[7] = "x"
        first.sync()
        io_calls.clear()
        second = PersistentDict("test_owner", filepath)
        second.sync()
        assert io_calls == []

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda pd: pd.__setitem__("k", 2),
            lambda pd: pd.__delitem__("k"),
            lambda pd: pd.update({"k": 3}),
            lambda pd: pd.pop("k"),
            lambda pd: pd.popitem(),
            lambda pd: pd.clear(),
            lambda pd: pd.setdefault("new", 1),
            lambda pd: pd.__ior__({"k": 4}),
        ],
        ids=["setitem", "delitem", "update", "pop", "popitem", "clear", "setdefault", "ior"],
    )
    def test_mutations_mark_dirty_and_are_written(self, temp_data_dir: Path, mutate: Any) -> None:
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["k"] = 1
        pd.sync()
        assert not pd._dirty
        mutate(pd)
        assert pd._dirty
        pd.sync()
        assert not pd._dirty
        assert dict(PersistentDict("test_owner", filepath)) == dict(pd)

    def test_noop_pop_and_setdefault_stay_clean(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd["k"] = 1
        pd.sync()
        assert pd.pop("missing", None) is None
        assert pd.setdefault("k", 5) == 1
        assert not pd._dirty

    def test_clear_empty_stays_clean(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd.sync()
        pd.clear()
        assert not pd._dirty

    def test_failed_sync_stays_dirty(
        self, temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.json")
        pd["a"] = 1

        def boom(*_args: object, **_kwargs: object) -> None:
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(persistentdict.os, "fsync", boom)
        with pytest.raises(OSError, match="disk full"):
            pd.sync()
        assert pd._dirty
        monkeypatch.undo()
        pd.sync()
        assert PersistentDict("test_owner", temp_data_dir / "test.json")["a"] == 1

    def test_in_place_nested_mutation_saved(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["history"] = []
        pd.sync()
        pd["history"].append("cmd")
        assert not pd._dirty
        pd.sync()
        assert PersistentDict("test_owner", filepath)["history"] == ["cmd"]

    def test_constructor_kwargs_dirty(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath, "c", {"a": 1})
        assert pd._dirty
        pd.sync()
        assert filepath.exists()

    def test_flag_n_writes_first_sync(self, temp_data_dir: Path, io_calls: list[str]) -> None:
        filepath = temp_data_dir / "test.json"
        PersistentDict("test_owner", filepath).sync()
        io_calls.clear()
        PersistentDict("test_owner", filepath, "n").sync()
        assert "move" in io_calls

    def test_deleted_file_rewritten(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict("test_owner", filepath)
        pd["a"] = 1
        pd.sync()
        filepath.unlink()
        pd.sync()
        assert filepath.exists()

    def test_corrupt_file_rewritten(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.json"
        filepath.write_text("{bad", encoding="utf-8")
        pd = PersistentDict("test_owner", filepath)
        pd.sync()
        assert filepath.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode bits")
class TestReapplyMode:
    """The 0600 mode is restored on load and on a skipped sync (#820)."""

    @staticmethod
    def _loose_file(temp_data_dir: Path) -> Path:
        filepath = temp_data_dir / "test.json"
        filepath.write_text('{"a": 1}', encoding="utf-8")
        filepath.chmod(0o644)
        return filepath

    def test_load_tightens_mode(self, tmp_path: Path) -> None:
        filepath = self._loose_file(tmp_path)
        PersistentDict("test_owner", filepath)
        assert filepath.stat().st_mode & 0o777 == 0o600

    def test_skipped_sync_reapplies_mode_without_rewrite(self, tmp_path: Path) -> None:
        filepath = self._loose_file(tmp_path)
        pd = PersistentDict("test_owner", filepath)
        filepath.chmod(0o644)
        before = filepath.stat()
        pd.sync()
        after = filepath.stat()
        assert after.st_mode & 0o777 == 0o600
        assert after.st_ino == before.st_ino
        assert after.st_mtime_ns == before.st_mtime_ns
        assert filepath.read_text(encoding="utf-8") == '{"a": 1}'

    def test_read_only_flag_does_not_chmod(self, tmp_path: Path) -> None:
        filepath = self._loose_file(tmp_path)
        pd = PersistentDict("test_owner", filepath, "r")
        assert pd["a"] == 1
        pd.sync()
        assert filepath.stat().st_mode & 0o777 == 0o644
