from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.evidence_age_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/evidence_age_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"] == case_id))


def test_corpus_covers_age_boundaries() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    assert {"fresh", "boundary-equal", "just-stale", "missing-timestamp", "last-good-stale", "mixed-age"} <= {r["id"] for r in corpus["cases"]}


def test_expired_green_becomes_dated_stale() -> None:
    verdict = evaluate_case(_case("just-stale"))
    assert verdict["authority"] == "DATED_STALE"
    assert verdict["headline"] == "stale"
    assert verdict["display_date"] is True


def test_missing_timestamp_never_earns_fresh() -> None:
    verdict = evaluate_case(_case("missing-timestamp"))
    assert verdict["authority"] == "NO_TIMESTAMP"
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
