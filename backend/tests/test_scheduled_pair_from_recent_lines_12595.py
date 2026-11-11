"""#12595 / #11286 review: a scheduled game's projected pair comes from recent line readings.

Fable's five cases (8:40 and 9:10 AM PT, Nov 11), on rows shaped like the two
production reads (Lakers at Hawks: books leaving the pair on each moneyline-only
pass; Rams at Cardinals: ten books' 36 h-old lines under this morning's time).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import recent_line_readings as rl

NOW = datetime(2030, 1, 6, 18, 0, tzinfo=timezone.utc)


def _row(book, minutes_ago, *, lines=True, valid_minutes_ago=None, spread=-3.5, total=47.5,
         home=27.6, away=24.1, home_ml=-170, away_ml=145, event_id=1):
    captured = NOW - timedelta(minutes=minutes_ago)
    return SimpleNamespace(
        event_id=event_id, bookmaker=book, captured_at=captured,
        valid_until=(NOW - timedelta(minutes=valid_minutes_ago)) if valid_minutes_ago is not None else None,
        home_moneyline=home_ml, away_moneyline=away_ml,
        home_spread=spread if lines else None, over_under=total if lines else None,
        home_spread_odds=-110 if lines else None, away_spread_odds=-110 if lines else None,
        over_odds=-110 if lines else None, under_odds=-110 if lines else None,
        home_win_probability=0.62, away_win_probability=0.38,
        projected_home_score=home if lines else None, projected_away_score=away if lines else None,
        reading_count=1,
    )


def test_a_lines_row_followed_by_a_newer_moneyline_only_row_keeps_the_book_in_the_pair():
    """Case 1. The recent-lines read takes each book's newest row WITH lines, so the
    moneyline-only row written 10 min later doesn't take the book out."""
    lines_rows = [_row("draftkings", 25, valid_minutes_ago=10), _row("fanduel", 25, valid_minutes_ago=10)]
    p = rl.projection_from_rows(lines_rows, now=NOW)
    assert p["projection_bookmaker_count"] == 2
    assert p["projected_home_score"] is not None and p["projection_unavailable"] is None


def test_a_lines_row_older_than_the_bound_is_out_and_no_book_left_means_absent_not_old():
    """Case 2, and Rams at Cardinals: lines last confirmed 36 h ago."""
    p = rl.projection_from_rows([_row("betmgm", 36 * 60, valid_minutes_ago=36 * 60)], now=NOW)
    assert p["projected_home_score"] is None and p["projected_away_score"] is None
    assert p["home_spread"] is None and p["over_under"] is None
    assert p["projection_unavailable"] == rl.NO_RECENT_LINES
    assert p["projection_captured_at"] is None and p["projection_bookmaker_count"] == 0


def test_the_pairs_time_and_count_describe_the_line_readings_only():
    """Case 3. Two fresh books (one confirmed 5 min ago, one 40 min ago) and one
    36 h-old book: the count is 2 and the stamp is the newest LINES confirmation."""
    rows = [_row("draftkings", 30, valid_minutes_ago=5), _row("fanduel", 40),
            _row("betmgm", 36 * 60, valid_minutes_ago=36 * 60)]
    p = rl.projection_from_rows(rows, now=NOW)
    assert p["projection_bookmaker_count"] == 2
    assert p["projection_captured_at"] == (NOW - timedelta(minutes=5)).isoformat()


def test_a_dedup_kept_lines_row_counts_by_its_last_confirmation_not_its_first_capture():
    """Inside the two-hour window lines are re-confirmed every 5 min without a new row."""
    p = rl.projection_from_rows([_row("caesars", 300, valid_minutes_ago=3)], now=NOW)
    assert p["projection_bookmaker_count"] == 1 and p["projection_unavailable"] is None


def test_a_second_region_book_whose_only_lines_row_is_old_is_out():
    """Fable's fifth case: a book the moneyline-only fetch never covers keeps its old
    lines row as its latest. It must not lend that pair to this morning's card."""
    rows = [_row("draftkings", 20), _row("betrivers_us2", 36 * 60, spread=-9.1, total=40.0,
                                         home=15.5, away=24.6)]
    p = rl.projection_from_rows(rows, now=NOW)
    assert p["projection_bookmaker_count"] == 1
    assert p["projected_home_score"] == pytest.approx(27.6)


@pytest.mark.parametrize("status", ["live", "completed", "closed", None])
def test_a_live_or_finished_game_reads_exactly_as_today(status):
    """Case 4. Out of scope: the aggregated pair is untouched and no new keys appear."""
    ev = SimpleNamespace(id=1, status=status)
    assert rl.in_scope(ev) is False
    aggregated = {"home_spread": -3.5, "over_under": 47.5, "projected_home_score": 27.6,
                  "projected_away_score": 24.1, "bookmaker_count": 9}
    assert rl.apply_projection(aggregated, None) is aggregated
    assert rl.projection_keys(aggregated) == {}


def test_apply_projection_replaces_only_the_pair_fields_and_adds_the_three_keys():
    aggregated = {"home_probability": 0.62, "home_spread": -9.1, "over_under": 40.0,
                  "projected_home_score": 15.5, "projected_away_score": 24.6, "bookmaker_count": 22}
    projection = rl.projection_from_rows([_row("draftkings", 20)], now=NOW)
    out = rl.apply_projection(aggregated, projection)
    assert out["home_probability"] == 0.62 and out["bookmaker_count"] == 22  # untouched
    assert out["projected_home_score"] == pytest.approx(27.6)
    assert set(rl.projection_keys(out)) == set(rl.PROJECTION_KEYS)
    assert aggregated["projected_home_score"] == 15.5  # a copy, not a mutation


def test_scope_is_one_constant(monkeypatch):
    """Decision 149: all leagues by default; a frozenset limits it, in one line."""
    nfl = SimpleNamespace(id=1, status="scheduled")
    assert rl.in_scope(nfl) is True and rl.card_in_scope("scheduled", "icehockey_nhl") is True
    monkeypatch.setattr(rl, "PROJECTION_RECENT_LINES_SPORTS", frozenset({"americanfootball_nfl", "basketball_nba"}))
    assert rl.card_in_scope("scheduled", "icehockey_nhl") is False
    assert rl.card_in_scope("scheduled", "basketball_nba") is True
    assert rl.in_scope(nfl) is False  # its sport isn't loaded, so a limited scope leaves it as today


def test_the_recent_lines_statement_asks_for_lines_within_the_scan_floor_only():
    sql = str(rl.recent_lines_per_bookmaker_query([1, 2], now=NOW).compile())
    assert "home_spread IS NOT NULL" in sql and "over_under IS NOT NULL" in sql
    assert "LIMIT" in sql and "captured_at >=" in sql


@pytest.mark.asyncio
async def test_a_failed_recent_read_leaves_todays_pair(caplog):
    class _DB:
        async def execute(self, stmt):
            raise RuntimeError("statement timeout")

    odds_map = {1: {"aggregated": {"projected_home_score": 15.5}}}
    await rl.apply_recent_line_projections(_DB(), [SimpleNamespace(id=1, status="scheduled")], odds_map, now=NOW)
    assert odds_map[1]["aggregated"] == {"projected_home_score": 15.5}
