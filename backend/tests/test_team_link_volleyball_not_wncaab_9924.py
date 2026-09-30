"""#9924 — Kalshi's women's volleyball boards are not women's basketball.

WHAT A READER SAW. Nebraska's women's basketball page led its futures and its
Championship path with "Division I Women's Volleyball Champion" (40.5%), and the
same board sat on Pittsburgh, Wisconsin, Louisville and 22 more WNCAAB pages.

WHY. ``KALSHI_FUTURES_TICKER_TO_SPORT_KEY["kxncaaw"]`` is women's basketball,
and women's basketball has its own explicit ``kxncaawb…`` entries, so the bare
stem answers only for KXNCAAWV (champion) and KXNCAAWVMATCH (match markets). The
league check (#5119) compared WNCAAB with WNCAAB and refused nothing. Measured
2026-09-30: 26 of KXNCAAWV-26's 49 open legs linked, all on WNCAAB rows, plus 7
of 8 open match legs ("Notre Dame vs Louisville" names no gender, so #9593's
check could not see it either).

The rows are production's own shapes (``futures_markets``/``teams`` read
2026-09-30).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.utils.market_team_sport import link_crosses_league, market_league_sport_key

from tests.test_team_link_fcs_league_9663 import _drain, _links
from tests.test_team_link_drain_advances_7307 import _make_engine
from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team


SPORTS = [(3, "basketball_wncaab"), (4, "basketball_ncaab")]

# id, sport_id, name, alternate_names
NEBRASKA = (151, 3, "Nebraska Cornhuskers", ["Nebraska", "Cornhuskers"])
PITT = (2833, 3, "Pittsburgh Panthers", ["Pitt", "Panthers"])
LOUISVILLE = (73, 3, "Louisville Cardinals", ["Louisville", "Cardinals"])
NOTRE_DAME = (2840, 3, "Notre Dame Fighting Irish", ["Notre Dame", "Fighting Irish"])
UCONN = (90, 3, "UConn Huskies", ["UConn", "Huskies"])

TEAMS = [NEBRASKA, PITT, LOUISVILLE, NOTRE_DAME, UCONN]

# id, external_id, name
MARKETS = [
    (60775180, "KXNCAAWV-26", "Division I Women's Volleyball Champion"),
    (63153011, "KXNCAAWVMATCH-26SEP301900NDLOU", "Notre Dame vs Louisville"),
    (60000001, "KXNCAAWB-26", "College Basketball (W) Champion"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 60775180, "Nebraska", NEBRASKA[0]),        # -> NULL
    (2, 60775180, "Pittsburgh", PITT[0]),          # -> NULL
    (3, 60775180, "Wisconsin", None),              # stays NULL
    (4, 63153011, "Louisville", LOUISVILLE[0]),    # -> NULL
    (5, 63153011, "Notre Dame", None),             # never binds
    (6, 60000001, "UConn", UCONN[0]),              # the basketball board: untouched
]

EXPECTED = {1: None, 2: None, 3: None, 4: None, 5: None, 6: UCONN[0]}


def _seed(session: Session, outcomes=OUTCOMES) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a in TEAMS:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, name in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="championship", llm_sport_category="basketball",
            status="open", market_tier=1,
        ))
    session.flush()
    for oid, mid, name, team_id in outcomes:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def test_the_volleyball_series_name_their_own_league_and_basketball_stays_basketball():
    assert market_league_sport_key("kalshi", "KXNCAAWV-26") == "volleyball_ncaaw"
    assert market_league_sport_key("kalshi", "KXNCAAWVMATCH-26SEP301900NDLOU") == (
        "volleyball_ncaaw"
    )
    # Women's basketball's own series keep their league.
    assert market_league_sport_key("kalshi", "KXNCAAWB-26") == "basketball_wncaab"
    assert market_league_sport_key("kalshi", "KXNCAAWBGAME-26NOV04UCONNLOU") == (
        "basketball_wncaab"
    )
    # The team page's refusals (routes/teams.py, routes/user.py) read the same answer.
    for ticker in ("KXNCAAWV-26", "KXNCAAWVMATCH-26SEP301900NDLOU"):
        assert link_crosses_league("kalshi", ticker, "basketball_wncaab")
        assert link_crosses_league("kalshi", ticker, "basketball_ncaab")
    assert not link_crosses_league("kalshi", "KXNCAAWB-26", "basketball_wncaab")


def test_volleyball_legs_leave_every_basketball_page_and_never_rebind():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == EXPECTED
    assert stats["links_outside_market_league"] == 3  # outcomes 1, 2, 4
    assert stats["outcomes_unlinked_outside_market_league"] == 3
    assert stats["outcomes_relinked_into_market_league"] == 0


def test_phase_2_refuses_an_unlinked_volleyball_leg_by_name():
    # "Nebraska" is Nebraska Cornhuskers by exact alias in the category; the
    # league check is what refuses it.
    outcomes = [(1, 60775180, "Nebraska", None), (4, 63153011, "Louisville", None)]
    with Session(_make_engine()) as session:
        _seed(session, outcomes)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == {1: None, 4: None}
    assert stats["outcomes_refused_outside_market_league"] >= 2
