import json
import re
from pathlib import Path

import pytest

from app.routes.user import _team_search_sport_display


_TESTS = Path(__file__).resolve().parent
_CATALOG = json.loads(
    (_TESTS / "fixtures" / "onboarding_leagues_13505.json").read_text()
)
_ACRONYMS = set(
    json.loads(
        (_TESTS.parents[1] / "contracts" / "category-acronyms.json").read_text()
    )["acronyms"]
) | {"AFL", "AFLW", "FCS", "IPL", "MILB", "NBL", "NRL", "NRLW", "PLL", "WNCAAB"}


def test_onboarding_league_catalog_has_readable_labels():
    case_errors = {acronym.title() for acronym in _ACRONYMS}
    for sport_key, stored_label in _CATALOG.items():
        label = _team_search_sport_display(sport_key, stored_label)
        assert label and "_" not in label, (sport_key, label)
        assert not (set(re.findall(r"\w+", label)) & case_errors), (sport_key, label)


@pytest.mark.parametrize(
    "sport_key, expected",
    [
        ("americanfootball_ncaaf_fcs", "NCAAF FCS"),
        ("aussierules_afl", "AFL"),
        ("baseball_kbo", "KBO"),
        ("baseball_milb", "MiLB"),
        ("cricket_ipl", "IPL"),
        ("icehockey_nhl", "NHL"),
        ("soccer_mexico_ligamx", "Liga MX"),
        ("soccer_fifa_world_cup", "FIFA World Cup"),
        ("soccer_uefa_nations_league", "UEFA Nations League"),
        ("soccer_england_league2", "League 2"),
        ("soccer_uefa_champs_league", "UEFA Champions League"),
        ("soccer_uefa_champs_league_women", "UEFA Women's Champions League"),
    ],
)
def test_onboarding_labels_keep_the_names_readers_already_see(sport_key, expected):
    assert _team_search_sport_display(sport_key, _CATALOG[sport_key]) == expected


@pytest.mark.parametrize(
    "stored_label",
    [None, "", "soccer_unknown_league", "UNKNOWN_LEAGUE", "Soccer Unknown League"],
)
def test_unnamed_league_uses_the_sport_name(stored_label):
    assert _team_search_sport_display("soccer_unknown_league", stored_label) == "Soccer"
