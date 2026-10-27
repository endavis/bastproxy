# Project: bastproxy
# Filename: tests/plugins/test_log_tz.py
#
# File Description: Tests for the logging timezone formatters
#
# By: Bast
"""Unit tests for `bastproxy.plugins.core.log.libs.tz`.

`formatTime_RFC3339_UTC` and `formatTime_RFC3339` replace
`logging.Formatter.formatTime`, so `logging` calls them positionally with
`(self, record, datefmt=None)`. Issue #8 renamed the unused `datefmt`
parameter to `_datefmt`; these tests pin down that the functions still work
correctly when installed as `Formatter.formatTime` and invoked through the
normal `Formatter.format` call path (which may pass a `datefmt` positionally).

"""

import logging

import pytest

from bastproxy.plugins.core.log.libs.tz import (
    formatTime_RFC3339,
    formatTime_RFC3339_UTC,
)


class TestFormatTimeRFC3339UTC:
    """Tests for `formatTime_RFC3339_UTC` installed as `Formatter.formatTime`."""

    def test_format_produces_rfc3339_utc_timestamp(self) -> None:
        """A `Formatter` using the UTC formatter produces an RFC3339 UTC timestamp."""
        formatter = logging.Formatter()
        formatter.formatTime = formatTime_RFC3339_UTC.__get__(formatter, logging.Formatter)  # type: ignore[method-assign]

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )

        timestamp = formatter.formatTime(record)

        assert timestamp.endswith("+00:00")

    def test_format_accepts_positional_datefmt(self) -> None:
        """Calling positionally with a `datefmt` (as `logging` does) still works."""
        formatter = logging.Formatter()
        formatter.formatTime = formatTime_RFC3339_UTC.__get__(formatter, logging.Formatter)  # type: ignore[method-assign]

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )

        # logging.Formatter.format() calls self.formatTime(record, self.datefmt)
        # positionally; simulate that call shape directly.
        timestamp = formatter.formatTime(record, "%Y-%m-%d")

        assert timestamp.endswith("+00:00")


class TestFormatTimeRFC3339:
    """Tests for `formatTime_RFC3339` installed as `Formatter.formatTime`."""

    def test_format_via_formatter_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`Formatter.format` produces an RFC3339 timestamp via the %(asctime)s field."""
        # monkeypatch restores whatever formatTime was installed before (bastproxy
        # itself replaces it at import), rather than deleting the class attribute.
        monkeypatch.setattr(logging.Formatter, "formatTime", formatTime_RFC3339)
        formatter = logging.Formatter("%(asctime)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )

        formatted = formatter.format(record)

        timestamp = formatted.split(" ", 1)[0]
        # RFC3339/ISO-8601 timestamps contain a 'T' separating date and time.
        assert "T" in timestamp

    def test_format_accepts_positional_datefmt(self) -> None:
        """Calling positionally with a `datefmt` (as `logging` does) still works."""
        formatter = logging.Formatter()
        formatter.formatTime = formatTime_RFC3339.__get__(formatter, logging.Formatter)  # type: ignore[method-assign]

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )

        timestamp = formatter.formatTime(record, "%Y-%m-%d")

        assert "T" in timestamp
