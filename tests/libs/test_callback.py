"""Tests for the Callback class.

This module tests the callback tracking and management system including:
- Creating callbacks with metadata
- Executing callbacks
- Callback equality and hashing
- Execution count tracking
- Callback enabled/disabled state

Test Classes:
    - `TestCallbackBasics`: Tests for basic callback operations.
    - `TestCallbackExecution`: Tests for callback execution and tracking.
    - `TestCallbackEquality`: Tests for callback equality and hashing.

"""

import time

from bastproxy.libs.callback import Callback

# Helper functions
test_execution_log = []


def helper_test_function() -> str:
    """Helper test function that logs execution.

    Returns:
        A test string.

    Raises:
        None

    """
    test_execution_log.append("executed")
    return "test_result"


def helper_function_with_args(args: dict | None) -> dict | None:
    """Helper function that accepts arguments.

    Args:
        args: Optional arguments dictionary.

    Returns:
        The args that were passed in.

    Raises:
        None

    """
    test_execution_log.append(f"executed_with_args:{args}")
    return args


def another_test_function() -> str:
    """Another test function.

    Returns:
        A different test string.

    Raises:
        None

    """
    return "another_result"


class TestCallbackBasics:
    """Test basic callback operations."""

    def test_callback_creation(self) -> None:
        """Test that callbacks can be created with required parameters."""
        callback = Callback(name="test_callback", owner_id="test_owner", func=helper_test_function)

        assert callback.name == "test_callback"
        assert callback.owner_id == "test_owner"
        assert callback.func == helper_test_function
        assert callback.enabled is True
        assert callback.raised_count == 0

    def test_callback_creation_with_disabled(self) -> None:
        """Test creating a disabled callback."""
        callback = Callback(
            name="disabled_callback",
            owner_id="test_owner",
            func=helper_test_function,
            enabled=False,
        )

        assert callback.enabled is False

    def test_callback_has_creation_time(self) -> None:
        """Test that callbacks track their creation time."""
        callback = Callback(name="test_callback", owner_id="test_owner", func=helper_test_function)

        assert callback.created_time is not None
        assert callback.last_raised_datetime is None

    def test_callback_string_representation(self) -> None:
        """Test the string representation of a callback."""
        callback = Callback(name="test_cb", owner_id="test_owner", func=helper_test_function)

        str_repr = str(callback)

        assert "test_cb" in str_repr
        assert "test_owner" in str_repr


class TestCallbackExecution:
    """Test callback execution and tracking."""

    def test_execute_callback_without_args(self) -> None:
        """Test executing a callback without arguments."""
        test_execution_log.clear()

        callback = Callback(name="exec_callback", owner_id="test_owner", func=helper_test_function)

        result = callback.execute()

        assert result == "test_result"
        assert "executed" in test_execution_log
        assert callback.raised_count == 1

    def test_execute_callback_with_args(self) -> None:
        """Test executing a callback with arguments."""
        test_execution_log.clear()

        callback = Callback(
            name="exec_args_callback",
            owner_id="test_owner",
            func=helper_function_with_args,
        )

        test_args = {"key": "value", "number": 42}
        result = callback.execute(args=test_args)

        assert result == test_args
        assert len(test_execution_log) == 1
        assert callback.raised_count == 1

    def test_execute_increments_raised_count(self) -> None:
        """Test that executing a callback increments the raised count."""
        callback = Callback(name="count_callback", owner_id="test_owner", func=helper_test_function)

        assert callback.raised_count == 0

        callback.execute()
        assert callback.raised_count == 1

        callback.execute()
        assert callback.raised_count == 2

        callback.execute()
        assert callback.raised_count == 3

    def test_execute_updates_last_raised_time(self) -> None:
        """Test that executing a callback updates last raised time."""
        callback = Callback(name="time_callback", owner_id="test_owner", func=helper_test_function)

        assert callback.last_raised_datetime is None

        callback.execute()

        assert callback.last_raised_datetime is not None
        first_time = callback.last_raised_datetime

        # Small delay to ensure timestamp changes (Windows has low clock resolution)
        time.sleep(0.001)

        # Execute again
        callback.execute()

        # Time should have been updated
        assert callback.last_raised_datetime != first_time
        assert callback.last_raised_datetime > first_time


class TestCallbackEquality:
    """Test callback equality and hashing."""

    def test_callback_hash(self) -> None:
        """Test that callbacks have a hash value."""
        callback = Callback(name="hash_callback", owner_id="test_owner", func=helper_test_function)

        hash_value = hash(callback)

        assert isinstance(hash_value, int)

    def test_different_callbacks_different_hashes(self) -> None:
        """Test that different callbacks have different hashes."""
        callback1 = Callback(name="callback1", owner_id="owner1", func=helper_test_function)
        callback2 = Callback(name="callback2", owner_id="owner2", func=another_test_function)

        assert hash(callback1) != hash(callback2)

    def test_callback_identity(self) -> None:
        """Test that a callback has consistent identity."""
        callback = Callback(name="self_callback", owner_id="test_owner", func=helper_test_function)

        # Test that the callback object has a consistent hash
        hash1 = hash(callback)
        hash2 = hash(callback)
        assert hash1 == hash2

    def test_callback_equals_same_callback(self) -> None:
        """Test that two callbacks with same properties are equal."""
        # Note: They won't be equal because creation_time differs
        callback1 = Callback(name="same_callback", owner_id="test_owner", func=helper_test_function)

        # Small delay to ensure timestamps differ (Windows has low clock resolution)
        time.sleep(0.001)

        callback2 = Callback(name="same_callback", owner_id="test_owner", func=helper_test_function)

        # These are NOT equal because they have different creation times
        assert callback1 != callback2
        assert hash(callback1) != hash(callback2)

    def test_callback_equals_wrapped_function(self) -> None:
        """Test that a callback equals its wrapped function."""
        callback = Callback(name="func_callback", owner_id="test_owner", func=helper_test_function)

        # Callback should equal its wrapped function
        assert callback == helper_test_function

    def test_callback_not_equals_different_function(self) -> None:
        """Test that a callback doesn't equal a different function."""
        callback = Callback(name="diff_callback", owner_id="test_owner", func=helper_test_function)

        assert callback != another_test_function

    def test_callback_not_equals_non_callable(self) -> None:
        """Test that a callback doesn't equal non-callable objects."""
        callback = Callback(
            name="noncall_callback", owner_id="test_owner", func=helper_test_function
        )

        assert callback != "string"
        assert callback != 42
        assert callback != None  # noqa: E711
        assert callback != {"key": "value"}
