"""#9816 — an MLB team page's Championship Path names the pennant, not "Conference".

Production, 2026-09-30 11:41Z: the Red Sox's page printed "Win Conference 5%" on
web and "Conference 5% #5" on iPhone. `GET /api/teams/boston-red-sox` served
``championship_path[1] = {tier: 2, label: "Conference", market_name: "American
League Champion"}`` because the tier labels were one table for every sport. MLB
has leagues and a pennant; both clients render ``label`` verbatim, so the server
names it. Fixtures are the production rows (names, ids, tickers and prices as
stored on 2026-09-30).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import teams as teams_mod

_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _row(tier, name, prob, *, source, ext, mid, category):
    outcome = SimpleNamespace(
        current_probability=prob, rank=5, probability_change_24h=None, is_winner=False
    )
    market = SimpleNamespace(
        market_tier=tier,
        name=name,
        canonical_market_key=None,
        id=mid,
        group_id=f"{source}:{ext}",
        source=source,
        external_id=ext,
        llm_sport_category=category,
    )
    return outcome, market


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


async def _path(rows, league, sport_key):
    return await teams_mod._get_championship_path(
        1, _DB(rows), league_slug=league, now=_NOW, team_sport_key=sport_key
    )


def _by_tier(path):
    return {p["tier"]: p for p in path}


_RED_SOX = [
    _row(2, "American League Champion", 0.055, source="kalshi", ext="KXMLBAL-26", mid=274, category="baseball"),
    _row(2, "MLB: 2026 American League Champion", 0.0485, source="polymarket", ext="215866", mid=199045, category="baseball"),
]
_DODGERS = [
    _row(2, "National League Champion", 0.39, source="kalshi", ext="KXMLBNL-26", mid=270, category="baseball"),
    _row(2, "MLB: 2026 National League Champion", 0.405, source="polymarket", ext="215871", mid=199050, category="baseball"),
]


@pytest.mark.asyncio
async def test_red_sox_pennant_step_names_the_american_league():
    step = _by_tier(await _path(_RED_SOX, "mlb", "baseball_mlb"))[2]
    assert step["label"] == "AL Pennant"
    assert step["market_id"] == 274
    assert step["probability"] == pytest.approx((0.055 + 0.0485) / 2, abs=1e-4)


@pytest.mark.asyncio
async def test_dodgers_pennant_step_names_the_national_league():
    step = _by_tier(await _path(_DODGERS, "mlb", "baseball_mlb"))[2]
    assert step["label"] == "NL Pennant"


@pytest.mark.asyncio
async def test_other_sports_keep_conference():
    """Strawman arm: the same tier-2 row on an NFL team still says Conference."""
    rows = [
        _row(2, "AFC Champion", 0.12, source="kalshi", ext="KXNFLAFC-27", mid=9, category="football"),
    ]
    step = _by_tier(await _path(rows, "nfl", "americanfootball_nfl"))[2]
    assert step["label"] == "Conference"


@pytest.mark.parametrize(
    ("tier", "sport", "name", "label"),
    [
        (2, "baseball_mlb", "American League Champion", "AL Pennant"),
        (2, "baseball_mlb", "MLB: 2026 National League Champion", "NL Pennant"),
        (2, "baseball_mlb", "AL Champion 2026", "AL Pennant"),
        # Names neither league: still the pennant, never "Conference".
        (2, "baseball_mlb", "Pennant Winner", "Pennant"),
        # A lowercase "al" inside a name is not the American League.
        (2, "baseball_mlb", "Pennant winner al fin", "Pennant"),
        (1, "baseball_mlb", "World Series Champion", "Championship"),
        (4, "baseball_mlb", "AL East Winner", "Division"),
        (2, "basketball_nba", "Eastern Conference Champion", "Conference"),
        (2, None, "American League Champion", "Conference"),
        (3, "baseball_mlb", "Something", "Other"),
    ],
)
def test_tier_label_table(tier, sport, name, label):
    assert teams_mod._championship_tier_label(tier, sport, name) == label
