"""Tests for BaseRecord.__call__ exception safety."""

import pytest

from bastproxy.libs.records import RMANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord


class Boom(BaseRecord):
    """Record whose _exec_ raises on demand."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = True
        self.runs = 0

    def _exec_(self) -> None:
        self.runs += 1
        if self.fail:
            raise RuntimeError("x")


def test_exception_propagates_and_state_restored() -> None:
    before = RMANAGER.get_latest_record()
    boom = Boom()
    with pytest.raises(RuntimeError, match="x"):
        boom()
    assert RMANAGER.get_latest_record() is before
    assert boom.executing is False


def test_record_can_run_again_after_exception() -> None:
    boom = Boom()
    with pytest.raises(RuntimeError):
        boom()
    boom.fail = False
    boom()
    assert boom.runs == 2
    assert boom.executing is False


def test_timing_finished_after_exception() -> None:
    boom = Boom()
    with pytest.raises(RuntimeError):
        boom()
    assert boom.execute_time_taken is not None


def test_success_path_still_works() -> None:
    before = RMANAGER.get_latest_record()
    boom = Boom()
    boom.fail = False
    boom()
    assert RMANAGER.get_latest_record() is before
    assert boom.executing is False
