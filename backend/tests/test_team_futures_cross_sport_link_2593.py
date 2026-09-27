"""#2593 — a team page stops printing another sport's market as the team's own.

WHAT A READER SAW (production, 2026-09-27 ~11:35Z): ``/api/teams/dallas-mavericks``
served "MLS Western Conference Champion — Dallas 7.5%" in the Mavericks' Season
Futures, and ``/api/teams/seattle-storm`` the same market's "Seattle" leg. Kalshi
market 23500's outcomes were linked by city name to NBA team 37 and WNBA team
13415, and ``_query_team_futures`` took any stored ``team_id`` as "always correct
— team_id is sport-scoped", skipping the BR53 sport check its own name branch
applies.

These tests drive the real ``_query_team_futures`` with the stored shapes read off
production (db-query 2026-09-27). The cross-sport rows must leave; the same-sport
control and a non-sport market's link must stay.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import futures as futures_route
from app.routes import user as user_route
from app.routes import teams as teams_route
from app.routes.user import _query_team_futures
from app.utils.market_team_sport import sport_key_llm_category as _sport_key_llm_category

pytestmark = pytest.mark.asyncio

MAVERICKS = 37


def _outcome(oid, name, prob, *, team_id=MAVERICKS):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=None, current_yes_ask=None,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"X-{oid}", probability_change_24h=0.0, rank=1,
    )


def _market(mid, name, category, outcomes, *, tier=2):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", group_id=None,
        status="open", llm_sport_category=category, resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        market_tier=tier, canonical_market_key=None, outcomes=outcomes,
    )


# The specimen: KXMLSWEST-26-DAL, outcome 383311, team_id 37, p 0.075.
MLS_WEST = _market(23500, "MLS Western Conference Champion", "soccer",
                   [_outcome(383311, "Dallas", 0.075)])
# CONTROL — the Mavericks' own title market (same sport), linked the same way.
NBA_TITLE = _market(900001, "2026-27 Pro Basketball Champion", "basketball",
                    [_outcome(900011, "Dallas Mavericks", 0.02)], tier=1)
# CONTROL — a market that makes no sport claim keeps its link: the Madden cover
# question is `entertainment` and its player legs carry their NFL clubs.
NO_CLAIM = _market(900002, "Who will be on the cover of a video game?",
                   "entertainment", [_outcome(900012, "Luka Doncic", 0.1)], tier=5)

MARKETS = [MLS_WEST, NBA_TITLE, NO_CLAIM]


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
    """Dispatches on the statement: team load, the FK branch, the market reload."""

    def __init__(self, markets=MARKETS, team_sport_key="basketball_nba"):
        self.markets = markets
        self.team_sport_key = team_sport_key

    async def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=MAVERICKS, name="Dallas Mavericks", sport_id=2, espn_id="6",
                roster_players=None, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, self.team_sport_key)])
        if "futures_outcomes.team_id IN" in sql and "futures_markets" in sql:
            return _result([
                (o, m, None)
                for m in self.markets for o in m.outcomes if o.team_id == MAVERICKS
            ])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            return _result(list(self.markets))
        return _result([])  # name branch, trade reads: nothing on record


def _served(data):
    return {(i["market_id"], i["outcome_name"]) for i in data["items"]}


async def _run(db=None):
    async def _nothing_refused(_db, markets):
        return {m.id: set() for m in markets}

    with patch.object(futures_route, "withheld_price_outcome_ids_for_markets",
                      _nothing_refused):
        return await _query_team_futures([MAVERICKS], db or _DB(), limit=30)


async def test_the_mls_leg_linked_to_the_mavericks_leaves_their_page():
    served = _served(await _run())
    assert (MLS_WEST.id, "Dallas") not in served, served


async def test_the_same_sport_control_and_the_no_claim_market_stay():
    served = _served(await _run())
    assert served == {
        (NBA_TITLE.id, "Dallas Mavericks"),
        (NO_CLAIM.id, "Luka Doncic"),
    }, served


async def test_without_the_check_the_specimen_would_print():
    """STRAWMAN — the fixture carries the defect. With the sport claim switched
    off the FK branch trusts the link again and the MLS row comes back, so the
    first test fails for the right reason if the check is removed."""
    with patch.object(user_route, "_link_crosses_sport", lambda *_a: False):
        served = _served(await _run())
    assert (MLS_WEST.id, "Dallas") in served


async def test_a_mapped_prefix_is_not_called_wrong_sport():
    """The team side is translated, never compared raw: an F1 constructor row
    (`motorsport_f1`) linked to a `motorsports` market keeps its link, and so
    does an NRL club on a `rugby` market. A raw-prefix compare refuses both."""
    f1 = _market(900003, "F1 Constructors Champion", "motorsports",
                 [_outcome(900013, "Dallas Racing", 0.3)], tier=1)
    nrl = _market(900004, "NRL Premiership Winner", "rugby",
                  [_outcome(900014, "Dallas Rugby", 0.2)], tier=1)
    assert _served(await _run(_DB([f1], "motorsport_f1"))) == {(f1.id, "Dallas Racing")}
    assert _served(await _run(_DB([nrl], "rugbyleague_nrl"))) == {(nrl.id, "Dallas Rugby")}


async def test_the_category_vocabulary_matches_the_stored_column():
    assert _sport_key_llm_category("americanfootball_nfl") == "football"
    assert _sport_key_llm_category("icehockey_nhl") == "hockey"
    assert _sport_key_llm_category("motorsport_f1") == "motorsports"
    assert _sport_key_llm_category("rugbyunion_six_nations") == "rugby"
    assert _sport_key_llm_category("soccer_usa_mls") == "soccer"
    # Unmapped prefixes keep the raw prefix — the pre-#2593 behaviour.
    assert _sport_key_llm_category("volleyball_x") == "volleyball"
    assert _sport_key_llm_category(None) == ""


# ── The hero: `_get_championship_path` (routes/teams.py) ─────────────────────
# Production 2026-09-27: FC Cincinnati's path was "NCAAB Championship Winner"
# (market 3, the Cincinnati Bearcats leg linked to the MLS club) and Austin FC's
# "PGA Championship Winner" (market 5, golfer Austin Eckroat).

FC_CINCINNATI = 13540


def _path_market(mid, name, category, *, tier=1):
    return SimpleNamespace(
        id=mid, name=name, llm_sport_category=category, market_tier=tier,
        group_id=f"g:{mid}", canonical_market_key=None,
    )


def _path_outcome(oid, prob):
    return SimpleNamespace(
        id=oid, current_probability=prob, rank=1, probability_change_24h=None,
        team_id=FC_CINCINNATI,
    )


NCAAB = _path_market(3, "NCAAB Championship Winner", "basketball")
MLS_CUP = _path_market(128718, "MLS Cup Winner 2026", "soccer")


class _PathDB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt, *a, **k):
        return _result(self.rows)


async def _path(rows, sport_key="soccer_usa_mls"):
    return await teams_route._get_championship_path(
        FC_CINCINNATI, _PathDB(rows), league_slug=None, team_sport_key=sport_key,
    )


async def test_the_bearcats_title_odds_stop_heading_fc_cincinnati():
    path = await _path([(_path_outcome(1, 0.0052), NCAAB)])
    assert path == [], path


async def test_the_clubs_own_mls_cup_takes_the_hero_once_the_bearcats_leave():
    """Before: two tier-1 candidates (0.0052 NCAAB, 0.0075 MLS Cup) — they agree
    within the bar, so the path AVERAGED another sport into the club's number.
    After: the MLS Cup price alone."""
    path = await _path([
        (_path_outcome(1, 0.0052), NCAAB),
        (_path_outcome(2, 0.0075), MLS_CUP),
    ])
    assert [(e["market_id"], e["probability"]) for e in path] == [(MLS_CUP.id, 0.0075)]


async def test_a_caller_with_no_sport_key_keeps_the_old_path():
    """STRAWMAN for the hero: with no team sport the refusal cannot arm, and the
    Bearcats leg is the path — the defect the fixture carries."""
    path = await _path([(_path_outcome(1, 0.0052), NCAAB)], sport_key=None)
    assert [e["market_id"] for e in path] == [NCAAB.id]


async def test_a_non_sport_market_is_not_refused_by_the_path():
    other = _path_market(77, "Some Title Question", "other")
    path = await _path([(_path_outcome(3, 0.2), other)])
    assert [e["market_id"] for e in path] == [77]


def test_the_team_route_hands_its_sport_to_the_path():
    """The refusal is inert unless the route passes the team's sport key — a
    missing kwarg silently restores the old path (the strawman above)."""
    from pathlib import Path

    src = Path(teams_route.__file__).read_text()
    call = src[src.index("champ_path = await _get_championship_path("):][:200]
    assert "team_sport_key=sport_key" in call, call
