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
    p = rl.projection_from_rows(lines_rows, lines_rows, now=NOW)
    assert p["projection_bookmaker_count"] == 2
    assert p["projected_home_score"] is not None and p["projection_unavailable"] is None


def test_a_lines_row_older_than_the_bound_is_out_and_no_book_left_means_absent_not_old():
    """Case 2, and Rams at Cardinals: lines last confirmed 36 h ago."""
    p = rl.projection_from_rows([_row("betmgm", 36 * 60, valid_minutes_ago=36 * 60)], [], now=NOW)
    assert p["projected_home_score"] is None and p["projected_away_score"] is None
    assert p["home_spread"] is None and p["over_under"] is None
    assert p["projection_unavailable"] == rl.NO_RECENT_LINES
    assert p["projection_captured_at"] is None and p["projection_bookmaker_count"] == 0


def test_the_pairs_time_and_count_describe_the_line_readings_only():
    """Case 3. Two fresh books (one confirmed 5 min ago, one 40 min ago) and one
    36 h-old book: the count is 2 and the stamp is the newest LINES confirmation."""
    rows = [_row("draftkings", 30, valid_minutes_ago=5), _row("fanduel", 40),
            _row("betmgm", 36 * 60, valid_minutes_ago=36 * 60)]
    p = rl.projection_from_rows(rows, rows, now=NOW)
    assert p["projection_bookmaker_count"] == 2
    assert p["projection_captured_at"] == (NOW - timedelta(minutes=5)).isoformat()


def test_a_dedup_kept_lines_row_counts_by_its_last_confirmation_not_its_first_capture():
    """Inside the two-hour window lines are re-confirmed every 5 min without a new row."""
    p = rl.projection_from_rows([_row("caesars", 300, valid_minutes_ago=3)], [], now=NOW)
    assert p["projection_bookmaker_count"] == 1 and p["projection_unavailable"] is None


def test_a_second_region_book_whose_only_lines_row_is_old_is_out():
    """Fable's fifth case: a book the moneyline-only fetch never covers keeps its old
    lines row as its latest. It must not lend that pair to this morning's card."""
    rows = [_row("draftkings", 20), _row("betrivers_us2", 36 * 60, spread=-9.1, total=40.0,
                                         home=15.5, away=24.6)]
    p = rl.projection_from_rows(rows, rows, now=NOW)
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
    projection = rl.projection_from_rows([_row("draftkings", 20)], [], now=NOW)
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








# --- Fable's review of #12599: the clock dates lines only by a lines reading ---


def test_lines_closed_by_a_moneyline_pass_are_dated_by_their_own_capture():
    """Probe 1: lines read 20 min ago, row closed 5 min ago by a moneyline-only pass.
    The latest row is the moneyline one; the lines row dates from `captured_at`."""
    lines = _row("draftkings", 20, valid_minutes_ago=5)
    moneyline_only = _row("draftkings", 5, lines=False)
    p = rl.projection_from_rows([moneyline_only], [lines], now=NOW)
    assert p["projection_captured_at"] == (NOW - timedelta(minutes=20)).isoformat()
    assert p["projection_bookmaker_count"] == 1


def test_old_lines_closed_recently_do_not_stretch_the_bound():
    """Probe 2: lines read 5 h 20 min ago, closed 80 min ago (a 4-hourly discovery
    league). The recent read (captured inside 90 min) finds nothing; the pair is absent."""
    moneyline_only = _row("fanduel", 80, lines=False)
    p = rl.projection_from_rows([moneyline_only], [], now=NOW)
    assert p["projection_unavailable"] == rl.NO_RECENT_LINES
    # and even if such a row were handed in, its capture time is outside the bound
    stale = _row("fanduel", 320, valid_minutes_ago=80)
    assert rl.projection_from_rows([moneyline_only], [stale], now=NOW)["projection_unavailable"] == rl.NO_RECENT_LINES


def test_a_latest_row_with_lines_is_dated_by_its_confirmation():
    """The current latest row has been re-read: `valid_until` is a lines confirmation."""
    latest = _row("caesars", 300, valid_minutes_ago=3)
    p = rl.projection_from_rows([latest], [], now=NOW)
    assert p["projection_captured_at"] == (NOW - timedelta(minutes=3)).isoformat()


def test_the_read_asks_only_for_books_whose_latest_row_lacks_lines_within_the_bound():
    from sqlalchemy.dialects import postgresql

    latest = {1: [_row("draftkings", 10), _row("fanduel", 10, lines=False)],
              2: [_row("betmgm", 5, lines=False)]}
    assert rl.books_needing_lines(latest) == [(1, "fanduel"), (2, "betmgm")]
    sql = str(rl.recent_lines_query([(1, "fanduel")], since=NOW - rl.PROJECTION_LINES_BOUND)
              .compile(dialect=postgresql.dialect()))
    assert "VALUES" in sql and "LATERAL" in sql and "LIMIT" in sql
    assert "home_spread IS NOT NULL" in sql and "over_under IS NOT NULL" in sql and "captured_at >=" in sql
    assert sql.lstrip().upper().startswith("SELECT")  # db-query can EXPLAIN it


@pytest.mark.asyncio
async def test_no_book_needing_lines_means_no_read():
    db = _DB()
    assert await rl.read_recent_lines(db, [], now=NOW) == {}
    assert db.log == []


class _Savepoint:
    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        self.log.append("SAVEPOINT")
        return self

    async def __aexit__(self, *exc):
        return False

    async def rollback(self):
        self.log.append("ROLLBACK TO SAVEPOINT")


class _DB:
    def __init__(self, rows=None, fail=False):
        self.log, self.rows, self.fail = [], rows or [], fail

    def begin_nested(self):
        return _Savepoint(self.log)

    async def execute(self, stmt):
        text_ = str(stmt)
        if text_.startswith("SET LOCAL"):
            self.log.append("SET LOCAL")
            return None
        self.log.append("READ")
        if self.fail:
            raise RuntimeError("canceling statement due to statement timeout")
        rows = self.rows

        class _R:
            def all(self_inner):
                return rows
        return _R()


@pytest.mark.asyncio
async def test_the_read_runs_in_a_savepoint_that_is_always_rolled_back():
    row = _row("draftkings", 20)
    row.id = 7
    db = _DB(rows=[row])
    out = await rl.read_recent_lines(db, [(1, "draftkings")], now=NOW)
    assert db.log == ["SAVEPOINT", "SET LOCAL", "READ", "ROLLBACK TO SAVEPOINT"]
    assert out[1][0].bookmaker == "draftkings"


@pytest.mark.asyncio
async def test_a_failed_read_withholds_the_pair_with_read_failed():
    db = _DB(fail=True)
    odds_map = {1: {"aggregated": {"projected_home_score": 15.5, "projected_away_score": 24.6,
                                   "home_spread": -9.1, "over_under": 40.0, "bookmaker_count": 22},
                    "all_snapshots": [_row("betmgm", 30, lines=False)]}}
    await rl.apply_recent_line_projections(db, [SimpleNamespace(id=1, status="scheduled")], odds_map, now=NOW)
    agg = odds_map[1]["aggregated"]
    assert agg["projected_home_score"] is None and agg["home_spread"] is None
    assert rl.projection_keys(agg)["projection_unavailable"] == rl.READ_FAILED
    assert db.log[-1] == "ROLLBACK TO SAVEPOINT"  # the request's transaction isn't left aborted
