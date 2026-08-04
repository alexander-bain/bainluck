"""#1542 Item 0 — bind the runtime Label Pass lifecycle util to the C143 corpus.

The dependency-free oracle (``scripts/evals/label_pass_lifecycle_contract.py``)
is the authority for the reason grammar. These tests prove the production port in
``app.utils.label_pass_lifecycle`` produces byte-identical decisions across every
committed corpus case — so the corpus can never drift from the code that runs.
"""

from __future__ import annotations

import pytest

from app.utils.label_pass_lifecycle import (
    TERMINAL_STATUSES,
    classify_pending,
    classify_post,
)
from scripts.evals.label_pass_lifecycle_contract import (
    load_corpus,
    pending_decision as oracle_pending,
    post_decision as oracle_post,
)


CASES = load_corpus()["cases"]


def _case(case_id: str) -> dict:
    return next(r for r in CASES if r["id"] == case_id)


@pytest.mark.parametrize("row", CASES, ids=[r["id"] for r in CASES])
def test_runtime_util_matches_oracle_and_corpus(row: dict) -> None:
    # The app util agrees with the dependency-free oracle...
    assert list(classify_pending(row)) == list(oracle_pending(row))
    assert classify_post(row) == oracle_post(row)
    # ...and both agree with the committed expected values.
    assert list(classify_pending(row)) == row["expected_pending"]
    assert classify_post(row) == row["expected_post"]


def test_terminal_set_is_the_contract_set() -> None:
    assert TERMINAL_STATUSES == {"resolved", "closed", "settled", "finalized"}


def test_stale_states_never_write() -> None:
    for cid in (
        "resolved",
        "closed",
        "past-resolution",
        "missing-market",
        "overtaken",
        "superseded",
        "unmatched-email",
        "wrong-email-match",
        "evidence-generation-stale",
        "created-at-refreshed-but-generation-stale",
        "get-valid-post-stale",
        "authority-outage",
    ):
        assert classify_post(_case(cid))["writes"] == 0, cid


def test_prose_is_quarantine_not_retire() -> None:
    # Title/LLM-only staleness must never *retire* on its own authority.
    state, reason = classify_pending(_case("title-llm-only"))
    assert state == "quarantine"
    assert reason == "non_authoritative_staleness"


def test_authority_outage_fails_closed_to_quarantine() -> None:
    state, reason = classify_pending(_case("authority-outage"))
    assert state == "quarantine"
    assert reason == "authority_unavailable"
    assert classify_post(_case("authority-outage"))["writes"] == 0


def test_stale_skip_is_not_training() -> None:
    # A Skip on a stale proposal is system retirement, not a human label.
    assert classify_post(_case("stale-skip"))["writes"] == 0


def test_valid_semantics_and_kill_switch_preserved() -> None:
    assert classify_post(_case("valid-accept"))["delta"] == 8
    assert classify_post(_case("valid-reject"))["delta"] == -18
    assert classify_post(_case("valid-kill-switch-off"))["delta"] == 0
    assert classify_post(_case("valid-skip"))["writes"] == 1


def test_poison_siblings_are_isolated() -> None:
    for cid in ("poison-first-isolated", "poison-middle-isolated", "poison-last-isolated"):
        assert classify_post(_case(cid)) == {
            "status": "written",
            "reason": "current",
            "writes": 1,
            "delta": 8,
        }, cid
