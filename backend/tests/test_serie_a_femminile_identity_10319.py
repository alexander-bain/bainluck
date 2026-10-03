"""The evidenced women's ticker gains identity, not game/mint authority."""

from datetime import datetime, timezone

import pytest

from app.services import llm
from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
from app.utils.futures_categorization import detect_league, infer_sport_from_league
from app.utils.sport_keys import (
    KALSHI_TICKER_TO_SPORT_KEY,
    SPORT_LEAGUE_MAP,
    competition_gender,
    get_sport_key_from_ticker,
    is_classification_only_ticker,
    is_kalshi_game_level_ticker,
    same_sport_same_gender,
)

KEY = "soccer_italy_serie_a_women"
SUBJECT = "KXSERIEAWGAME-26OCT03PARTER"


@pytest.mark.parametrize("ticker", [SUBJECT, SUBJECT + "-TIE"])
def test_retained_subject_classifies_without_new_game_authority(ticker):
    assert get_sport_key_from_ticker(ticker) == KEY
    assert not is_kalshi_game_level_ticker(ticker)
    assert not is_classification_only_ticker(ticker)
    assert "kxserieawgame" not in KALSHI_TICKER_TO_SPORT_KEY
    assert KEY not in SPORT_LEAGUE_MAP  # No men's ESPN schedule alias.


@pytest.mark.parametrize(
    "ticker,key,game_level",
    [
        ("KXSERIEAGAME-26OCT03INTNAP", "soccer_italy_serie_a", True),
        ("KXSERIEA-26-CHAMPION", "soccer_italy_serie_a", False),
        ("KXFIFAWGAME-26X", "soccer", True),
        ("KXFIFAWCW-26", "soccer_fifa_world_cup_women", False),
    ],
)
def test_existing_mens_and_womens_controls(ticker, key, game_level):
    assert get_sport_key_from_ticker(ticker) == key
    assert is_kalshi_game_level_ticker(ticker) is game_level


def test_deterministic_classifiers_do_not_request_llm(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("Known competition must not call the LLM")

    monkeypatch.setattr(llm, "classify", refuse)
    assert llm.classify_gender("Parma Calcio vs Ternana", KEY) == "women"
    assert llm.classify_league("Parma Calcio vs Ternana", KEY) == "Serie_A_Femminile"
    assert competition_gender(KEY) == "women"
    assert not same_sport_same_gender(KEY, "soccer_italy_serie_a")
    assert not same_sport_same_gender("soccer_italy_serie_a", KEY)
    assert same_sport_same_gender(KEY, KEY)


@pytest.mark.parametrize("prior_league", [None, "Serie_A", "Serie_A_Femminile"])
def test_event_tags_use_exact_competition_over_stale_mens_league(prior_league):
    tags = compute_event_tags(
        KEY,
        "scheduled",
        datetime(2026, 10, 3, 10, 30, tzinfo=timezone.utc),
        llm_league=prior_league,
        llm_gender=llm.classify_gender("Parma Calcio vs Ternana", KEY),
    )
    assert {"sport:soccer", "league:serie_a_femminile", "gender:women"} <= set(tags)
    assert "league:serie_a" not in tags
    assert "gender:men" not in tags


def test_market_classification_and_tags_do_not_inherit_mens_prefix():
    league = detect_league("Parma Calcio vs Ternana", KEY, "soccer")
    assert league == "SERIE_A_FEMMINILE"
    assert infer_sport_from_league(league) == "soccer"
    tags = compute_market_tags(
        llm_sport_category="soccer",
        llm_league=league,
        llm_gender=llm.classify_gender("Parma Calcio vs Ternana", KEY),
    )
    assert {"sport:soccer", "league:serie_a_femminile", "gender:women"} <= set(tags)
    assert "league:serie_a" not in tags
    assert (
        detect_league("Inter vs Napoli", "soccer_italy_serie_a", "soccer") == "SERIE_A"
    )


def test_missing_or_contradictory_metadata_is_not_relabelled_by_tags():
    # Source prevention is not a broad repair of already-written metadata.
    for gender in [None, "men"]:
        tags = compute_market_tags(
            llm_sport_category="soccer",
            llm_league="Serie_A_Femminile",
            llm_gender=gender,
        )
        assert "gender:women" not in tags
