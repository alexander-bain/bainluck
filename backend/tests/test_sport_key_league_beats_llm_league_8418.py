"""#8418: the sport key's own league is the event's `league:` tag, not the LLM's.

An SHL game page's rail was headed "More SHL" over four Stanley Cup markets.
The heading comes from the sport key; the cards come from the event's
`league:` tag, and every live SHL and Liiga game carried `league:nhl` because
`_extract_league` read the stored `llm_league` ("NHL" on all six rows read)
before the deterministic `_SPORT_KEY_TO_LEAGUE`.

The pairs below are (sport key, stored `llm_league`) combinations read from
production events over 21 days (2026-09-24), with the row count.
"""

from datetime import datetime, timezone

import pytest

from app.utils.event_taxonomy import (
    ALLOWED_TAGS,
    _SPORT_KEY_TO_LEAGUE,
    _extract_league,
    compute_event_tags,
)


def _league_tags(sport_key: str, llm_league: str | None) -> list[str]:
    tags = compute_event_tags(
        sport_key=sport_key,
        status="live",
        commence_time=datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc),
        llm_league=llm_league,
    )
    return [t for t in tags if t.startswith("league:")]


@pytest.mark.parametrize(
    "sport_key, llm_league, expected",
    [
        # The specimen: 15316465, Skellefteå AIK @ HV71 (17 rows).
        ("icehockey_sweden_hockey_league", "NHL", "shl"),
        ("icehockey_liiga", "NHL", "liiga"),  # 57 rows
        ("icehockey_sweden_allsvenskan", "NHL", "allsvenskan"),  # 28 rows
    ],
)
def test_a_named_european_hockey_league_keeps_its_own_tag(sport_key, llm_league, expected):
    assert _league_tags(sport_key, llm_league) == [f"league:{expected}"]


@pytest.mark.parametrize(
    "sport_key, llm_league",
    [
        ("baseball_milb", "MLB"),  # 180 rows
        ("icehockey_mestis", "NHL"),  # 10 rows
        ("soccer_spain_segunda_division", "La_Liga"),  # 11 rows
    ],
)
def test_a_named_competition_we_have_no_tag_for_gets_none_not_the_bigger_league(
    sport_key, llm_league
):
    assert _league_tags(sport_key, llm_league) == []


@pytest.mark.parametrize(
    "sport_key, llm_league",
    [
        ("basketball_other", "NFL"),  # 13 rows
        ("tennis_other", "NCAAF"),  # 16 rows
        ("tennis_other", "UFC"),  # 7 rows
        ("esports", "NCAAF"),
        ("americanfootball_other", "Europa_League"),
        ("rugby_other", "CFL"),
    ],
)
def test_a_generic_key_refuses_an_llm_league_of_another_sport(sport_key, llm_league):
    assert _league_tags(sport_key, llm_league) == []


@pytest.mark.parametrize(
    "sport_key, llm_league, expected",
    [
        ("icehockey_other", "NHL", "nhl"),  # 143 rows
        ("icehockey_other", "AHL", "ahl"),
        ("basketball_other", "WNBA", "wnba"),  # 21 rows
        ("basketball_other", "EuroLeague", "euroleague"),  # 36 rows
        ("mma_other", "UFC", "ufc"),
        ("baseball_other", "MLB", "mlb"),
    ],
)
def test_a_generic_key_still_takes_an_llm_league_of_its_own_sport(
    sport_key, llm_league, expected
):
    """Control: the LLM label keeps the one job it can do."""
    assert _league_tags(sport_key, llm_league) == [f"league:{expected}"]


@pytest.mark.parametrize(
    "sport_key, llm_league, expected",
    [
        # These two were right only because the LLM happened to agree; they
        # are now deterministic, so the change does not strip them.
        ("icehockey_nhl_preseason", "NHL", "nhl"),  # 27 rows
        ("americanfootball_ncaaf_fcs", "NCAAF", "ncaaf"),  # 146 rows
        ("americanfootball_ncaaf_fcs", None, "ncaaf"),
        ("americanfootball_ncaaf_fcs", "NCAAB", "ncaaf"),  # 1 row
    ],
)
def test_keys_the_llm_used_to_tag_correctly_keep_their_tag(sport_key, llm_league, expected):
    assert _league_tags(sport_key, llm_league) == [f"league:{expected}"]


def test_every_mapped_key_ignores_every_other_allowed_league():
    """No LLM label, however valid a tag, moves a key that has a league of its own."""
    for sport_key, own in _SPORT_KEY_TO_LEAGUE.items():
        for label in ALLOWED_TAGS["league"]:
            assert _extract_league(sport_key, label) == own, (sport_key, label)
