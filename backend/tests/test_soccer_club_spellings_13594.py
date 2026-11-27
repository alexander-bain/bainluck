"""Regression tests for #13594 UEFA club spelling pairs across providers."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.schedule_sentinel import name_similarity
from app.utils.event_twin_fold import fold_twin_events
from app.utils.name_normalization import names_match, shared_token_rivals
from app.utils.prediction_market_matching import _fuzzy_team_match

_KICKOFF = datetime(2026, 6, 15, 17, 45, tzinfo=timezone.utc)


def _event(
    event_id: int,
    sport_key: str,
    away: str,
    home: str,
    sources: dict,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        sport_id=1,
        sport=SimpleNamespace(key=sport_key),
        away_team_name=away,
        home_team_name=home,
        commence_time=_KICKOFF,
        commence_time_source="the_odds_api",
        win_probability_sources=sources,
        status="scheduled",
        home_score=None,
        away_score=None,
        opening_home_prob=None,
        opening_away_prob=None,
    )


_TWIN_MATCHUP_PAIRS = [
    (
        "soccer_uefa_champs_league",
        ("VfB Stuttgart", "Internazionale"),
        ("VfB Stuttgart", "Inter Milan"),
    ),
    (
        "soccer_italy_serie_a",
        ("VfB Stuttgart", "Internazionale"),
        ("VfB Stuttgart", "Inter Milan"),
    ),
    (
        "soccer_uefa_europa_league",
        ("PFC Levski Sofia", "Marseille"),
        ("PFK Levski Sofia", "Olympique de Marseille"),
    ),
    (
        "soccer_uefa_europa_league",
        ("AC Milan", "Olympiakos Piraeus"),
        ("AC Milan", "Olympiakós SFP"),
    ),
    (
        "soccer_uefa_europa_league",
        ("AC Milan", "Olympiakos Piraeus"),
        ("Milan", "Olympiacos"),
    ),
    (
        "soccer_uefa_europa_league",
        ("Lech Poznań", "Union Saint-Gilloise"),
        ("KKS Lech Poznań", "RU Saint-Gilloise"),
    ),
    (
        "soccer_uefa_europa_league",
        ("NK Celje", "Ferencváros TC"),
        ("NK Celje", "Ferencvarosi"),
    ),
    (
        "soccer_uefa_europa_league",
        ("AZ Alkmaar", "Sparta Prague"),
        ("AZ", "AC Sparta Praha"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("Mjällby AIF", "FC Kairat"),
        ("Mjällby AIF", "Qairat FK"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("AS Monaco", "Hearts"),
        ("Monaco", "Heart of Midlothian"),
    ),
    (
        "soccer_spl",
        ("Celtic", "Hearts"),
        ("Celtic", "Heart of Midlothian"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("FC Copenhagen", "Inter Club d'Escaldes"),
        ("FC København", "Inter Club d'Escaldes"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("Red Star Belgrade", "Gent"),
        ("Crvena Zvezda", "Gent"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("KuPS Kuopio", "SC Braga"),
        ("Kuopion PS", "SC Braga"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("Sint Truiden", "Hajduk Split"),
        ("K. Sint-Truidense VV", "HNK Hajduk Split"),
    ),
    (
        "soccer_uefa_europa_conference_league",
        ("Omonoia FC", "Juventus"),
        ("Omonia Nicosia", "Juventus"),
    ),
]


@pytest.mark.parametrize(("sport_key", "main_pair", "twin_pair"), _TWIN_MATCHUP_PAIRS)
def test_uefa_club_spellings_fold_and_fuzzy_match(sport_key, main_pair, twin_pair):
    main_ev = _event(
        1, sport_key, main_pair[0], main_pair[1], {"betting": {"home": 0.5, "away": 0.5}}
    )
    twin_ev = _event(
        2,
        sport_key,
        twin_pair[0],
        twin_pair[1],
        {"polymarket": {"home": 0.52, "away": 0.48}},
    )
    folded = fold_twin_events([main_ev, twin_ev])
    assert len(folded.events) == 1
    assert folded.dropped_ids == [2]
    assert _fuzzy_team_match(twin_pair[0], main_pair[0])
    assert _fuzzy_team_match(twin_pair[1], main_pair[1])


@pytest.mark.parametrize(
    ("name_a", "name_b"),
    [
        ("Ferencvarosi", "Ferencváros TC"),
        ("Qairat FK", "FC Kairat"),
        ("Heart of Midlothian", "Hearts"),
        ("FC København", "FC Copenhagen"),
        ("Crvena Zvezda", "Red Star Belgrade"),
        ("Kuopion PS", "KuPS Kuopio"),
        ("K. Sint-Truidense VV", "Sint Truiden"),
        ("Omonia Nicosia", "Omonoia FC"),
    ],
)
def test_non_pinned_uefa_aliases_match_names(name_a, name_b):
    assert names_match(name_a, name_b)


def test_derby_clubs_and_espn_inter_identity_do_not_conflate():
    # Pinned #6215 / #7441 guard: names_match keeps Inter Milan != Internazionale
    # and AC Milan vs Inter Milan stay strictly distinct under shared_token_rivals
    # and _fuzzy_team_match, while Milan folds with AC Milan inside UEL.
    assert names_match("Inter Milan", "Internazionale") is False
    assert shared_token_rivals("AC Milan", "Inter Milan") is True
    assert _fuzzy_team_match("AC Milan", "Inter Milan") is False

    ac_ev = _event(
        2,
        "soccer_uefa_europa_league",
        "AC Milan",
        "Olympiakos Piraeus",
        {"betting": {"home": 0.4, "away": 0.6}},
    )
    milan_ev = _event(
        3,
        "soccer_uefa_europa_league",
        "Milan",
        "Olympiacos",
        {"kalshi": {"home": 0.41, "away": 0.59}},
    )
    other_ev = _event(
        4,
        "soccer_uefa_europa_league",
        "Real Madrid",
        "Olympiakos Piraeus",
        {"polymarket": {"home": 0.5, "away": 0.5}},
    )
    assert len(fold_twin_events([ac_ev, milan_ev]).events) == 1
    assert len(fold_twin_events([ac_ev, other_ev]).events) == 2


def test_league_scoped_az_and_milan_do_not_bleed_across_sports():
    ev_a = _event(
        1,
        "baseball_mlb",
        "AZ",
        "San Francisco Giants",
        {"betting": {"home": 0.5, "away": 0.5}},
    )
    ev_b = _event(
        2,
        "baseball_mlb",
        "AZ Alkmaar",
        "San Francisco Giants",
        {"polymarket": {"home": 0.5, "away": 0.5}},
    )
    assert len(fold_twin_events([ev_a, ev_b]).events) == 2


def test_schedule_sentinel_recognizes_internazionale():
    assert name_similarity("Internazionale", "Inter Milan") == 1.0
    assert name_similarity("AC Milan", "Inter Milan") < 0.60


def test_az_sparta_catchall_and_monaco_hearts_fc_suffix_fold():
    # Pair 1: UEL AZ Alkmaar @ Sparta Prague vs catch-all soccer_other AZ @ AC Sparta Praha
    az_uel = _event(
        10,
        "soccer_uefa_europa_league",
        "AZ Alkmaar",
        "Sparta Prague",
        {"betting": {"home": 0.45, "away": 0.55}},
    )
    az_other = _event(
        11,
        "soccer_other",
        "AZ",
        "AC Sparta Praha",
        {"kalshi": {"home": 0.44, "away": 0.56}},
    )
    az_other.sport_id = 2
    res1 = fold_twin_events([az_uel, az_other])
    assert len(res1.events) == 1
    assert res1.events[0].id == 10

    # Pair 2: UECL AS Monaco @ Hearts vs UECL AS Monaco FC @ Heart of Midlothian FC
    monaco_canon = _event(
        20,
        "soccer_uefa_europa_conference_league",
        "AS Monaco",
        "Hearts",
        {"betting": {"home": 0.25, "away": 0.75}},
    )
    monaco_fc = _event(
        21,
        "soccer_uefa_europa_conference_league",
        "AS Monaco FC",
        "Heart of Midlothian FC",
        {"polymarket": {"home": 0.26, "away": 0.74}},
    )
    res2 = fold_twin_events([monaco_canon, monaco_fc])
    assert len(res2.events) == 1
    assert res2.events[0].id == 20
    assert names_match("Heart of Midlothian FC", "Hearts")
    assert names_match("AS Monaco FC", "AS Monaco")


def test_az_catchall_refuses_different_squad_or_different_minute():
    az_uel = _event(
        30,
        "soccer_uefa_europa_league",
        "AZ Alkmaar",
        "Sparta Prague",
        {"betting": {"home": 0.45, "away": 0.55}},
    )
    jong_az = _event(
        31,
        "soccer_other",
        "Jong AZ",
        "AC Sparta Praha",
        {"kalshi": {"home": 0.44, "away": 0.56}},
    )
    jong_az.sport_id = 2
    assert len(fold_twin_events([az_uel, jong_az]).events) == 2

    az_late = _event(
        32,
        "soccer_other",
        "AZ",
        "AC Sparta Praha",
        {"kalshi": {"home": 0.44, "away": 0.56}},
    )
    az_late.sport_id = 2
    az_late.commence_time = datetime(2026, 6, 15, 19, 45, tzinfo=timezone.utc)
    assert len(fold_twin_events([az_uel, az_late]).events) == 2
