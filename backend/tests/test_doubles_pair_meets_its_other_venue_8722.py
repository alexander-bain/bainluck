"""A doubles match both venues price is ONE row, at the venue's hour (#8722).

SHIP (TRUTH/MATCHING): tonight's Laver Cup doubles stops reading "Starts in 43m"
after it was played, and a doubles match Kalshi and Polymarket both list stops
showing as two rows — one of them counting down to a start hours late.

The production specimen, read 2026-09-25 22:0xZ:

    event 15318449  "Alcaraz / Mensik" v "Bublik / Fritz"   22:30Z  source 'kalshi'
                    = KXLAVERCUPDOUBLESMATCH-26SEP25ALCMENBUBFRI expected expiration
    market 62219411 "Laver Cup (Doubles): Alcaraz/Mensik vs Bublik/Fritz"
                    venue_game_start 19:30Z, event_id NULL, receipt not_game_level

Three defects, each guarded here:

1. The spacing around a pair's slash split one side into two names, so no
   Kalshi doubles market ever met a Polymarket doubles row — 44 matches in the
   21 days to 2026-09-25 were two rows each, 0 carried both venues.
2. "Laver Cup (Doubles):" never stripped, so the match-winner market was not
   game-level; the doubles group has no prop to mint from, so no row existed at
   the venue's hour when Kalshi arrived.
3. Kalshi's expiration and Gamma's fixture instant both rank 0 in the start-time
   authority, so once linked the tie rule kept the expiration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.event_registry import (
    commence_time_write_authorized,
    polymarket_venue_corrects_a_kalshi_expiration,
)
from app.tasks.prediction_market_matching import (
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    polymarket_venue_redate,
)
from app.utils.name_normalization import normalize_team_name_for_matching
from app.utils.prediction_market_matching import (
    _expand_team_search_terms,
    _fuzzy_team_match,
    extract_matchup,
    is_game_level_market,
    match_teams_to_event,
)
from tests.test_phase15_redates_polymarket_listing_stamp_6073 import (
    _new_rail,
    _run_phase15,
)

KALSHI_HOME, KALSHI_AWAY = "Alcaraz / Mensik", "Bublik / Fritz"
POLY_NAME = "Laver Cup (Doubles): Alcaraz/Mensik vs Bublik/Fritz"
#: Kalshi `expected_expiration_time`, stored as the start.
KALSHI_EXPIRATION = datetime(2026, 9, 25, 22, 30, tzinfo=timezone.utc)
#: Gamma 1074594 `startTime`.
VENUE_START = datetime(2026, 9, 25, 19, 30, tzinfo=timezone.utc)


# ── 1. one pair, three spellings ─────────────────────────────────────────────

@pytest.mark.parametrize("spelling", ["Alcaraz / Mensik", "Alcaraz/Mensik", "Alcaraz/ Mensik"])
def test_every_venue_spelling_of_a_pair_normalizes_to_one_side(spelling):
    assert normalize_team_name_for_matching(spelling) == "alcaraz/mensik"


def test_polymarket_pair_matches_the_kalshi_row_and_orients_both_sides():
    matchup = extract_matchup("Alcaraz/Mensik vs Bublik/Fritz")
    assert (matchup.team_a, matchup.team_b) == ("Alcaraz/Mensik", "Bublik/Fritz")
    oriented = match_teams_to_event(matchup, KALSHI_HOME, KALSHI_AWAY)
    assert oriented is not None and oriented["yes_is_home"] is True


def test_kalshi_pair_matches_the_polymarket_row():
    matchup = extract_matchup("Alcaraz / Mensik vs Bublik / Fritz")
    oriented = match_teams_to_event(matchup, "Alcaraz/Mensik", "Bublik/Fritz")
    assert oriented is not None and oriented["yes_is_home"] is True


def test_a_different_pair_is_still_refused():
    """The collapse must not bind two pairs that share nobody."""
    assert _fuzzy_team_match("Alcaraz/Mensik", "Bublik / Fritz") is False
    matchup = extract_matchup("Alcaraz/Mensik vs Bublik/Fritz")
    assert match_teams_to_event(matchup, "Arends / Pel", "Nouza / Oberleitner") is None


def test_candidate_search_retrieves_the_other_venues_spelling():
    """Without this the name gate is never asked: `%Alcaraz/Mensik%` cannot
    retrieve the Kalshi row "Alcaraz / Mensik"."""
    assert "Alcaraz / Mensik" in _expand_team_search_terms("Alcaraz/Mensik")
    assert "Alcaraz/Mensik" in _expand_team_search_terms("Alcaraz / Mensik")


def test_the_compact_spelling_adds_no_bare_surname_search():
    """"%Mensik%" is every singles match he plays; the pair is the identity."""
    assert _expand_team_search_terms("Alcaraz/Mensik") == ["Alcaraz/Mensik", "Alcaraz / Mensik"]


def test_a_name_without_a_slash_gets_no_new_terms():
    assert _expand_team_search_terms("Boston Celtics") == ["Boston Celtics", "Celtics"]


# ── 2. the Laver Cup title is a tournament prefix ────────────────────────────

@pytest.mark.parametrize(
    "name, pair",
    [
        (POLY_NAME, ("Alcaraz/Mensik", "Bublik/Fritz")),
        ("Laver Cup: Casper Ruud vs Francisco Cerundolo", ("Casper Ruud", "Francisco Cerundolo")),
    ],
)
def test_laver_cup_match_winner_markets_are_game_level(name, pair):
    assert is_game_level_market(name, "game_prop") is True
    matchup = extract_matchup(name)
    assert (matchup.team_a, matchup.team_b) == pair


@pytest.mark.parametrize(
    "name",
    [
        "2026 Laver Cup: Winner",           # Polymarket's team outright
        "Laver Cup Winner",
        "Set 1 Winner: Casper Ruud vs Francisco Cerundolo",   # a prop still is not
    ],
)
def test_laver_cup_non_matches_stay_out(name):
    assert is_game_level_market(name, "game_prop") is False


# ── 3. the venue's fixture instant corrects Kalshi's expiration ──────────────

@pytest.mark.parametrize("kalshi_source", ["kalshi", "kalshi_occurrence"])
def test_venue_start_may_replace_a_kalshi_expiration(kalshi_source):
    assert polymarket_venue_corrects_a_kalshi_expiration(
        kalshi_source, POLYMARKET_VENUE_COMMENCE_SOURCE,
    )
    ok, _why = commence_time_write_authorized(kalshi_source, POLYMARKET_VENUE_COMMENCE_SOURCE)
    assert ok is True


@pytest.mark.parametrize(
    "current, incoming",
    [
        (POLYMARKET_VENUE_COMMENCE_SOURCE, "kalshi"),   # never the reverse
        ("kalshi", "polymarket"),                        # the listing stamp is not a start
        ("kalshi_ticker", POLYMARKET_VENUE_COMMENCE_SOURCE),  # a DATE, a different question
        ("espn", POLYMARKET_VENUE_COMMENCE_SOURCE),      # a schedule still outranks
        ("odds_api", POLYMARKET_VENUE_COMMENCE_SOURCE),
        (None, POLYMARKET_VENUE_COMMENCE_SOURCE),
    ],
)
def test_the_clause_is_directional_and_narrow(current, incoming):
    ok, _why = commence_time_write_authorized(current, incoming)
    assert ok is False


class _E:
    commence_time = KALSHI_EXPIRATION
    commence_time_source = "kalshi"


class _M:
    source = "polymarket"
    market_metadata = {"venue_game_start": "2026-09-25T19:30:00Z"}


def test_redate_moves_a_kalshi_timed_start_back_to_the_venue_start():
    assert polymarket_venue_redate(_M(), _E()) == VENUE_START


def test_redate_never_moves_a_kalshi_timed_start_later():
    """An expiration sits after the match; a later fixture is a reschedule or a
    disputed fixture (Korea Open, 2026-09-25: moneyline 20h after its own O/U
    sibling), not the correction the registry authorized."""
    later = datetime(2026, 9, 26, 2, 0, tzinfo=timezone.utc)
    assert polymarket_venue_redate(_M(), _E(), fixture=later) is None


def test_the_earlier_only_bound_does_not_touch_polymarkets_own_listing_rail():
    """#6073's rail moves a listing stamp in EITHER direction; unchanged."""
    class _PE:
        commence_time = datetime(2026, 9, 24, 16, 15, tzinfo=timezone.utc)
        commence_time_source = "polymarket"

    assert polymarket_venue_redate(_M(), _PE()) == VENUE_START


# ── end to end: the real Phase 1.5 pass over the specimen's shape ────────────

def _kalshi_event(session, sport):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=KALSHI_HOME, away_team_name=KALSHI_AWAY,
        commence_time=KALSHI_EXPIRATION, commence_time_source="kalshi",
        status="scheduled", external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _poly_leg(session, event, *, venue_start=VENUE_START):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket",
        external_id="0xa01ecf80d465294ae2fdc737d3058dc423c5a475bfb3af24926eaa8ea33be1ea",
        name=POLY_NAME, category="game_prop", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="tennis",
        group_id="polymarket:1074594", group_type="polymarket_sub_market",
        market_metadata={"venue_game_start": venue_start.isoformat().replace("+00:00", "Z")},
    )
    session.add(m)
    session.commit()
    return m


@pytest.mark.asyncio
async def test_phase15_redates_the_laver_cup_doubles_to_the_venue_start():
    session, tennis = _new_rail()
    event = _kalshi_event(session, tennis)
    _poly_leg(session, event)

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_START
    assert event.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE


@pytest.mark.asyncio
async def test_phase15_leaves_a_kalshi_row_alone_when_the_leg_names_another_pair():
    """The pairing gate (`phase15_link_is_valid_for_redate`) still binds: a leg
    about two other pairs never re-times this row."""
    from app.models.models import FuturesMarket

    session, tennis = _new_rail()
    event = _kalshi_event(session, tennis)
    leg = _poly_leg(session, event)
    session.query(FuturesMarket).filter_by(id=leg.id).update(
        {"name": "Laver Cup (Doubles): Arends/Pel vs Nouza/Oberleitner"}
    )
    session.commit()

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == KALSHI_EXPIRATION
    assert event.commence_time_source == "kalshi"
