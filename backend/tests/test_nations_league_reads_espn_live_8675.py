"""#8675 — a Nations League match gets its live score and its full time from ESPN.

Production 2026-09-25: event 15290672, Georgia v Northern Ireland
(`soccer_uefa_nations_league`, kickoff 16:02Z) served `live` with a null score
for its whole 90 minutes and was still `live` at 18:37Z, while ESPN's
`soccer/uefa.nations` board read STATUS_FULL_TIME 0–1 from ~18:00Z. The key was
in neither ESPN map nor StatPal's, so nothing read a live score for the
competition, and the row finished only when the Odds API scores poll did.

Turning the ESPN board on has a second half, and it is the one that can hurt a
reader: ESPN spells three of the competition's nations differently from the Odds
API rows we hold (`Türkiye`/`Turkey`, `Czechia`/`Czech Republic`,
`Bosnia-Herzegovina`/`Bosnia & Herzegovina`). `names_match` said False for all
three, so the live pass could not pair those rows AND the registry's structured
match — which compares with the same `names_match` — would create a second row
for each of those games from ESPN's board. The rosters below are the real ones:
our 54 Nations League team names from production and ESPN's 54
`uefa.nations/teams` entries, both read 2026-09-25.
"""

from itertools import product
from types import SimpleNamespace

import pytest

from app.utils import name_normalization
from app.utils.name_normalization import names_match
from app.utils.sport_keys import (
    ESPN_SPORT_MAPPING,
    EXPECTED_GAME_STATE_INDICATORS,
    SPORT_LEAGUE_MAP,
)

NL = "soccer_uefa_nations_league"

#: (our row's name, ESPN displayName, ESPN shortDisplayName) — every team in
#: the competition, paired as the same country.
ROSTER = [
    ("Albania", "Albania", "Albania"), ("Andorra", "Andorra", "Andorra"),
    ("Armenia", "Armenia", "Armenia"), ("Austria", "Austria", "Austria"),
    ("Azerbaijan", "Azerbaijan", "Azerbaijan"), ("Belarus", "Belarus", "Belarus"),
    ("Belgium", "Belgium", "Belgium"),
    ("Bosnia & Herzegovina", "Bosnia-Herzegovina", "Bosnia-Herz"),
    ("Bulgaria", "Bulgaria", "Bulgaria"), ("Croatia", "Croatia", "Croatia"),
    ("Cyprus", "Cyprus", "Cyprus"), ("Czech Republic", "Czechia", "Czechia"),
    ("Denmark", "Denmark", "Denmark"), ("England", "England", "England"),
    ("Estonia", "Estonia", "Estonia"),
    ("Faroe Islands", "Faroe Islands", "Faroe Islands"),
    ("Finland", "Finland", "Finland"), ("France", "France", "France"),
    ("Georgia", "Georgia", "Georgia"), ("Germany", "Germany", "Germany"),
    ("Gibraltar", "Gibraltar", "Gibraltar"), ("Greece", "Greece", "Greece"),
    ("Hungary", "Hungary", "Hungary"), ("Iceland", "Iceland", "Iceland"),
    ("Israel", "Israel", "Israel"), ("Italy", "Italy", "Italy"),
    ("Kazakhstan", "Kazakhstan", "Kazakhstan"), ("Kosovo", "Kosovo", "Kosovo"),
    ("Latvia", "Latvia", "Latvia"),
    ("Liechtenstein", "Liechtenstein", "Liechtenstein"),
    ("Lithuania", "Lithuania", "Lithuania"),
    ("Luxembourg", "Luxembourg", "Luxembourg"), ("Malta", "Malta", "Malta"),
    ("Moldova", "Moldova", "Moldova"), ("Montenegro", "Montenegro", "Montenegro"),
    ("Netherlands", "Netherlands", "Netherlands"),
    ("North Macedonia", "North Macedonia", "North Macedonia"),
    ("Northern Ireland", "Northern Ireland", "N Ireland"),
    ("Norway", "Norway", "Norway"), ("Poland", "Poland", "Poland"),
    ("Portugal", "Portugal", "Portugal"),
    ("Republic of Ireland", "Republic of Ireland", "Rep Ireland"),
    ("Romania", "Romania", "Romania"), ("San Marino", "San Marino", "San Marino"),
    ("Scotland", "Scotland", "Scotland"), ("Serbia", "Serbia", "Serbia"),
    ("Slovakia", "Slovakia", "Slovakia"), ("Slovenia", "Slovenia", "Slovenia"),
    ("Spain", "Spain", "Spain"), ("Sweden", "Sweden", "Sweden"),
    ("Switzerland", "Switzerland", "Switzerland"),
    ("Turkey", "Türkiye", "Türkiye"), ("Ukraine", "Ukraine", "Ukraine"),
    ("Wales", "Wales", "Wales"),
]

ALIASED = {
    ("Turkey", "Türkiye"),
    ("Czech Republic", "Czechia"),
    ("Bosnia & Herzegovina", "Bosnia-Herzegovina"),
}


def _espn_team(display, short):
    return SimpleNamespace(
        display_name=display, short_name=short, name=display, location=display,
    )


def test_the_competition_is_on_every_espn_map_the_live_pass_reads():
    assert SPORT_LEAGUE_MAP[NL] == ("soccer", "uefa.nations")
    assert ESPN_SPORT_MAPPING[NL] == "soccer/uefa.nations"
    assert EXPECTED_GAME_STATE_INDICATORS[NL] == 2
    # `sync_espn_live_events` gates on the copy re-exported through config.
    from app.tasks.config import ESPN_SPORT_MAPPING as TASK_MAP
    assert NL in TASK_MAP


def test_the_roster_is_the_whole_competition():
    assert len(ROSTER) == 54
    assert len({r[0] for r in ROSTER}) == 54


@pytest.mark.parametrize("ours,display,short", ROSTER)
def test_every_nation_pairs_with_its_espn_entry_through_the_live_matcher(ours, display, short):
    from app.tasks.espn_sync import espn_names_match

    assert espn_names_match([ours], _espn_team(display, short))
    # The registry's structured match calls names_match with ESPN's display
    # name directly, in both argument orders across its two orientation arms.
    assert names_match(display, ours)
    assert names_match(ours, display)


@pytest.mark.parametrize("ours,display", sorted(ALIASED))
def test_the_three_spellings_matched_nothing_before_the_fold(ours, display, monkeypatch):
    """Strawman: the pairs are rescued by the fold and by nothing else."""
    monkeypatch.setattr(name_normalization, "_NATION_NAME_ALIASES", {})
    assert not names_match(ours, display)
    assert not names_match(display, ours)


def test_the_fold_adds_exactly_the_three_countries_and_nothing_else(monkeypatch):
    """Over every pair of names in the competition, both feeds' spellings, the
    fold's ONLY new equalities are the three countries' own two spellings."""
    names = sorted({r[0] for r in ROSTER} | {r[1] for r in ROSTER} | {r[2] for r in ROSTER})
    pairs = [(a, b) for a, b in product(names, names) if a < b]
    with_fold = {p for p in pairs if names_match(*p)}
    monkeypatch.setattr(name_normalization, "_NATION_NAME_ALIASES", {})
    without = {p for p in pairs if names_match(*p)}

    assert without <= with_fold
    assert with_fold - without == {tuple(sorted(p)) for p in ALIASED}


@pytest.mark.parametrize("a,b", [
    ("Turkey", "Georgia"),
    ("Türkiye", "Turkmenistan"),
    ("Czechia", "Chechnya"),
    ("Bosnia-Herzegovina", "Herzegovina FC"),
])
def test_the_fold_is_whole_name_only(a, b):
    assert not names_match(a, b)
