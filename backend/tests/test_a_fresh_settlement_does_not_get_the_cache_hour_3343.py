"""A settlement made one minute ago does not buy an hour of not looking (#3343).

═══ WHAT A READER SAW ═══

`/events/15304419`, US Open R32, live/064's LOOK on production: the **settled**
hero — `Final`, an `AG · WON` chip, `7-6, 3-5`, "were 42% pregame" — over a match
that was level at one set all and still being played. Seven reads in eight served
that body; the eighth served the live score. The row underneath said `live` and
its `completed_at` was NULL the whole time.

═══ WHY THE CACHE COULD NOT SELF-CORRECT ═══

`_cached_detail_payload` picks its TTL from the cached status, and
`_EVENT_DETAIL_SETTLED_TTL` grants a settled entry a full hour. That hour rests
on a premise its own comment states — *"a settled row's content never changes
again"* — together with the claim that this "has exactly one exception and this
ship is it: RETIREMENT".

There is a second exception, and the repo already knew it: **resurrection**, a
row going `completed` → `live` again. `venue_live_write_is_a_resurrection` in
`app/utils/event_completion.py` was written by live/042 for that transition.

So one premature `completed` — a provider calling a match early — takes a
one-hour lease that nothing can end. The correction lands in the row; the cache
never re-reads to see it. The 7-in-8 ratio is two web dynos: one holding the
poisoned hour-long entry, one refreshing every 30s.

═══ WHAT THESE TESTS PIN ═══

Both directions, because a fix that simply shortened every settled TTL would
pass the defect half and quietly cost the latency decision `_EVENT_DETAIL_
SETTLED_TTL` was measured for. So each "it re-reads" case is paired with a
control that must still be served from cache:

* a settlement minutes old re-reads at the live cadence …
* … while a settlement hours old keeps its hour, and
* … while `closed` with no `completed_at` — 54,496 of 55,629 rows on production
  2026-09-08, the archival population — keeps its hour too. That measurement is
  why the fix is a freshness window and not a "must carry `completed_at`" test.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import events as events_route

EVENT_ID = 4243343
#: A fixed epoch so nothing here reads the clock (gotcha #44).
NOW = 1_788_900_000.0


def _iso(offset_seconds: float) -> str:
    """`completed_at` as `_format_event` stores it: an ISO string, tz-aware."""
    return datetime.fromtimestamp(NOW + offset_seconds, tz=timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _clean_cache():
    events_route._event_detail_cache.clear()
    yield
    events_route._event_detail_cache.clear()


def _plant(status: str, *, age: float, completed_at) -> dict:
    """One entry, `age` seconds old, exactly as `get_event` would have written it."""
    payload = {"id": EVENT_ID, "status": status, "completed_at": completed_at}
    events_route._event_detail_cache[EVENT_ID] = (NOW - age, status, payload)
    return payload


def _served(age_at_read: float = 0.0):
    return events_route._cached_detail_payload(EVENT_ID, NOW + age_at_read)


class TestTheConstantsStillMeanWhatTheLadderAssumes:
    """A ladder read off constants is only as good as their ordering."""

    def test_the_window_is_a_real_window(self):
        assert events_route._EVENT_DETAIL_FRESHLY_SETTLED_WINDOW > 0, (
            "a falsy window makes every settlement 'durable' on arrival and "
            "restores #3343 in full"
        )

    def test_a_denied_hour_is_actually_shorter_than_the_hour(self):
        assert (
            events_route._EVENT_DETAIL_LIVE_TTL < events_route._EVENT_DETAIL_SETTLED_TTL
        ), "the penalty for a fresh settlement must cost the entry something"

    def test_the_window_outlasts_the_cadence_that_would_correct_it(self):
        assert (
            events_route._EVENT_DETAIL_FRESHLY_SETTLED_WINDOW
            > events_route._EVENT_DETAIL_LIVE_TTL
        ), "a window inside one live TTL cannot span a correction"


class TestTheDefect:
    """The half that was broken: a fresh settlement stops buying the hour."""

    @pytest.mark.parametrize("status", sorted(events_route.SETTLED_STATUSES))
    def test_a_minutes_old_settlement_re_reads(self, status):
        """#3343 itself. Five minutes in, the old ladder still served the body."""
        _plant(status, age=300.0, completed_at=_iso(-300.0))
        assert _served() is None, (
            "a settlement made five minutes ago is still being served from "
            "cache — a premature `completed` keeps its winner on screen"
        )

    def test_the_entry_that_re_reads_would_have_survived_the_full_hour(self):
        """Names the exact quantity the fix removes: 55 more minutes of it."""
        _plant("completed", age=300.0, completed_at=_iso(-300.0))
        assert _served() is None
        assert 300.0 < events_route._EVENT_DETAIL_SETTLED_TTL, (
            "this entry is inside the settled hour, so the old ladder served "
            "it; that is the window #3343 lived in"
        )

    def test_a_resurrection_becomes_visible_within_the_live_cadence(self):
        """The reader-facing promise, stated as a duration rather than a flag."""
        _plant(
            "completed",
            age=events_route._EVENT_DETAIL_LIVE_TTL + 1,
            completed_at=_iso(-(events_route._EVENT_DETAIL_LIVE_TTL + 1)),
        )
        assert _served() is None


class TestTheControls:
    """The half that must NOT change. Each one is a latency decision."""

    def test_a_settlement_hours_old_keeps_its_hour(self):
        _plant("completed", age=300.0, completed_at=_iso(-3 * 3600.0))
        assert _served() is not None, (
            "a match that finished three hours ago is not coming back; "
            "re-reading it is pure cost"
        )

    def test_closed_with_no_completed_at_keeps_its_hour(self):
        """54,496 of 55,629 `closed` rows. The reason this is a window."""
        _plant("closed", age=300.0, completed_at=None)
        assert _served() is not None, (
            "the archival population lost the settled shortcut — this is the "
            "98% the measurement rejected"
        )

    def test_a_freshly_settled_entry_is_not_a_per_request_recompute(self):
        """Denied the hour is not denied the cache."""
        _plant("completed", age=1.0, completed_at=_iso(-1.0))
        assert _served() is not None, (
            "a one-second-old entry re-queried; the fix has turned the fresh "
            "window into no caching at all"
        )

    def test_the_live_ladder_is_untouched(self):
        _plant("live", age=1.0, completed_at=None)
        assert _served() is not None
        _plant("live", age=events_route._EVENT_DETAIL_LIVE_TTL + 1, completed_at=None)
        assert _served() is None

    def test_the_default_ladder_is_untouched(self):
        _plant("scheduled", age=1.0, completed_at=None)
        assert _served() is not None
        _plant(
            "scheduled",
            age=events_route._EVENT_DETAIL_DEFAULT_TTL + 1,
            completed_at=None,
        )
        assert _served() is None

    def test_a_miss_is_still_a_miss(self):
        assert _served() is None


class TestTheWindowHelper:
    """`_settled_within_reversal_window`'s truth table, including the two
    abstentions — each falls the way it does for a reason, not by default."""

    @pytest.mark.parametrize(
        "offset,expected",
        [
            (-1.0, True),
            (-599.0, True),
            (-601.0, False),
            (-3 * 3600.0, False),
        ],
    )
    def test_recency_decides(self, offset, expected):
        payload = {"completed_at": _iso(offset)}
        assert events_route._settled_within_reversal_window(payload, NOW) is expected

    def test_the_boundary_is_closed_on_the_durable_side(self):
        exact = -float(events_route._EVENT_DETAIL_FRESHLY_SETTLED_WINDOW)
        payload = {"completed_at": _iso(exact)}
        assert events_route._settled_within_reversal_window(payload, NOW) is False

    @pytest.mark.parametrize("missing", [None, "", "not-a-timestamp", 17, {}])
    def test_no_usable_stamp_abstains_and_keeps_the_hour(self, missing):
        """Absence must not read as 'might be fresh' — that is the 98%."""
        assert (
            events_route._settled_within_reversal_window({"completed_at": missing}, NOW)
            is False
        )

    def test_an_absent_key_abstains(self):
        assert events_route._settled_within_reversal_window({}, NOW) is False

    def test_a_future_stamp_denies_the_hour(self):
        """A stamp ahead of the clock is corrupt; re-read it rather than trust
        it for an hour."""
        assert (
            events_route._settled_within_reversal_window(
                {"completed_at": _iso(+3600.0)}, NOW
            )
            is True
        )

    def test_a_datetime_is_accepted_as_well_as_a_string(self):
        """A serializer that stops isoformatting degrades to re-checking, not
        to a silent hour."""
        aware = datetime.fromtimestamp(NOW, tz=timezone.utc) - timedelta(seconds=1)
        assert (
            events_route._settled_within_reversal_window({"completed_at": aware}, NOW)
            is True
        )

    def test_a_naive_datetime_is_read_as_utc(self):
        naive = (
            datetime.fromtimestamp(NOW, tz=timezone.utc) - timedelta(seconds=1)
        ).replace(tzinfo=None)
        assert (
            events_route._settled_within_reversal_window({"completed_at": naive}, NOW)
            is True
        )
