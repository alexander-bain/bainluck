from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.admin_health_evidence_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/admin_health_evidence_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"] == case_id))


def test_corpus_covers_admin_health_boundaries() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    assert {"all-green", "all-unknown", "stale-success", "recovery-red-poller-green", "worker-heartbeat-stale"} <= {r["id"] for r in corpus["cases"]}


def test_unknown_cannot_become_green() -> None:
    verdict = evaluate_case(_case("all-unknown"))
    assert verdict["headline"] == "unknown"
    assert verdict["evidence_complete"] is False


def test_missing_capability_blocks_green() -> None:
    verdict = evaluate_case(_case("missing-registry-capability"))
    assert "REQUIRED_CAPABILITY_UNREGISTERED" in verdict["reason_codes"]
    assert verdict["headline"] == "unknown"


def test_loader_rejects_bad_version_and_duplicate_ids(tmp_path: Path) -> None:
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
