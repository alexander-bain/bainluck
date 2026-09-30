"""#9761 — Kalshi's NFL player and team series name the NFL, so a pro leg leaves the college.

WHAT A READER SAW. The LSU Tigers' football page listed "Garrett Nussmeier — Top
Fantasy Rookie QB 3%" and "Zavion Thomas — Top Fantasy Rookie WR 1%" under Season
futures (2026-09-30). Those are NFL questions about players who left LSU.

WHY. ``KXNFLFFLEADER`` is in neither ticker map nor ``_SERIES_LEAGUE_SUPPLEMENT``,
so ``market_league_sport_key`` answered None, and a series with no league is no
claim: the league checks (#5119 Phase 3, #9617 Step 0, the bind-site refusal)
never saw the NFL and the player's name reached his college roster. Measured on
production 2026-09-30: 76 open NFL series had no league and 365 open legs on them
sat outside the NFL (336 on college football teams). Replayed through the NFL
league matcher, 94 move to their NFL club ("Buffalo" → Bills, not Bulls) and 271
clear (players, "Baltimore vs Minnesota").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.utils import market_team_sport as mts
from app.utils.market_team_sport import link_crosses_league, market_league_sport_key

from tests.test_team_link_drain_advances_7307 import _make_engine
from tests.test_team_link_fcs_league_9663 import _drain, _links


SPORTS = [(1, "americanfootball_nfl"), (2, "americanfootball_ncaaf")]

# id, sport_id, name, alternate_names, roster
LSU = (9, 2, "LSU Tigers", ["LSU", "Tigers"],
       [{"name": "Garrett Nussmeier"}, {"name": "Zavion Thomas"}])  # last season's roster
BULLS = (400, 2, "Buffalo Bulls", ["Bulls", "Buffalo"], None)
BILLS = (401, 1, "Buffalo Bills", ["Bills", "Buffalo"], None)
CHIEFS = (402, 1, "Kansas City Chiefs", ["Chiefs", "Kansas City"], None)

# id, external_id, name
MARKETS = [
    (1, "KXNFLFFLEADER-27ROOKQB", "Top Fantasy Rookie QB"),
    (2, "KXNFLFFLEADER-27ROOKWR", "Top Fantasy Rookie WR"),
    (3, "KXNFLTEAMPTS-26", "Pro Football Highest Scoring Team"),
    (4, "KXNCAAFLEADER-26RSHYDS", "Division I: Rushing Yards Leader"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 1, "Garrett Nussmeier", LSU[0]),   # production's link -> NULL, stays NULL
    (2, 2, "Zavion Thomas", None),         # unlinked: the LSU roster must not take it
    (3, 3, "Buffalo", BULLS[0]),           # -> the Bills
    (4, 4, "Garrett Nussmeier", LSU[0]),   # a college board: the college link stands
]


def _seed(session: Session) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for tid, sid, name, aliases, roster in (LSU, BULLS, BILLS, CHIEFS):
        session.add(Team(id=tid, sport_id=sid, name=name, alternate_names=aliases,
                         roster_players=roster))
    for mid, ext, name in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="championship", llm_sport_category="football",
            status="open", market_tier=5,
        ))
    session.flush()
    for oid, mid, name, team_id in OUTCOMES:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def test_the_nfl_series_name_the_nfl():
    for ticker in (
        "KXNFLFFLEADER-27ROOKQB", "KXNFLFFLEADERTOP-27QB", "KXNFLMATCHUP-27AFC",
        "KXNFLWEEKHIGHSCORE-26WK10", "KXNFLNEXTTEAM-26BMAY", "KXNFLSEASONRSHTD-26",
        "KXRANKLISTFFDST-27",
    ):
        assert market_league_sport_key("kalshi", ticker) == "americanfootball_nfl", ticker
    # The team page's own refusal reads the same answer.
    assert link_crosses_league("kalshi", "KXNFLFFLEADER-27ROOKQB", "americanfootball_ncaaf")
    assert not link_crosses_league("kalshi", "KXNFLFFLEADER-27ROOKQB", "americanfootball_nfl")


def test_the_netflix_series_that_share_the_stem_name_no_league():
    for ticker in ("KXNFLXA-26", "KXNFLXAPP-26SEP", "KXNFLXINCREASE-26"):
        assert market_league_sport_key("kalshi", ticker) is None, ticker
    assert "kxnflx" not in mts._SERIES_LEAGUE_SUPPLEMENT


def test_every_listed_series_is_lower_case_and_listed_once():
    series = mts._NFL_SUPPLEMENT_SERIES
    assert len(series) == len(set(series))
    assert all(s == s.lower() and s.startswith("kx") for s in series)


def test_a_pro_leg_leaves_the_college_and_the_old_roster_cannot_take_it_back():
    with Session(_make_engine()) as session:
        _seed(session)
        first = _drain(session)
        after_first = _links(session)
        # The NULL re-enters Phase 2 on the next run, where LSU's stale roster
        # still lists him; the league check must refuse it.
        second = _drain(session)
        after_second = _links(session)

    assert first["errors"] == [] and second["errors"] == []
    expected = {1: None, 2: None, 3: BILLS[0], 4: LSU[0]}
    assert after_first == expected
    assert after_second == expected
    assert first["links_outside_market_league"] == 2  # outcomes 1 and 3
    assert first["outcomes_relinked_into_market_league"] == 1
    assert first["outcomes_unlinked_outside_market_league"] == 1
    assert second["links_outside_market_league"] == 0
