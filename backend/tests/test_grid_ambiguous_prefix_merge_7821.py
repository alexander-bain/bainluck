"""#7821 — an ambiguous short name is settled by the venue's ticker, not by length.

Kalshi's bracket outcome is `Florida`; ours are `Florida Gators` and `Florida
Atlantic Owls`. The grid used to bind the LONGEST match, which is systematically
the more-qualified sibling — always a different institution. The reader saw
Florida, the #1 overall seed, blank across all five bracket columns while
Miami (OH) was served Miami (FL)'s prices (a 0.06% champion shown with an 8.5%
chance of reaching the title game).

THE TRAP THESE TESTS ARE BUILT AROUND: a test that exercises `Duke` cannot fail
against this defect, because `duke` has exactly one candidate and every tiebreak
rule agrees on a set of one. Every assertion below is on a name with TWO OR MORE
candidates, and the no-anchor cases are pinned as hard as the anchored ones —
the "fewest remaining words" rule that was measured and rejected got Florida
right and traded away California and North Carolina, so a fix that swaps one
correct answer for another must fail here.

Population numbers quoted in the fixtures are the live NCAAB key set measured
2026-09-21: 351 keys, 105 merges, and old→new is LOST=0 ADDED=0 CHANGED=4.
"""

import pytest

from app.routes.playoffs import (
    _canon_ticker,
    _resolve_ambiguous_merge,
    _should_prefix_merge,
    _ticker_suffix,
)

# The real NCAAB abbreviations, as measured on production 2026-09-21.
# `florida atlantic owls` and `texas a&m-cc islanders` genuinely have none —
# that absence is data, not a gap in the fixture.
ABBREV = {
    "florida gators": "FLA",
    "florida st seminoles": "FSU",
    "miami hurricanes": "MIA",
    "miami (oh) redhawks": "M-OH",
    "texas longhorns": "TEX",
    "texas a&m aggies": "TA&M",
    "ole miss rebels": "MISS",
    "mississippi st bulldogs": "MSST",
    "north carolina tar heels": "UNC",
    "california golden bears": "MIA",  # yes, really — see test_corrupt_abbreviation_*
    "california baptist lancers": "CBU",
}

# Candidate lists arrive LONGEST-FIRST, exactly as the route builds them, so
# element 0 is what the old rule bound.
FLORIDA = ["florida atlantic owls", "florida gators"]
MIAMI = ["miami (oh) redhawks", "miami hurricanes"]
TEXAS = ["texas a&m-cc islanders", "texas longhorns"]
OLE_MISS = ["mississippi st bulldogs", "ole miss rebels"]


def _resolve(short, candidates, suffix=None, abbrev=ABBREV):
    suffixes = {short: {suffix}} if suffix else {}
    return _resolve_ambiguous_merge(short, candidates, suffixes, abbrev)


# ---------------------------------------------------------------------------
# The anchored cases — the ticker beats the longest match
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "short,candidates,suffix,expected",
    [
        ("florida", FLORIDA, "FLA", "florida gators"),
        ("miami", MIAMI, "MIA", "miami hurricanes"),
        ("texas", TEXAS, "TEX", "texas longhorns"),
        ("ole miss", OLE_MISS, "MISS", "ole miss rebels"),
    ],
)
def test_ticker_suffix_settles_an_ambiguous_name(short, candidates, suffix, expected):
    """All four are live mis-merges; all four resolve to the school the venue meant."""
    assert _resolve(short, candidates, suffix) == expected
    # And prove the assertion is not vacuous: the old rule really did differ.
    assert candidates[0] != expected


def test_florida_and_north_carolina_and_california_hold_in_one_test():
    """The one-test-three-names guard the issue asks for.

    A tiebreak that fixes Florida by preferring the *fewest remaining words*
    scores Florida correct and then sends North Carolina to NC State and
    California to California Baptist. Pinning all three together is what makes
    that trade impossible to land green.
    """
    assert _resolve("florida", FLORIDA, "FLA") == "florida gators"

    # No ticker: North Carolina keeps the answer it already had.
    nc = ["north carolina tar heels", "north carolina a&t aggies"]
    assert _resolve("north carolina", nc) == "north carolina tar heels"

    # No ticker: California keeps the answer it already had.
    cal = ["california golden bears", "california baptist lancers"]
    assert _resolve("california", cal) == "california golden bears"


# ---------------------------------------------------------------------------
# The refusals — the anchor must stay silent rather than guess
# ---------------------------------------------------------------------------

def test_no_ticker_keeps_todays_answer():
    """odds_api supplies no ticker, so an odds-only family must not move.

    This is the arm that stops a future tiebreak being smuggled in under the
    anchor: with no suffix the function may only return `candidates[0]`.
    """
    assert _resolve("florida", FLORIDA) == "florida atlantic owls"


def test_ticker_matching_no_candidate_keeps_todays_answer():
    """`TXAM` is the venue's Texas A&M; ours is abbreviated `TA&M`.

    They do not compare equal, so the anchor declines and the known-wrong
    length answer stands. Recorded deliberately: this is the one live NCAAB
    family #7821 does NOT repair, and a later fix for it must change this
    assertion on purpose rather than discover it.
    """
    txam = ["texas a&m-cc islanders", "texas a&m aggies"]
    assert _resolve("texas a&m", txam, "TXAM") == "texas a&m-cc islanders"


def test_ticker_matching_two_candidates_keeps_todays_answer():
    """Two hits means we do not know, and "we do not know" may not pick one."""
    both = ["miami (oh) redhawks", "miami hurricanes"]
    abbrev = {"miami (oh) redhawks": "MIA", "miami hurricanes": "MIA"}
    assert _resolve("miami", both, "MIA", abbrev) == "miami (oh) redhawks"


def test_corrupt_abbreviation_cannot_reach_outside_its_own_family():
    """`California Golden Bears` really does carry `abbreviation='MIA'` in prod.

    That is why the abbreviation is only ever used to choose among candidates a
    name rule already produced, never as a lookup on its own: a `MIA` ticker
    cannot pull California onto the Miami row, because California is not a
    candidate for `miami`.
    """
    assert "california golden bears" not in MIAMI
    assert _resolve("miami", MIAMI, "MIA") == "miami hurricanes"


def test_a_candidate_with_no_abbreviation_is_not_preferred_for_having_none():
    """Absence of identity is not evidence either way — it just does not vote."""
    assert _resolve("florida", FLORIDA, "ZZZ") == "florida atlantic owls"


# ---------------------------------------------------------------------------
# The predicate that was documented but not implemented
# ---------------------------------------------------------------------------

def test_location_modifier_guard_applies_to_multi_word_short_names():
    """`_should_prefix_merge`'s docstring claimed this before it did it.

    The old body returned True for any multi-word short name before reaching
    the modifier check, so `north carolina` prefix-matched `north carolina st`.
    This assertion fails against the pre-#7821 function.
    """
    assert _should_prefix_merge("north carolina", "north carolina st") is False
    assert _should_prefix_merge("michigan", "michigan st spartans") is False
    # ...and a real mascot remainder still merges, in both word counts.
    assert _should_prefix_merge("north carolina", "north carolina tar heels") is True
    assert _should_prefix_merge("florida", "florida gators") is True


# ---------------------------------------------------------------------------
# Ticker parsing
# ---------------------------------------------------------------------------

def test_ticker_suffix_splits_on_the_market_ticker_not_the_last_dash():
    """Loyola Chicago is `…-27R32-L-IL`; splitting on the last `-` yields `IL`."""
    assert _ticker_suffix("KXMARMADROUND-27R32-L-IL", "KXMARMADROUND-27R32") == "L-IL"
    assert _ticker_suffix("KXMARMADROUND-27R32-FLA", "KXMARMADROUND-27R32") == "FLA"


def test_odds_api_external_ids_contribute_no_anchor():
    """odds_api stores the outcome NAME in `external_id`, so it never anchors."""
    assert _ticker_suffix("Florida Gators", "basketball_ncaab_championship_winner") is None
    assert _ticker_suffix(None, "KXMARMADROUND-27R32") is None
    assert _ticker_suffix("KXMARMADROUND-27R32-FLA", None) is None
    # A bare market ticker with an empty tail is not a suffix.
    assert _ticker_suffix("KXMARMADROUND-27R32-", "KXMARMADROUND-27R32") is None


def test_canon_ticker_folds_case_and_punctuation():
    assert _canon_ticker("TA&M") == _canon_ticker("ta&m") == "TAM"
    # ...and the venue's own spelling of the same school does not fold onto it,
    # which is exactly why `texas a&m` is still unrepaired above.
    assert _canon_ticker("TXAM") != _canon_ticker("TA&M")
    assert _canon_ticker("M-OH") == "MOH"
    assert _canon_ticker(None) == ""
