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
from pathlib import Path

import pytest

from bastproxy.libs.persistentdict import PersistentDict


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

    def test_corrupt_pickle_moved_aside(self, temp_data_dir: Path) -> None:
        filepath = temp_data_dir / "test.pkl"
        filepath.write_bytes(b"\x00garbage")
        pd = PersistentDict("test_owner", filepath, tformat="pickle")
        assert len(pd) == 0
        assert len(list(temp_data_dir.glob("test.pkl.corrupt-*"))) == 1

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

    def test_pickle_rejects_lambda(self, temp_data_dir: Path) -> None:
        pd = PersistentDict("test_owner", temp_data_dir / "test.pkl", tformat="pickle")
        with pytest.raises(TypeError):
            pd.check_serializable("k", lambda: 1)

    @pytest.mark.parametrize(("name", "fmt"), [("t.json", "json"), ("t.pkl", "pickle")])
    def test_sync_fsyncs_before_rename(
        self, temp_data_dir: Path, monkeypatch: pytest.MonkeyPatch, name: str, fmt: str
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
        pd = PersistentDict("test_owner", temp_data_dir / name, tformat=fmt)
        pd["a"] = 1
        pd.sync()
        assert events.index("fsync") < events.index("move")
