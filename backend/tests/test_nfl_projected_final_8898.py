"""#8898 — every NFL page projected a ~9–8 final with the home team winning.

Production, 2026-09-26 19:20Z: Dolphins–Chiefs (`/events/14781701`) printed
**"Projected final: 9 – 8"** under **15% – 85%** — the 85% favourite losing a
nine-point game. 14 of the 15 NFL games that weekend printed the same shape.
Three leaks compounded, each reproduced by running the route's own loop over the
293 markets production links to the event:

1. Kalshi's NFL spread rungs read ``KC Chiefs wins by over 10.5 points``; the
   name rule refused both sides (``kc`` is not ``kansas``), so the whole Kalshi
   spread was dropped — 412 of 412 open NFL rungs.
2. ``Xavier Worthy: over 16.5 yards`` (Player Longest Reception) was banked as a
   game total and pulled Kalshi's total to 17.1.
3. Polymarket's ``Chiefs vs. Dolphins`` carries ``Spread -1.5`` twice — 0.815
   for the Chiefs, 0.145 for the Dolphins — and read as one ladder it put the
   home team ahead by 1.5. ``Dolphins O/U 16.5`` priced the game total too.

Every fixture below is production's text and price, verbatim. The route is
served, not re-implemented.
"""

import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import get_event_odds_history
from app.utils.binary_spread import resolve_rung_side
from tests.test_projection_source_confidence_3921 import (
    COMMENCE,
    _DispatchingSession,
    _market,
    _outcome,
    _spread_market,
)

_SPECIMEN_ID = 14781701

# KXNFLSPREAD-26SEP27KCMIA, all 26 rungs.
_KALSHI_SPREAD_RUNGS = (
    ("KC Chiefs wins by over 1.5 points", 0.825),
    ("KC Chiefs wins by over 2.5 points", 0.8),
    ("KC Chiefs wins by over 3.5 points", 0.725),
    ("KC Chiefs wins by over 4.5 points", 0.725),
    ("KC Chiefs wins by over 5.5 points", 0.705),
    ("KC Chiefs wins by over 6.5 points", 0.655),
    ("KC Chiefs wins by over 7.5 points", 0.595),
    ("KC Chiefs wins by over 9.5 points", 0.535),
    ("KC Chiefs wins by over 10.5 points", 0.495),
    ("KC Chiefs wins by over 13.5 points", 0.415),
    ("KC Chiefs wins by over 14.5 points", 0.375),
    ("KC Chiefs wins by over 16.5 points", 0.345),
    ("KC Chiefs wins by over 17.5 points", 0.295),
    ("KC Chiefs wins by over 20.5 points", 0.245),
    ("KC Chiefs wins by over 23.5 points", 0.185),
    ("KC Chiefs wins by over 27.5 points", 0.115),
    ("KC Chiefs wins by over 30.5 points", 0.075),
    ("MIA Dolphins wins by over 1.5 points", 0.145),
    ("MIA Dolphins wins by over 2.5 points", 0.135),
    ("MIA Dolphins wins by over 3.5 points", 0.095),
    ("MIA Dolphins wins by over 4.5 points", 0.085),
    ("MIA Dolphins wins by over 5.5 points", 0.085),
    ("MIA Dolphins wins by over 6.5 points", 0.065),
    ("MIA Dolphins wins by over 7.5 points", 0.05),
    ("MIA Dolphins wins by over 9.5 points", 0.045),
    ("MIA Dolphins wins by over 10.5 points", 0.025),
)

# KXNFLTOTAL-26SEP27KCMIA, all 19 rungs.
_KALSHI_TOTAL_RUNGS = (
    ("Over 24.5 points scored", 0.955),
    ("Over 27.5 points scored", 0.935),
    ("Over 30.5 points scored", 0.89),
    ("Over 33.5 points scored", 0.825),
    ("Over 36.5 points scored", 0.765),
    ("Over 39.5 points scored", 0.685),
    ("Over 42.5 points scored", 0.595),
    ("Over 43.5 points scored", 0.555),
    ("Over 44.5 points scored", 0.52),
    ("Over 45.5 points scored", 0.485),
    ("Over 46.5 points scored", 0.465),
    ("Over 47.5 points scored", 0.425),
    ("Over 48.5 points scored", 0.415),
    ("Over 51.5 points scored", 0.305),
    ("Over 54.5 points scored", 0.255),
    ("Over 57.5 points scored", 0.18),
    ("Over 60.5 points scored", 0.125),
    ("Over 63.5 points scored", 0.09),
    ("Over 66.5 points scored", 0.055),
)

# KXNFLLONGREC-26SEP27KCMIA — the five rungs inside the NFL total range.
_LONGEST_RECEPTION_RUNGS = (
    ("Malik Washington: over 15.5 yards", 0.55),
    ("Xavier Worthy: over 16.5 yards", 0.53),
    ("Tyquan Thornton: over 17.5 yards", 0.48),
    ("Rashee Rice: over 19.5 yards", 0.495),
    ("Travis Kelce: over 19.5 yards", 0.5),
)

# Polymarket event 864744 `Chiefs vs. Dolphins`: every full-game spread rung
# (both teams' legs, one name each), every game total, every team total.
_PM_SPREAD_RUNGS = (
    ("Spread -1.5", 0.815), ("Spread -1.5", 0.145),
    ("Spread -2.5", 0.81), ("Spread -2.5", 0.145),
    ("Spread -3.5", 0.725), ("Spread -3.5", 0.095),
    ("Spread -4.5", 0.72), ("Spread -4.5", 0.085),
    ("Spread -5.5", 0.705), ("Spread -5.5", 0.0805),
    ("Spread -6.5", 0.665), ("Spread -6.5", 0.0605),
    ("Spread -7.5", 0.585), ("Spread -7.5", 0.045),
    ("Spread -8.5", 0.555), ("Spread -8.5", 0.0465),
    ("Spread -9.5", 0.535), ("Spread -9.5", 0.0325),
    ("Spread -10.5", 0.485), ("Spread -10.5", 0.022),
    ("Spread -13.5", 0.405), ("Spread -13.5", 0.0295),
    ("Spread -14.5", 0.37), ("Spread -14.5", 0.0345),
    ("Spread -16.5", 0.345), ("Spread -16.5", 0.0345),
    ("Spread -17.5", 0.295), ("Spread -17.5", 0.0265),
    ("Spread -19.5", 0.255), ("Spread -19.5", 0.031),
    ("Spread -20.5", 0.24), ("Spread -20.5", 0.025),
    ("Spread -21.5", 0.18), ("Spread -21.5", 0.043),
)
_PM_GAME_TOTAL_RUNGS = (
    ("O/U 24.5", 0.9595), ("O/U 26.5", 0.945), ("O/U 28.5", 0.93),
    ("O/U 30.5", 0.885), ("O/U 32.5", 0.865), ("O/U 34.5", 0.835),
    ("O/U 36.5", 0.765), ("O/U 38.5", 0.705), ("O/U 40.5", 0.63),
    ("O/U 41.5", 0.595), ("O/U 42.5", 0.59), ("O/U 43.5", 0.56),
    ("O/U 44.5", 0.515), ("O/U 45.5", 0.485), ("O/U 46.5", 0.455),
    ("O/U 47.5", 0.425), ("O/U 48.5", 0.395), ("O/U 50.5", 0.345),
    ("O/U 52.5", 0.29), ("O/U 54.5", 0.245), ("O/U 56.5", 0.21),
    ("O/U 58.5", 0.16), ("O/U 60.5", 0.12), ("O/U 62.5", 0.085),
    ("O/U 64.5", 0.085),
)
_PM_TEAM_TOTAL_RUNGS = (
    ("Chiefs O/U 10.5", 0.964), ("Chiefs O/U 20.5", 0.79),
    ("Dolphins O/U 10.5", 0.745), ("Dolphins O/U 16.5", 0.53),
    ("Dolphins O/U 20.5", 0.325),
)


def _kalshi_rung_ticker(name):
    # Production's per-rung ticker: team code + the line rounded up
    # (`KC Chiefs wins by over 9.5 points` -> `...-KC10`).
    code = name.split()[0]
    line = float(name.split("over ")[1].split()[0])
    return f"KXNFLSPREAD-26SEP27KCMIA-{code}{math.ceil(line)}"


def _kalshi_spread():
    return _market(
        "kalshi",
        [_outcome(n, p, _kalshi_rung_ticker(n)) for n, p in _KALSHI_SPREAD_RUNGS],
        name="KC Chiefs vs MIA Dolphins: Spread",
        external_id="KXNFLSPREAD-26SEP27KCMIA",
    )


def _kalshi_total():
    return _market(
        "kalshi",
        [_outcome(n, p) for n, p in _KALSHI_TOTAL_RUNGS],
        name="KC Chiefs vs MIA Dolphins: Total Points",
        external_id="KXNFLTOTAL-26SEP27KCMIA",
    )


def _longest_reception():
    return _market(
        "kalshi",
        [_outcome(n, p) for n, p in _LONGEST_RECEPTION_RUNGS],
        name="Kansas City vs Miami: Player Longest Reception",
        external_id="KXNFLLONGREC-26SEP27KCMIA",
    )


def _pm_umbrella(*groups):
    rungs = [rung for group in groups for rung in group]
    return _market(
        "polymarket",
        [_outcome(n, p) for n, p in rungs],
        name="Chiefs vs. Dolphins",
        external_id="864744",
    )


def _event():
    # The row's real orientation: Miami is HOME.
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status="scheduled",
        commence_time=COMMENCE,
        completed_at=None,
        home_team_name="Miami Dolphins",
        away_team_name="Kansas City Chiefs",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="americanfootball_nfl"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.15}},
    )


async def _pm_spread_data(*markets):
    payload = await get_event_odds_history(
        event_id=_SPECIMEN_ID,
        hours=720,
        response=MagicMock(headers={}),
        db=_DispatchingSession(_event(), markets),
    )
    return payload.get("pm_spread_data") or {}


def _all_specimen_markets():
    return (
        _kalshi_spread(),
        _kalshi_total(),
        _longest_reception(),
        _pm_umbrella(_PM_SPREAD_RUNGS, _PM_GAME_TOTAL_RUNGS, _PM_TEAM_TOTAL_RUNGS),
    )


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


async def test_the_specimen_projects_the_favourite_winning_a_football_score():
    """Production printed 9 – 8 (Miami ahead). The markets say KC by ~10, ~45 total."""
    projected = (await _pm_spread_data(*_all_specimen_markets()))["projected_final"]

    home, away = projected["home_score"], projected["away_score"]
    assert away - home > 8, projected
    assert 43 <= home + away <= 47, projected
    assert projected["spread_source"] == "kalshi", projected


# ---------------------------------------------------------------------------
# Leak 1 — Kalshi's `KC Chiefs` rungs
# ---------------------------------------------------------------------------


async def test_every_kalshi_spread_rung_reaches_the_served_ladder():
    arm = (await _pm_spread_data(_kalshi_spread()))["implied_spreads"]["kalshi"]

    assert len(arm["contracts"]) == len(_KALSHI_SPREAD_RUNGS)
    assert -12 < arm["home_margin"] < -9, arm["home_margin"]


# Every rung form on the open Kalshi NFL spread markets of 2026-09-26/28.
_NFL_RUNG_FORMS = (
    ("ARI Cardinals", "San Francisco 49ers", "Arizona Cardinals"),
    ("BAL Ravens", "Dallas Cowboys", "Baltimore Ravens"),
    ("BUF Bills", "Buffalo Bills", "Los Angeles Chargers"),
    ("CAR Panthers", "Cleveland Browns", "Carolina Panthers"),
    ("CHI Bears", "Chicago Bears", "Philadelphia Eagles"),
    ("CIN Bengals", "Pittsburgh Steelers", "Cincinnati Bengals"),
    ("CLE Browns", "Cleveland Browns", "Carolina Panthers"),
    ("DAL Cowboys", "Dallas Cowboys", "Baltimore Ravens"),
    ("DEN Broncos", "Denver Broncos", "Los Angeles Rams"),
    ("DET Lions", "Detroit Lions", "New York Jets"),
    ("HOU Texans", "Indianapolis Colts", "Houston Texans"),
    ("IND Colts", "Indianapolis Colts", "Houston Texans"),
    ("JAC Jaguars", "Jacksonville Jaguars", "New England Patriots"),
    ("KC Chiefs", "Miami Dolphins", "Kansas City Chiefs"),
    ("LA Chargers", "Buffalo Bills", "Los Angeles Chargers"),
    ("LA Rams", "Denver Broncos", "Los Angeles Rams"),
    ("LV Raiders", "New Orleans Saints", "Las Vegas Raiders"),
    ("MIA Dolphins", "Miami Dolphins", "Kansas City Chiefs"),
    ("MIN Vikings", "Tampa Bay Buccaneers", "Minnesota Vikings"),
    ("NE Patriots", "Jacksonville Jaguars", "New England Patriots"),
    ("NO Saints", "New Orleans Saints", "Las Vegas Raiders"),
    ("NY Giants", "New York Giants", "Tennessee Titans"),
    ("NY Jets", "Detroit Lions", "New York Jets"),
    ("PHI Eagles", "Chicago Bears", "Philadelphia Eagles"),
    ("PIT Steelers", "Pittsburgh Steelers", "Cincinnati Bengals"),
    ("SEA Seahawks", "Washington Commanders", "Seattle Seahawks"),
    ("SF 49ers", "San Francisco 49ers", "Arizona Cardinals"),
    ("TB Buccaneers", "Tampa Bay Buccaneers", "Minnesota Vikings"),
    ("TEN Titans", "New York Giants", "Tennessee Titans"),
    ("WAS Commanders", "Washington Commanders", "Seattle Seahawks"),
)


@pytest.mark.parametrize("rung,home,away", _NFL_RUNG_FORMS)
def test_a_code_and_nickname_rung_names_its_own_side(rung, home, away):
    expected = "home" if rung.split()[-1] == home.split()[-1] else "away"
    assert resolve_rung_side(rung, home, away) == expected


def test_a_shared_city_code_still_names_only_its_own_club():
    assert resolve_rung_side("LA Rams", "Los Angeles Chargers", "Los Angeles Rams") == "away"
    assert resolve_rung_side("LA Chargers", "Los Angeles Chargers", "Los Angeles Rams") == "home"
    assert resolve_rung_side("NY Jets", "New York Giants", "New York Jets") == "away"


def test_the_code_must_belong_to_the_club_the_nickname_names():
    # Nickname alone is not enough: a code from another city refuses.
    assert resolve_rung_side("KC Dolphins", "Miami Dolphins", "Kansas City Chiefs") is None
    assert resolve_rung_side("BUF Chiefs", "Miami Dolphins", "Kansas City Chiefs") is None


# ---------------------------------------------------------------------------
# Leak 2 — a subject in front of the line is not the game's total
# ---------------------------------------------------------------------------


async def test_player_yardage_props_never_price_the_game_total():
    arm = (await _pm_spread_data(_kalshi_total(), _longest_reception()))[
        "implied_totals"
    ]["kalshi"]

    assert min(c["threshold"] for c in arm["contracts"]) == 24.5
    assert len(arm["contracts"]) == len(_KALSHI_TOTAL_RUNGS)
    assert 44 <= arm["total"] <= 46, arm["total"]


async def test_team_totals_in_a_matchup_market_never_price_the_game_total():
    arm = (
        await _pm_spread_data(_pm_umbrella(_PM_GAME_TOTAL_RUNGS, _PM_TEAM_TOTAL_RUNGS))
    )["implied_totals"]["polymarket"]

    # Control inside the same market: every bare `O/U N` still prices it.
    assert len(arm["contracts"]) == len(_PM_GAME_TOTAL_RUNGS)
    assert 44 <= arm["total"] <= 46, arm["total"]


# ---------------------------------------------------------------------------
# Leak 3 — two teams' side-less ladders in one market
# ---------------------------------------------------------------------------


async def test_a_market_pricing_one_sideless_line_twice_serves_no_spread():
    data = await _pm_spread_data(_pm_umbrella(_PM_SPREAD_RUNGS))

    assert "polymarket" not in (data.get("implied_spreads") or {})


async def test_a_one_sided_sideless_ladder_is_still_served():
    # Control: unique lines are one ladder, and the extractor path keeps them.
    market = _spread_market("polymarket", [3.5, 7.5, 10.5, 14.5])
    arm = (await _pm_spread_data(market))["implied_spreads"]["polymarket"]

    assert [c["threshold"] for c in arm["contracts"]] == [3.5, 7.5, 10.5, 14.5]
