"""#11286 (decision 138: A): scheduled NFL and NBA games get spreads and totals once an hour.

Builder E counted projections recorded per scheduled NFL game in 24 h: 0 for all 14,
because a game outside the live and starting-soon tiers was fetched for the
moneyline only. One fetch an hour per league now asks for spreads and totals too,
shared between discovery and the poller's "later" tier. No other league, no other
cadence, and Redis failures fall back to the moneyline (the quota is the constraint).
"""
import ast
import inspect
import textwrap

import pytest

from app.utils import scheduled_full_markets as sfm


class _Redis:
    def __init__(self):
        self.store = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, ex=None):
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True


class _Boom:
    def get(self, k):
        raise RuntimeError("redis down")

    def set(self, k, v, ex=None):
        raise RuntimeError("redis down")


NOW = 1_800_000_000.0


@pytest.mark.parametrize("sport", ["americanfootball_nfl", "basketball_nba"])
def test_nfl_and_nba_get_full_markets_when_the_hour_is_unpaid(sport):
    assert sfm.scheduled_markets(sport, _Redis(), NOW) == "h2h,spreads,totals"


@pytest.mark.parametrize("sport", ["icehockey_nhl", "baseball_mlb", "basketball_ncaab",
                                   "americanfootball_ncaaf", "basketball_wnba", "soccer_epl"])
def test_no_other_league_changes(sport):
    assert sfm.scheduled_markets(sport, _Redis(), NOW) == "h2h"


def test_once_an_hour_shared_by_both_paths():
    r = _Redis()
    sfm.record_full_fetch("americanfootball_nfl", r, NOW)
    # Every pass inside 55 minutes pays nothing.
    for minutes in (15, 30, 45, 54):
        assert sfm.scheduled_markets("americanfootball_nfl", r, NOW + minutes * 60) == "h2h"
    assert sfm.scheduled_markets("americanfootball_nfl", r, NOW + 55 * 60) == "h2h,spreads,totals"
    # The other league's hour is its own.
    assert sfm.scheduled_markets("basketball_nba", r, NOW + 60) == "h2h,spreads,totals"


def test_redis_failure_falls_back_to_the_moneyline():
    assert sfm.scheduled_markets("basketball_nba", _Boom(), NOW) == "h2h"
    assert sfm.scheduled_markets("basketball_nba", None, NOW) == "h2h"
    sfm.record_full_fetch("basketball_nba", _Boom(), NOW)  # never raises
    sfm.record_full_fetch("basketball_nba", None, NOW)


def test_an_unreadable_stamp_counts_as_unpaid():
    r = _Redis()
    r.store[sfm.stamp_key("basketball_nba")] = b"not-a-number"
    assert sfm.scheduled_markets("basketball_nba", r, NOW) == "h2h,spreads,totals"


def test_the_stamp_expires_on_its_own():
    r = _Redis()
    captured = {}
    r.set = lambda k, v, ex=None: captured.update(k=k, v=v, ex=ex)
    sfm.record_full_fetch("americanfootball_nfl", r, NOW)
    assert captured["k"] == "bainluck:scheduled_full_markets:americanfootball_nfl"
    assert captured["ex"] >= sfm.SCHEDULED_FULL_MARKETS_INTERVAL_SECONDS


def _code(fn) -> str:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value.value = ""
    return ast.unparse(tree)


def test_discovery_asks_the_helper_and_stamps_after_a_full_fetch():
    from app.tasks import sports

    code = _code(sports._discover_events)
    assert "scheduled_markets(sport_key, r," in code
    assert "markets=discover_markets" in code
    assert "record_full_fetch(sport_key, r," in code
    assert "markets='h2h'" not in code and 'markets="h2h"' not in code
    # Still a partial caller for the shared writer (us region only).
    assert "update_opening=False" in code and "drop_below_floor=False" in code


def test_the_pollers_later_tier_asks_the_helper_and_nothing_else_changed():
    from app.tasks import odds_polling

    code = _code(odds_polling._poll_all_odds)
    assert "api_markets = scheduled_markets(sport_key, r, now.timestamp())" in code
    assert "record_full_fetch(sport_key, r, received_at)" in code
    # Live and starting-soon are untouched, and conservation still forces h2h first.
    assert code.count("api_markets = 'h2h,spreads,totals'") == 2
    assert code.index("if quota_conservation:") < code.index("api_markets = scheduled_markets(")
    # Review (bot, Fable): every poll still writes opening odds; a fetch that didn't
    # ask for lines says so, so its absent spread and total don't overwrite them.
    assert "lines_fetched='spreads' in api_markets" in code
    assert "update_opening='spreads' in api_markets" not in code



# --- Review (bot, 8690c248): opening odds on a moneyline-only poll ---


class _OpeningSession:
    """Answers the status read with 'scheduled' and records the opening UPDATE's values."""

    def __init__(self):
        self.updates = []

    async def execute(self, stmt):
        from sqlalchemy.sql.dml import Update

        if isinstance(stmt, Update):
            self.updates.append({
                (c if isinstance(c, str) else c.key): getattr(v, "value", v)
                for c, v in stmt._values.items()
            })
            return None

        class _R:
            def scalar_one_or_none(self_inner):
                return "scheduled"
        return _R()


@pytest.mark.asyncio
async def test_a_moneyline_only_poll_still_writes_the_opening_moneyline():
    """Calibration reads COALESCE(calibration_probability, opening_probability):
    an h2h-only poll must keep writing the opening probabilities and favourite."""
    from datetime import datetime, timedelta, timezone

    from app.tasks.odds_polling import _maybe_set_opening_odds

    session = _OpeningSession()
    await _maybe_set_opening_odds(
        session, 1, 0.62, 0.38, None, None,
        commence_time=datetime.now(timezone.utc) + timedelta(days=2), lines_fetched=False,
    )
    assert len(session.updates) == 1
    written = session.updates[0]
    assert written["opening_home_probability"] == 0.62 and written["opening_away_probability"] == 0.38
    assert "opening_favorite" in written


@pytest.mark.asyncio
async def test_a_moneyline_only_poll_after_a_full_fetch_does_not_null_the_opening_lines():
    from datetime import datetime, timedelta, timezone

    from app.tasks.odds_polling import _maybe_set_opening_odds

    later = datetime.now(timezone.utc) + timedelta(days=2)
    session = _OpeningSession()
    await _maybe_set_opening_odds(session, 1, 0.62, 0.38, -3.5, 47.5, commence_time=later, lines_fetched=True)
    await _maybe_set_opening_odds(session, 1, 0.63, 0.37, None, None, commence_time=later, lines_fetched=False)
    full, h2h = session.updates
    assert full["opening_home_spread"] == -3.5 and full["opening_over_under"] == 47.5
    assert "opening_home_spread" not in h2h and "opening_over_under" not in h2h  # left as the full fetch wrote them
    assert h2h["opening_home_probability"] == 0.63


@pytest.mark.asyncio
async def test_a_full_fetch_still_writes_the_lines_exactly_as_before():
    """Default behaviour is unchanged: a lines-carrying fetch writes spread and total,
    including None when every book has pulled them."""
    from datetime import datetime, timedelta, timezone

    from app.tasks.odds_polling import _maybe_set_opening_odds

    session = _OpeningSession()
    await _maybe_set_opening_odds(session, 1, 0.5, 0.5, None, None,
                                  commence_time=datetime.now(timezone.utc) + timedelta(days=1))
    assert session.updates[0]["opening_home_spread"] is None
    assert session.updates[0]["opening_over_under"] is None


@pytest.mark.parametrize("lag_s", [10, 70, 130])
def test_discovery_at_05_and_35_refreshes_lines_every_hour_not_ninety_minutes(lag_s):
    """Nov 12 (#11286): lines landed at 5:36 and the 6:35 run, 59 minutes later,
    stayed moneyline-only, so the next lines were at 7:05, matching the
    90-minute projection bound. Replay six hours of discovery runs at :05 and :35,
    each fetch landing ``lag_s`` into its run."""
    r = _Redis()
    fetches = []
    start = NOW - (NOW % 3600) + 5 * 60  # a :05 run
    for run in range(12):
        t = start + run * 1800 + lag_s
        if sfm.scheduled_markets("americanfootball_nfl", r, t) == "h2h,spreads,totals":
            sfm.record_full_fetch("americanfootball_nfl", r, t)
            fetches.append(t)
    gaps = [b - a for a, b in zip(fetches, fetches[1:])]
    assert len(fetches) == 6 and set(gaps) == {3600}
    # never two lines fetches inside 55 minutes, never a 90-minute wait
    assert min(gaps) >= sfm.SCHEDULED_FULL_MARKETS_INTERVAL_SECONDS
    assert max(gaps) < 90 * 60
