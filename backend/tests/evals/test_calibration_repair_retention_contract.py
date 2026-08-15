from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.calibration_repair_retention_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/calibration_repair_retention_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 24
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"repair-cap-cursor-skip", "retention-deadline-cursor-skip", "empty-200-unknown-existence", "legitimate-multi-winner"} <= ids


def test_repair_cursor_cannot_advance_past_capped_candidates() -> None:
    assert "CURSOR_SKIPS_UNPROCESSED" in evaluate_case(_case("repair-cap-cursor-skip"))["reason_codes"]


def test_retention_cursor_cannot_advance_past_unfetched_candidates() -> None:
    assert "CURSOR_SKIPS_UNFETCHED" in evaluate_case(_case("retention-deadline-cursor-skip"))["reason_codes"]


def test_a_retry_cannot_launder_an_undischarged_invalidation() -> None:
    """CAL-P062 / C-CERT-1852-R2 specimen two, as a canonical contract row.

    R2 noted the corpus stayed green through the defect because its
    ``rerun-idempotent`` row models a no-op AFTER success — never a committed
    write followed by a failed invalidation followed by a retry. This row does.
    """
    actual = evaluate_case(_case("invalidation-retry-cannot-launder-prior-debt"))
    assert actual["discharged"] is False
    assert "PRIOR_OBLIGATION_UNDISCHARGED" in actual["reason_codes"]


def test_the_shipping_rule_agrees_with_the_oracle_case_by_case() -> None:
    """The oracle is a SECOND OPINION, so it has to be checked against the code.

    ``_invalidation`` re-derives the rule rather than importing it, which is
    what makes the corpus an independent specification — and worthless unless
    somebody compares them. A disagreement here is the finding.
    """
    from app.utils.calibration_invalidation import invalidation_discharged

    rows = [r for r in load_corpus(FIXTURE)["cases"] if r["kind"] == "invalidation"]
    assert len(rows) >= 5
    for row in rows:
        spec = row["invalidation"]
        shipped, _why = invalidation_discharged(
            status=spec["status"],
            wrote_rows=bool(spec["wrote_rows"]),
            drift_count=int(spec["drift_count"]),
            prior_obligation_open=bool(spec["prior_obligation_open"]),
        )
        assert shipped is row["expected"]["discharged"], row["id"]


def test_empty_response_needs_existence_authority() -> None:
    assert "EMPTY_RESPONSE_INVENTS_ABSENCE" in evaluate_case(_case("empty-200-unknown-existence"))["reason_codes"]


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
