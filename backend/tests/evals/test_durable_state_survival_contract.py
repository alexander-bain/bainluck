from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.durable_state_survival_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures" / "durable_state_survival_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 34
    assert report["passed"] == 34
    families = {row["artifact"]["family"] for row in corpus["cases"]}
    assert {"calibration", "flow", "grid", "calibration_sentinel", "board", "horizon", "grid_register", "settled_concept"} <= families


def test_redis_eviction_uses_dated_durable_copy() -> None:
    result = evaluate_case(_case("redis-evicted-durable-good"))
    assert result["provenance"]["source"] == "durable"
    assert result["provenance"]["dated"] is True
    assert result["health"] == "GREEN"


@pytest.mark.parametrize("case_id", ["redis-outage-fresh-process", "tls-eof-durable-good", "command-timeout-durable-good"])
def test_dependency_failure_does_not_erase_durable_truth(case_id: str) -> None:
    assert evaluate_case(_case(case_id))["provenance"]["source"] == "durable"


def test_fresh_process_cannot_claim_process_memory_as_durability() -> None:
    row = _case("warm-process-fallback")
    row["reads"]["fresh_process"] = True
    result = evaluate_case(row)
    assert result["provenance"]["source"] == "unavailable"
    assert result["health"] == "UNKNOWN"


@pytest.mark.parametrize("case_id", ["durable-malformed", "durable-wrong-version", "durable-too-old"])
def test_untrustworthy_durable_state_is_unknown(case_id: str) -> None:
    result = evaluate_case(_case(case_id))
    assert result["provenance"]["source"] == "unavailable"
    assert result["health"] == "UNKNOWN"


def test_durable_write_is_required_before_volatile_publish() -> None:
    result = evaluate_case(_case("durable-write-fails"))
    assert result["task_success"] is False
    assert "VOLATILE_PUBLISHED_WITHOUT_DURABLE" not in result["errors"]
    row = _case("durable-write-fails")
    row["publication"]["volatile_write"] = "ok"
    assert "VOLATILE_PUBLISHED_WITHOUT_DURABLE" in evaluate_case(row)["errors"]


def test_volatile_failure_after_durable_publish_can_serve_durable() -> None:
    result = evaluate_case(_case("volatile-write-fails-after-durable"))
    assert result["task_success"] is True
    assert result["provenance"]["source"] == "durable"


def test_volatile_ahead_of_durable_is_torn_not_fresh_truth() -> None:
    result = evaluate_case(_case("volatile-ahead-generation-conflict"))
    assert result["provenance"]["source"] == "durable"
    assert result["health"] == "UNKNOWN"
    assert "VOLATILE_AHEAD_OF_DURABLE" in result["errors"]


def test_incomplete_compute_and_cancellation_never_publish() -> None:
    assert evaluate_case(_case("producer-compute-failure"))["task_success"] is False
    row = _case("cancelled-producer")
    row["publication"]["volatile_write"] = "ok"
    assert "CANCELLED_RUN_PUBLISHED" in evaluate_case(row)["errors"]


def test_checked_zero_is_unknown_on_every_surface() -> None:
    result = evaluate_case(_case("checked-zero"))
    assert result["health"] == "UNKNOWN"
    assert {value["health"] for value in result["surfaces"].values()} == {"UNKNOWN"}


def test_mixed_composite_must_keep_per_field_provenance() -> None:
    row = _case("mixed-composite")
    row["composite"]["per_field_metadata"] = False
    result = evaluate_case(row)
    assert "MIXED_COMPOSITE_ERASES_PROVENANCE" in result["errors"]
    assert result["health"] == "UNKNOWN"


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_preserves_healthy_siblings(case_id: str) -> None:
    row = _case(case_id)
    assert evaluate_case(row)["errors"] == []
    row["poison"]["healthy_siblings_survive"] = False
    assert "POISON_WIPES_HEALTHY_STATE" in evaluate_case(row)["errors"]


def test_evaluation_is_order_independent_and_redacts_error_details() -> None:
    corpus = load_corpus(FIXTURE)
    reversed_corpus = copy.deepcopy(corpus)
    reversed_corpus["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(reversed_corpus)
    output = json.dumps(evaluate_case(_case("tls-eof-durable-good")))
    assert "redis.example.internal" not in output
    assert "secret" not in output


def test_loader_rejects_wrong_version_and_duplicate_ids(tmp_path: Path) -> None:
    corpus = load_corpus(FIXTURE)
    corpus["schema_version"] = "wrong"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="SCHEMA_VERSION_INVALID"):
        load_corpus(path)
    corpus = load_corpus(FIXTURE)
    corpus["cases"].append(copy.deepcopy(corpus["cases"][0]))
    path.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="CASE_ID_DUPLICATE"):
        load_corpus(path)
