"""#9663 — Kalshi's FCS title board is the FCS league, not FBS.

WHAT A READER SAW. The South Carolina Gamecocks' and San Diego State's football
pages carried a 0.5-1% "Championship" step and the Washington Huskies' hero read
0.6%, all from Kalshi's FCS national title board (KXNCAAFFCS-27). None of those
schools play FCS.

WHY. The ticker maps are prefix maps, so ``KXNCAAFFCS`` resolves through
``kxncaaf`` to ``americanfootball_ncaaf``. The league check (#5119) compared FBS
with FBS and refused nothing, while every FCS row was refused as the other
league. Measured 2026-09-29: 68 of the board's 128 legs linked, all 68 on FBS
rows, and none of the 60 unlinked could ever bind. Replayed with the board read
as FCS: 49 of the 68 move to their FCS school (13 of them were on the wrong
school), 19 clear, and 41 of the 60 unlinked gain one.

The team rows are production's own shapes (``teams`` read 2026-09-29).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils.market_team_sport import link_crosses_league, market_league_sport_key

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)


SPORTS = [(2, "americanfootball_ncaaf"), (6, "americanfootball_ncaaf_fcs")]

# id, sport_id, name, alternate_names
GAMECOCKS = (15295, 2, "South Carolina Gamecocks", ["Gamecocks", "South Carolina"])
HUSKIES = (15301, 2, "Washington Huskies", ["Huskies", "Washington"])
AZTECS = (19767, 2, "San Diego State Aztecs", ["Aztecs", "San Diego St"])
VILLANOVA = (18622, 6, "Villanova Wildcats", ["Wildcats", "Villanova"])
EAGLES = (18623, 6, "Eastern Washington Eagles", ["Eagles", "E Washington"])
TOREROS = (18984, 6, "San Diego Toreros", ["Toreros", "San Diego"])
SC_STATE = (19781, 6, "South Carolina State Bulldogs", None)

TEAMS = [GAMECOCKS, HUSKIES, AZTECS, VILLANOVA, EAGLES, TOREROS, SC_STATE]

# id, external_id, name
MARKETS = [
    (500001, "KXNCAAFFCS-27", "College Football FCS Championship"),
    (500002, "KXNCAAF-27", "College Football Championship"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 500001, "San Diego", AZTECS[0]),              # -> Toreros
    (2, 500001, "Eastern Washington", HUSKIES[0]),    # -> Eagles
    (3, 500001, "South Carolina St.", GAMECOCKS[0]),  # no unique FCS answer -> NULL
    (4, 500001, "Villanova", None),                   # -> Villanova (was refused as FCS)
    (5, 500002, "Washington", HUSKIES[0]),            # FBS board: untouched
    (6, 500002, "San Diego St.", AZTECS[0]),          # FBS board: untouched
]

EXPECTED = {
    1: TOREROS[0],
    2: EAGLES[0],
    3: None,
    4: VILLANOVA[0],
    5: HUSKIES[0],
    6: AZTECS[0],
}


def _seed(session: Session, outcomes=OUTCOMES) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a in TEAMS:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, name in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="championship", llm_sport_category="football",
            status="open", market_tier=1,
        ))
    session.flush()
    for oid, mid, name, team_id in outcomes:
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


def test_the_fcs_board_names_the_fcs_league_and_only_that_series_does():
    assert market_league_sport_key("kalshi", "KXNCAAFFCS-27") == "americanfootball_ncaaf_fcs"
    # Series that merely share the stem stay FBS.
    assert market_league_sport_key("kalshi", "KXNCAAF-27") == "americanfootball_ncaaf"
    assert market_league_sport_key("kalshi", "KXNCAAFFINALIST-27") == "americanfootball_ncaaf"
    assert market_league_sport_key("kalshi", "KXNCAAFFIRSTTDTEAM-26NOV01") == (
        "americanfootball_ncaaf"
    )
    # The team page's own refusal (routes/teams.py) reads the same answer.
    assert link_crosses_league("kalshi", "KXNCAAFFCS-27", "americanfootball_ncaaf")
    assert not link_crosses_league("kalshi", "KXNCAAFFCS-27", "americanfootball_ncaaf_fcs")
    assert not link_crosses_league("kalshi", "KXNCAAF-27", "americanfootball_ncaaf")


def test_fcs_legs_on_fbs_schools_move_to_their_fcs_school_or_clear():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == EXPECTED
    assert stats["links_outside_market_league"] == 3  # outcomes 1, 2, 3
    assert stats["outcomes_relinked_into_market_league"] == 2
    assert stats["outcomes_unlinked_outside_market_league"] == 1


def test_step_0_binds_an_unlinked_fcs_leg_inside_fcs_not_fbs():
    # Read off the bare ticker map the board is FBS, where "San Diego" is San
    # Diego State by city (its name minus "State Aztecs"). Phase 3 would then
    # clear that link on the next run, and Step 0 would write it again.
    outcomes = [(1, 500001, "San Diego", None)]
    with Session(_make_engine()) as session:
        _seed(session, outcomes)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == {1: TOREROS[0]}
    assert stats["outcomes_linked_by_league"] == 1
    assert stats["links_outside_market_league"] == 0
