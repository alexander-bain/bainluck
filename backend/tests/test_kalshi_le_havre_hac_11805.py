"""#11805: Le Havre–PSG links to an existing game instead of a third row.

Original production receipt, Oct 27 2026: market 67820166,
KXLIGUE1GAME-26OCT30HACPSG, kept the parsed sides Le Havre/PSG because HAC
did not resolve. Both existing same-time Ligue 1 rows were rejected on names.
The expected clubs below come from that venue fixture and its two existing
rows, independently of the abbreviation table under test.

The patch changes ticker vocabulary. It does not reconcile old event IDs.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import _score_candidates
from app.utils.prediction_market_matching import (
    extract_game_date_from_ticker,
    extract_matchup_with_ticker_fallback,
    extract_teams_from_ticker,
)

TICKER = "KXLIGUE1GAME-26OCT30HACPSG"
MARKET_NAME = "Le Havre vs PSG"
ATTEMPTED_AT = datetime(2026, 10, 27, 10, 59, 45, 587562, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 10, 30, 18, tzinfo=timezone.utc)


def _candidate(
    event_id, away, *, sport_key="soccer_france_ligue_one", external_id=None
):
    return SimpleNamespace(
        id=event_id,
        sport_id=1,
        sport=SimpleNamespace(key=sport_key),
        home_team_name="Le Havre AC",
        away_team_name=away,
        commence_time=KICKOFF,
        status="scheduled",
        external_id=external_id,
    )


def _choose(candidates):
    market = SimpleNamespace(
        name=MARKET_NAME,
        external_id=TICKER,
        source="kalshi",
        llm_sport_category="soccer",
        market_metadata={},
        commence_time=None,
    )
    matchup = extract_matchup_with_ticker_fallback(MARKET_NAME, TICKER)
    return _score_candidates(
        candidates,
        matchup,
        market,
        ATTEMPTED_AT,
        extract_game_date_from_ticker(TICKER),
    )


@pytest.mark.parametrize("ticker", [TICKER, TICKER + "-HAC", TICKER + "-PSG"])
def test_hac_game_and_outcome_tickers_name_both_clubs(ticker):
    assert extract_teams_from_ticker(ticker) == ("Le Havre", "Paris Saint-Germain")


def test_actual_matcher_selects_an_existing_psg_row():
    polymarket_row = _candidate(15331418, "Paris Saint-Germain FC")
    odds_row = _candidate(
        15332583,
        "Paris Saint Germain",
        external_id="9a9f6c78276f74f15f42b013b033aa5d",
    )
    odds_row.home_team_name = "Le Havre"

    result = _choose([odds_row, polymarket_row])

    assert (
        result is not None
    ), "the existing game was missed and a third row would be minted"
    assert result["event_id"] == 15331418
    assert result["yes_is_home"] is True


@pytest.mark.parametrize(
    "ticker",
    [
        "KXSERIEAGAME-26OCT30HACROM",
        "KXLALIGAGAME-26OCT30HACVIL",
        "KXEPLGAME-26OCT30HACARS",
    ],
)
def test_hac_cannot_answer_another_domestic_leagues_ticker(ticker):
    assert extract_teams_from_ticker(ticker) is None


def test_hac_cannot_answer_an_nba_ticker():
    assert extract_teams_from_ticker("KXNBAGAME-26OCT30HACBOS") is None


def test_the_existing_le_havre_row_needs_psg_as_its_opponent():
    assert _choose([_candidate(10, "Olympique Lyonnais")]) is None


def test_matching_club_names_cannot_override_a_different_precise_league():
    row = _candidate(11, "Paris Saint-Germain FC", sport_key="soccer_italy_serie_a")
    assert _choose([row]) is None
