from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.cursor_durability_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/cursor_durability_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"kalshi-winner-preadvance", "polymarket-volume-precommit", "datagolf-last-handled", "clob-error-replay"} <= ids


def test_cursor_never_outpaces_committed_prefix() -> None:
    verdict = evaluate_case(_case("kalshi-winner-preadvance"))
    assert verdict["classification"] == "SKIPS_WORK"
    assert "CURSOR_ADVANCES_PAST_DURABLE_WORK" in verdict["reason_codes"]


def test_idempotent_replay_is_explicitly_safe() -> None:
    verdict = evaluate_case(_case("clob-error-replay"))
    assert verdict["classification"] == "REPLAYS_SAFE"
    assert verdict["verdict"] == "PASS"


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
