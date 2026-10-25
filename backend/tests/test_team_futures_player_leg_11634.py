"""#11634 — a team page stops leading with one of its players' award prices.

WHAT A READER SAW (production, 2026-10-25 ~16:10Z, 390px):
``/sport/baseball/mlb/team/los-angeles-dodgers`` led with "CHAMPIONSHIP 27%".
The Dodgers were out (swept in the NLCS) and ``championship_path`` was empty,
so the page's futures fallback picked the best remaining row: Max Muncy's
"Silver Slugger: NL Third Baseman" leg (market 52755974, tier 5, 27%).

The leg is FK-linked to the club (``futures_outcomes.team_id = 10707``, read off
production the same minute), so the served ``matched_team`` cannot tell a
player's leg from the club's. ``outcome_is_player`` does, from the club's own
roster — the roster branch's test, asked of every served row.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routes import futures as futures_route
from app.routes.user import _query_team_futures

DODGERS = 10707


def _outcome(oid, name, prob, *, team_id=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=None, current_yes_ask=None,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"X-{oid}", probability_change_24h=0.0, rank=1,
    )


def _market(mid, name, outcomes, *, tier=1):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=None, group_id=None,
        status="open", llm_sport_category="baseball", resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        market_tier=tier, canonical_market_key=None, outcomes=outcomes,
    )


# Production ids and prices, 2026-10-25. Every leg is stored on the club's row.
SILVER_SLUGGER = _market(52755974, "Silver Slugger: NL Third Baseman",
                         [_outcome(198634611, "Max Muncy", 0.27, team_id=DODGERS)], tier=5)
WORLD_SERIES = _market(212, "World Series Champion",
                       [_outcome(1, "Los Angeles Dodgers", 0.004, team_id=DODGERS)])


def _result(rows):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    return res


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _DB:
    """Team load (with its roster), the FK branch, the stats read, the market reload."""

    def __init__(self, roster, markets):
        self.roster = roster
        self.markets = markets

    async def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        where = sql.split("WHERE", 1)[-1]
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=DODGERS, name="Los Angeles Dodgers", sport_id=1, espn_id=None,
                roster_players=self.roster, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, "baseball_mlb")])
        if "futures_outcomes.team_id IN" in where:
            return _result([
                (o, m, None)
                for m in self.markets for o in m.outcomes if o.team_id == DODGERS
            ])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            return _result(list(self.markets))
        return _result([])


async def _served(db):
    async def _nothing_refused(_db, markets):
        return {m.id: set() for m in markets}

    with patch.object(futures_route, "withheld_price_outcome_ids_for_markets",
                      _nothing_refused):
        data = await _query_team_futures([DODGERS], db, limit=30)
    return {i["market_id"]: i for i in data["items"]}


ROSTER = [{"name": "Max Muncy"}, {"name": "Shohei Ohtani"}, "Andy Pages"]


async def test_a_players_leg_is_marked_and_the_clubs_own_leg_is_not():
    items = await _served(_DB(ROSTER, [SILVER_SLUGGER, WORLD_SERIES]))
    assert items[SILVER_SLUGGER.id]["outcome_is_player"] is True
    assert items[WORLD_SERIES.id]["outcome_is_player"] is False
    # Both still reach the page: the flag refuses nothing on its own. The row
    # stays in Season Futures; only the hero/journey picker declines it.
    assert items[SILVER_SLUGGER.id]["matched_team"]["id"] == DODGERS


async def test_a_bare_string_roster_entry_counts():
    pages = _market(9, "Gold Glove: NL Center Field",
                    [_outcome(9, "Andy Pages", 0.05, team_id=DODGERS)], tier=5)
    items = await _served(_DB(ROSTER, [pages]))
    assert items[9]["outcome_is_player"] is True


async def test_no_roster_is_not_evidence():
    """Unknown stays unknown: a club with no stored roster marks nothing, so the
    picker keeps today's behaviour rather than losing a real season price."""
    items = await _served(_DB(None, [SILVER_SLUGGER, WORLD_SERIES]))
    assert items[SILVER_SLUGGER.id]["outcome_is_player"] is False
    assert items[WORLD_SERIES.id]["outcome_is_player"] is False
