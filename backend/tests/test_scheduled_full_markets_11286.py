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
    # Discovery's next three passes (every 15 min) and the poller inside the hour pay nothing.
    for minutes in (15, 30, 45, 59):
        assert sfm.scheduled_markets("americanfootball_nfl", r, NOW + minutes * 60) == "h2h"
    assert sfm.scheduled_markets("americanfootball_nfl", r, NOW + 3600) == "h2h,spreads,totals"
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
