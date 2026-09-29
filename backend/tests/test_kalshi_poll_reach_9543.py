"""#9543: the Kalshi beat upserts the existing rows it wrote longest ago first.

The loop breaks on a deadline every beat. Walking the existing partition in
the venue's listing order cut off the same tail every beat, so poll-carried
fields (#9383's threshold label, #3508's competition) never reached it. The
real-Postgres half is
`tests/integration/test_kalshi_poll_reaches_the_stalest_rows_first_real_postgres_9543.py`.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.tasks import kalshi as kalshi_mod
from app.tasks.kalshi import _least_recently_polled_first

NOW = datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)


def _ev(ticker):
    return SimpleNamespace(event_ticker=ticker)


def _order(tickers, stamps):
    return [
        e.event_ticker
        for e in _least_recently_polled_first([_ev(t) for t in tickers], stamps)
    ]


class TestOldestPollFirst:
    def test_listing_order_is_replaced_by_poll_age(self):
        stamps = {
            "A": NOW - timedelta(hours=1),
            "B": NOW - timedelta(hours=30),
            "C": NOW - timedelta(hours=5),
        }
        assert _order(["A", "B", "C"], stamps) == ["B", "C", "A"]

    def test_a_row_with_no_stamp_goes_first(self):
        stamps = {"A": NOW - timedelta(hours=40), "B": None}
        assert _order(["A", "B"], stamps) == ["B", "A"]

    def test_a_ticker_missing_from_the_map_counts_as_never_polled(self):
        assert _order(["A", "B"], {"A": NOW}) == ["B", "A"]

    def test_ties_keep_their_listing_order(self):
        stamps = {t: NOW for t in "ABCD"}
        assert _order(list("DBCA"), stamps) == list("DBCA")
        assert _order(list("XY"), {}) == ["X", "Y"]

    def test_a_naive_stamp_is_read_as_utc_not_refused(self):
        stamps = {
            "A": (NOW - timedelta(hours=1)).replace(tzinfo=None),
            "B": NOW - timedelta(hours=2),
        }
        assert _order(["A", "B"], stamps) == ["B", "A"]

    def test_empty(self):
        assert _least_recently_polled_first([], {}) == []


class TestTheBeatUsesIt:
    """Source guard: the loop order is built from the poll's own stamp."""

    SRC = inspect.getsource(kalshi_mod._poll_kalshi_markets)

    def test_the_existing_tickers_query_reads_the_poll_stamp(self):
        assert (
            "SELECT external_id, volume_updated_at FROM futures_markets" in self.SRC
        )

    def test_existing_events_are_rotated_before_the_floor_and_the_loop(self):
        rotate = self.SRC.index("existing_events = _least_recently_polled_first(")
        floor = self.SRC.index(
            "events = _floor_series_first(new_events + existing_events)"
        )
        loop = self.SRC.index('_mark_phase("upsert_loop")')
        assert rotate < floor < loop

    def test_the_upsert_still_rewrites_the_stamp_it_orders_by(self):
        """Without this the stalest row stays stalest and the rotation stalls."""
        update_set = self.SRC[self.SRC.index("update_set = {") :]
        update_set = update_set[: update_set.index("}")]
        assert '"volume_updated_at": func.now()' in update_set
