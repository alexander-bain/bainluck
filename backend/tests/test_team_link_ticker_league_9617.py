"""#9617 — a Kalshi city-only outcome binds inside the league its ticker names.

WHAT A READER SAW. ``/teams/new-york-knicks`` carried no Kalshi title price at
all while ``/teams/boston-celtics`` carried three; the Liberty and Lynx pages
showed only Polymarket's WNBA champion price while the Aces page showed Kalshi's
beside it. Measured 2026-09-29: the open KXNBA champion market had 7 of 30
outcomes linked to a team, KXWNBA 2 of 15, KXSB 26 of 32.

WHY. Kalshi names teams by city ("New York"). ``_backfill_team_links`` matched
each outcome against every team in its sport CATEGORY — basketball is NBA + WNBA
+ men's and women's college — so "New York" hit the Knicks AND the Liberty, read
ambiguous, and bound to nothing. The ticker already names the league.

The team rows below are production's own shapes (names and ``alternate_names``
read from ``teams`` on 2026-09-29): the Knicks and the Liberty both carry the
bare alias "New York"; the Falcons carry no city alias at all; the Lakers carry
"Los Angeles" and the Clippers do not.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import select

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.utils.team_linking import match_outcome_to_league_team, match_outcome_to_team

from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)
from sqlalchemy.orm import Session


def _t(team_id, name, alts, sport_key):
    return {"id": team_id, "name": name, "alternate_names": alts, "sport_key": sport_key}


KNICKS = _t(108, "New York Knicks", ["New York", "Knicks", "New York Knicks"], "basketball_nba")
NETS = _t(48, "Brooklyn Nets", ["Nets", "Brooklyn", "Brooklyn Nets"], "basketball_nba")
LAKERS = _t(49, "Los Angeles Lakers", ["Los Angeles", "Lakers"], "basketball_nba")
CLIPPERS = _t(537, "Los Angeles Clippers", ["LA", "Clippers", "LA Clippers"], "basketball_nba")
BLAZERS = _t(104, "Portland Trail Blazers", ["Trail Blazers", "Portland"], "basketball_nba")
WOLVES = _t(106, "Minnesota Timberwolves", ["Minnesota", "Timberwolves", "Minnesota Timberwolves"], "basketball_nba")
LIBERTY = _t(13414, "New York Liberty", ["Liberty", "New York"], "basketball_wnba")
SPARKS = _t(13957, "Los Angeles Sparks", ["Sparks"], "basketball_wnba")
LYNX = _t(13923, "Minnesota Lynx", ["Lynx"], "basketball_wnba")
KENTUCKY_M = _t(179, "Kentucky Wildcats", ["Kentucky", "Wildcats"], "basketball_ncaab")
KENTUCKY_W = _t(77, "Kentucky Wildcats", ["Kentucky", "Wildcats"], "basketball_wncaab")

FALCONS = _t(553, "Atlanta Falcons", ["Falcons"], "americanfootball_nfl")
GIANTS = _t(547, "New York Giants", ["Giants"], "americanfootball_nfl")
JETS = _t(550, "New York Jets", ["Jets"], "americanfootball_nfl")
PENN_STATE = _t(15356, "Penn State Nittany Lions", ["Nittany Lions", "Penn State"], "americanfootball_ncaaf")
MIDDLE_TENN = _t(17177, "Middle Tennessee Blue Raiders", ["Blue Raiders", "MTSU"], "americanfootball_ncaaf")
TENN = _t(15937, "Tennessee Volunteers", ["Tennessee", "Volunteers", "vols"], "americanfootball_ncaaf")

NBA = [KNICKS, NETS, LAKERS, CLIPPERS, BLAZERS, WOLVES]
WNBA = [LIBERTY, SPARKS, LYNX]
BASKETBALL = NBA + WNBA + [KENTUCKY_M, KENTUCKY_W]


# --- BEFORE: the category-wide matcher refuses the city --------------------


def test_the_category_wide_matcher_cannot_bind_a_city_two_leagues_share():
    # The defect, reproduced on the production rows: both clubs answer to it.
    assert match_outcome_to_team("New York", BASKETBALL) is None
    assert match_outcome_to_team("Minnesota", BASKETBALL) is None


# --- the league-scoped matcher ---------------------------------------------


def test_the_same_city_binds_to_each_leagues_own_club():
    assert match_outcome_to_league_team("New York", NBA) == KNICKS["id"]
    assert match_outcome_to_league_team("New York", WNBA) == LIBERTY["id"]


def test_a_club_with_no_city_alias_binds_by_its_own_name_minus_the_nickname():
    # The Lynx carry only "Lynx"; the Falcons only "Falcons".
    assert match_outcome_to_league_team("Minnesota", WNBA) == LYNX["id"]
    assert match_outcome_to_league_team("Atlanta", [FALCONS, GIANTS, JETS]) == FALCONS["id"]


def test_a_two_word_nickname_drops_two_words():
    # Middle Tennessee carries only "Blue Raiders" and "MTSU".
    assert match_outcome_to_league_team("Middle Tennessee", [MIDDLE_TENN, TENN]) == MIDDLE_TENN["id"]


def test_a_bare_city_that_still_names_a_sibling_stays_ambiguous():
    # "Los Angeles" is an exact alias of the Lakers only, but it names the
    # Clippers too. In the WNBA it names one club.
    assert match_outcome_to_league_team("Los Angeles", NBA) is None
    assert match_outcome_to_league_team("Los Angeles", WNBA) == SPARKS["id"]


def test_two_clubs_in_one_city_in_one_league_bind_neither():
    assert match_outcome_to_league_team("New York", [FALCONS, GIANTS, JETS]) is None


def test_an_alias_is_never_shortened():
    # Dropping the last word of the alias "Penn State" would make "Penn" (the
    # Quakers) name Penn State. Only the team's own name loses its nickname.
    assert match_outcome_to_league_team("Penn", [PENN_STATE]) is None


def test_no_substring_match_inside_a_league():
    # The category matcher's substring arm, scoped to one college league, would
    # bind a school that has no row to a school whose name it contains.
    assert match_outcome_to_team(
        "Western Kentucky wins 1st Half", [KENTUCKY_M]
    ) == KENTUCKY_M["id"]
    assert match_outcome_to_league_team("Western Kentucky wins 1st Half", [KENTUCKY_M]) is None
    assert match_outcome_to_league_team("Western Kentucky", [KENTUCKY_M]) is None
    # #9726: one word before a city alias is another school, so the category
    # matcher refuses the bare name too.
    assert match_outcome_to_team("Western Kentucky", [KENTUCKY_M]) is None


def test_a_player_or_a_matchup_is_not_a_team():
    # CERT-3796 follow-up 9617-PLAYER-MATCHUP-REFUSAL-GUARDS. A player's name
    # and a head-to-head label both reach this matcher from Kalshi award and
    # game series. Neither equals a team's name, alias or city, so neither binds
    # — while the category matcher's substring arm hands the matchup to the Knicks.
    assert match_outcome_to_league_team("Caitlin Clark", WNBA) is None
    assert match_outcome_to_team("New York vs Toronto", NBA) == KNICKS["id"]
    assert match_outcome_to_league_team("New York vs Toronto", NBA) is None


def test_empty_and_unknown_names_bind_nothing():
    assert match_outcome_to_league_team("", NBA) is None
    assert match_outcome_to_league_team("Seattle", NBA) is None
    assert match_outcome_to_league_team("New York", []) is None


# --- the drain, on a real database -----------------------------------------


def _seed(session: Session) -> None:
    session.add_all([
        Sport(id=1, key="basketball_nba", name="NBA", active=True),
        Sport(id=2, key="basketball_wnba", name="WNBA", active=True),
    ])
    for team, sport_id in ((KNICKS, 1), (WOLVES, 1), (LIBERTY, 2), (LYNX, 2)):
        session.add(Team(
            id=team["id"], sport_id=sport_id, name=team["name"],
            alternate_names=team["alternate_names"],
        ))
    markets = [
        (12046267, "kalshi", "KXWNBA-26", "Women's Pro Basketball Champion"),
        (12046300, "kalshi", "KXNBA-27", "2027 Pro Basketball Champion"),
        # A Polymarket numeric id is not a ticker; its outcome keeps the old path.
        (9413479, "polymarket", "350828", "WNBA: 2026 Champion"),
        # A Kalshi series no map knows keeps the old path too.
        (12046400, "kalshi", "KXNOTALEAGUE-26", "Pro Basketball Something"),
        # The ticker read belongs to Kalshi: another source's id that happens
        # to begin like a Kalshi series is not a league claim.
        (12046500, "polymarket", "kxnba-lookalike-slug", "NBA Champion"),
    ]
    for mid, source, ext, name in markets:
        session.add(FuturesMarket(
            id=mid, source=source, external_id=ext, name=name,
            category="championship", llm_sport_category="basketball",
            status="open", market_tier=1,
        ))
    session.flush()
    outcomes = [
        (1, 12046267, "New York"), (2, 12046267, "Minnesota"),
        (3, 12046300, "New York"), (4, 12046300, "Minnesota"),
        (5, 9413479, "New York"),
        (6, 12046400, "New York"),
        (7, 12046500, "New York"),
    ]
    for oid, mid, name in outcomes:
        session.add(FuturesOutcome(id=oid, market_id=mid, external_id=f"o{oid}", name=name))
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


def test_the_drain_binds_kalshi_cities_inside_the_ticker_league_and_nothing_else():
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        stats = _drain(session)
        bound = dict(session.execute(
            select(FuturesOutcome.id, FuturesOutcome.team_id)
        ).all())

    assert stats["errors"] == []
    assert bound == {
        1: LIBERTY["id"],   # KXWNBA "New York"
        2: LYNX["id"],      # KXWNBA "Minnesota" — the Lynx carry no city alias
        3: KNICKS["id"],    # KXNBA "New York"
        4: WOLVES["id"],    # KXNBA "Minnesota"
        5: None,            # Polymarket: no ticker, category-wide rule unchanged
        6: None,            # unknown Kalshi series: category-wide rule unchanged
        7: None,            # a non-Kalshi id shaped like a ticker names no league
    }
    assert stats["outcomes_linked_by_league"] == 4
    assert stats["outcomes_linked"] == 4
