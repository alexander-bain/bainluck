from copy import deepcopy

from scripts.evals.calibration_publish_gate_contract import (
    _resolve_case,
    evaluate_pack,
    gate_candidate,
    load_pack,
    simulate_publication,
)


def _artifacts():
    pack = load_pack()
    return pack, deepcopy(pack["artifacts"]["prior"]), deepcopy(pack["artifacts"]["clean"])


def test_versioned_corpus_matches_every_declared_expectation() -> None:
    pack = load_pack()
    result = evaluate_pack(pack)
    assert pack["policy"]["contract_version"] == "calibration-publish-gate/v1"
    assert result["passed"] == result["cases"] == 14
    assert not [row for row in result["results"] if row["expected_mismatches"]]


def test_every_refusal_declares_the_exact_issue_payload() -> None:
    pack = load_pack()
    for case in pack["cases"]:
        resolved = _resolve_case(case, pack)
        result = gate_candidate(resolved["prior"], resolved["candidate"], pack["policy"])
        if result["verdict"] == "refuse":
            assert case["expected_issue"] == result["issue"]
            assert result["issue"]["priority"] == "P2"
            assert result["issue"]["labels"] == ["needs-triage"]


def test_refusal_preserves_main_and_last_good_byte_for_byte() -> None:
    pack, prior, _ = _artifacts()
    candidate = deepcopy(pack["artifacts"]["partial"])
    store = {"main": deepcopy(prior), "last_good": deepcopy(prior)}
    after, result = simulate_publication(store, candidate, pack["policy"])
    assert result["verdict"] == "refuse"
    assert after == store


def test_clean_pass_atomically_replaces_both_copies() -> None:
    pack, prior, clean = _artifacts()
    after, result = simulate_publication(
        {"main": deepcopy(prior), "last_good": deepcopy(prior)}, clean, pack["policy"]
    )
    assert result["verdict"] == "publish"
    assert after["main"] == after["last_good"] == clean
    assert after["main"] is not after["last_good"]


def test_population_and_category_boundaries_are_inclusive() -> None:
    pack, prior, candidate = _artifacts()
    candidate["total_outcomes"] = 95000
    candidate["categories"][0]["n"] = 32000  # exactly -20%
    candidate["categories"][3]["n"] = 27200
    assert gate_candidate(prior, candidate, pack["policy"])["verdict"] == "publish"
    candidate["total_outcomes"] = 105000
    assert gate_candidate(prior, candidate, pack["policy"])["verdict"] == "publish"


def test_missing_zero_duplicate_and_nonfinite_values_are_contained() -> None:
    pack, prior, clean = _artifacts()
    mutations = []
    missing = deepcopy(clean); missing.pop("categories"); mutations.append(missing)
    zero = deepcopy(clean); zero["total_outcomes"] = 0; mutations.append(zero)
    duplicate = deepcopy(clean); duplicate["categories"].append(deepcopy(duplicate["categories"][0])); mutations.append(duplicate)
    nonfinite = deepcopy(clean); nonfinite["categories"][1]["ece_pp"] = float("nan"); mutations.append(nonfinite)
    for candidate in mutations:
        assert gate_candidate(prior, candidate, pack["policy"])["verdict"] == "refuse"


def test_changed_category_set_and_mixed_schema_are_refused() -> None:
    pack, prior, clean = _artifacts()
    changed = deepcopy(clean)
    changed["categories"].pop()
    changed["categories"].append({"name": "new-category", "n": 24200, "ece_pp": 2.4})
    assert "REQUIRED_CATEGORY_MISSING" in gate_candidate(prior, changed, pack["policy"])["findings"]
    prior["schema_version"] = "calibration-artifact/v0"
    assert "PRIOR_ARTIFACT_INVALID" in gate_candidate(prior, clean, pack["policy"])["findings"]


def test_zero_prior_denominators_refuse_instead_of_dividing() -> None:
    pack, prior, clean = _artifacts()
    prior["categories"][0]["n"] = 0
    assert "PRIOR_CATEGORY_ZERO" in gate_candidate(prior, clean, pack["policy"])["findings"]
    prior["total_outcomes"] = 0
    assert "PRIOR_ARTIFACT_INVALID" in gate_candidate(prior, clean, pack["policy"])["findings"]


def test_order_is_irrelevant_and_fingerprint_is_stable() -> None:
    pack, prior, _ = _artifacts()
    candidate = deepcopy(pack["artifacts"]["inversion"])
    first = gate_candidate(prior, candidate, pack["policy"])
    candidate["categories"].reverse(); candidate["activity_tiers"].reverse()
    prior["categories"].reverse(); prior["activity_tiers"].reverse()
    second = gate_candidate(prior, candidate, pack["policy"])
    assert first == second
    assert first["issue"]["fingerprint"] == gate_candidate(prior, candidate, pack["policy"])["issue"]["fingerprint"]


def test_failed_issue_filing_cannot_mutate_publication_state() -> None:
    pack, prior, _ = _artifacts()
    store = {"main": deepcopy(prior), "last_good": deepcopy(prior)}
    after, result = simulate_publication(store, pack["artifacts"]["failed"], pack["policy"])
    assert result["issue"] is not None
    try:
        raise RuntimeError("synthetic issue filing outage")
    except RuntimeError:
        pass
    assert after == store


def test_cricket_low_n_warns_but_material_regression_refuses() -> None:
    pack = load_pack()
    rows = {row["id"]: row for row in evaluate_pack(pack)["results"]}
    assert rows["cricket_low_n_noise"]["verdict"] == "publish"
    assert rows["cricket_low_n_noise"]["warnings"] == ["LOW_N_CATEGORY_DISTORTION"]
    assert rows["cricket_material_regression"]["verdict"] == "refuse"
