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

from pathlib import Path

from libs.persistentdict import PersistentDict


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
