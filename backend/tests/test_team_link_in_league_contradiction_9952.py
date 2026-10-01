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


# ── Polymarket (#9952 after-check, 2026-10-01) ───────────────────────────────
# With the Kalshi legs moved, UNC's page still printed NC State's playoff, title,
# quarter, semi and top-4-seed odds: five Polymarket "North Carolina St." legs
# (slug ``ncaa-football-…``, which names no league) sat on team 6. Replay over all
# 5,695 open Polymarket links: 7 contradictions, every one the wrong school.

NFL = (3, "americanfootball_nfl")
COMMANDERS = (300, 3, "Washington Commanders", ["Washington", "Commanders"])

# id, external_id, event slug
PM_MARKETS = [
    (2001, "948140", "ncaa-football-team-to-make-college-football-playoffs-20260803190433067"),
    # A pro-football- slug names the NFL: a college team under it is Phase 3's row.
    (2002, "777001", "pro-football-2026-27-nfc-champion"),
]

PM_OUTCOMES = [
    (11, 2001, "North Carolina St.", UNC[0]),   # -> NC State
    (12, 2001, "North Carolina", UNC[0]),       # already right: untouched
    (13, 2001, "North Carolina 4.5+", UNC[0]),  # no answer: untouched
    (14, 2002, "Northwestern", NW_STATE[0]),    # crosses the league: not 3d's
]


def _seed_polymarket(session: Session, outcomes=PM_OUTCOMES) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS + [NFL]])
    for i, s, n, a in TEAMS + [COMMANDERS]:
        session.add(Team(id=i, sport_id=s, name=n, alternate_names=a))
    for mid, ext, slug in PM_MARKETS:
        session.add(FuturesMarket(
            id=mid, source="polymarket", external_id=ext, name=slug,
            category="championship", llm_sport_category="football",
            status="open", market_tier=1,
            market_metadata={"polymarket_event_slug": slug},
        ))
    session.flush()
    for oid, mid, name, team_id in outcomes:
        session.add(FuturesOutcome(
            id=oid, market_id=mid, external_id=f"o{oid}", name=name, team_id=team_id,
        ))
    session.commit()


def test_a_polymarket_leg_on_the_wrong_school_moves_to_the_school_its_name_is():
    with Session(_make_engine()) as session:
        _seed_polymarket(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert stats["units_rolled_back"] == []
    assert links[11] == NC_STATE[0]
    assert links[12] == UNC[0]
    assert links[13] == UNC[0]
    assert stats["links_contradicted_in_league"] == 1
    assert stats["outcomes_relinked_in_league"] == 1


def test_a_polymarket_board_whose_slug_names_another_league_is_left_to_phase_3():
    with Session(_make_engine()) as session:
        _seed_polymarket(session)
        stats = _drain(session)
        links = _links(session)

    # Phase 3 reads the pro-football- slug and finds no NFL "Northwestern": it
    # clears the link. 3d never counted it as an in-league contradiction.
    assert links[14] is None
    assert stats["links_contradicted_in_league"] == 1


def test_the_slug_keeps_a_crossing_polymarket_leg_out_of_3d_when_phase_3_has_not_reached_it():
    # limit=1: Phase 3 clears only its lowest crossing id (14); 15 is still
    # crossing when 3d reads. Without the slug 3d would see an NCAAF board and
    # move 15 to the Northwestern Wildcats.
    outcomes = PM_OUTCOMES + [(15, 2002, "Northwestern", NW_STATE[0])]
    with Session(_make_engine()) as session:
        _seed_polymarket(session, outcomes)
        stats = _drain(session, limit=1)
        links = _links(session)

    assert stats["errors"] == []
    assert links[14] is None
    assert links[15] == NW_STATE[0]
    assert stats["links_contradicted_in_league"] == 1
