"""The page store (#424)."""

from bastproxy.plugins.core.web.libs._store import LoginTokens, PageStore, SessionStore


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


def test_view_only_login_token_is_taken_once() -> None:
    logins = LoginTokens()
    view, full = logins.issue(view_only=True), logins.issue()
    assert logins.take(view) is True
    assert logins.take(view) is None
    assert logins.take(full) is False
    assert logins.take("unknown") is None


def test_consume_keeps_its_meaning_for_view_only_tokens() -> None:
    logins = LoginTokens()
    token = logins.issue(view_only=True)
    assert logins.consume(token)
    assert not logins.consume(token)


def test_view_only_flags_are_dropped_with_expired_and_evicted_tokens() -> None:
    clock = Clock()
    logins = LoginTokens(cap=2, clock=clock)
    first = logins.issue(view_only=True)
    logins.issue(view_only=True)
    logins.issue()
    assert logins.take(first) is None
    clock.now = 1000
    logins.issue()
    assert logins._view == set()


def test_is_view_only_is_true_only_for_live_view_sessions() -> None:
    clock = Clock()
    sessions = SessionStore(cap=2, clock=clock)
    view, full = sessions.create(100, view_only=True), sessions.create(100)
    assert sessions.is_view_only(view) is True
    assert sessions.is_view_only(full) is False
    assert sessions.is_view_only(None) is False
    assert sessions.is_view_only("unknown") is False
    sessions.create(100)  # evicts the oldest, the view session
    assert sessions.is_view_only(view) is False
    assert sessions._view == set()


def test_view_only_session_ends_on_expiry_and_on_clear() -> None:
    clock = Clock()
    sessions = SessionStore(clock=clock)
    expiring = sessions.create(100, view_only=True)
    clock.now = 100
    assert sessions.is_view_only(expiring) is False
    cleared = sessions.create(100, view_only=True)
    sessions.clear()
    assert sessions.is_view_only(cleared) is False
    assert sessions._view == set()


def test_lookup_reads_a_session_once() -> None:
    clock = Clock()
    sessions = SessionStore(clock=clock)
    view, full = sessions.create(100, view_only=True), sessions.create(100)
    assert sessions.lookup(view) is True
    assert sessions.lookup(full) is False
    assert sessions.lookup(None) is None
    assert sessions.lookup("unknown") is None
    clock.now = 100
    assert sessions.lookup(view) is None
    assert sessions.lookup(full) is None
