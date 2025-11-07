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
        pd = PersistentDict(filepath)
        assert len(pd) == 0
        assert pd.filename == filepath

    def test_basic_operations(self, temp_data_dir: Path) -> None:
        """Test basic dictionary operations.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict(filepath)

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
        pd1 = PersistentDict(filepath)
        pd1["test_key"] = "test_value"
        pd1["number"] = 42
        pd1.sync()

        # Load in new instance
        pd2 = PersistentDict(filepath)
        assert pd2["test_key"] == "test_value"
        assert pd2["number"] == 42

    def test_context_manager(self, temp_data_dir: Path) -> None:
        """Test context manager automatically syncs.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"

        # Use as context manager
        with PersistentDict(filepath) as pd:
            pd["auto_sync"] = True

        # Verify data was saved
        pd2 = PersistentDict(filepath)
        assert pd2["auto_sync"] is True

    def test_delete_operation(self, temp_data_dir: Path) -> None:
        """Test deleting keys from dictionary.

        Args:
            temp_data_dir: Temporary directory for test data.

        """
        filepath = temp_data_dir / "test.json"
        pd = PersistentDict(filepath)

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
        pd = PersistentDict(filepath)

        pd.update({"key1": "val1", "key2": "val2"})
        assert pd["key1"] == "val1"
        assert pd["key2"] == "val2"
