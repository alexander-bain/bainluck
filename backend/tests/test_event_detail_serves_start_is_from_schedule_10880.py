"""#10880 — the event page says whether its start came from a schedule.

The iPhone event page now offers "Add to Calendar" in a quiet secondary menu,
the same item the Discover and Sports cards carry (PR #11145). The item writes
the start into the reader's own calendar, where nothing of ours can correct it,
so it may only use a start a sports schedule provider published. The cards
learn that from `/api/feed`'s `start_is_from_schedule`. The page reads
`/api/events/{id}`, which served `commence_time` with no provenance, so the page
could not tell ESPN's kick-off from Kalshi's expected expiration (gotcha #14).

The detail route serves `served_commence_time`, not the column. While a row is
held (#9634) that is StatPal's start for a later SESSION, not for this match, so
that served start reads False whatever the column's provenance says.

THESE TESTS DRIVE `get_event` (the #5324 rule), through the shared detail rig,
so a route that stops serving the key, or serves it off a different start than
`commence_time`, fails here and not only in a serializer test. Every True arm
has a control of the same shape that reads False.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.routes import events as events_route
from app.utils.event_completion import (
    STATPAL_LATER_SESSION_KEY,
    statpal_later_session_value,
)
from app.utils.scheduled_start import (
    SCHEDULE_START_SOURCES,
    served_start_is_from_schedule,
)
from tests.test_blend_fold_chart_pin_parity_3911 import (
    CANON_ID,
    _now,
    _RouteSession,
    both_routes as _shared_both_routes,
)
from tests.test_feed_card_serves_start_is_from_schedule_10880 import NOT_A_SCHEDULE


@pytest.fixture
def both_routes(monkeypatch):
    return _shared_both_routes.__wrapped__(monkeypatch)


@pytest.fixture(autouse=True)
def _clean_cache(both_routes):
    events_route._event_detail_cache.clear()
    yield
    events_route._event_detail_cache.clear()


def _session(source, **kw):
    session = _RouteSession(_now(), **kw)
    # A transient row: the assignment lands in `__dict__`, as a loaded column does.
    session.event.commence_time_source = source
    return session


class TestTheRoute:
    @pytest.mark.parametrize("source", sorted(SCHEDULE_START_SOURCES))
    def test_a_schedule_providers_start_serves_true(self, both_routes, source):
        detail = both_routes.detail(_session(source))
        assert detail["status"] == "scheduled"
        assert detail["start_is_from_schedule"] is True

    @pytest.mark.parametrize("source", NOT_A_SCHEDULE)
    def test_control_a_markets_start_serves_false(self, both_routes, source):
        detail = both_routes.detail(_session(source))
        assert detail["status"] == "scheduled"
        assert detail["start_is_from_schedule"] is False

    def test_the_key_is_always_a_bool(self, both_routes):
        # Never omitted and never null: iOS reads absent as false, but a route
        # that dropped the key would hide the item on every page in silence.
        detail = both_routes.detail(_session("espn"))
        assert type(detail["start_is_from_schedule"]) is bool

    def test_a_held_rows_session_start_serves_false(self, both_routes):
        session = _session("espn")
        stored = session.event.commence_time
        later = (_now() + timedelta(hours=6)).replace(microsecond=0)
        session.event.win_probability_sources = {
            **(session.event.win_probability_sources or {}),
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(later),
        }
        detail = both_routes.detail(session)
        # The rig really is serving the substituted start; otherwise this
        # would pass for the wrong reason.
        assert detail["commence_time"] != stored.isoformat()
        assert detail["start_is_from_schedule"] is False

    def test_control_the_same_row_unheld_serves_true(self, both_routes):
        session = _session("espn")
        detail = both_routes.detail(session)
        assert detail["commence_time"] == session.event.commence_time.isoformat()
        assert detail["start_is_from_schedule"] is True

    def test_an_unloaded_column_serves_false_without_a_lazy_load(self, both_routes):
        # An expired async row has no column in `__dict__`; `getattr` would
        # lazy-load and raise MissingGreenlet. Absent serves "not from a schedule".
        session = _session("espn")
        del session.event.__dict__["commence_time_source"]
        detail = both_routes.detail(session)
        assert detail["start_is_from_schedule"] is False

    def test_the_cached_payload_carries_the_key(self, both_routes):
        both_routes.detail(_session("espn"))
        _cached_at, _status, payload = both_routes.cache[CANON_ID]
        assert payload["start_is_from_schedule"] is True


class TestServedStartIsFromSchedule:
    def test_the_stored_start_reads_its_provenance(self):
        start = _now()
        for source in SCHEDULE_START_SOURCES:
            assert served_start_is_from_schedule(source, start, start) is True
        for source in NOT_A_SCHEDULE:
            assert served_start_is_from_schedule(source, start, start) is False

    def test_a_substituted_start_is_never_from_a_schedule(self):
        start = _now()
        assert served_start_is_from_schedule("espn", start, start + timedelta(hours=6)) is False

    def test_no_stored_start_is_false(self):
        assert served_start_is_from_schedule("espn", None, None) is False
