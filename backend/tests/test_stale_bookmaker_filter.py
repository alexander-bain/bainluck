"""Tests for _filter_stale_bookmaker_snapshots in events.py.

This filter prevents stale pregame odds from contaminating the aggregate
probability displayed on the event detail page. The bug it prevents:
bookmakers that stopped updating during a live game contribute their
pregame values (e.g., 59%) to the aggregate even though live bookmakers
show 2%. The filter must run for ALL non-scheduled statuses (live,
completed, closed) — not just live.
"""

import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.utils.odds_filtering import filter_stale_bookmaker_snapshots as _filter_stale_bookmaker_snapshots


def _snap(
    bookmaker: str,
    captured_at: datetime,
    home_prob: float = 0.5,
    valid_until: datetime = None,
    home_spread: float = None,
    over_under: float = None,
):
    """Create a lightweight snapshot-like object for testing."""
    return SimpleNamespace(
        bookmaker=bookmaker,
        captured_at=captured_at,
        home_win_probability=home_prob,
        valid_until=valid_until,
        home_spread=home_spread,
        over_under=over_under,
    )


@pytest.fixture
def commence_time():
    """Game start time."""
    return datetime(2026, 2, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def pregame(commence_time):
    """Timestamp before game started (pregame odds)."""
    return commence_time - timedelta(hours=1)


@pytest.fixture
def live(commence_time):
    """Timestamp after game started (live odds)."""
    return commence_time + timedelta(minutes=30)


class TestScheduledEventsPassthrough:
    """Scheduled events should return all snapshots unchanged."""

    def test_scheduled_returns_all(self, commence_time, pregame):
        snaps = [_snap("bookA", pregame, 0.55), _snap("bookB", pregame, 0.60)]
        result = _filter_stale_bookmaker_snapshots(snaps, "scheduled", commence_time)
        assert result == snaps

    def test_scheduled_ignores_commence_time(self, pregame):
        snaps = [_snap("bookA", pregame, 0.55)]
        result = _filter_stale_bookmaker_snapshots(snaps, "scheduled", None)
        assert result == snaps


class TestLiveGames:
    """Live games should filter out pregame-only bookmakers."""

    def test_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),   # pregame only
            _snap("live_book", live, 0.02),         # updated during game
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"

    def test_keeps_all_live_bookmakers(self, commence_time, live):
        snaps = [
            _snap("bookA", live, 0.02),
            _snap("bookB", live + timedelta(minutes=5), 0.03),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 2

    def test_filters_stale_outlier_without_dropping_active_books(self, commence_time, pregame, live):
        """Pregame outlier is suppressed while active live books remain."""
        snaps = [
            _snap("stale_outlier", pregame, 0.98),
            _snap("live_book_a", live, 0.02),
            _snap("live_book_b", live + timedelta(minutes=2), 0.03),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert [snap.bookmaker for snap in result] == ["live_book_a", "live_book_b"]

    def test_falls_back_when_no_live_probs(self, commence_time, pregame, live):
        """If live snapshots have no probability, fall back to all."""
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, None),  # live but no prob
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert result == snaps


class TestCompletedGames:
    """Completed games MUST also filter — this was the original bug."""

    def test_completed_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "completed", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"

    def test_closed_filters_pregame_bookmakers(self, commence_time, pregame, live):
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "closed", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"


class TestEdgeCases:
    def test_empty_snapshots(self, commence_time):
        result = _filter_stale_bookmaker_snapshots([], "live", commence_time)
        assert result == []

    def test_no_commence_time(self, pregame):
        snaps = [_snap("bookA", pregame, 0.55)]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", None)
        assert result == snaps

    def test_all_pregame_falls_back(self, commence_time, pregame):
        """If ALL bookmakers are pregame, return all (better than nothing)."""
        snaps = [
            _snap("bookA", pregame, 0.55),
            _snap("bookB", pregame, 0.60),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert result == snaps

    def test_snapshot_exactly_at_commence_time(self, commence_time):
        """Snapshot captured exactly at commence_time counts as live."""
        snaps = [_snap("bookA", commence_time, 0.50)]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1


class TestCommenceTimeSanityCheck:
    """When commence_time is wrong (in the future), skip filtering entirely."""

    def test_future_commence_time_skips_filter(self, pregame):
        """If event is 'live' but commence_time is in the future, return all."""
        future_commence = datetime(2099, 1, 1, tzinfo=timezone.utc)
        snaps = [
            _snap("bookA", pregame, 0.59),
            _snap("bookB", pregame, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", future_commence)
        # Should NOT filter — commence_time is clearly wrong
        assert result == snaps

    def test_future_commence_time_completed(self, pregame):
        """Same sanity check for completed events."""
        future_commence = datetime(2099, 1, 1, tzinfo=timezone.utc)
        snaps = [_snap("bookA", pregame, 0.59)]
        result = _filter_stale_bookmaker_snapshots(snaps, "completed", future_commence)
        assert result == snaps

    def test_past_commence_time_still_filters(self, commence_time, pregame, live):
        """Normal case: past commence_time still filters as expected."""
        snaps = [
            _snap("stale_book", pregame, 0.59),
            _snap("live_book", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"


class TestValidUntilDedup:
    """Write-time dedup sets valid_until on confirmed-unchanged snapshots.

    A bookmaker whose odds haven't changed since pregame will have:
      captured_at = pregame time, valid_until = latest poll time
    The filter should keep these because they're still being actively polled.
    """

    def test_deduped_pregame_snapshot_kept_via_valid_until(self, commence_time, pregame, live):
        """Snapshot with old captured_at but recent valid_until is kept."""
        snaps = [
            # Deduped: pregame odds, but confirmed during live game
            _snap("bookA", pregame, 0.55, valid_until=live),
            # Fresh live snapshot
            _snap("bookB", live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 2

    def test_deduped_pregame_snapshot_without_valid_until_filtered(self, commence_time, pregame):
        """Snapshot with old captured_at and no valid_until is filtered."""
        snaps = [
            _snap("stale_book", pregame, 0.55),  # no valid_until
            _snap("live_book", commence_time + timedelta(minutes=30), 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"

    def test_deduped_pregame_snapshot_with_old_valid_until_filtered(self, commence_time, pregame):
        """Snapshot with both captured_at AND valid_until before game is filtered."""
        snaps = [
            _snap("stale_book", pregame, 0.55, valid_until=pregame + timedelta(minutes=10)),
            _snap("live_book", commence_time + timedelta(minutes=30), 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "live_book"


class TestRecencyFilter:
    """Live events filter bookmakers that stopped updating recently."""

    def test_stale_live_bookmaker_filtered(self, commence_time):
        """Bookmaker that posted one live update then stopped for >10 min."""
        early_live = commence_time + timedelta(minutes=5)
        recent_live = commence_time + timedelta(minutes=30)
        snaps = [
            # Updated once early in the game, then stopped
            _snap("stale_live", early_live, 0.45),
            # Still actively updating
            _snap("active_book", recent_live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1
        assert result[0].bookmaker == "active_book"

    def test_recency_filter_only_for_live(self, commence_time):
        """Recency filter does not apply to completed/closed events."""
        early_live = commence_time + timedelta(minutes=5)
        late_live = commence_time + timedelta(hours=2)
        snaps = [
            _snap("early_book", early_live, 0.45),
            _snap("late_book", late_live, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "completed", commence_time)
        # Both pass Layer 1 (both after commence_time). Layer 2 skipped for completed.
        assert len(result) == 2

    def test_recency_filter_uses_valid_until(self, commence_time, pregame):
        """Bookmaker with old captured_at but recent valid_until passes recency."""
        recent_time = commence_time + timedelta(minutes=30)
        snaps = [
            # Deduped: pregame odds, confirmed recently via valid_until
            _snap("bookA", pregame, 0.55, valid_until=recent_time),
            # Fresh live snapshot
            _snap("bookB", recent_time, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 2

    def test_recency_filter_within_10_min_kept(self, commence_time):
        """Bookmakers within 10 min of each other are both kept."""
        t1 = commence_time + timedelta(minutes=25)
        t2 = commence_time + timedelta(minutes=30)
        snaps = [
            _snap("bookA", t1, 0.45),
            _snap("bookB", t2, 0.02),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 2

    def test_recency_filter_falls_back_when_all_filtered(self, commence_time):
        """If recency filter would remove all, keep all live snapshots."""
        early = commence_time + timedelta(minutes=5)
        snaps = [
            _snap("bookA", early, 0.45),
            _snap("bookB", early, None),  # no prob
        ]
        # Only bookA has valid prob, recency wouldn't remove it
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        # Both pass Layer 1, recency doesn't remove bookA (it's the latest)
        assert len(result) == 2

    def test_single_live_snapshot_no_recency_filter(self, commence_time):
        """Single live snapshot skips recency filter (needs >1)."""
        live_time = commence_time + timedelta(minutes=30)
        snaps = [
            _snap("bookA", live_time, 0.45),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", commence_time)
        assert len(result) == 1


class TestLiveBooksThatPulledTheMoneyline:
    """#8922: a live book with no moneyline still quotes the spread and total.

    Specimen: production 2026-09-26 20:30Z, /events/15315949, Notre Dame 35–3
    Purdue at the end of the 3rd quarter (kickoff 18:00Z). Every live book had
    pulled its moneyline; four books froze at kickoff still carrying one. The
    filter read the live set as empty and re-admitted the frozen four, so
    `current_odds` served spread 36.5 / total 54.2 — the mean of all eleven —
    and the margin map printed `PROJECTION ND by 36.1+` under a headline of
    `Projected final: 6 – 47`.
    """

    KICKOFF = datetime(2026, 9, 26, 18, 0, 0, tzinfo=timezone.utc)

    def _specimen(self):
        k = self.KICKOFF
        live = [  # (book, captured, home spread) — all total 52.5, no moneyline
            ("betmgm", k + timedelta(hours=2, minutes=29), 43.5),
            ("bovada", k + timedelta(hours=2, minutes=26), 41.5),
            ("draftkings", k + timedelta(hours=2, minutes=26), 41.5),
            ("fanatics", k + timedelta(hours=2, minutes=30), 40.5),
            ("fanduel", k + timedelta(hours=2, minutes=30), 42.5),
            ("mybookieag", k + timedelta(hours=2, minutes=27), 41.5),
            ("williamhill_us", k + timedelta(hours=2, minutes=26), 41.5),
        ]
        frozen = [  # (book, captured, home prob, home spread, total)
            ("betonlineag", k - timedelta(minutes=24), 0.0567, 27.0, 57.0),
            ("betrivers", k - timedelta(minutes=24), 0.0561, 27.5, 57.5),
            ("betus", k - timedelta(hours=1, minutes=18), 0.0567, 27.0, 57.0),
            ("lowvig", k - timedelta(minutes=24), 0.0567, 27.0, 57.0),
        ]
        return [
            _snap(b, t, None, home_spread=sp, over_under=52.5) for b, t, sp in live
        ] + [
            _snap(b, t, p, home_spread=sp, over_under=ou) for b, t, p, sp, ou in frozen
        ]

    def test_frozen_pregame_books_stay_out(self):
        result = _filter_stale_bookmaker_snapshots(self._specimen(), "live", self.KICKOFF)
        assert sorted(s.bookmaker for s in result) == [
            "betmgm", "bovada", "draftkings", "fanatics",
            "fanduel", "mybookieag", "williamhill_us",
        ]

    def test_served_line_is_the_live_books_not_the_pregame_mean(self):
        """The number the reader sees: ND by ~41.8 / 52.5, not 36.5 / 54.2."""
        from app.utils.odds_math import aggregate_bookmaker_odds

        result = _filter_stale_bookmaker_snapshots(self._specimen(), "live", self.KICKOFF)
        agg = aggregate_bookmaker_odds(result)
        assert agg["home_spread"] == 41.8
        assert agg["over_under"] == 52.5
        # No live book prices the winner, so there is no sportsbook consensus
        # to serve — never the frozen 5.6% under a live stamp (#7221's class).
        assert agg["home_probability"] is None

    def test_strawman_the_old_probe_reproduces_production(self):
        """The unfiltered eleven give exactly what production served."""
        from app.utils.odds_math import aggregate_bookmaker_odds

        agg = aggregate_bookmaker_odds(self._specimen())
        assert (agg["home_spread"], agg["over_under"]) == (36.5, 54.2)

    def test_completed_game_filters_the_same_way(self):
        result = _filter_stale_bookmaker_snapshots(self._specimen(), "completed", self.KICKOFF)
        assert len(result) == 7
        assert all(s.home_win_probability is None for s in result)

    def test_recency_layer_drops_a_silent_moneyline_book_behind_a_spread_only_one(self):
        """Layer 2 asks the same question: a fresh spread-only book is enough."""
        k = self.KICKOFF
        snaps = [
            _snap("went_quiet", k + timedelta(minutes=10), 0.30, home_spread=3.5),
            _snap("still_live", k + timedelta(minutes=60), None, home_spread=-10.5),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", k)
        assert [s.bookmaker for s in result] == ["still_live"]

    def test_a_live_row_quoting_nothing_still_falls_back(self):
        """Control: a post-kickoff row with no quote at all is not evidence."""
        k = self.KICKOFF
        snaps = [
            _snap("frozen", k - timedelta(minutes=30), 0.40, home_spread=2.5, over_under=45.0),
            _snap("empty_live", k + timedelta(minutes=30), None),
        ]
        result = _filter_stale_bookmaker_snapshots(snaps, "live", k)
        assert result == snaps
