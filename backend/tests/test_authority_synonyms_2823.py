"""The dozen clubs ESPN simply calls something else. #2823.

``AUTHORITY_SYNONYMS`` is the one place this codebase states, by hand, that two
team names are one club. Everything else in ``authority_name_forms`` is a
structural reduction that can be argued from the shape of a string; these
twelve cannot be, which is why they are a lookup and not a rule, and why they
need guards of their own.

═══ WHAT THESE TESTS ARE SHAPED TO CATCH ═══

**Vacuity, first and loudest.** A guard over a hand-written list must not
iterate that list — empty the list and an iterating test's body never runs, so
it passes. That is not hypothetical: it is exactly the defect
``test_the_affix_list_is_observable`` shipped with, measured and fixed in the
same change as this file. So every case below is driven from
:data:`EXPECTED_SYNONYMS`, a literal declared HERE, and
:func:`test_the_shipped_table_is_the_table_this_suite_proves` asserts the two
are equal.

**Asymmetry**, because a synonym is a claim about what the authority calls a
team we hold, and the converse is not implied.

**Scope**, because the table is keyed on sport and a missing key must fail
closed rather than fall back to a global match.

**The one row that must never agree.** E416569 sits in the same 17
disagreements these entries were drawn from, and it is a real mis-anchor. It
has its own guard in ``test_authority_name_forms.py``; the case here is the
narrower one — that no synonym entry moved it.
"""

from __future__ import annotations

import pytest

from app.utils.authority_id_collisions import (
    AuthorityRecord,
    CandidateRow,
    _teams_agree,
    authority_names,
)
from app.utils.authority_name_forms import (
    AUTHORITY_SYNONYMS,
    canonical_forms,
    synonym_forms,
)
from app.utils.name_normalization import normalize_team_name_for_matching

#: The table as this suite expects to find it, declared HERE as a literal.
#:
#: Every row was measured on production 2026-09-03 by
#: ``scripts/audit_anchor_schedule.py --verdict teams_disagree`` over the whole
#: 685-row anchored window, and each one is a fixture the rail refused to
#: correct purely because we and ESPN spell a team differently.
EXPECTED_SYNONYMS = {
    ("americanfootball_ncaaf", "appalachian state mountaineers"): (
        "app state mountaineers"
    ),
    ("americanfootball_ncaaf", "southern mississippi golden eagles"): (
        "southern miss golden eagles"
    ),
    ("americanfootball_ncaaf", "southeastern louisiana lions"): "se louisiana lions",
    ("americanfootball_ncaaf", "nicholls state colonels"): "nicholls colonels",
    ("americanfootball_ncaaf", "sam houston state bearkats"): "sam houston bearkats",
    ("soccer_spain_la_liga", "athletic bilbao"): "athletic club",
    ("soccer_spain_la_liga", "real racing club de santander"): "racing santander",
    ("soccer_usa_mls", "new york red bulls"): "red bull new york",
    ("soccer_uefa_champs_league", "lask"): "lask linz",
    ("soccer_uefa_champs_league", "sporting lisbon"): "sporting cp",
    ("soccer_uefa_champs_league", "slavia praha"): "slavia prague",
    ("soccer_germany_bundesliga", "hamburger sv"): "hamburg sv",
}

#: The real refused fixtures, as the census printed them: the row's own two
#: names, ESPN's two names, and the sport. Each is one of the 16 rows this
#: change exists to clear, with the event id kept so a reader can go and look.
REFUSED_FIXTURES = [
    (
        15297186,
        "soccer_spain_la_liga",
        "Athletic Bilbao",
        "Atlético Madrid",
        "Athletic Club",
        "Atlético Madrid",
    ),
    (
        15296364,
        "soccer_spain_la_liga",
        "Rayo Vallecano",
        "Real Racing Club de Santander",
        "Rayo Vallecano",
        "Racing Santander",
    ),
    (
        15298235,
        "soccer_spain_la_liga",
        "Real Racing Club de Santander",
        "Alavés",
        "Racing Santander",
        "Alavés",
    ),
    (
        15298237,
        "soccer_spain_la_liga",
        "Athletic Bilbao",
        "Elche CF",
        "Athletic Club",
        "Elche",
    ),
    (
        15181917,
        "americanfootball_ncaaf",
        "Appalachian State Mountaineers",
        "Maine Black Bears",
        "App State Mountaineers",
        "Maine Black Bears",
    ),
    (
        15181920,
        "americanfootball_ncaaf",
        "Southern Mississippi Golden Eagles",
        "Alcorn State Braves",
        "Southern Miss Golden Eagles",
        "Alcorn State Braves",
    ),
    (
        15181941,
        "americanfootball_ncaaf",
        "South Alabama Jaguars",
        "Southeastern Louisiana Lions",
        "South Alabama Jaguars",
        "SE Louisiana Lions",
    ),
    (
        15181940,
        "americanfootball_ncaaf",
        "Kansas State Wildcats",
        "Nicholls State Colonels",
        "Kansas State Wildcats",
        "Nicholls Colonels",
    ),
    (
        14793425,
        "americanfootball_ncaaf",
        "Troy Trojans",
        "Sam Houston State Bearkats",
        "Troy Trojans",
        "Sam Houston Bearkats",
    ),
    (
        15291069,
        "soccer_usa_mls",
        "Seattle Sounders FC",
        "New York Red Bulls",
        "Seattle Sounders FC",
        "Red Bull New York",
    ),
    (
        15301194,
        "soccer_usa_mls",
        "Columbus Crew SC",
        "New York Red Bulls",
        "Columbus Crew",
        "Red Bull New York",
    ),
    (
        15296749,
        "soccer_uefa_champs_league",
        "AEK Athens",
        "LASK",
        "AEK Athens",
        "LASK Linz",
    ),
    (
        15296759,
        "soccer_uefa_champs_league",
        "Sporting Lisbon",
        "Galatasaray",
        "Sporting CP",
        "Galatasaray",
    ),
    (
        15296765,
        "soccer_uefa_champs_league",
        "Slavia Praha",
        "RC Lens",
        "Slavia Prague",
        "Lens",
    ),
    (
        15297805,
        "soccer_germany_bundesliga",
        "RB Leipzig",
        "Hamburger SV",
        "RB Leipzig",
        "Hamburg SV",
    ),
]


def _espn(display: str) -> dict:
    """A competitor block holding only what ESPN's label gives us.

    Deliberately thin. The census recorded ESPN's rendered label, not the whole
    competitor object, and inventing ``location``/``nickname`` values to pad it
    out would let :func:`composed_forms` carry a case the synonym table is
    supposed to carry — the test would pass with the table deleted.
    """
    return {"displayName": display, "name": display}


def _agrees(sport: str, home: str, away: str, espn_home: str, espn_away: str) -> bool:
    record = AuthorityRecord(
        authority_id="401000000",
        home_names=authority_names({"team": _espn(espn_home)}),
        away_names=authority_names({"team": _espn(espn_away)}),
        label=f"{espn_home} v {espn_away}",
    )
    row = CandidateRow(
        event_id=1, sport_key=sport, home_team_name=home, away_team_name=away
    )
    agrees, _inverted, _channel = _teams_agree(row, record)
    return agrees


# ── 1. NON-VACUITY: the table itself is observed ────────────────────────────


def test_the_shipped_table_is_the_table_this_suite_proves():
    """Emptying, shrinking or quietly growing ``AUTHORITY_SYNONYMS`` fails here.

    The reason this assertion exists rather than a loop over the shipped table:
    a loop over a hand-written list is blind to that list being emptied, which
    is the defect ``test_the_affix_list_is_observable`` shipped with. Every
    other test in this file iterates :data:`EXPECTED_SYNONYMS`.
    """
    assert AUTHORITY_SYNONYMS == EXPECTED_SYNONYMS, (
        "the shipped synonym table differs from the one these tests prove. Each "
        "entry needs a production row that the rail refused — re-derive with "
        "scripts/audit_anchor_schedule.py --verdict teams_disagree"
    )


# ── 2. THE 15 REFUSED FIXTURES NOW AGREE ────────────────────────────────────


@pytest.mark.parametrize(
    "event_id,sport,home,away,espn_home,espn_away",
    REFUSED_FIXTURES,
    ids=[f"E{f[0]}" for f in REFUSED_FIXTURES],
)
def test_a_refused_fixture_now_agrees(
    event_id, sport, home, away, espn_home, espn_away
):
    """Each is a real row the rail declined to correct on 2026-09-03."""
    assert _agrees(sport, home, away, espn_home, espn_away)


def test_every_table_entry_is_exercised_by_a_refused_fixture():
    """No entry may be here without a row that needed it.

    The standing rule of this module — an entry nobody can point at a row for is
    an entry that grows a list until it collides. This is that rule as a test
    rather than a comment, and it is what stops the table becoming a dumping
    ground for plausible-looking aliases.
    """
    exercised = set()
    for _id, sport, home, away, _eh, _ea in REFUSED_FIXTURES:
        for name in (home, away):
            key = (sport, normalize_team_name_for_matching(name))
            if key in EXPECTED_SYNONYMS:
                exercised.add(key)
    assert exercised == set(EXPECTED_SYNONYMS), (
        "entries with no refused fixture behind them: "
        f"{sorted(set(EXPECTED_SYNONYMS) - exercised)}"
    )


# ── 3. THE SHAPES THAT WOULD MAKE IT A RULE ─────────────────────────────────


def test_a_synonym_is_directional():
    """ESPN's spelling does not gain OUR spelling.

    Knowing ESPN calls our ``Sporting Lisbon`` ``Sporting CP`` says nothing
    about how to read a row we stored as ``Sporting CP``. A table that answered
    both ways would be a symmetric equivalence, which is a rule.
    """
    for (sport, ours), theirs in EXPECTED_SYNONYMS.items():
        assert synonym_forms(ours, sport), f"{ours} should map"
        assert not synonym_forms(theirs, sport), f"{theirs} must not map back"


def test_a_synonym_is_scoped_to_its_sport():
    """A missing sport key fails closed, it does not fall back to a global match.

    ``Sporting Lisbon`` has 26 rows in ``soccer_portugal_primeira_liga`` against
    the 5 Champions League rows that earned its entry (measured 2026-09-03).
    Those rows are NOT covered, deliberately — none of them produced a refusal,
    so an entry for them would be a guess. This test pins that as a decision
    rather than leaving it to be discovered as a surprise.
    """
    assert synonym_forms("Sporting Lisbon", "soccer_uefa_champs_league")
    assert not synonym_forms("Sporting Lisbon", "soccer_portugal_primeira_liga")
    assert not synonym_forms("Athletic Bilbao", "soccer_other")


def test_a_synonym_never_chains():
    """``A -> B`` and ``B -> C`` must not combine into ``A -> C``.

    The target is expanded through ``canonical_forms``, which does not consult
    the table, so one hop is all there is. Asserted over the real table: no
    entry's target is itself a key.
    """
    for (sport, _ours), theirs in EXPECTED_SYNONYMS.items():
        assert (sport, theirs) not in EXPECTED_SYNONYMS, f"{theirs} chains"


def test_an_unlisted_name_gains_nothing():
    """The control. Without it, every case above could pass on a blanket rule."""
    for sport in {s for s, _ in EXPECTED_SYNONYMS}:
        assert not synonym_forms("Some Unlisted Rovers", sport)
    assert not synonym_forms("", "soccer_usa_mls")
    assert not synonym_forms(None, "soccer_usa_mls")
    assert not synonym_forms("Athletic Bilbao", None)


def test_the_target_is_reduced_the_same_way_both_sides_are():
    """The mapped spelling goes through ``canonical_forms``, not in raw.

    Otherwise a target carrying a club initialism would compare unequal to the
    authority's own reduced form, and the entry would silently do nothing.
    """
    for (sport, ours), theirs in EXPECTED_SYNONYMS.items():
        assert synonym_forms(ours, sport) == canonical_forms(theirs)


# ── 4. AND THE ROW THAT MUST STILL REFUSE ───────────────────────────────────


def test_the_mis_anchor_2792_did_not_move():
    """E416569 was in the same 17. Nothing here may reach it.

    Ohio State @ Texas wearing *Texas v Texas State*'s id. ``Texas`` matches
    ``Texas``, so the verdict rests entirely on ``Ohio State Buckeyes`` staying
    away from ``Texas State Bobcats``.
    """
    assert not _agrees(
        "americanfootball_ncaaf",
        "Texas Longhorns",
        "Ohio State Buckeyes",
        "Texas Longhorns",
        "Texas State Bobcats",
    )


def test_houston_baptist_is_not_quietly_aliased():
    """The rename stays refused until the stored row is corrected.

    Houston Baptist University became Houston Christian University in 2022. An
    alias would make the rail agree while leaving a four-year-stale name on
    every surface a user reads, so this row is a data fix and is meant to keep
    failing until someone does it.
    """
    assert (
        "americanfootball_ncaaf",
        "houston baptist huskies",
    ) not in AUTHORITY_SYNONYMS
    assert not _agrees(
        "americanfootball_ncaaf",
        "Rice Owls",
        "Houston Baptist Huskies",
        "Rice Owls",
        "Houston Christian Huskies",
    )
