from copy import deepcopy

from scripts.evals.calibration_population_integrity import evaluate, load_fixture, validate


def test_corpus_is_versioned_and_pins_population() -> None:
    corpus = load_fixture()
    assert corpus["schema_version"] == "calibration-population-integrity/v1"
    assert corpus["population_version"] == "q267"
    assert corpus["audited_commit"] == "71571f4a"


def test_all_contract_rows_are_coherent() -> None:
    result = evaluate(load_fixture())
    assert len(result) == 16
    assert all(not errors for errors in result.values()), result


def test_current_defects_and_clean_contracts_are_disjoint() -> None:
    corpus = load_fixture()
    defects = set(corpus["confirmed_current_defects"])
    clean = set(corpus["confirmed_clean_contracts"])
    ids = {row["id"] for row in corpus["scenarios"]}
    assert defects.isdisjoint(clean)
    assert defects | clean <= ids


def test_winner_write_without_source_is_rejected() -> None:
    corpus = load_fixture()
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "ws_ungraded_requires_source"))
    row["expected"]["stamp_source"] = False
    assert validate(row, corpus) == ["winner_without_provenance"]


def test_unattended_resolved_shape_write_is_rejected() -> None:
    corpus = load_fixture()
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "resolved_shape_beat_is_immutable"))
    row["expected"]["write_shape"] = True
    assert validate(row, corpus) == ["unattended_resolved_shape_mutation"]


def test_zero_volume_is_not_the_liquidity_decision() -> None:
    corpus = load_fixture()
    kept = next(r for r in corpus["scenarios"] if r["id"] == "kalshi_zero_volume_with_bid_kept")
    dropped = next(r for r in corpus["scenarios"] if r["id"] == "kalshi_zero_volume_no_evidence_dropped")
    assert kept["volume"] == dropped["volume"] == 0
    assert kept["expected"]["eligible"] is True
    assert dropped["expected"]["eligible"] is False


def test_stale_last_good_must_remain_marked_in_memory() -> None:
    corpus = load_fixture()
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "last_good_missing_main_is_marked"))
    row["expected"]["memoized_copy_marked"] = False
    assert validate(row, corpus) == ["stale_marker_not_memoized"]
