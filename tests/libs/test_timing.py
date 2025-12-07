"""Tests for the Timing class and duration decorator.

This module tests the timing functionality including:
- Starting and finishing timers
- Toggling timing enabled/disabled
- Duration decorator for function timing
- Timer unique identifiers
- Elapsed time calculation

Test Classes:
    - `TestTimingBasics`: Tests for basic timing operations.
    - `TestTimingToggle`: Tests for enabling/disabling timing.
    - `TestTimerLifecycle`: Tests for timer start/finish lifecycle.

"""

import time

from bastproxy.libs.timing import Timing, duration


# Helper function for testing the duration decorator
@duration
def timed_function_fast() -> str:
    """Fast function for timing tests.

    Returns:
        A test string.

    Raises:
        None

    """
    return "fast"


@duration
def timed_function_slow() -> str:
    """Slow function for timing tests.

    Returns:
        A test string.

    Raises:
        None

    """
    time.sleep(0.01)  # Sleep 10ms
    return "slow"


class TestTimingBasics:
    """Test basic timing operations."""

    def test_timing_creation(self) -> None:
        """Test that Timing instances can be created."""
        timing = Timing()

        assert timing is not None
        assert timing.enabled is True
        assert isinstance(timing.timing, dict)
        assert len(timing.timing) == 0

    def test_timing_has_api(self) -> None:
        """Test that Timing instances have an API."""
        timing = Timing()

        assert timing.api is not None

    def test_timing_initial_state(self) -> None:
        """Test that new Timing instances have correct initial state."""
        timing = Timing()

        assert timing.enabled is True
        assert timing.timing == {}


class TestTimingToggle:
    """Test enabling/disabling timing functionality."""

    def test_toggle_without_argument(self) -> None:
        """Test toggling timing without providing a boolean."""
        timing = Timing()

        assert timing.enabled is True

        timing._api_toggle()
        assert timing.enabled is False

        timing._api_toggle()
        assert timing.enabled is True

    def test_toggle_with_true(self) -> None:
        """Test explicitly setting timing to enabled."""
        timing = Timing()

        timing.enabled = False
        timing._api_toggle(True)

        assert timing.enabled is True

    def test_toggle_with_false(self) -> None:
        """Test explicitly setting timing to disabled."""
        timing = Timing()

        timing.enabled = True
        timing._api_toggle(False)

        assert timing.enabled is False

    def test_toggle_multiple_times(self) -> None:
        """Test toggling timing multiple times."""
        timing = Timing()

        original_state = timing.enabled

        timing._api_toggle()
        timing._api_toggle()

        # Should return to original state
        assert timing.enabled == original_state


class TestTimerLifecycle:
    """Test timer start/finish lifecycle."""

    def test_start_timer(self) -> None:
        """Test starting a timer."""
        timing = Timing()

        uid = timing._api_start("test_timer")

        assert uid is not None
        assert isinstance(uid, str)
        assert len(uid) == 32  # UUID hex length
        assert uid in timing.timing

    def test_start_timer_with_name(self) -> None:
        """Test starting a timer with a custom name."""
        timing = Timing()

        uid = timing._api_start("custom_timer_name")

        assert uid in timing.timing
        assert timing.timing[uid]["name"] == "custom_timer_name"

    def test_start_timer_with_args(self) -> None:
        """Test starting a timer with arguments."""
        timing = Timing()

        test_args = {"key": "value", "number": 42}
        uid = timing._api_start("timer_with_args", args=test_args)

        assert uid in timing.timing
        assert timing.timing[uid]["args"] == test_args

    def test_finish_timer(self) -> None:
        """Test finishing a timer."""
        timing = Timing()

        uid = timing._api_start("test_timer")
        time.sleep(0.001)  # Sleep 1ms to ensure measurable time
        elapsed = timing._api_finish(uid)

        assert elapsed is not None
        assert isinstance(elapsed, float)
        assert elapsed >= 0  # Elapsed time should be non-negative
        assert uid not in timing.timing  # Timer should be removed

    def test_finish_nonexistent_timer(self) -> None:
        """Test finishing a timer that doesn't exist."""
        timing = Timing()

        result = timing._api_finish("nonexistent_uid")

        assert result is None

    def test_multiple_timers(self) -> None:
        """Test managing multiple timers simultaneously."""
        timing = Timing()

        uid1 = timing._api_start("timer1")
        uid2 = timing._api_start("timer2")
        uid3 = timing._api_start("timer3")

        assert len(timing.timing) == 3
        assert uid1 in timing.timing
        assert uid2 in timing.timing
        assert uid3 in timing.timing

        # Finish timers in different order
        timing._api_finish(uid2)
        assert len(timing.timing) == 2
        assert uid2 not in timing.timing

        timing._api_finish(uid1)
        assert len(timing.timing) == 1

        timing._api_finish(uid3)
        assert len(timing.timing) == 0

    def test_timer_disabled(self) -> None:
        """Test that timers don't start when timing is disabled."""
        timing = Timing()
        timing._api_toggle(False)

        uid = timing._api_start("disabled_timer")

        assert uid is None
        assert len(timing.timing) == 0

    def test_finish_timer_when_disabled(self) -> None:
        """Test that finishing a timer when disabled returns None."""
        timing = Timing()

        uid = timing._api_start("test_timer")
        timing._api_toggle(False)
        result = timing._api_finish(uid)

        assert result is None
        # Timer should still exist because finish was disabled
        assert uid in timing.timing


class TestTimerData:
    """Test timer data storage and retrieval."""

    def test_timer_has_start_time(self) -> None:
        """Test that started timers record start time."""
        timing = Timing()

        uid = timing._api_start("test_timer")

        assert "start" in timing.timing[uid]
        assert isinstance(timing.timing[uid]["start"], float)
        assert timing.timing[uid]["start"] > 0

    def test_timer_has_owner_id(self) -> None:
        """Test that started timers record owner ID."""
        timing = Timing()

        uid = timing._api_start("test_timer")

        assert "owner_id" in timing.timing[uid]
        assert isinstance(timing.timing[uid]["owner_id"], str)

    def test_timer_stores_name(self) -> None:
        """Test that timer name is stored correctly."""
        timing = Timing()

        uid = timing._api_start("my_custom_timer")

        assert timing.timing[uid]["name"] == "my_custom_timer"

    def test_timer_without_args(self) -> None:
        """Test that timers without args have None for args."""
        timing = Timing()

        uid = timing._api_start("timer_no_args")

        assert timing.timing[uid]["args"] is None

    def test_elapsed_time_increases(self) -> None:
        """Test that elapsed time increases with longer execution."""
        timing = Timing()

        # Fast timer
        uid1 = timing._api_start("fast_timer")
        elapsed1 = timing._api_finish(uid1)

        # Slow timer
        uid2 = timing._api_start("slow_timer")
        time.sleep(0.01)  # Sleep 10ms
        elapsed2 = timing._api_finish(uid2)

        assert elapsed1 is not None
        assert elapsed2 is not None
        assert elapsed2 > elapsed1  # Slow timer should take longer


class TestDurationDecorator:
    """Test the duration decorator functionality."""

    def test_duration_decorator_executes_function(self) -> None:
        """Test that decorated functions still execute correctly."""
        result = timed_function_fast()

        assert result == "fast"

    def test_duration_decorator_returns_correct_value(self) -> None:
        """Test that decorated functions return the correct value."""
        result = timed_function_slow()

        assert result == "slow"

    def test_decorated_function_maintains_name(self) -> None:
        """Test that decorated functions maintain their name."""
        assert timed_function_fast.__name__ == "timed_function_fast"
        assert timed_function_slow.__name__ == "timed_function_slow"
