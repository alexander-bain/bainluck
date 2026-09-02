"""CAL-P989 (#2660, #1818): `resolution_date` is close_time, not the legal backstop.

THE DEFECT THESE GUARD. The Kalshi poller wrote
``resolution_date = max(expiration_time)``. ``expiration_time`` is Kalshi's LATEST
POSSIBLE expiry — for a ``can_close_early`` market (99.7% of them) it equals
``latest_expiration_time``. Measured live on 2026-09-02 over a 179-event sample of
the 10,187 Kalshi rows that are ``status='open'`` with a future ``resolution_date``:
of the 49 already finalized at the venue, **0** had a stored date in the past. So
``status != 'resolved' AND past resolution_date`` selected none of them, Discover
kept selling a golf round that had settled five days earlier, and #1818's repair was
structurally blind to its own population.

EVERY FIXTURE BELOW IS A REAL VENUE PAYLOAD, not an invented shape:

* ``KXWTASETWINNER-26SEP01POTSEM-2`` — finalized, close 2026-09-01T22:54:02Z,
  expiration 2026-09-15T16:40:00Z. The 14-day backstop is the whole bug.
* ``KXSB-27`` — active, close == expiration == 2029-02-13T23:30:00Z. The no-op
  case, and the reason this fix does NOT close #2644.

CLOCK DISCIPLINE (gotcha #44). ``derive_resolution_window`` takes no clock and
these tests assert on returned datetimes, never on "is it in the past". The one
place a now-relative claim is made (``test_settled_prop_becomes_visible_to_a_past_
predicate``) pins ``now`` to an explicit literal rather than reading the wall clock,
so no test here can flip with the date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pytest

from app.utils.kalshi_resolution_window import (
    ResolutionWindow,
    derive_resolution_window,
)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class FakeMarket:
    """Only the two fields the derivation reads. Mirrors ``KalshiMarket``."""

    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None


# --- Real venue payloads, fetched 2026-09-02 -------------------------------

#: WTA set-winner props: FINALIZED at the venue, 14-day backstop. The #2660 shape.
SETTLED_PROP = [
    FakeMarket(_ts("2026-09-01T22:54:02Z"), _ts("2026-09-15T16:40:00Z")),
    FakeMarket(_ts("2026-09-01T22:54:02Z"), _ts("2026-09-15T16:40:00Z")),
]

#: 2027 Pro Football Champion: ACTIVE, close == expiration. The #2644 shape.
ACTIVE_FUTURE = [
    FakeMarket(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z")),
    FakeMarket(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z")),
]


class TestSettledPropShape:
    """The population #2660 is about."""

    def test_resolution_date_is_close_time_not_the_backstop(self):
        w = derive_resolution_window(SETTLED_PROP)
        assert w.resolution_date == _ts("2026-09-01T22:54:02Z"), (
            "resolution_date must be when trading actually stopped. Getting "
            "2026-09-15 here means the legal backstop is back, and with it the "
            "14-day window in which a settled market renders as live."
        )

    def test_the_backstop_is_preserved_not_discarded(self):
        w = derive_resolution_window(SETTLED_PROP)
        assert w.expiration_time == _ts("2026-09-15T16:40:00Z"), (
            "no data loss: expiration_time must still hold exactly what "
            "resolution_date used to hold (CAL-P061's 421/421 reproduction "
            "has to stay checkable)"
        )

    def test_settled_prop_becomes_visible_to_a_past_predicate(self):
        """The whole point, stated as the predicate #1818 actually runs.

        ``now`` is a literal, not the wall clock: this test asserts a property of
        the two DATES relative to a fixed instant, which is what the repair's
        SQL evaluates. It cannot flip with the calendar.
        """
        now = _ts("2026-09-02T19:30:00Z")  # when the population was measured
        w = derive_resolution_window(SETTLED_PROP)

        assert w.resolution_date < now, (
            "a market Kalshi finalized on Sep 1 must read as past by Sep 2, or "
            "`status != 'resolved' AND past resolution_date` cannot select it"
        )
        assert w.expiration_time > now, (
            "control: the OLD value is still in the future at the same instant. "
            "If this ever fails the fixture has drifted and the test above "
            "would pass for the wrong reason."
        )


class TestActiveFutureShape:
    """The no-op case. This fix must not pretend to close #2644."""

    def test_active_future_is_unchanged(self):
        w = derive_resolution_window(ACTIVE_FUTURE)
        assert w.resolution_date == _ts("2029-02-13T23:30:00Z")
        assert w.expiration_time == _ts("2029-02-13T23:30:00Z")

    def test_the_2029_defect_survives_this_fix(self):
        """#2644 needs `expected_expiration_time` (2027-02-14) and does not get it here.

        Guarding the LIMIT, not just the win: if someone later "fixes" #2644 by
        editing this derivation, this test fails and forces them to read why the
        13-negatives hazard makes that the wrong move.
        """
        w = derive_resolution_window(ACTIVE_FUTURE)
        assert w.resolution_date.year == 2029, (
            "KXSB-27 still resolves 2029 after this change — close_time is a "
            "no-op for active futures. #2644 is a separate ship."
        )


class TestFallbackAndAggregation:
    def test_falls_back_to_backstop_when_no_close_time_exists(self):
        w = derive_resolution_window([FakeMarket(None, _ts("2026-09-15T16:40:00Z"))])
        assert w.resolution_date == _ts("2026-09-15T16:40:00Z")
        assert w.used_expiration_fallback is True

    def test_fallback_flag_is_false_when_close_and_expiration_coincide(self):
        """73% of active rows have close == expiration.

        Comparing the two dates cannot tell "fell back" from "they agree", so the
        flag must be set from whether a close_time existed, not from equality.
        """
        w = derive_resolution_window(ACTIVE_FUTURE)
        assert w.used_expiration_fallback is False

    def test_partial_close_times_use_the_legs_that_have_one(self):
        w = derive_resolution_window(
            [
                FakeMarket(None, _ts("2026-09-15T16:40:00Z")),
                FakeMarket(_ts("2026-09-01T22:54:02Z"), _ts("2026-09-15T16:40:00Z")),
            ]
        )
        assert w.resolution_date == _ts("2026-09-01T22:54:02Z")
        assert w.used_expiration_fallback is False

    def test_both_none_is_none_not_a_crash(self):
        w = derive_resolution_window([FakeMarket(None, None)])
        assert w.resolution_date is None
        assert w.expiration_time is None

    def test_empty_event_is_none_not_a_crash(self):
        w = derive_resolution_window([])
        assert w.resolution_date is None
        assert w.expiration_time is None

    def test_aggregation_is_max_across_sub_markets(self):
        """The event resolves when its LAST leg does — same aggregation as before."""
        w = derive_resolution_window(
            [
                FakeMarket(_ts("2026-09-01T20:00:00Z"), _ts("2026-09-10T00:00:00Z")),
                FakeMarket(_ts("2026-09-01T22:54:02Z"), _ts("2026-09-15T16:40:00Z")),
            ]
        )
        assert w.resolution_date == _ts("2026-09-01T22:54:02Z")
        assert w.expiration_time == _ts("2026-09-15T16:40:00Z")


class TestPollerWiring:
    """The derivation is worthless if the poller does not call it.

    A pure function with green unit tests and no call site is the classic
    vacuous guard, so assert the wiring at the source (gotcha: containment
    checks satisfied by a sibling call site — this pins the UPSERT keys, which
    is what actually reaches Postgres).
    """

    def test_poller_writes_both_columns_from_the_derivation(self):
        import inspect

        from app.tasks import kalshi as kalshi_task

        src = inspect.getsource(kalshi_task)
        assert "derive_resolution_window(event.markets)" in src, (
            "the Kalshi poller must derive the window, not re-inline "
            "max(expiration_time)"
        )
        assert (
            '"resolution_date": resolution_date' in src
        ), "resolution_date must be written from the derivation's close_time"
        assert '"expiration_time": expiration_time' in src, (
            "the backstop must be persisted to its own column, or the switch "
            "loses data"
        )
        assert '"resolution_date": expiration_time' not in src, (
            "RED-FIRST ANCHOR: this is the exact defect line. Its presence "
            "means resolution_date is the legal backstop again and #2660 has "
            "regressed."
        )

    def test_the_gap_create_path_uses_the_same_derivation(self):
        """There are TWO writers, and fixing one is how half a fix ships.

        The gap-create path (`status="resolved"` recovery) carried its own copy
        of `max(expiration_time)`. Guarded separately from the poller because a
        containment check on the module as a whole is satisfied by either call
        site alone.
        """
        import inspect

        from app.tasks import kalshi as kalshi_task

        src = inspect.getsource(kalshi_task)
        assert "derive_resolution_window(event.markets)" in src
        assert src.count("derive_resolution_window(event.markets)") == 2, (
            "both the poller and the gap-create path must derive the window; "
            f"found {src.count('derive_resolution_window(event.markets)')} "
            "call site(s)"
        )
        assert (
            "resolution_date = max(exp_times) if exp_times else max_close" not in src
        ), (
            "RED-FIRST ANCHOR for the second writer: the gap-create path's own "
            "max(expiration_time) is back, so rows created by the settled "
            "recovery carry the legal backstop again."
        )
        assert "expiration_time=expiration_time," in src, (
            "the gap-create INSERT must persist the backstop too, or rows "
            "created by that path have a NULL backstop while poller rows do not"
        )

    def test_model_carries_the_backstop_column(self):
        from app.models.models import FuturesMarket

        assert hasattr(FuturesMarket, "expiration_time"), (
            "FuturesMarket.expiration_time must exist or the poller's UPSERT "
            "raises on an unknown key"
        )


class TestReturnContract:
    def test_returns_a_frozen_window(self):
        w = derive_resolution_window(SETTLED_PROP)
        assert isinstance(w, ResolutionWindow)
        with pytest.raises(Exception):
            w.resolution_date = _ts("2030-01-01T00:00:00Z")  # type: ignore[misc]
