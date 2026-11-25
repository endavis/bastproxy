"""The page store (#424)."""

from bastproxy.plugins.core.web.libs._store import PageStore


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_add_and_get() -> None:
    store = PageStore()
    token = store.add("plugins.x", "t", b"body")
    page = store.get(token)
    assert page is not None
    assert page.body == b"body"
    assert store.count() == 1


def test_tokens_are_unguessable_and_unique() -> None:
    store = PageStore()
    tokens = {store.add("o", "t", b"") for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(token) >= 43 for token in tokens)


def test_unknown_token_is_none() -> None:
    assert PageStore().get("nope") is None


def test_cap_drops_the_oldest_first() -> None:
    store = PageStore(cap=3)
    tokens = [store.add("o", str(i), b"") for i in range(5)]
    assert store.count() == 3
    assert [store.get(t) is not None for t in tokens] == [False, False, True, True, True]


def test_expiry_drops_old_pages() -> None:
    clock = Clock()
    store = PageStore(ttl=100, clock=clock)
    old = store.add("o", "old", b"")
    clock.now = 60
    new = store.add("o", "new", b"")
    clock.now = 100
    assert store.get(old) is None
    assert store.get(new) is not None
    clock.now = 161
    assert store.get(new) is None
    assert store.count() == 0
