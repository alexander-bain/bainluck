"""#8072 — an NL award is never linked to an AL club, and a shared name is no answer.

WHAT A READER SAW. The Athletics' team page (``/api/teams/athletics`` →
``futures``) listed "Max Muncy — NL MVP Winner? 1%" and "NL Hank Aaron Award
Winner? 1%". Those are the Dodgers' Max Muncy's National League awards; the
Athletics are an American League club.

WHY. Both clubs carry a "Max Muncy" on ``roster_players``, and
``match_outcome_to_roster`` returned whichever roster it read first (the team
query has no ORDER BY). The market's own ticker names the half of the league
(``KXMLBNLMVP``) and nothing consulted it. Measured 2026-09-29 over the 1,179 open
Kalshi links on conference-named series: 10 sit in the other conference
(Muncy ×2 on the Athletics, Caleb Durbin ×2 on the Red Sox, Skubal's NLCS MVP
on the Tigers, Peralta's ALCS MVP on the Mets, four AFC/NFC Player of the Month
legs). Distinct-club namesakes on rosters: Max Muncy, Byron Young (Rams/Eagles),
Jaylon Jones, Marcus Harris and seven college names.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils.market_team_sport import link_crosses_conference, market_conference
from app.utils.team_linking import match_outcome_to_roster

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)


SPORTS = [(1, "baseball_mlb"), (2, "americanfootball_nfl")]

# id, sport_id, name, alternate_names, roster
DODGERS = (10707, 1, "Los Angeles Dodgers", ["Dodgers"], ["Max Muncy", "Mookie Betts", "Freddie Freeman"])
ATHLETICS = (11494, 1, "Athletics", ["A's"], ["Max Muncy", "Nick Kurtz", "Shea Langeliers"])
YANKEES = (10720, 1, "New York Yankees", ["Yankees", "New York"], ["Aaron Judge"])
METS = (10719, 1, "New York Mets", ["Mets", "New York"], ["Juan Soto"])
RAMS = (580, 2, "Los Angeles Rams", ["Rams"], ["Byron Young", "Jared Verse"])
EAGLES = (571, 2, "Philadelphia Eagles", ["Eagles"], ["Byron Young", "Jalen Hurts"])

TEAMS = [DODGERS, ATHLETICS, YANKEES, METS, RAMS, EAGLES]

# id, external_id, name, category
MARKETS = [
    (209, "KXMLBNLMVP-26", "NL MVP Winner?", "baseball"),
    (211, "KXMLBNLHAARON-26", "NL Hank Aaron Award Winner?", "baseball"),
    (212, "KXMLBALMVP-26", "AL MVP Winner?", "baseball"),
    (213, "KXMLBAL-26", "American League Champion", "baseball"),
    (214, "KXMLBAWARDFIN-26NLMVP", "National League MVP Finalists", "baseball"),
    # No conference in the ticker: the World Series MVP can be either half.
    (215, "KXMLBWSMVP-26", "Pro Baseball Championship Series MVP Winner", "baseball"),
    (216, "KXNFLDPOTY-27", "Defensive Player of the Year Winner?", "football"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 209, "Max Muncy", ATHLETICS[0]),        # NL award on an AL club -> NULL
    (2, 211, "Max Muncy", ATHLETICS[0]),        # same
    (3, 213, "New York", METS[0]),              # AL champion on the Mets -> Yankees
    (4, 214, "Max Muncy (LAD)", DODGERS[0]),    # already right: untouched
    (5, 215, "Max Muncy", ATHLETICS[0]),        # no conference claim: untouched
    # Unlinked, through Phase 2's roster step.
    (6, 209, "Max Muncy", None),                # two clubs' rosters: no answer
    (7, 212, "Nick Kurtz", None),               # one club: Athletics
    (8, 212, "Mookie Betts", None),             # Dodgers, but an AL award: refused
    (9, 216, "Byron Young", None),              # Rams and Eagles: no answer
]

EXPECTED = {
    1: None,
    2: None,
    3: YANKEES[0],
    4: DODGERS[0],
    5: ATHLETICS[0],
    6: None,
    7: ATHLETICS[0],
    8: None,
    9: None,
}


def _seed(session: Session) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a, roster in TEAMS:
        session.add(Team(
            id=i, sport_id=s, name=n, alternate_names=a,
            roster_players=[{"name": p} for p in roster],
        ))
    for mid, ext, name, category in MARKETS:
        session.add(FuturesMarket(
            id=mid, source="kalshi", external_id=ext, name=name,
            category="award", llm_sport_category=category,
            status="open", market_tier=3,
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


def test_the_ticker_names_the_conference_only_for_listed_series():
    assert market_conference("kalshi", "KXMLBNLMVP-26") == ("baseball_mlb", "National League")
    assert market_conference("kalshi", "KXMLBAL-26") == ("baseball_mlb", "American League")
    assert market_conference("kalshi", "KXMLBAWARDFIN-26NLMVP") == ("baseball_mlb", "National League")
    assert market_conference("kalshi", "KXMLBGG-26AL1B") == ("baseball_mlb", "American League")
    assert market_conference("kalshi", "KXNFLPOTM-SEP26NFCDEFENSE") == (
        "americanfootball_nfl", "National Football Conference",
    )
    assert market_conference("kalshi", "KXNFLAFCEAST-27") == (
        "americanfootball_nfl", "American Football Conference",
    )
    # No claim: a both-halves series, an unlisted series sharing the stem, a
    # non-Kalshi id, a both-halves series whose event segment names no half.
    assert market_conference("kalshi", "KXMLBWSMVP-26") is None
    assert market_conference("kalshi", "KXMLBALLSTAR-26") is None
    assert market_conference("polymarket", "KXMLBNLMVP-26") is None
    assert market_conference("kalshi", "KXMLBAWARDFIN-26MVP") is None
    # The half is the event segment's head, never "AL" inside another word.
    assert market_conference("kalshi", "KXMLBAWARDFIN-26FINALMVP") is None


def test_a_link_crosses_only_when_both_conferences_are_known_and_differ():
    assert link_crosses_conference("kalshi", "KXMLBNLMVP-26", "baseball_mlb", "Athletics")
    assert link_crosses_conference("kalshi", "KXMLBNLMVP-26", "baseball_mlb_preseason", "Athletics")
    assert not link_crosses_conference("kalshi", "KXMLBNLMVP-26", "baseball_mlb", "Los Angeles Dodgers")
    # A team of another league is #5119's check, not this one.
    assert not link_crosses_conference("kalshi", "KXMLBNLMVP-26", "americanfootball_ncaaf", "Athletics")
    # A team the static map does not place is no claim.
    assert not link_crosses_conference("kalshi", "KXMLBNLMVP-26", "baseball_mlb", "Oakland")
    assert not link_crosses_conference("kalshi", "KXMLBWSMVP-26", "baseball_mlb", "Athletics")
    assert link_crosses_conference(
        "kalshi", "KXNFLPOTM-SEP26AFCDEFENSE", "americanfootball_nfl", "Los Angeles Rams",
    )


def test_a_name_on_two_clubs_rosters_is_no_answer():
    rosters = {ATHLETICS[0]: ATHLETICS[4], DODGERS[0]: DODGERS[4]}
    assert match_outcome_to_roster("Max Muncy", rosters) is None
    # Either order: the answer never depended on which roster came first.
    assert match_outcome_to_roster("Max Muncy", dict(reversed(rosters.items()))) is None
    assert match_outcome_to_roster("Nick Kurtz", rosters) == ATHLETICS[0]
    assert match_outcome_to_roster("Mookie Betts", rosters) == DODGERS[0]


def test_two_rows_for_one_club_still_resolve_to_the_first():
    # Production's NHL/NBA twin rows ("Orlando" / "Orlando Magic") carry one roster.
    magic = ["Franz Wagner", "Paolo Banchero", "Desmond Bane", "Jalen Suggs"]
    rosters = {9001: magic, 9002: list(magic)}
    assert match_outcome_to_roster("Franz Wagner", rosters) == 9001
    # A club that shares one player with a twin pair is still a different club.
    rosters[9003] = ["Franz Wagner", "Someone Else", "Third Player", "Fourth Player"]
    assert match_outcome_to_roster("Franz Wagner", rosters) is None


def test_stored_links_in_the_other_conference_move_or_clear_and_rosters_stop_guessing():
    with Session(_make_engine()) as session:
        _seed(session)
        stats = _drain(session)
        links = _links(session)

    assert stats["errors"] == []
    assert links == EXPECTED
    assert stats["links_outside_market_conference"] == 3   # outcomes 1, 2, 3
    assert stats["outcomes_relinked_into_market_conference"] == 1
    assert stats["outcomes_unlinked_outside_market_conference"] == 2
    assert stats["outcomes_refused_outside_market_conference"] == 1   # outcome 8


def test_a_second_run_undoes_nothing_the_first_decided():
    with Session(_make_engine()) as session:
        _seed(session)
        _drain(session)
        stats = _drain(session)
        links = _links(session)

    assert links == EXPECTED
    assert stats["links_outside_market_conference"] == 0
    assert stats["outcomes_relinked_into_market_conference"] == 0
    assert stats["outcomes_unlinked_outside_market_conference"] == 0


def test_the_conference_relink_budget_is_the_runs_limit():
    with Session(_make_engine()) as session:
        _seed(session)
        stats: dict = {
            "outcomes_relinked_into_market_conference": 0,
            "outcomes_unlinked_outside_market_conference": 0,
        }
        asyncio.run(
            team_linking._relink_outside_market_conference(_AsyncShim(session), stats, 1)
        )
        links = _links(session)

    assert stats["links_outside_market_conference"] == 3
    # Lowest id first: outcome 1 clears, 2 and 3 wait for the next run.
    assert links[1] is None
    assert links[2] == ATHLETICS[0] and links[3] == METS[0]
