"""#9726 — a player's surname is not a college's city alias.

WHAT A READER SAW. The Washington Huskies' football page listed, under Season
futures, NFL and fantasy props for Parker Washington (Jaguars), Darnell
Washington (Steelers), Mike Washington Jr. and Malik Washington. None of them
play for the Huskies.

WHY. The Huskies carry the alias "Washington". ``_names_match``'s substring arm
found "washington" inside "parker washington", no other club carries that bare
alias, so Step 1 bound it before the roster step (which knows Darnell is a
Steeler) ever ran. Measured 2026-09-30 over the open two-word links ending in a
team alias of 8+ characters: 71 of 487 rest only on that shape (40 on the
Huskies; Campbell, Marshall, the Wizards, the Nationals, "Georgia Southern" on
Southern University, "West Virginia" on Virginia). The other 416 keep their team.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils import team_linking as linking
from app.utils.team_linking import _names_match, given_name_before_city, match_outcome_to_team

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)


FIXTURE = Path(__file__).parent / "fixtures" / "team_link_given_name_city_9726.json"

# id, sport_id, name, alternate_names, roster
HUSKIES = (15301, 1, "Washington Huskies", ["Washington", "Huskies"], ["Jordan Washington"])
CAMELS = (16001, 1, "Campbell Fighting Camels", ["Campbell", "Fighting Camels"], [])
SOUTHERN = (16002, 1, "Southern University Jaguars", ["Southern", "Jaguars"], [])
CHARLOTTE = (16003, 1, "Charlotte 49ers", ["Charlotte", "49ers"], [])
SOONERS = (16004, 1, "Oklahoma Sooners", ["Oklahoma", "Sooners"], [])
STEELERS = (540, 2, "Pittsburgh Steelers", ["Steelers", "Pittsburgh"], ["Darnell Washington"])
JAGUARS = (564, 2, "Jacksonville Jaguars", ["Jacksonville"], ["Parker Washington"])
ATHLETICS = (11494, 3, "Athletics", ["Athletics", "A's"], [])

TEAMS = [HUSKIES, CAMELS, SOUTHERN, CHARLOTTE, SOONERS, STEELERS, JAGUARS, ATHLETICS]
SPORTS = [(1, "americanfootball_ncaaf"), (2, "americanfootball_nfl"), (3, "baseball_mlb")]


def _dicts(teams=TEAMS) -> list[dict]:
    return [
        {"id": i, "name": n, "alternate_names": a, "sport_key": dict(SPORTS)[s]}
        for i, s, n, a, _ in teams
    ]


# --- the rule -----------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Parker Washington",
        "Mike Washington Jr.",
        "Malik Washington",
        "Darnell Washington",
        "A'Mauri Washington",
        "P.J. Washington",
        "Matt Campbell",
        "Georgia Southern",
        "Eastern Washington",
    ],
)
def test_a_given_name_before_a_city_alias_binds_to_no_club(name):
    assert match_outcome_to_team(name, _dicts()) is None


@pytest.mark.parametrize(
    "name, team",
    [
        ("Washington", HUSKIES),               # the alias itself, exact
        ("Washington Huskies", HUSKIES),       # the whole name
        ("UNC Charlotte", CHARLOTTE),          # an abbreviation is not a given name
        ("PIT Steelers D/ST", STEELERS),       # a nickname alias, not a city
        ("Oakland Athletics", ATHLETICS),      # the name is all alias: no city to guard
        ("Norman, Oklahoma", SOONERS),         # a place, comma-separated
        ("Washington 8.5+", HUSKIES),          # the city leads
    ],
)
def test_names_that_still_name_their_club(name, team):
    assert match_outcome_to_team(name, _dicts([team])) == team[0]


def test_only_a_city_prefix_of_the_teams_own_name_is_guarded():
    assert given_name_before_city("Parker Washington", "Washington", "Washington Huskies")
    assert given_name_before_city("Mike Washington Jr.", "Washington", "Washington Huskies")
    # Nickname alias, alias that is the whole name, two words in front, all-caps.
    assert not given_name_before_city("Arizona Steelers", "Steelers", "Pittsburgh Steelers")
    assert not given_name_before_city("Oakland Athletics", "Athletics", "Athletics")
    assert not given_name_before_city("Jo Ann Washington", "Washington", "Washington Huskies")
    assert not given_name_before_city("UNC Charlotte", "Charlotte", "Charlotte 49ers")


def test_production_links_only_the_given_name_shape_loses():
    rows = json.loads(FIXTURE.read_text())["rows"]
    lost = sorted(
        (r["name"], r["team"])
        for r in rows
        if not _names_match(r["name"], r["team"], r["alternate_names"])
    )
    assert len(rows) == 487
    assert len(lost) == 71
    # Every lost link, read by hand: a person or another school, never the club.
    assert {pair for pair in lost} == {
        ("A'Mauri Washington", "Washington Huskies"),
        ("Amare Campbell", "Campbell Fighting Camels"),
        ("Ben Campbell", "Campbell Fighting Camels"),
        ("Brian Campbell", "Campbell Fighting Camels"),
        ("Chris Marshall", "Marshall Thundering Herd"),
        ("Dan Campbell", "Campbell Fighting Camels"),
        ("Darnell Washington", "Washington Huskies"),
        ("Denzel Washington", "Washington Wizards"),
        ("Eastern Washington", "Washington Huskies"),
        ("Ernest Campbell", "Campbell Fighting Camels"),
        ("Georgia Southern", "Southern University Jaguars"),
        ("Jack Campbell", "Campbell Fighting Camels"),
        ("Jordan Marshall", "Marshall Thundering Herd"),
        ("Jordan Washington", "Washington Huskies"),
        ("Malik Washington", "Washington Huskies"),
        ("Matt Campbell", "Campbell Fighting Camels"),
        ("Mike Washington Jr.", "Washington Huskies"),
        ("P.J. Washington", "Washington Wizards"),
        ("Parker Washington", "Washington Huskies"),
        ("Ron Washington", "Washington Nationals"),
        ("West Virginia", "Virginia Cavaliers"),
        ("Will Campbell", "Campbell Fighting Camels"),
    }


# --- Phase 3c: the links already written --------------------------------------

# id, external_id, name, category
MARKETS = [
    (301, "KXNFLSEASONREC-27C75", "Pro Football: 75+ Receptions Season", "football"),
    (302, "KXNCAAFBIGTENLEADER-26PASSTD", "Big Ten: Passing Touchdowns Leader", "football"),
    (303, "KXRANKLISTFFDST-27", "Fantasy Football: 2026-27 Season Top D/ST", "football"),
]

# id, market_id, name, stored team_id
OUTCOMES = [
    (1, 301, "Parker Washington", HUSKIES[0]),    # cleared, then the roster: Jaguars
    (2, 301, "Darnell Washington", HUSKIES[0]),   # cleared, then the roster: Steelers
    (3, 302, "Malik Washington", HUSKIES[0]),     # cleared, no roster answer: NULL
    (4, 302, "Jordan Washington", HUSKIES[0]),    # the Huskies' own roster: kept
    (5, 303, "Washington D/ST", HUSKIES[0]),      # the Commanders' fantasy defense: cleared, NULL
    (6, 301, "Darnell Washington", STEELERS[0]),  # already right: kept
    (7, 302, "Matt Campbell", None),              # unlinked: Step 1 no longer binds it
]

EXPECTED = {
    1: JAGUARS[0],
    2: STEELERS[0],
    3: None,
    4: HUSKIES[0],
    5: None,
    6: STEELERS[0],
    7: None,
}


def _seed(session: Session) -> None:
    session.add_all([Sport(id=i, key=k, name=k, active=True) for i, k in SPORTS])
    for i, s, n, a, roster in TEAMS:
        session.add(Team(
            id=i, sport_id=s, name=n, alternate_names=a,
            roster_players=[{"name": p} for p in roster] or None,
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


def test_stored_surname_links_clear_and_the_roster_takes_over():
    with Session(_make_engine()) as session:
        _seed(session)
        first = _drain(session)
        second = _drain(session)
        links = _links(session)

    assert first["errors"] == [] and second["errors"] == []
    assert first["links_on_given_name_city_alias"] == 4        # outcomes 1, 2, 3, 5
    assert first["outcomes_unlinked_given_name_city_alias"] == 4
    assert links == EXPECTED
    # A second run finds nothing left to clear and undoes nothing.
    assert second["links_on_given_name_city_alias"] == 0


def test_the_unlink_budget_is_the_runs_limit():
    with Session(_make_engine()) as session:
        _seed(session)
        stats: dict = {"outcomes_unlinked_given_name_city_alias": 0}
        asyncio.run(team_linking._unlink_given_name_city_alias(_AsyncShim(session), stats, 1))
        links = _links(session)

    assert stats["links_on_given_name_city_alias"] == 4
    assert links[1] is None
    assert links[2] == HUSKIES[0] and links[3] == HUSKIES[0]


def test_a_closed_markets_stored_link_is_left_alone():
    with Session(_make_engine()) as session:
        _seed(session)
        session.add(FuturesMarket(
            id=304, source="kalshi", external_id="KXNFLSEASONREC-26C75",
            name="Pro Football: 75+ Receptions Season", category="award",
            llm_sport_category="football", status="closed", market_tier=3,
        ))
        session.flush()
        session.add(FuturesOutcome(
            id=10, market_id=304, external_id="o10", name="Parker Washington",
            team_id=HUSKIES[0],
        ))
        session.commit()
        stats: dict = {"outcomes_unlinked_given_name_city_alias": 0}
        asyncio.run(team_linking._unlink_given_name_city_alias(_AsyncShim(session), stats, 100))
        links = _links(session)

    assert links[10] == HUSKIES[0]


def test_strawman_without_the_guard_the_surname_binds_to_the_huskies(monkeypatch):
    monkeypatch.setattr(linking, "given_name_before_city", lambda *a: False)
    assert match_outcome_to_team("Parker Washington", _dicts()) == HUSKIES[0]
    assert match_outcome_to_team("Matt Campbell", _dicts()) == CAMELS[0]


def test_phase_3c_never_clears_a_link_step_1_would_make_again():
    # If any of the team's names still matches, Step 1 would re-bind the NULL on
    # the next pass and the two phases would flip the row every hour.
    rests = team_linking._rests_on_given_name_city
    assert rests("Parker Washington", "Washington Huskies", ["Washington"])
    assert not rests(
        "Parker Washington", "Washington Huskies", ["Washington", "Parker Washington"]
    )


# --- a fantasy defense named by its city (#9726, after-check 2026-09-30) -------
#
# The production after-check (06:59Z) found the page still listing "Washington
# D/ST", which the issue names: the city leads, so the given-name rule never saw
# it. Every open D/ST outcome linked on production at 07:06Z, with its team's
# stored names (07:12Z): the four named by a city sit on a college; the eighteen
# named by a nickname sit on their NFL club.

# name, team, alternate_names, still linked after the fix
DST_LINKS = [
    ("Chargers D/ST", "Los Angeles Chargers", ["Chargers"], True),
    ("Cincinnati D/ST", "Cincinnati Bearcats", ["Cincinnati", "Bearcats"], False),
    ("Commanders D/ST", "Washington Commanders", ["Commanders"], True),
    ("Dolphins D/ST", "Miami Dolphins", ["fins", "phins", "Dolphins"], True),
    ("LA Chargers D/ST", "Los Angeles Chargers", ["Chargers"], True),
    ("LA Chargers D/ST", "Los Angeles Chargers", ["Chargers"], True),
    ("MIA Dolphins D/ST", "Miami Dolphins", ["fins", "phins", "Dolphins"], True),
    ("MIA Dolphins D/ST", "Miami Dolphins", ["fins", "phins", "Dolphins"], True),
    ("Minnesota D/ST", "Minnesota Golden Gophers", ["Minnesota", "Golden Gophers"], False),
    ("NE Patriots D/ST", "New England Patriots", ["pats", "Patriots"], True),
    ("NE Patriots D/ST", "New England Patriots", ["pats", "Patriots"], True),
    ("Patriots D/ST", "New England Patriots", ["pats", "Patriots"], True),
    ("PIT Steelers D/ST", "Pittsburgh Steelers", ["Steelers"], True),
    ("PIT Steelers D/ST", "Pittsburgh Steelers", ["Steelers"], True),
    ("PIT Steelers D/ST", "Pittsburgh Steelers", ["Steelers"], True),
    ("PIT Steelers D/ST", "Pittsburgh Steelers", ["Steelers"], True),
    ("PIT Steelers D/ST: 1+", "Pittsburgh Steelers", ["Steelers"], True),
    ("Steelers D/ST", "Pittsburgh Steelers", ["Steelers"], True),
    ("Tennessee D/ST", "Tennessee Volunteers", ["vols", "Tennessee", "Volunteers"], False),
    ("WAS Commanders D/ST", "Washington Commanders", ["Commanders"], True),
    ("WAS Commanders D/ST", "Washington Commanders", ["Commanders"], True),
    ("Washington D/ST", "Washington Huskies", ["Washington", "Huskies"], False),
]


def test_production_dst_links_only_the_city_named_defenses_lose():
    assert len(DST_LINKS) == 22
    kept = [(n, t) for n, t, a, _ in DST_LINKS if _names_match(n, t, a)]
    lost = sorted({(n, t) for n, t, a, _ in DST_LINKS if not _names_match(n, t, a)})
    assert len(kept) == 18
    assert lost == [
        ("Cincinnati D/ST", "Cincinnati Bearcats"),
        ("Minnesota D/ST", "Minnesota Golden Gophers"),
        ("Tennessee D/ST", "Tennessee Volunteers"),
        ("Washington D/ST", "Washington Huskies"),
    ]
    assert all(_names_match(n, t, a) == keep for n, t, a, keep in DST_LINKS)


@pytest.mark.parametrize(
    "name", ["Washington D/ST", "Washington DST", "Washington D/ST: 1+", "washington d/st"]
)
def test_a_city_and_then_dst_binds_to_no_club(name):
    assert match_outcome_to_team(name, _dicts()) is None


def test_only_a_city_alias_before_dst_is_guarded():
    guard = linking.fantasy_defense_on_city
    assert guard("Washington D/ST", "Washington", "Washington Huskies")
    assert guard("Minnesota D/ST: 1+", "Minnesota", "Minnesota Golden Gophers")
    # A nickname alias; the city with no D/ST; D/ST alone; a name that is all alias.
    assert not guard("Steelers D/ST", "Steelers", "Pittsburgh Steelers")
    assert not guard("Washington 8.5+", "Washington", "Washington Huskies")
    assert not guard("D/ST", "Washington", "Washington Huskies")
    assert not guard("Athletics DST", "Athletics", "Athletics")


def test_strawman_without_the_dst_guard_the_defense_binds_to_the_huskies(monkeypatch):
    monkeypatch.setattr(linking, "fantasy_defense_on_city", lambda *a: False)
    assert match_outcome_to_team("Washington D/ST", _dicts()) == HUSKIES[0]
    assert team_linking._rests_on_given_name_city(
        "Washington D/ST", "Washington Huskies", ["Washington", "Huskies"]
    ) is False
