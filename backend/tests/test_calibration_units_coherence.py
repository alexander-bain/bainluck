"""The units-coherence guard (Fable ruling, CAL-P068 — banking CAL-P067's near-miss).

CAL-P067 came within one line of populating the selection-bias census from the
#1912 MC pack's per-category table. The numbers looked made for each other:
soccer reads 34,619 graded of 138,650, i.e. **25.0%** — precisely the figure the
ruling quotes when it says soccer flips immediately.

They are not the same population, and not even the same UNIT:

* the MC pack's census is **MARKET**-level and **Polymarket-`0x`-only**
* a published calibration cell's ``n`` is **OUTCOME**-level and **all-source**

Dividing the cell's 98,381 outcomes by the census's 138,650 markets yields
**0.7096**. Measured against the pre-guard code, that did not merely slip past
the incoherence check — it returned ``provable``. A confident PASS, computed
from two different populations in two different units, on a public page.

The existing guard only refuses a share **above 1.0**, and a market-level
numerator over an outcome-level denominator lands plausibly below it. Ratios do
not carry units, so no amount of range-checking a ratio can catch this. The
only thing that can is refusing to compute one until both sides have DECLARED
what they count — which is what this suite pins.
"""

import pytest

from app.utils.calibration_provability import (
    PROVABILITY_PROVABLE,
    PROVABILITY_UNKNOWN,
    UNIT_MARKETS,
    UNIT_OUTCOMES,
    GradedShareCensus,
    annotate_cells,
)

# The exact numbers from the near-miss.
SOCCER_CELL_OUTCOMES = 98_381
SOCCER_PM_MARKETS = 138_650
SOCCER_ALL_SOURCE_OUTCOMES = 393_524


def _cells():
    return [{"category": "soccer", "mce": 3.54, "n": SOCCER_CELL_OUTCOMES}]


def test_the_exact_near_miss_is_now_refused():
    """The one this exists for. A market-level census must never annotate an
    outcome-level cell, however plausible the ratio looks."""
    census = GradedShareCensus(
        by_key={"soccer": SOCCER_PM_MARKETS},
        unit=UNIT_MARKETS,
        population="polymarket_0x_resolved",
    )
    out = annotate_cells(_cells(), census=census)
    assert out[0]["provability"] == PROVABILITY_UNKNOWN
    assert out[0]["graded_share"] is None
    why = out[0]["provability_reason"]
    assert "unit" in why.lower()
    assert UNIT_MARKETS in why and UNIT_OUTCOMES in why


def test_a_matching_unit_census_annotates_normally():
    census = GradedShareCensus(
        by_key={"soccer": SOCCER_ALL_SOURCE_OUTCOMES},
        unit=UNIT_OUTCOMES,
        population="all_sources_resolved",
    )
    out = annotate_cells(_cells(), census=census)
    assert out[0]["provability"] == "not_provable_selection_biased"
    assert out[0]["graded_share"] == pytest.approx(0.25, abs=0.001)


def test_a_provable_cell_still_reads_provable_through_the_guard():
    census = GradedShareCensus(
        by_key={"baseball": 200_000}, unit=UNIT_OUTCOMES, population="all_sources_resolved"
    )
    out = annotate_cells(
        [{"category": "baseball", "n": 192_090}], census=census
    )
    assert out[0]["provability"] == PROVABILITY_PROVABLE


def test_the_refusal_is_per_census_not_per_cell():
    """A mismatched census poisons every cell it touches, not just the one
    someone happened to look at."""
    census = GradedShareCensus(
        by_key={"soccer": 1, "baseball": 2, "tennis": 3},
        unit=UNIT_MARKETS,
        population="polymarket_0x_resolved",
    )
    out = annotate_cells(
        [{"category": c, "n": 100} for c in ("soccer", "baseball", "tennis")],
        census=census,
    )
    assert {c["provability"] for c in out} == {PROVABILITY_UNKNOWN}


def test_a_census_must_declare_its_unit_at_construction():
    """An undeclared unit is the state the guard exists to make unreachable, so
    it cannot be defaulted into existence."""
    with pytest.raises((TypeError, ValueError)):
        GradedShareCensus(by_key={"soccer": 1})  # no unit
    with pytest.raises(ValueError):
        GradedShareCensus(by_key={"soccer": 1}, unit="widgets", population="x")


def test_a_census_must_declare_its_population():
    with pytest.raises((TypeError, ValueError)):
        GradedShareCensus(by_key={"soccer": 1}, unit=UNIT_OUTCOMES)


def test_a_source_scoped_population_is_refused_against_an_all_source_cell():
    """Right unit, wrong population. Published cells pool every source, so a
    Polymarket-only denominator understates the graded share of every cell it
    touches — the same error as the unit mismatch, one axis over."""
    census = GradedShareCensus(
        by_key={"soccer": SOCCER_ALL_SOURCE_OUTCOMES},
        unit=UNIT_OUTCOMES,
        population="polymarket_0x_resolved",
    )
    out = annotate_cells(_cells(), census=census)
    assert out[0]["provability"] == PROVABILITY_UNKNOWN
    assert "population" in out[0]["provability_reason"].lower()


def test_no_census_at_all_still_reads_unknown_never_provable():
    out = annotate_cells(_cells(), census=None)
    assert out[0]["provability"] == PROVABILITY_UNKNOWN
    assert out[0]["graded_share"] is None


def test_the_guard_cannot_be_bypassed_with_a_bare_dict():
    """Passing a raw mapping is exactly how the near-miss would have happened —
    a dict carries no unit, so it must not be accepted as a census."""
    with pytest.raises(TypeError):
        annotate_cells(_cells(), census={"soccer": SOCCER_PM_MARKETS})
