from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.calibration_orphan_containment_contract import evaluate_case, evaluate_corpus, load_corpus, materialize

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_orphan_containment_contract.json"


def _case(case_id: str) -> dict:
    corpus = load_corpus(FIXTURE)
    return materialize(corpus, next(row for row in corpus["cases"] if row["id"] == case_id))


def test_corpus_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 37
    assert report["passed"] == 37
    ids = {row["id"] for row in corpus["cases"]}
    assert {"old-active-orphan", "current-scheduled-beat", "pid-reuse", "missing-application-name"} <= ids
    assert {"poison-first", "poison-middle", "poison-last", "checked-zero"} <= ids


def test_age_alone_never_authorizes() -> None:
    assert "AGE_ONLY_AUTHORITY" in evaluate_case(_case("age-only-refused"))


def test_current_beat_is_never_candidate() -> None:
    assert "CURRENT_GENERATION_TARGETED" in evaluate_case(_case("current-scheduled-beat"))


def test_pid_reuse_is_refused() -> None:
    assert evaluate_case(_case("pid-reuse")) == ["PID_OR_IDENTITY_CHANGED"]


def test_clean_attended_sequence_requires_cancel_first() -> None:
    assert evaluate_case(_case("attended-cancel-then-terminate")) == []
    assert "TERMINATE_WITHOUT_CANCEL_FIRST" in evaluate_case(_case("terminate-without-cancel"))


def test_natural_completion_prevents_termination() -> None:
    assert evaluate_case(_case("natural-completion-during-grace")) == ["ACTION_OUTSIDE_REVALIDATED_SET", "TERMINATE_AFTER_NATURAL_COMPLETION"]


def test_success_requires_observed_effect_not_command_return() -> None:
    assert set(evaluate_case(_case("command-returned-not-gone"))) == {"SUCCESS_WITH_CANDIDATE_PRESENT", "SUCCESS_WITHOUT_XMIN_ADVANCE"}


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_keeps_siblings(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["siblings_preserved"] = False
    assert "POISON_ERASES_SIBLINGS" in evaluate_case(row)


def test_order_independent() -> None:
    corpus = load_corpus(FIXTURE)
    other = copy.deepcopy(corpus)
    other["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(other)


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
