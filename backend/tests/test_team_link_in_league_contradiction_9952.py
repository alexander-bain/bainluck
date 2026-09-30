"""#9952 — a stored link on the wrong school inside the right league is re-decided.

WHAT A READER SAW. North Carolina's football page listed NC State's Kalshi odds
as its own — "North Carolina St." to make the College Football Playoff 9.5%, to
make the national championship 5.6% — while the NC State Wolfpack row, whose
alias is "north carolina state", carried none of them.

WHY. Phase 2 selects only ``team_id IS NULL``; Phase 3 re-decides a link outside
its market's league (#5119), 3b the other conference (#8072), 3c a surname-city
(#9726). The Tar Heels are NCAAF on an NCAAF board, so the link was permanent.
Measured 2026-09-30 over all 19,693 open Kalshi links: the #9617 matcher named a
different team on 114 legs (10 names, all NCAAF) — 53 "North Carolina St." on
UNC, 46 "Northwestern" on the Northwestern State Demons, 4 "Virginia Tech" on
Virginia, 4 "Kentucky" on Western Kentucky — and every stored link was wrong.

Rows, names and aliases are production's own (read 2026-09-30).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tests.test_team_link_fcs_league_9663 import _drain, _links
from tests.test_team_link_drain_advances_7307 import _make_engine
from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team


SPORTS = [(1, "americanfootball_ncaaf"), (2, "baseball_mlb")]

# id, sport_id, name, alternate_names
NC_STATE = (4, 1, "NC State Wolfpack", ["NC State", "north carolina state", "Wolfpack"])
UNC = (6, 1, "North Carolina Tar Heels", ["North Carolina", "Tar Heels"])
NORTHWESTERN = (40, 1, "Northwestern Wildcats", ["Northwestern", "Wildcats"])
NW_STATE = (15400, 1, "Northwestern State Demons", ["Northwestern State", "Demons"])
MIAMI = (15264, 1, "Miami Hurricanes", ["Miami", "Hurricanes"])
ANGELS = (120, 2, "Los Angeles Angels", ["Angels"])
DODGERS = (121, 2, "Los Angeles Dodgers", ["Dodgers"])

TEAMS = [NC_STATE, UNC, NORTHWESTERN, NW_STATE, MIAMI, ANGELS, DODGERS]

# id, external_id, name, llm_sport_category
MARKETS = [
    (1001, "KXNCAAFPLAYOFF-26", "NCAA Football: Team to make College Football Playoffs", "football"),
    (1002, "KXNCAAFCONFMATCHUP-ACC26", "ACC Championship matchup", "football"),
    (1003, "KXMLBAL-26", "AL pennant", "baseball"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 1001, "North Carolina St.", UNC[0]),        # -> NC State
    (2, 1001, "Northwestern", NW_STATE[0]),         # -> Northwestern Wildcats
    (3, 1001, "Northwestern St.", NORTHWESTERN[0]),  # -> Northwestern State
    (4, 1001, "North Carolina", UNC[0]),            # already right: untouched
    (5, 1002, "Miami (FL) vs North Carolina St.", UNC[0]),  # no answer: untouched
    (6, 1001, "Drake Maye", UNC[0]),                # a person: no answer, untouched
    # The matcher's answer (the Dodgers) is NL on an AL board — 3b would move it
    # straight back to an AL club, so 3d leaves the link for 3b's own reading.
    (7, 1003, "Los Angeles D", ANGELS[0]),
]


def _seed(session: Session, outcomes=OUTCOMES) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a in TEAMS:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, name, cat in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="championship", llm_sport_category=cat,
            status="open", market_tier=1,
        ))
    session.flush()
    for oid, mid, name, team_id in outcomes:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def test_the_wrong_school_in_the_right_league_moves_to_the_school_its_name_is():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert stats["units_rolled_back"] == []
    assert links[1] == NC_STATE[0]
    assert links[2] == NORTHWESTERN[0]
    assert links[3] == NW_STATE[0]
    assert stats["links_contradicted_in_league"] == 3
    assert stats["outcomes_relinked_in_league"] == 3


def test_a_link_the_matcher_agrees_with_or_cannot_read_is_never_moved_or_cleared():
    with Session(_make_engine()) as session:
        _seed(session)
        _drain(session)
        links = _links(session)

    assert links[4] == UNC[0]
    assert links[5] == UNC[0]
    assert links[6] == UNC[0]


def test_an_answer_across_the_boards_conference_is_left_for_phase_3b():
    with Session(_make_engine()) as session:
        _seed(session, [OUTCOMES[6]])
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links[7] == ANGELS[0]
    assert stats["outcomes_relinked_in_league"] == 0


def test_the_relink_is_bounded_by_the_run_limit():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session, limit=1)
        links = _links(session)

    assert stats["links_contradicted_in_league"] == 3
    assert stats["outcomes_relinked_in_league"] == 1
    assert links[1] == NC_STATE[0]  # lowest id first
    assert links[2] == NW_STATE[0]
