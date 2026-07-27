"""Queue #261 Item 3 — calibration truth-evidence regression-visibility artifact.

``_build_truth_evidence`` turns the cheap truth-class census into the artifact
block the cockpit/sentinel consume. ``contract_ok`` goes RED ONLY on a real
contract violation (an unknown resolution_source in the resolved population, or
the Queue #259 candidate==published partition breaking) — never on a source-mix
ratio.
"""

from app.tasks.precompute_calibration import _build_truth_evidence


def _census(**classes):
    return {k: {"outcomes": v[0], "markets": v[1]} for k, v in classes.items()}


def test_clean_population_is_contract_ok():
    census = _census(eligible=(1000, 400), price_derived=(50, 20), missing=(3, 2))
    art = _build_truth_evidence(
        census,
        mex_normalized_markets=40,
        mex_published_markets=40,
        published_outcomes=900,
        published_questions=300,
    )
    assert art["contract_ok"] is True
    assert art["contract_violations"] == []
    # Price-derived rows are surfaced as the leakage-containment count.
    assert art["price_derived_excluded"] == {"outcomes": 50, "markets": 20}
    assert art["unknown_sources"] == {"outcomes": 0, "markets": 0}
    assert art["partition_invariant"]["ok"] is True


def test_unknown_source_trips_contract():
    census = _census(eligible=(1000, 400), unknown=(7, 3))
    art = _build_truth_evidence(
        census,
        mex_normalized_markets=40,
        mex_published_markets=40,
        published_outcomes=900,
        published_questions=300,
    )
    assert art["contract_ok"] is False
    assert any("unknown resolution_source" in v for v in art["contract_violations"])
    assert art["unknown_sources"]["outcomes"] == 7


def test_broken_partition_invariant_trips_contract():
    census = _census(eligible=(1000, 400))
    art = _build_truth_evidence(
        census,
        mex_normalized_markets=40,
        mex_published_markets=37,  # a post-normalization filter dropped members
        published_outcomes=900,
        published_questions=300,
    )
    assert art["contract_ok"] is False
    assert any("partition invariant" in v for v in art["contract_violations"])


def test_source_mix_ratio_alone_is_not_a_violation():
    # A population that is MOSTLY price-derived-excluded is not itself a contract
    # violation — no unknown sources, partition intact → GREEN. (No source-bias
    # interpretation, per Item 3.)
    census = _census(eligible=(10, 5), price_derived=(9000, 3000))
    art = _build_truth_evidence(
        census,
        mex_normalized_markets=5,
        mex_published_markets=5,
        published_outcomes=10,
        published_questions=8,
    )
    assert art["contract_ok"] is True
    assert art["price_derived_excluded"]["outcomes"] == 9000
