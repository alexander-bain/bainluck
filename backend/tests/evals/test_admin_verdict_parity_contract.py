from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.admin_verdict_parity_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/admin_verdict_parity_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"] == case_id))


def test_corpus_covers_shared_surface_boundaries() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    assert {"flow-skipped", "grid-explained-artifact", "sentinel-stale", "missing-timestamp", "worker-down"} <= {r["id"] for r in corpus["cases"]}


def test_stale_verdict_is_red_everywhere() -> None:
    verdict = evaluate_case(_case("sentinel-stale"))
    assert verdict["canonical_verdict"] == "red"
    assert set(verdict["surface_states"].values()) == {"red"}


def test_unknown_freshness_is_unknown_everywhere() -> None:
    verdict = evaluate_case(_case("missing-timestamp"))
    assert verdict["canonical_verdict"] == "unknown"
    assert set(verdict["surface_states"].values()) == {"unknown"}


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
