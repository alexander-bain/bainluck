from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.recent_program_merge_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE=Path(__file__).parent/"fixtures/recent_program_merge_contract.json"


def _case(case_id:str)->dict:
    return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"]==case_id))


def test_corpus_covers_all_three_merges()->None:
    corpus=load_corpus(FIXTURE)
    report=evaluate_corpus(corpus)
    assert report["total"]>=20
    assert report["passed"]==report["total"]
    assert {r["program"] for r in corpus["cases"]}=={"latency","calibration","ux"}


def test_typeahead_timeout_must_be_exposed()->None:
    verdict=evaluate_case(_case("typeahead-timeout-hidden"))
    assert verdict["verdict"]=="REFUSE"
    assert verdict["cache_action"]=="skip"
    assert "DEGRADATION_HIDDEN" in verdict["reason_codes"]


def test_unwired_reachability_is_unknown_not_zero()->None:
    verdict=evaluate_case(_case("reachability-unwired"))
    assert verdict["section"]=="unavailable"
    assert verdict["count"] is None and verdict["checked"] is False


def test_corruption_remains_priority_eligible()->None:
    verdict=evaluate_case(_case("ux-rare-corruption"))
    assert verdict["priority"]=="eligible_exception"


def test_loader_rejects_bad_version_and_duplicate_ids(tmp_path:Path)->None:
    corpus=load_corpus(FIXTURE)
    corpus["schema_version"]="wrong"
    path=tmp_path/"bad.json"
    path.write_text(json.dumps(corpus),encoding="utf-8")
    with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"):
        load_corpus(path)
    corpus=load_corpus(FIXTURE)
    corpus["cases"].append(copy.deepcopy(corpus["cases"][0]))
    path.write_text(json.dumps(corpus),encoding="utf-8")
    with pytest.raises(ValueError,match="CASE_ID_DUPLICATE"):
        load_corpus(path)
