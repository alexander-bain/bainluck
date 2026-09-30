"""#5119 — a Kalshi outcome is never linked outside the league its ticker names.

WHAT A READER SAW. ``/teams/buffalo-bills`` carried Polymarket's and the Odds
API's Super Bowl, AFC and playoff prices and not one of Kalshi's; the Houston
Texans' page the same. The NFL odds-movement chart drew Buffalo twice ("Buffalo
Bills 11.8%", "Buffalo 11.5%") because Kalshi's leg sat on a different team row.

WHY. City-name matching across the whole football category put Kalshi's
"Buffalo" (KXSB-27) on the Buffalo Bulls and "Houston" on the Houston Cougars —
college teams. Phase 2 of ``_backfill_team_links`` only selects
``team_id IS NULL``, so a wrong link was permanent. Measured 2026-09-29: 520 open
Kalshi outcomes linked outside their ticker's league; 173 have a unique answer
inside it (Buffalo→Bills on 28 markets, Houston→Texans, Miami→Dolphins,
Carolina→Panthers, Arizona→Cardinals, MLS clubs off NBA rows, NCAA men's legs
off women's rows), the rest have none (a rookie-award leg on the player's
college, "Tennessee: 2+ wins in first 12 weeks" on the Volunteers).

The team rows are production's own shapes (``teams`` read 2026-09-29).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)


SPORTS = [
    (1, "americanfootball_nfl"),
    (2, "americanfootball_ncaaf"),
    (3, "basketball_nba"),
    (4, "soccer_usa_mls"),
    (5, "soccer_epl"),
]

# id, sport_id, name, alternate_names[, roster]
BILLS = (538, 1, "Buffalo Bills", ["Bills"])
TEXANS = (563, 1, "Houston Texans", ["Texans"])
TITANS = (570, 1, "Tennessee Titans", ["Titans"])
CHIEFS = (560, 1, "Kansas City Chiefs", ["Chiefs", "Kansas City"])
BULLS_CFB = (17120, 2, "Buffalo Bulls", ["Buffalo", "Bulls"], ["Josh Allen"])
COUGARS = (14126, 2, "Houston Cougars", ["Houston", "Cougars"])
VOLS = (15937, 2, "Tennessee Volunteers", ["Tennessee", "Volunteers", "vols"])
CHICAGO_NBA = (4, 3, "Chicago Bulls", ["Chicago", "Bulls"])
CHICAGO_FIRE = (9101, 4, "Chicago Fire", ["Fire"])
ARSENAL = (7001, 5, "Arsenal", ["Arsenal FC"])
NOTRE_DAME = (15300, 2, "Notre Dame Fighting Irish", ["Notre Dame"], ["Jeremiyah Love"])

TEAMS = [
    BILLS, TEXANS, TITANS, CHIEFS, BULLS_CFB, COUGARS, VOLS,
    CHICAGO_NBA, CHICAGO_FIRE, ARSENAL, NOTRE_DAME,
]

# id, source, external_id, name, category, status
MARKETS = [
    (40533, "kalshi", "KXSB-27", "2027 Pro Football Champion", "football", "open"),
    (62679, "kalshi", "KXNFLWINSWEEK-26", "Pro Football wins by week", "football", "open"),
    (383313, "kalshi", "KXMLSEAST-26", "MLS Eastern Conference Champion", "basketball", "open"),
    # A Champions League leg on an EPL club: soccer is not a one-league sport.
    (50001, "kalshi", "KXUCL-26", "Champions League Winner", "soccer", "open"),
    # Polymarket's id is no league claim.
    (129037, "polymarket", "202857", "Pro Football: 2027 Champion", "football", "open"),
    # Settled markets are outside this pass.
    (40000, "kalshi", "KXSB-26", "2026 Pro Football Champion", "football", "closed"),
    # The repair pass reads Kalshi only (the population measured); the Odds API
    # names clubs in full and was not.
    (86832, "odds_api", "americanfootball_nfl_super_bowl_winner", "NFL Super Bowl Winner", "football", "open"),
    (70001, "kalshi", "KXNFLOROTY-26", "Offensive Rookie of the Year", "football", "open"),
    # An NFL game market whose event carries college team rows: Phase 2a's roster path.
    (70002, "kalshi", "KXNFLGAME-26OCT04BUFHOU", "Buffalo at Houston", "football", "open"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 40533, "Buffalo", BULLS_CFB[0]),          # -> Bills
    (2, 40533, "Houston", COUGARS[0]),            # -> Texans
    (3, 40533, "Kansas City", CHIEFS[0]),         # already right: untouched
    (4, 62679, "Tennessee: 2+ wins in first 12 weeks", VOLS[0]),  # no NFL answer -> NULL
    (5, 383313, "Chicago", CHICAGO_NBA[0]),       # -> Chicago Fire
    (6, 50001, "Arsenal", ARSENAL[0]),            # soccer: untouched
    (7, 129037, "Buffalo", BULLS_CFB[0]),         # no venue league: untouched
    (8, 40000, "Buffalo", BULLS_CFB[0]),          # closed market: untouched
    # Unlinked: Phase 2's league check refuses the category matcher's college hit.
    (9, 62679, "Tennessee: 3+ wins in first 8 weeks", None),
    (10, 70001, "Jeremiyah Love", None),          # college roster hit: refused
    (11, 70002, "Josh Allen", None),              # event roster hit (2a), then 2b: refused
    (12, 86832, "Buffalo", BULLS_CFB[0]),         # Odds API: untouched by the repair
]


def _seed(session: Session) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a, *roster in TEAMS:
        session.add(Team(
            id=i, sport_id=s, name=n, alternate_names=a,
            roster_players=[{"name": p} for p in roster[0]] if roster else None,
        ))
    session.add(Event(
        id=900, sport_id=1, home_team_name="Houston Texans", away_team_name="Buffalo Bills",
        home_team_id=COUGARS[0], away_team_id=BULLS_CFB[0],
        commence_time=datetime(2026, 10, 4, 17, tzinfo=timezone.utc),
    ))
    for mid, source, ext, name, category, status in MARKETS:
        session.add(FuturesMarket(
            id=mid, source=source, external_id=ext, name=name,
            category="championship", llm_sport_category=category,
            status=status, market_tier=1, event_id=900 if mid == 70002 else None,
        ))
    session.flush()
    for oid, mid, name, team_id in OUTCOMES:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def _drain(session: Session) -> dict:
    @asynccontextmanager
    async def _fake_task_session():
        yield _AsyncShim(session)

    async def _run():
        import unittest.mock as mock

        with mock.patch.object(team_linking, "get_task_session", _fake_task_session), \
                mock.patch.object(team_linking, "_cursor_store", _FakeCursorStore):
            return await team_linking._backfill_team_links(limit=100, use_llm=False)

    return asyncio.run(_run())


def _links(session: Session) -> dict:
    session.flush()
    return dict(session.execute(select(FuturesOutcome.id, FuturesOutcome.team_id)).all())


EXPECTED = {
    1: BILLS[0],
    2: TEXANS[0],
    3: CHIEFS[0],
    4: None,
    5: CHICAGO_FIRE[0],
    6: ARSENAL[0],
    7: BULLS_CFB[0],
    8: BULLS_CFB[0],
    9: None,
    10: None,
    11: None,
    12: BULLS_CFB[0],
}


def test_stored_links_outside_the_ticker_league_move_inside_it_or_clear():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == EXPECTED
    assert stats["links_outside_market_league"] == 4  # outcomes 1, 2, 4, 5
    assert stats["outcomes_relinked_into_market_league"] == 3
    assert stats["outcomes_unlinked_outside_market_league"] == 1


def test_the_category_matcher_cannot_link_an_unlinked_outcome_outside_its_league():
    # Outcome 9: the football-wide name match answers the Volunteers.
    from app.utils.team_linking import match_outcome_to_team

    football = [
        {"id": t[0], "name": t[2], "alternate_names": t[3], "sport_key": dict(SPORTS)[t[1]]}
        for t in TEAMS if t[1] in (1, 2)
    ]
    assert match_outcome_to_team(OUTCOMES[8][2], football) == VOLS[0]

    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert links[9] is None
    assert links[10] is None   # Notre Dame's roster answered; NFL award
    assert links[11] is None   # the event's college rows answered; NFL game
    # 9 by name, 10 by the category roster, 11 by the event roster then the category roster.
    assert stats["outcomes_refused_outside_market_league"] == 4


def test_a_second_run_undoes_nothing_the_first_decided():
    # An unlinked outcome re-enters Phase 2; its league check must refuse the
    # college team the repair just took it off, or the two passes flip-flop hourly.
    with Session(_make_engine()) as session:
        _seed(session)
        _drain(session)
        stats = _drain(session)
        links = _links(session)

    assert links == EXPECTED
    # The first run wrapped its cursor, so this one re-reads 4, 9, 10 and 11.
    assert stats["outcomes_refused_outside_market_league"] == 5
    assert stats["links_outside_market_league"] == 0
    assert stats["outcomes_relinked_into_market_league"] == 0
    assert stats["outcomes_unlinked_outside_market_league"] == 0


def test_the_relink_budget_is_the_runs_limit():
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        stats: dict = {
            "outcomes_relinked_into_market_league": 0,
            "outcomes_unlinked_outside_market_league": 0,
        }
        asyncio.run(team_linking._relink_outside_market_league(_AsyncShim(session), stats, 2))
        session.flush()
        links = _links(session)

    assert stats["links_outside_market_league"] == 4
    # Lowest ids first: outcomes 1 and 2 move, 4 and 5 wait for the next run.
    assert links[1] == BILLS[0] and links[2] == TEXANS[0]
    assert links[4] == VOLS[0] and links[5] == CHICAGO_NBA[0]
