"""#9472: a tennis row stored by two short surnames still reads its Kalshi price.

Kalshi stores ``Lys v Sun`` and prices it ``Eva Lys`` / ``Xinran Sun``.
``_fuzzy_team_match`` refuses a bare token of <=3 letters on purpose, so neither
outcome named a side and ``/events/15320683`` (China Open, 2026-09-30 03:00Z)
carried no Kalshi leg while its market quoted 0.685 on $11,495 traded. ``Gao v
Udvardy`` beside it spoke only because ``Udvardy`` is long.

Fixtures are production rows (db-query 2026-09-29 03:10Z). The refusal cases are
the 14 inning/half-winner derivative outcomes the looser ``players_agree``
comparator paired to a team in the replay of 6,792 linked markets.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.utils import live_blend as lb
from app.utils import prediction_market_matching as pmm
from app.utils.prediction_market_matching import (
    MatchupInfo,
    _names_player_by_surname,
    _surname_side_outcomes,
    find_moneyline_outcome,
)

NOW = datetime(2026, 9, 29, 2, 51, 33, tzinfo=timezone.utc)


def _outcome(name: str, p: str, rank: int) -> NS:
    return NS(
        name=name, current_probability=Decimal(p), current_yes_bid=None,
        current_yes_ask=None, last_updated=NOW, rank=rank, id=rank,
        is_winner=None, result=None, status="active", market_status="active",
    )


def _entry(market_id: int, name: str, ticker: str, outcomes: list) -> lb.MarketOutcomes:
    market = NS(
        id=market_id, source="kalshi", name=name, external_id=ticker,
        status="open", market_type="game", market_metadata={},
        llm_sport_category="tennis",
    )
    return lb.MarketOutcomes(
        market=market, outcomes=outcomes,
        event_commence_time=datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc),
        event_has_result=False,
    )


def _lys_sun(order: str = "home_first") -> lb.MarketOutcomes:
    outs = [_outcome("Eva Lys", "0.685", 1), _outcome("Xinran Sun", "0.305", 2)]
    if order == "away_first":
        outs.reverse()
    return _entry(62983159, "Lys vs Sun", "KXWTAMATCH-26SEP28LYSSUN", outs)


# ── the specimen, end to end through the blend writer's reader ─────────────


@pytest.mark.parametrize("order", ["home_first", "away_first"])
def test_specimen_15320683_reads_kalshis_home_price(order):
    reading = lb.compute_source_home_probability([_lys_sun(order)], "Lys", "Sun")
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.685)
    assert reading.outcome.name == "Eva Lys"


def test_specimen_oriented_when_the_row_stores_the_other_player_home():
    reading = lb.compute_source_home_probability([_lys_sun()], "Sun", "Lys")
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.305)


def test_control_gao_v_udvardy_reads_what_it_read_before():
    """The side test already named ``Panna Udvardy``; the fallback is never asked."""
    outs = [_outcome("Panna Udvardy", "0.645", 1), _outcome("Xinyu Gao", "0.345", 2)]
    entry = _entry(62983167, "Gao vs Udvardy", "KXWTAMATCH-26SEP28GAOUDV", outs)
    reading = lb.compute_source_home_probability([entry], "Gao", "Udvardy")
    assert reading is not None
    assert reading.home_probability == pytest.approx(0.355)
    assert reading.outcome.name == "Panna Udvardy"


def test_fallback_not_consulted_when_the_side_test_names_an_outcome(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("fallback asked although the side test named a side")

    monkeypatch.setattr(pmm, "_surname_side_outcomes", boom)
    outs = [_outcome("Panna Udvardy", "0.645", 1), _outcome("Xinyu Gao", "0.345", 2)]
    matchup = MatchupInfo("Gao", "Udvardy", "Gao", "bare_matchup")
    outcome, yes_is_home = find_moneyline_outcome(outs, matchup, "Gao", "Udvardy")
    assert (outcome.name, yes_is_home) == ("Panna Udvardy", False)


def test_strawman_without_the_fallback_the_specimen_is_silent(monkeypatch):
    """Proves the specimen exercises the new arm, not some other path."""
    monkeypatch.setattr(pmm, "_surname_side_outcomes", lambda *_a, **_k: None)
    assert lb.compute_source_home_probability([_lys_sun()], "Lys", "Sun") is None


# ── refusals: a wrong pairing prices the wrong player ──────────────────────


@pytest.mark.parametrize(
    "outcomes, home, away",
    [
        # Production derivative shapes (markets 63153105, 62398911, 61485056).
        (["San Diego wins 6th inning", "Chicago C wins 6th inning"],
         "San Diego Padres", "Chicago Cubs"),
        (["Dallas wins 1st half", "Golden State wins 1st half"],
         "Dallas Wings", "Golden State Valkyries"),
        (["New Mexico St. wins 1st Half", "Western Kentucky wins 1st Half"],
         "New Mexico State Aggies", "Western Kentucky Hilltoppers"),
        # One side named twice.
        (["Eva Lys", "Anna Lys"], "Lys", "Sun"),
        # Only one side named — either side.
        (["Eva Lys", "Someone Else"], "Lys", "Sun"),
        (["Someone Else", "Xinran Sun"], "Lys", "Sun"),
    ],
)
def test_refuses_anything_but_a_one_to_one_surname_pairing(outcomes, home, away):
    outs = [_outcome(n, "0.5", i) for i, n in enumerate(outcomes, 1)]
    assert _surname_side_outcomes(outs, home, away) is None


def test_refuses_an_outcome_that_names_both_sides():
    """``Mei Xinran Sun`` names both ``Xinran Sun`` and ``Sun``; ``Li Sun`` only the
    away side. Without the both-sides refusal this would pair one-to-one."""
    outs = [_outcome("Mei Xinran Sun", "0.6", 1), _outcome("Li Sun", "0.4", 2)]
    assert _surname_side_outcomes(outs, "Xinran Sun", "Sun") is None


@pytest.mark.parametrize(
    "outcome, side, expected",
    [
        ("Eva Lys", "Lys", True),
        ("Xinran Sun", "Sun", True),
        ("J. Cui", "Cui", True),
        ("Botic van de Zandschulp", "Van de Zandschulp", True),
        ("Anna Maria Lys", "Lys", True),
        ("Anna Maria Eva Lys", "Lys", False),  # three given names
        ("Team 2 Lys", "Lys", False),  # a digit is not a given name
        ("Lys", "Lys", False),  # nothing in front: not a full name
        ("Lys Eva", "Lys", False),  # surname must be LAST
        ("Eva Lys / Xinran Sun", "Lys / Sun", False),  # doubles: #8722's rule
        ("San Diego wins 6th inning", "San Diego Padres", False),
    ],
)
def test_names_player_by_surname(outcome, side, expected):
    assert _names_player_by_surname(outcome, side) is expected
