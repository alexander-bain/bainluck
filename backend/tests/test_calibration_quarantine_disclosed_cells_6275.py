"""CAL-P1318 (#6275): the identity quarantine discloses the cells it empties.

WHAT HAPPENED. The quarantine shipped, the bank rebuilt to 128/128 over ~14
hourly beats, and the publish gate refused at the 2026-09-16 12:29:54Z beat:

    gate_ok false   codes ["category_collapse"]   version_bumped false
    candidate_population 711,772   published_population 747,028   (-4.72%)
    terminal failed   beats_to_publish 14   banked 0/128

Two categories breached Rule 3's 20% limit, from the ledger's own
``category_diff``: esports 22,544 -> 14,526 (-35.6%) and mma 3,087 -> 2,144
(-30.6%). Rule 2 PASSED — the total is inside the +-5% band — so this is not a
shrink, and the version-bump escape is not the instrument for it.

WHY IT COULD NOT SELF-CORRECT. A refusal clears the checkpoint and the bank
restarts at 0/128, so the next generation spends another ~14 hours arriving at
the identical verdict. Waiting is not a strategy for this code, which is the
whole reason these tests are pinned to the production numbers rather than to a
round-numbered fixture: if the disclosure stops reaching the gate, the failure
mode is not a wrong number on a page, it is a page frozen at a stale artifact
while the build loops forever.

THE FIX IS A SENTENCE, NOT A THRESHOLD. ``CATEGORY_DROP_TOLERANCE`` does not
move and no version is bumped. The gate already records rather than vetoes a
collapse the candidate's own artifact explains (CAL-P1054/D90); the quarantine
rung simply published a total and no cell list, so the gate had nothing to read.

The negative controls are the point of the file. An excuse that can be obtained
by any disclosure at all, or one that keeps paying out after the baseline has
caught up, would be worse than the refusal it replaces.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from app.tasks.precompute_calibration import (
    IDENTITY_QUARANTINE_DISCLOSED_CELLS,
    _main_input_fingerprint,
    population_predicate_fingerprint,
    compute_calibration_payload,
)
from app.utils.calibration_publish_gate import (
    CATEGORY_DROP_TOLERANCE,
    _disclosed_excluded_cells,
    evaluate_publish,
)

from tests.test_calibration_publish_gate_297 import payload

#: The published q271 cells, and the candidate the 12:29:54Z beat produced.
#: Verbatim from the gate ledger's ``category_diff`` — every category it
#: reported that clears ``CATEGORY_MIN_N``, not just the two that breached, so a
#: change that fixes esports by breaking baseball cannot pass this file.
_PUBLISHED = {
    "baseball": 140_893,
    "soccer": 118_226,
    "basketball": 69_121,
    "tennis": 53_464,
    "weather": 41_568,
    "football": 29_215,
    "table_tennis": 27_367,
    "esports": 22_544,
    "golf": 19_720,
    "hockey": 15_641,
    "politics": 13_952,
    "economics": 13_659,
    "entertainment": 5_824,
    "motorsports": 3_812,
    "tech": 3_444,
    "cricket": 3_165,
    "mma": 3_087,
    "other": 2_591,
    "geopolitics": 1_749,
}
_CANDIDATE = {
    "baseball": 122_525,
    "soccer": 115_990,
    "basketball": 66_329,
    "tennis": 49_127,
    "weather": 42_223,
    "football": 29_854,
    "table_tennis": 27_406,
    "esports": 14_526,
    "golf": 19_809,
    "hockey": 15_170,
    "politics": 14_096,
    "economics": 13_527,
    "entertainment": 6_032,
    "motorsports": 3_807,
    "tech": 3_440,
    "cricket": 3_124,
    "mma": 2_144,
    "other": 2_790,
    "geopolitics": 1_752,
}

#: The categories that actually breached, and so the ones an excuse must cover.
_BREACHED = ("esports", "mma")

_PUBLISHED_POPULATION = 747_028
_CANDIDATE_POPULATION = 711_772


def _disclosure() -> dict:
    """The rung section exactly as the payload builder emits it."""
    return {
        "applies_to": "all",
        "rule": "irrelevant to the gate, carried so the shape is the real one",
        "excluded": 35_256,
        "excluded_markets": 19_028,
        "excluded_cells": [
            list(cell) for cell in sorted(IDENTITY_QUARANTINE_DISCLOSED_CELLS)
        ],
    }


def _artifact(cats: dict[str, int], population: int, *, disclose: bool) -> dict:
    p = payload(outcomes=population, version="q271", categories=cats)
    # The quarantine moved WHICH rows qualify, so the two artifacts state
    # different predicates. That is the real condition and it must not be the
    # thing that carries the test: Rule 2 is inside its band either way.
    p["population_predicate_fingerprint"] = (
        "post-6275" if disclose or cats is _CANDIDATE else "pre-6275"
    )
    if disclose:
        p["identity_quarantine_filter"] = _disclosure()
    return p


def _codes(candidate: dict, published: dict) -> tuple[bool, list[str], list[str]]:
    v = evaluate_publish(candidate, published)
    return v.ok, list(v.codes), [o.get("code") for o in v.observations]


# ---------------------------------------------------------------------------
# The production specimen, both ways round
# ---------------------------------------------------------------------------


def test_the_1229z_beat_refuses_when_the_rung_discloses_nothing():
    """The bug, reproduced on the numbers the gate actually refused."""
    published = _artifact(_PUBLISHED, _PUBLISHED_POPULATION, disclose=False)
    candidate = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=False)

    ok, codes, _ = _codes(candidate, published)

    assert not ok
    assert "category_collapse" in codes, (
        "if this stops refusing, the disclosure below is excusing nothing and "
        "every other test in this file is vacuous"
    )


def test_the_same_beat_publishes_once_the_quarantine_names_its_cells():
    published = _artifact(_PUBLISHED, _PUBLISHED_POPULATION, disclose=False)
    candidate = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)

    ok, codes, observed = _codes(candidate, published)

    assert ok, f"still refusing: {codes}"
    assert "category_collapse" not in codes
    # Recorded, never silent — an admitted collapse that says nothing is the
    # uncheckable-read-as-clean shape the gate exists to refuse.
    assert observed.count("category_collapse_disclosed_exclusion") == len(_BREACHED)


def test_the_recorded_observation_names_both_breached_categories():
    published = _artifact(_PUBLISHED, _PUBLISHED_POPULATION, disclose=False)
    candidate = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)

    verdict = evaluate_publish(candidate, published)
    excused = {
        o.get("category")
        for o in verdict.observations
        if o.get("code") == "category_collapse_disclosed_exclusion"
    }

    assert excused == set(_BREACHED)


def test_rule_2_was_never_the_refusal_so_no_version_is_bumped():
    """-4.72% is inside the band: the bump/declaration escape is not in play."""
    published = _artifact(_PUBLISHED, _PUBLISHED_POPULATION, disclose=False)
    candidate = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)

    verdict = evaluate_publish(candidate, published)

    assert candidate["population_version"] == published["population_version"] == "q271"
    assert not verdict.version_bumped
    assert "population_shrink" not in verdict.codes
    assert "population_drift" not in verdict.codes


# ---------------------------------------------------------------------------
# Negative controls — what the excuse must NOT do
# ---------------------------------------------------------------------------


def test_the_excuse_disarms_itself_once_the_disclosure_is_the_baseline():
    """One-shot by construction, and this is the property that makes it safe.

    ``_newly_excluded_in`` fires only where the CANDIDATE discloses a cell the
    BASELINE does not. After this publishes, the served artifact carries the
    same cells — so a SECOND, unrelated esports collapse on top of it gets no
    excuse and refuses exactly as Rule 3 always did.
    """
    baseline = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)
    worse = dict(_CANDIDATE, esports=7_000)
    candidate = _artifact(worse, _CANDIDATE_POPULATION - 7_526, disclose=True)

    ok, codes, _ = _codes(candidate, baseline)

    assert not ok
    assert "category_collapse" in codes


def test_a_collapse_in_a_category_the_rung_never_touches_still_refuses():
    """weather is not a quarantine cell, so nothing excuses it falling over."""
    published = _artifact(_PUBLISHED, _PUBLISHED_POPULATION, disclose=False)
    doomed = dict(_CANDIDATE, weather=10_000)
    candidate = _artifact(doomed, _CANDIDATE_POPULATION - 32_223, disclose=True)

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes
    refused = {
        r.get("category")
        for r in verdict.rejections
        if r.get("code") == "category_collapse"
    }
    assert "weather" in refused
    assert refused.isdisjoint(_BREACHED), "the disclosed cells should still be excused"


def test_a_steady_build_on_the_new_baseline_publishes():
    """The disclosure must not become a permanent refusal of its own."""
    baseline = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)
    steady = {k: v + 3 for k, v in _CANDIDATE.items()}
    candidate = _artifact(steady, _CANDIDATE_POPULATION + 57, disclose=True)

    ok, codes, _ = _codes(candidate, baseline)

    assert ok, f"a quiet hour should publish, not refuse: {codes}"


# ---------------------------------------------------------------------------
# The wiring: the constant has to REACH the gate, through the real payload key
# ---------------------------------------------------------------------------


def test_the_gate_reads_the_cells_off_the_rung_section_by_its_real_name():
    """Not "a dict with a key" — the section name is half the contract.

    ``_disclosed_excluded_cells`` keys its result by SECTION, and the
    observation text names the rung. A disclosure filed under a renamed or
    nested section reads as no disclosure at all.
    """
    artifact = _artifact(_CANDIDATE, _CANDIDATE_POPULATION, disclose=True)

    disclosed = _disclosed_excluded_cells(artifact)

    assert "identity_quarantine_filter" in disclosed
    cells = {tuple(c) for c in disclosed["identity_quarantine_filter"]}
    assert cells == set(IDENTITY_QUARANTINE_DISCLOSED_CELLS)
    for category in _BREACHED:
        assert ("kalshi", category) in cells


def test_the_payload_builder_emits_the_key_from_the_constant():
    """The source-level half: the two ends of the wire are actually joined.

    Every other test here builds the section itself, so all of them would stay
    green if ``compute_calibration_payload`` quietly stopped emitting the key —
    exactly the regression that costs a 14-hour rebuild cycle to notice.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(compute_calibration_payload)))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        if "rule" in keys and "excluded_markets" in keys and "excluded_cells" in keys:
            value = node.values[keys.index("excluded_cells")]
            names += [n.id for n in ast.walk(value) if isinstance(n, ast.Name)]

    assert "IDENTITY_QUARANTINE_DISCLOSED_CELLS" in names, (
        "the quarantine section must build `excluded_cells` FROM the constant — "
        "a literal list here would drift from the measurement silently"
    )


# ---------------------------------------------------------------------------
# The invariant that makes this a disclosure and not an allowlist
# ---------------------------------------------------------------------------


def test_editing_the_disclosure_cannot_discard_an_in_flight_bank(monkeypatch):
    """A sentence about the population must never re-key the population.

    ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`` is hashed into
    ``_main_input_fingerprint`` BY VALUE because it is interpolated into the
    population SQL: adding a cell there changes which rows qualify, so the
    in-flight bank must be discarded. This tuple reaches no SQL at all. If it
    ever gets hashed, adding a category to a disclosure would throw away ~14
    hours of banked work for nothing.
    """
    before_main = _main_input_fingerprint()
    before_predicate = population_predicate_fingerprint()

    monkeypatch.setattr(
        "app.tasks.precompute_calibration.IDENTITY_QUARANTINE_DISCLOSED_CELLS",
        IDENTITY_QUARANTINE_DISCLOSED_CELLS + (("kalshi", "curling"),),
    )

    assert _main_input_fingerprint() == before_main
    assert population_predicate_fingerprint() == before_predicate


def test_the_disclosed_cells_are_well_formed_and_kalshi_only():
    """Measured 2026-09-16: the predicate reads a date token out of the
    market's own ticker, and no other source writes one."""
    assert IDENTITY_QUARANTINE_DISCLOSED_CELLS, "an empty disclosure excuses nothing"
    assert len(set(IDENTITY_QUARANTINE_DISCLOSED_CELLS)) == len(
        IDENTITY_QUARANTINE_DISCLOSED_CELLS
    ), "a duplicated cell means the tuple was edited by hand without re-measuring"
    for cell in IDENTITY_QUARANTINE_DISCLOSED_CELLS:
        assert isinstance(cell, tuple) and len(cell) == 2
        source, category = cell
        assert source == "kalshi"
        assert category and category == category.lower()


def test_the_breached_categories_are_the_ones_the_measurement_found():
    """A cell absent here is not disclosed, so the gate refuses it — fail
    closed. Pinning the two that actually breached keeps that honest."""
    cells = dict.fromkeys(c[1] for c in IDENTITY_QUARANTINE_DISCLOSED_CELLS)
    for category in _BREACHED:
        assert category in cells
        drop = (_PUBLISHED[category] - _CANDIDATE[category]) / _PUBLISHED[category]
        assert drop > CATEGORY_DROP_TOLERANCE
