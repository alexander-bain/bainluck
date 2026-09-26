"""#8854 — a Polymarket lineup prop is not a fixture, so it must not mint one.

WHAT PRODUCTION HELD (2026-09-26 15:55Z). 55 upcoming `soccer_other` events whose
away side read "<Team> - <Team> Starting 11" — `/events/15318630` "Croatia v
England - Croatia Starting 11", 15318565 "Croatia v Spain - Croatia Starting 11" —
two per Nations League fixture, all id-less, all minted from 2026-09-25 04:26Z by
the auto-create path from markets named "Croatia vs. England - Croatia Starting
11". `/api/events?sport=soccer_other` served them.

WHY #2871 LET IT THROUGH. `_DERIVATIVE_SUFFIX_RE` refuses a dash-introduced market
TYPE ("- Exact Score", "- 1st Half Winner"). This is the first type measured with a
TEAM in front of it, so the vocabulary never matched, `is_derivative_market_name`
answered False, and `extract_matchup` glued "- Croatia Starting 11" to team_b.

THE ONE-VOCABULARY CONTRACT. The same pattern is (1) the auto-create refusal, (2)
the link-search copy that lets a derivative attach to the fixture we hold (#6134),
and (3) the population predicate of `repair_2871_phantom_derivative_events`, which
runs it in POSTGRES. Each consumer is pinned below, and the hyphenated-nation
cases pin the cleaned name, because (2) and (3) both read the stripped string.
"""

import importlib.util
import pathlib
import re

import pytest

from app.utils.prediction_market_matching import (
    _DERIVATIVE_SUFFIX_RE,
    extract_matchup,
    is_derivative_market_name,
    matchup_for_link_search,
)

# (market name, the away team a link search must look for)
STARTING_ELEVEN = [
    ("Croatia vs. England - Croatia Starting 11", "England"),
    ("Albania vs. Belarus - Albania Starting 11", "Belarus"),
    ("Faroe Islands vs. Kazakhstan - Faroe Islands Starting 11", "Kazakhstan"),
    ("Kazakhstan vs. Faroe Islands - Faroe Islands Starting 11", "Faroe Islands"),
    ("Croatia vs. England - England Starting XI", "England"),
    # A hyphenated nation on either side: the team slot may join words with a
    # BARE hyphen but must never cross the spaced separator.
    ("Bosnia-Herzegovina vs. Wales - Bosnia-Herzegovina Starting 11", "Wales"),
    ("Mali vs. Guinea-Bissau - Guinea-Bissau Starting 11", "Guinea-Bissau"),
    ("Guinea-Bissau vs. Mali - Mali Starting 11", "Mali"),
]


@pytest.mark.parametrize("name,_away", STARTING_ELEVEN)
def test_a_lineup_prop_is_a_derivative(name, _away):
    assert is_derivative_market_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Croatia vs. England",
        "Bosnia-Herzegovina vs. Wales",
        "FC Thun vs. Lausanne-Sport",
        "Mets vs. Dodgers - Game 4",
        "CF Estrela da Amadora vs. FC Porto - More Markets",
    ],
)
def test_the_fixtures_themselves_are_not(name):
    """The controls #2871 already pins, re-asserted against the widened pattern."""
    assert is_derivative_market_name(name) is False


@pytest.mark.parametrize("name,away", STARTING_ELEVEN)
def test_the_link_search_looks_for_the_real_away_team(name, away):
    """#6134's half of the contract: the prop attaches to the fixture we hold."""
    search = matchup_for_link_search(extract_matchup(name), name)
    assert search is not None
    assert search.team_b == away


def test_the_pattern_stays_postgres_safe():
    """The repair runs this pattern with `~*` in Postgres. ARE reads a mixed
    greedy/lazy expression differently from Python, and `\\S`/`\\W`/`\\D` are
    illegal inside a bracket there. Measured on production 2026-09-26: the widened
    pattern adds exactly the 55 phantom rows and strips each to the same name
    Python does."""
    pattern = _DERIVATIVE_SUFFIX_RE.pattern
    assert not re.search(r"[+*?}]\?", pattern), "a lazy quantifier crept in"
    for bracket in re.findall(r"\[[^\]]*\]", pattern):
        assert not re.search(r"\\[SWD]", bracket), f"negated class escape in {bracket}"


def test_the_repair_population_is_the_same_vocabulary():
    scripts = pathlib.Path(__file__).resolve().parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location(
        "repair_2871_phantom_derivative_events",
        scripts / "repair_2871_phantom_derivative_events.py",
    )
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)

    assert repair.DERIV_RE == _DERIVATIVE_SUFFIX_RE.pattern
    assert re.search(repair.DERIV_RE, "England - Croatia Starting 11", re.IGNORECASE)
    assert re.sub(repair.DERIV_RE, "", "England - Croatia Starting 11", flags=re.IGNORECASE) == "England"
