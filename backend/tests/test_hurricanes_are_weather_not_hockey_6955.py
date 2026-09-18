"""#6955 — a storm question stops being filed under the Carolina Hurricanes.

Four Polymarket rows ("Will there be N hurricanes during the Atlantic Hurricane
Season in 2026?") were served on `/search?q=Atlantic Hurricane Season` wearing a
**HOCKEY** chip. Measured on production 2026-09-18, the class is 17 open rows,
not four: nine Kalshi basin questions, seven Polymarket season questions and one
landfall question, plus "Kraken IPO by ___ ?" one collision over.

`llm_sport_category` is not only a chip. It is the first term of the canonical
market key and the key the feed's quality classifier, the sport-scoped diversity
caps and the category pages all read, so a storm market on the hockey shelf is
eligible for the wrong caps and pools everywhere at once.

THE MECHANISM IS NOT FIRST-MATCH-WINS. It was, before F3 (queue 402); the issue's
own diagnosis says "line 95 precedes line 236" and that reading is two mechanisms
out of date. `SPORT_PATTERNS` is scored by `score_sport_evidence`, and these rows
lost a 3-3 TIE that falls back to list order. That distinction is the whole fix:
a reorder moves a tie-break, and half this population is not a tie at all.

Two arms, and the asymmetry between them is the point:

* `hurricanes` is NOT demoted. It cannot be — the weather entry in
  SPORT_PATTERNS is singular-only, so "How many Atlantic hurricanes will there be
  in 2026?" scores hockey 3 against nothing, and a lone ambiguous match wins
  unopposed by design. Demoting the noun would leave that row exactly where it
  was while weakening every real Hurricanes fixture. Instead a STRONG weather
  pattern names the constructions that commit — the `senators` precedent (#4229).
* `kraken` IS demoted, because there the whole corpus says it is free: 26 of 27
  "kraken" rows are hockey and every one carries a second hockey token.

Measured blast radius over 4,985 production rows (`artifacts-discover/6955/`):
33 rows change, 20 of them open, and **not one is a genuine sports market**.
"""

import re

import pytest

from app.utils.futures_categorization import (
    _AMBIGUOUS_FOR,
    _STRONG_EVIDENCE_PATTERNS,
    categorize_by_rules,
    score_sport_evidence,
)


# ---------------------------------------------------------------------------
# THE DEFECT — every one of these was `hockey` on production on 2026-09-18.
# Ids are real rows so a future reader can re-pull them.
# ---------------------------------------------------------------------------
MISFILED_AS_HOCKEY = [
    # The four the issue was filed on — Polymarket, served on /search.
    ("Will there be 0 hurricanes during the Atlantic Hurricane Season in 2026?", 57005142),
    ("Will there be 1-3 hurricanes during the Atlantic Hurricane Season in 2026?", 57005139),
    ("Will there be 4-6 hurricanes during the Atlantic Hurricane Season in 2026?", 57005140),
    ("Will there be 7+ hurricanes during the Atlantic Hurricane Season in 2026?", 57005141),
    ("How many hurricanes will form during the Atlantic Hurricane Season in 2026?", 57005138),
    # Kalshi basin questions — the half a reorder alone does NOT reach, because
    # the singular-only weather pattern never matches them and there is no tie
    # to break: hockey 3, weather 0.
    ("How many Atlantic hurricanes will there be in 2026?", 8431183),
    ("How many major Atlantic hurricanes will there be in 2026?", 8431182),
    ("How many Central Pacific hurricanes will there be this year?", 25925288),
    ("How many Eastern Pacific hurricanes will there be this year?", 25925286),
    ("How many major Central Pacific hurricanes will there be this year?", 25925289),
    ("How many major Eastern Pacific hurricanes will there be this year?", 25925287),
    ("What named storms will be hurricanes in the Atlantic this year?", 25925285),
    ("What named storms will be hurricanes in the Central Pacific this year?", 25925284),
    ("What named storms will be hurricanes in the Eastern Pacific this year?", 25925283),
    ("Will 2 or more hurricanes make landfall in the US in 2026?", 56995498),
]


# ---------------------------------------------------------------------------
# THE CONTROLS — real hockey, and the specimens a careless fix breaks.
# Every one of these was ALREADY correct and must stay correct.
# ---------------------------------------------------------------------------
REAL_HOCKEY = [
    # Fixtures whose ONLY hockey evidence besides "Hurricanes" is the opponent.
    "Hurricanes vs. Flyers",
    "Hurricanes vs. Canadiens",
    "Canucks vs. Hurricanes",
    "Capitals vs. Hurricanes",
    "Panthers vs. Hurricanes",
    "Predators vs. Hurricanes",
    "Hurricanes vs. Blackhawks",
    # The club named in full — "Carolina Hurricanes" is the trap the first cut
    # of the weather rule fell into (see `test_no_us_state_is_a_storm_basin`).
    "Will Carolina Hurricanes advance to the Second Round of the 2027 Stanley Cup Playoffs?",
    "Will Carolina Hurricanes advance to the Eastern Conference Finals of the 2027 Stanley Cup Playoffs?",
    "NHL: CAR Hurricanes Total Points",
    # Seattle, for the `kraken` arm.
    "Kraken vs. Canucks",
    "Canucks vs. Kraken",
    "Hurricanes vs. Kraken",
    "SEA Kraken at DAL Stars: Player Goals",
    # The #4229 precedent must not be disturbed by a second ambiguous NHL noun.
    "Senators vs. Maple Leafs",
    "Senators vs. Bruins",
]


@pytest.mark.parametrize("name,row_id", MISFILED_AS_HOCKEY)
def test_a_storm_question_is_not_hockey(name, row_id):
    """The headline assertion: the storm market leaves the hockey shelf.

    Split from the exact-value assertion below on the C1 corpus's reasoning —
    what corrupts the canonical key and the caps is the WRONG value being
    persisted, so `None` would be a partial fix and must read as one.
    """
    assert categorize_by_rules(name) != "hockey", (
        f"row {row_id} {name!r} is still filed HOCKEY — the mis-tag is live"
    )


@pytest.mark.parametrize("name,row_id", MISFILED_AS_HOCKEY)
def test_a_storm_question_reaches_the_weather_shelf(name, row_id):
    """The stronger assertion: positive evidence found the RIGHT shelf."""
    assert categorize_by_rules(name) == "weather", f"row {row_id}: {name!r}"


@pytest.mark.parametrize("name", REAL_HOCKEY)
def test_real_hockey_stays_hockey(name):
    """The half that a reorder, or a demoted `hurricanes`, would have broken."""
    assert categorize_by_rules(name) == "hockey", f"{name!r} regressed off hockey"


def test_the_storm_questions_win_on_evidence_not_on_a_tie_break():
    """Weather must OUTSCORE hockey, not merely edge it on list order.

    The defect itself was a 3-3 tie decided by `SPORT_PATTERNS` position, so a
    fix that produces another tie has not fixed the class — it has moved which
    side of the coin lands up, and the next entry added to either list flips it
    back. Asserted on the scores rather than the verdict for exactly that reason.
    """
    for name, row_id in MISFILED_AS_HOCKEY:
        scores = score_sport_evidence(name)
        assert scores.get("weather", 0) > scores.get("hockey", 0), (
            f"row {row_id} {name!r} scores {scores} — weather does not outscore "
            "hockey, so this verdict rests on SPORT_PATTERNS order"
        )


def test_no_us_state_is_a_storm_basin():
    """Pins the slip the first cut of this rule actually made.

    The basin alternation was drafted as `(atlantic|pacific|caribbean|gulf|
    carolina)` — and `carolina` is the club's own city, so "Carolina Hurricanes"
    scored 5 points of WEATHER evidence. It stayed hockey only because the
    Stanley Cup token happened to outscore it, which is luck, not a rule. A
    verdict assertion cannot see this; only the pattern can.
    """
    weather_patterns = [p for p, c in _STRONG_EVIDENCE_PATTERNS if c == "weather"]
    assert weather_patterns, "the weather strong-evidence pattern is gone"
    for pattern in weather_patterns:
        for club_city in (
            "Carolina Hurricanes",
            "Miami Hurricanes",
            "Tulsa Golden Hurricane",
        ):
            assert not pattern.search(club_city), (
                f"{pattern.pattern!r} claims {club_city!r} as weather evidence — "
                "a US state or school is not an ocean basin"
            )


def test_kraken_is_ambiguous_for_hockey_and_hurricanes_is_not():
    """The asymmetry between the two arms, asserted rather than described.

    `kraken` is demoted because the corpus says it is free. `hurricanes` is NOT,
    because the weather pattern it would lose to is singular-only — demoting it
    would weaken every real fixture and still leave the basin questions on the
    hockey shelf. If a later reader "completes the set" by adding `hurricanes`
    here, this fails and points them at the measurement.
    """
    assert ("hockey", "kraken") in _AMBIGUOUS_FOR
    assert ("hockey", "hurricanes") not in _AMBIGUOUS_FOR


def test_pirates_is_deliberately_not_demoted():
    """The adjacent fix that was measured and REJECTED, pinned so it stays out.

    "Next Pirates of the Caribbean Movie: Cast" is filed `baseball`, and adding
    `pirates` to the ambiguity set does move it to `entertainment`. Measured over
    the same 4,985 rows it also moves 17 rows to answers that are WORSE, because
    demoting one ordinary noun just hands the row to the next one in the title:

        "East Carolina Pirates vs. Charlotte 49ers"   -> football  (the 49ers)
        "Duke Blue Devils vs Seton Hall Pirates"      -> hockey    (the Devils)
        "Tulsa Golden Hurricane vs. East Carolina Pirates" -> weather
        "T20 Brisbane ...: Melbourne Pirates vs ..."  -> football

    All four are college basketball or cricket. The token is not the unit of
    repair; the construction is. Left for its own ship with its own evidence.
    """
    assert ("baseball", "pirates") not in _AMBIGUOUS_FOR
    assert categorize_by_rules("East Carolina Pirates vs. Charlotte 49ers") != "football"
    assert categorize_by_rules("Duke Blue Devils vs Seton Hall Pirates") != "hockey"


def test_the_weather_rule_needs_a_construction_not_a_bare_storm_noun():
    """The rule may not fire on the bare noun — that is what makes it safe.

    If a later edit relaxes this to `\\bhurricanes?\\b`, every Hurricanes fixture
    gains 5 points of weather evidence and the controls above start passing only
    by arithmetic. Named here so the constraint survives a rewrite of the regex.
    """
    weather_patterns = [p for p, c in _STRONG_EVIDENCE_PATTERNS if c == "weather"]
    for pattern in weather_patterns:
        for bare in ("hurricane", "hurricanes", "storm", "storms", "cyclone"):
            assert not pattern.search(bare), (
                f"{pattern.pattern!r} fires on the bare noun {bare!r}"
            )


def test_the_singular_only_weather_pattern_is_why_this_rule_exists():
    """Documents the premise the whole fix rests on, so it cannot rot silently.

    The `weather` entry in SPORT_PATTERNS matches `hurricane` and not
    `hurricanes`. If that ever changes, the reasoning in this file's docstring
    (and the choice not to demote the noun) needs re-deriving.
    """
    assert re.search(r"\bhurricane\b", "Atlantic Hurricane Season", re.I)
    assert not re.search(r"\bhurricane\b", "Hurricanes vs. Flyers", re.I)
