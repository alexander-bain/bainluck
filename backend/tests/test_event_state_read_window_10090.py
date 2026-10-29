"""#10090 — a detail payload says WHEN it read the event row, on the database's clock.

Two detail payloads for one game can carry the same `blend_fold_revision`: a
kick-off or a touchdown moves no price. Authority's probe on the web page
(`artifacts-authority-10090-g1r-ba11/sameRevPollReplay10090.test.ts`) showed
the consequence: a fresh read that began before kick-off (`scheduled`) landed
after a `live 0-0` poll at the same revision and the page went back to
`scheduled`; a `live 7-0` became `0-0` the same way. Neither arrival order nor
the revision can say which payload's state is current, and a higher score or a
later status is not proof either (score corrections and repairs are real).

The producer half: `get_event` publishes `state_read_not_before` /
`state_read_not_after`, the database's `transaction_timestamp()` and
`clock_timestamp()` read once after every read of the served row. The row's
state was read inside that window. Graded here:

* the window is valid only as a pair of timezone-aware datetimes in order, and
  fails closed to "no keys" otherwise — never a guessed clock;
* it is taken AFTER duplicate resolution, so it brackets the row actually served;
* a cached payload keeps the window of the build that made it (a cached poll is
  honestly older), while a new build carries a new one;
* a failure to read it serves the page exactly as before;
* the payload says whether its window was read inside the request that
  carried it (`state_read_fresh`): a build's own response says ``true``, the
  cache entry and every poll served from it say ``false``, and no window means
  no flag (A6 clock bridge, C1).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.routes import events as events_route
from app.routes.events import (
    STATE_READ_FRESH_KEY,
    STATE_READ_NOT_AFTER_KEY,
    STATE_READ_NOT_BEFORE_KEY,
    build_event_detail_uncoalesced,
    event_state_read_window,
    get_event,
)
from tests.test_blend_fold_chart_pin_parity_3911 import (
    CANON_ID,
    _now,
    _Result,
    _RouteSession,
    both_routes,  # noqa: F401 — the shared detail rig
)

T0 = datetime(2026, 10, 19, 1, 15, 0, 123456, tzinfo=timezone.utc)
WINDOW_STATEMENT = "transaction_timestamp()"


def _window(start: datetime, width_ms: int = 3):
    return (start, start + timedelta(milliseconds=width_ms))


class _WindowSession:
    """Answers only the window statement, as `event_state_read_window` asks it."""

    def __init__(self, answer):
        self.answer = answer
        self.statements = []

    async def execute(self, statement, *_a, **_kw):
        self.statements.append(" ".join(str(statement).split()))
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Result(self.answer)


def _read(answer):
    return asyncio.run(event_state_read_window(_WindowSession(answer)))


class TestTheWindow:
    def test_an_ordered_aware_pair_is_served_as_utc_iso(self):
        lo, hi = _window(T0)
        assert _read([(lo, hi)]) == {
            STATE_READ_NOT_BEFORE_KEY: "2026-10-19T01:15:00.123456+00:00",
            STATE_READ_NOT_AFTER_KEY: "2026-10-19T01:15:00.126456+00:00",
        }

    def test_a_non_utc_offset_is_converted_not_relabelled(self):
        pacific = timezone(timedelta(hours=-7))
        lo = T0.astimezone(pacific)
        window = _read([(lo, lo)])
        assert window[STATE_READ_NOT_BEFORE_KEY] == T0.isoformat()
        assert window[STATE_READ_NOT_AFTER_KEY] == T0.isoformat()

    def test_it_asks_the_database_clock_and_nothing_else(self):
        session = _WindowSession([_window(T0)])
        asyncio.run(event_state_read_window(session))
        assert session.statements == ["SELECT transaction_timestamp(), clock_timestamp()"]

    @pytest.mark.parametrize(
        "answer",
        [
            [],  # no row
            [(T0,)],  # half a pair
            [(T0, T0, T0)],  # wrong width
            [(T0.replace(tzinfo=None), T0.replace(tzinfo=None))],  # naive
            [(T0, T0.replace(tzinfo=None))],  # half naive
            [(T0 + timedelta(milliseconds=1), T0)],  # reversed
            [(T0.isoformat(), T0.isoformat())],  # strings are not clocks
            [(None, T0)],
            RuntimeError("connection went away"),
        ],
        ids=["no-row", "half", "wide", "naive", "half-naive", "reversed", "strings", "null", "raises"],
    )
    def test_anything_else_is_no_claim(self, answer):
        assert _read(answer) == {}


class _ClockedSession(_RouteSession):
    """The shared route rig, plus the window statement and a statement log."""

    def __init__(self, now, window, **kw):
        super().__init__(now, **kw)
        self.window = window
        self.statements = []

    async def execute(self, statement, *a, **kw):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if WINDOW_STATEMENT in sql:
            if isinstance(self.window, Exception):
                raise self.window
            return _Result([] if self.window is None else [self.window])
        return await super().execute(statement, *a, **kw)


def _keys(window):
    lo, hi = window
    return {
        STATE_READ_NOT_BEFORE_KEY: lo.isoformat(),
        STATE_READ_NOT_AFTER_KEY: hi.isoformat(),
    }


def _served_window(payload):
    return {k: payload[k] for k in (STATE_READ_NOT_BEFORE_KEY, STATE_READ_NOT_AFTER_KEY) if k in payload}


class TestTheDetailRoute:
    def test_the_build_publishes_its_window_and_caches_it(self, both_routes):
        both_routes.cache.clear()
        first = _window(T0)
        session = _ClockedSession(_now(), first)
        detail = both_routes.detail(session)
        assert _served_window(detail) == _keys(first)
        _cached_at, _status, payload = both_routes.cache[CANON_ID]
        assert _served_window(payload) == _keys(first)
        assert sum(WINDOW_STATEMENT in s for s in session.statements) == 1

    def test_a_cached_poll_keeps_the_older_window_and_a_new_build_moves_it(self, both_routes):
        """The cached payload describes the build that made it — so a poll served
        from cache is honestly OLDER than a fresh read, which is exactly the
        ordering a reader needs and the one arrival order cannot give."""
        both_routes.cache.clear()
        first, later = _window(T0), _window(T0 + timedelta(seconds=40))
        both_routes.detail(_ClockedSession(_now(), first))
        cached_session = _ClockedSession(_now(), later)
        cached = both_routes.detail(cached_session)
        assert _served_window(cached) == _keys(first)
        assert not any(WINDOW_STATEMENT in s for s in cached_session.statements)

        fresh = asyncio.run(get_event(CANON_ID, db=_ClockedSession(_now(), later), fresh=True))
        assert _served_window(fresh) == _keys(later)
        events_route._DETAIL_FRESH_BUILDS.clear()

    def test_the_window_is_read_after_the_served_row_is_resolved(self, both_routes, monkeypatch):
        """A duplicate resolves to its canonical row with a SECOND read; a window
        taken before it would not bracket the row actually served."""
        both_routes.cache.clear()
        real_resolve = events_route.resolve_served_event

        async def _marked_resolve(db, event, *, requested_id):
            db.statements.append("-- resolved")
            return await real_resolve(db, event, requested_id=requested_id)

        monkeypatch.setattr(events_route, "resolve_served_event", _marked_resolve)
        session = _ClockedSession(_now(), _window(T0))
        both_routes.detail(session)
        resolved = session.statements.index("-- resolved")
        window = next(i for i, s in enumerate(session.statements) if WINDOW_STATEMENT in s)
        assert window > resolved

    @pytest.mark.parametrize("failure", [None, RuntimeError("db went away")], ids=["no-row", "raises"])
    def test_no_window_serves_the_page_exactly_as_before(self, both_routes, failure):
        both_routes.cache.clear()
        without = both_routes.detail(_ClockedSession(_now(), failure))
        both_routes.cache.clear()
        with_window = both_routes.detail(_ClockedSession(_now(), _window(T0)))
        assert STATE_READ_NOT_BEFORE_KEY not in without
        assert STATE_READ_NOT_AFTER_KEY not in without
        # The fresh flag qualifies the window and leaves with it (C1).
        claim = {*_keys(_window(T0)), STATE_READ_FRESH_KEY}
        stripped = {k: v for k, v in with_window.items() if k not in claim}
        assert stripped.keys() == without.keys()
        assert stripped["status"] == without["status"]
        assert stripped["hero_probability"] == without["hero_probability"]


class TestTheFreshFlag:
    """C1 for the A6 clock bridge: a collector pairs its own request bracket
    with the window, which is sound only when the window was read inside that
    request. A cached payload carries an earlier build's window, so it must
    say so — or a 40-second-old read becomes a fresh anchor."""

    def test_the_build_says_fresh_and_its_cache_entry_says_cached(self, both_routes):
        both_routes.cache.clear()
        first = _window(T0)
        detail = both_routes.detail(_ClockedSession(_now(), first))
        _cached_at, _status, entry = both_routes.cache[CANON_ID]
        assert detail[STATE_READ_FRESH_KEY] is True
        assert entry[STATE_READ_FRESH_KEY] is False
        # The flag is the ONLY difference: same window, same page.
        assert {k: v for k, v in detail.items() if k != STATE_READ_FRESH_KEY} == {
            k: v for k, v in entry.items() if k != STATE_READ_FRESH_KEY
        }
        assert _served_window(entry) == _keys(first)

    def test_a_poll_served_from_cache_says_cached(self, both_routes):
        both_routes.cache.clear()
        first, later = _window(T0), _window(T0 + timedelta(seconds=40))
        built = both_routes.detail(_ClockedSession(_now(), first))
        session = _ClockedSession(_now(), later)
        polled = both_routes.detail(session)
        assert not any(WINDOW_STATEMENT in s for s in session.statements)
        assert _served_window(polled) == _keys(first)
        assert polled[STATE_READ_FRESH_KEY] is False
        # Serving the build's own copy as fresh did not flip the shared entry,
        # and the poll did not flip the build's copy after the fact.
        assert built[STATE_READ_FRESH_KEY] is True
        assert both_routes.cache[CANON_ID][2][STATE_READ_FRESH_KEY] is False

    def test_a_fresh_read_says_fresh_with_its_own_window(self, both_routes):
        both_routes.cache.clear()
        first, later = _window(T0), _window(T0 + timedelta(seconds=40))
        both_routes.detail(_ClockedSession(_now(), first))
        try:
            fresh = asyncio.run(
                get_event(CANON_ID, db=_ClockedSession(_now(), later), fresh=True)
            )
        finally:
            events_route._DETAIL_FRESH_BUILDS.clear()
        assert _served_window(fresh) == _keys(later)
        assert fresh[STATE_READ_FRESH_KEY] is True
        assert both_routes.cache[CANON_ID][2][STATE_READ_FRESH_KEY] is False

    def test_a_fresh_reader_answered_by_a_newer_entry_says_fresh(self, both_routes):
        """The barrier may answer a fresh read from an ordinary entry built
        after the reader asked: that build read the row inside the reader's
        request, so the reader's copy is fresh. The entry stays cached."""
        both_routes.cache.clear()
        both_routes.detail(_ClockedSession(_now(), _window(T0)))
        built_at = both_routes.cache[CANON_ID][0]

        async def _no_build():
            raise AssertionError("a newer entry answers; nothing is built")

        answered = asyncio.run(
            events_route._coalesced_fresh_detail(CANON_ID, built_at - 1.0, _no_build)
        )
        assert answered[STATE_READ_FRESH_KEY] is True
        assert both_routes.cache[CANON_ID][2][STATE_READ_FRESH_KEY] is False

    def test_an_older_entry_never_answers_a_fresh_read_as_fresh(self, both_routes):
        both_routes.cache.clear()
        both_routes.detail(_ClockedSession(_now(), _window(T0)))
        built_at = both_routes.cache[CANON_ID][0]
        later = _window(T0 + timedelta(seconds=40))

        async def _build():
            return await get_event(CANON_ID, db=_ClockedSession(_now(), later), fresh=True)

        try:
            answered = asyncio.run(
                events_route._coalesced_fresh_detail(CANON_ID, built_at, _build)
            )
        finally:
            events_route._DETAIL_FRESH_BUILDS.clear()
        # A tie is "before": the entry did not answer, a new build did.
        assert _served_window(answered) == _keys(later)
        assert answered[STATE_READ_FRESH_KEY] is True

    def test_the_uncoalesced_build_says_fresh_and_publishes_nothing(self, both_routes):
        both_routes.cache.clear()
        detail = asyncio.run(
            build_event_detail_uncoalesced(_ClockedSession(_now(), _window(T0)), CANON_ID)
        )
        assert detail[STATE_READ_FRESH_KEY] is True
        assert CANON_ID not in both_routes.cache

    @pytest.mark.parametrize("failure", [None, RuntimeError("db went away")], ids=["no-row", "raises"])
    def test_no_window_means_no_flag_built_or_cached(self, both_routes, failure):
        both_routes.cache.clear()
        built = both_routes.detail(_ClockedSession(_now(), failure))
        polled = both_routes.detail(_ClockedSession(_now(), _window(T0)))
        assert STATE_READ_FRESH_KEY not in built
        assert STATE_READ_FRESH_KEY not in polled
        assert STATE_READ_FRESH_KEY not in both_routes.cache[CANON_ID][2]
