"""EchoRecord: a bounded, one-shot record of sent lines (#545)."""

from bastproxy.plugins.core.triggers.plugin._echo import EchoRecord


class FakeClock:
    """A clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_consume_unknown_text_is_false() -> None:
    record = EchoRecord()
    record.add("look")
    assert record.consume("north") is False
    assert len(record) == 1


def test_consume_is_one_shot() -> None:
    record = EchoRecord()
    record.add("look")
    assert record.consume("look") is True
    assert record.consume("look") is False
    assert len(record) == 0


def test_add_ignores_empty_text() -> None:
    record = EchoRecord()
    record.add("")
    assert len(record) == 0


def test_consume_removes_only_first_equal_entry() -> None:
    record = EchoRecord()
    record.add("look")
    record.add("look")
    assert record.consume("look") is True
    assert len(record) == 1
    assert record.consume("look") is True
    assert record.consume("look") is False


def test_count_bound_drops_oldest() -> None:
    record = EchoRecord(max_entries=2)
    for text in ("a", "b", "c"):
        record.add(text)
    assert len(record) == 2
    assert record.consume("a") is False
    assert record.consume("b") is True
    assert record.consume("c") is True


def test_age_bound_drops_expired() -> None:
    clock = FakeClock()
    record = EchoRecord(max_age=15.0, clock=clock)
    record.add("look")
    clock.now += 14.9
    record.add("north")
    clock.now += 0.2  # look is 15.1 old, north is 0.2 old
    assert record.consume("look") is False
    assert record.consume("north") is True


def test_entry_expires_at_exactly_max_age() -> None:
    clock = FakeClock()
    record = EchoRecord(max_age=15.0, clock=clock)
    record.add("look")
    clock.now += 15.0
    assert record.consume("look") is False
    assert len(record) == 0


def test_entry_just_under_max_age_is_kept() -> None:
    clock = FakeClock()
    record = EchoRecord(max_age=15.0, clock=clock)
    record.add("look")
    clock.now += 14.999
    assert record.consume("look") is True
