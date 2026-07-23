"""Unit tests for the team championship-path season truth (Queue #242 Item 1).

The championship path is forward-looking: prior-season and future-season markets
must not leak in, and every entry declares the season it describes. (The
graded-winner / settled exclusion is enforced in SQL via ``~graded.exists()`` and
is covered by the live acceptance check, not mockable here.)
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import teams as teams_mod


def _outcome(prob, rank=1, change=None):
    return SimpleNamespace(
        current_probability=prob,
        rank=rank,
        probability_change_24h=change,
        is_winner=False,
    )


def _market(tier, name, key=None, mid=1, gid=None):
    return SimpleNamespace(
        market_tier=tier,
        name=name,
        canonical_market_key=key,
        id=mid,
        group_id=gid,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _Result(self._rows)


_NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)  # MLB 2026 season in play


@pytest.mark.asyncio
async def test_prior_season_market_excluded():
    rows = [
        (_outcome(0.995), _market(4, "2025-26 NL Central Winner",
                                  key="baseball:MLB:division:2025-26", mid=10)),
        (_outcome(0.15), _market(1, "2026 World Series",
                                 key="baseball:MLB:championship:2026", mid=11)),
    ]
    path = await teams_mod._get_championship_path(1, _DB(rows), league_slug="mlb", now=_NOW)
    tiers = {p["tier"] for p in path}
    # The settled 2025-26 division market must NOT leak into the 2026 path.
    assert 4 not in tiers
    assert 1 in tiers


@pytest.mark.asyncio
async def test_future_season_market_excluded():
    rows = [
        (_outcome(0.20), _market(1, "2027 World Series Winner", mid=12)),
    ]
    path = await teams_mod._get_championship_path(1, _DB(rows), league_slug="mlb", now=_NOW)
    assert path == []


@pytest.mark.asyncio
async def test_current_season_stamped():
    rows = [
        (_outcome(0.15), _market(1, "2026 World Series",
                                 key="baseball:MLB:championship:2026", mid=11)),
    ]
    path = await teams_mod._get_championship_path(1, _DB(rows), league_slug="mlb", now=_NOW)
    assert len(path) == 1
    assert path[0]["season"] == "2026"
    assert path[0]["probability"] == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_yearless_market_passes_through_and_uses_current_season():
    # A market with no year in name/key can't be judged prior/future — keep it,
    # and stamp it with the league's current season.
    rows = [
        (_outcome(0.30), _market(2, "NL Pennant", mid=13)),
    ]
    path = await teams_mod._get_championship_path(1, _DB(rows), league_slug="mlb", now=_NOW)
    assert len(path) == 1
    assert path[0]["season"] == "2026"


@pytest.mark.asyncio
async def test_no_league_slug_still_returns_path():
    # Unknown league → no year-based prior filtering, still returns entries.
    rows = [
        (_outcome(0.25), _market(1, "Championship", mid=14)),
    ]
    path = await teams_mod._get_championship_path(1, _DB(rows), league_slug=None, now=_NOW)
    assert len(path) == 1
