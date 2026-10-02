"""#5355 — the DataGolf opening-timing rule is a DECLARED predicate move.

The rule moves ``population_predicate_fingerprint`` unbumped. #8458 is what an
undeclared move costs: the strict band refused every candidate for nine days
while the rebuild's ordinary growth passed 5%. So the move is declared by its
exact digest pair, and these tests hold the declaration to what it says:

* the declared pair publishes across real growth when the candidate states a
  positive narrowing inside the cap;
* it refuses when the narrowing is absent, zero, or past the cap, and when the
  rebuilt-with-narrowing growth passes the ceiling;
* it states its size ONCE (``"listed": False``) without loosening the identity
  quarantine's two-statement cross-check;
* the pair's candidate digest is THIS tree's digest, and its published digest is
  the one the #6275 succession lands on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.calibration_publish_gate import (
    DECLARED_PREDICATE_SUCCESSIONS,
    PREDICATE_FIELD,
    census,
    evaluate_publish,
    gate_ledger_record,
)

#: Master's pin since #8458, and the predicate the 2026-09-26 22:17Z served
#: artifact states (artifacts-calibration-2839/cal.json).
PUBLISHED_PREDICATE = "27b49126ac461fce9d5f078b471bb17f"
CANDIDATE_PREDICATE = "3944c947edb78d220ed3bef7defcc526"
PAIR = (PUBLISHED_PREDICATE, CANDIDATE_PREDICATE)

#: The served artifact's population, and a rebuild's worth of growth past 5%.
PUBLISHED_POP = 942_284
CANDIDATE_POP = 1_030_000

#: Not a measured figure — the real count is read off the candidate at evaluate
#: time. Sized under DataGolf's whole published share (23,816).
NARROWING = 9_000


def _payload(*, outcomes: int, predicate: str, excluded=None) -> dict:
    payload = {
        "buckets": [
            {
                "bucket_idx": i,
                "n": max(1, outcomes // 20),
                "winners": max(1, outcomes // 40),
                "sum_prob": max(1, outcomes // 40) * 1.0,
                "price_moved": i % 2 == 0,
            }
            for i in range(10)
        ],
        "by_category": [
            {"category": "soccer", "outcomes": int(outcomes * 0.4), "ece": 1.5},
            {"category": "golf", "outcomes": int(outcomes * 0.1), "ece": 1.5},
        ],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes - 100,
        "total_winners": outcomes // 3,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": "q271",
        PREDICATE_FIELD: predicate,
    }
    if excluded is not None:
        # The shape `compute_calibration_payload` emits for #5355.
        payload["datagolf_opening_timing_filter"] = {
            "applies_to": "datagolf",
            "rule": "r",
            "excluded": excluded,
            "excluded_markets": max(0, excluded // 50),
            "excluded_cells": [["datagolf", "golf"]],
        }
    return payload


def _published() -> dict:
    return _payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE)


def _candidate(**kw) -> dict:
    kw.setdefault("outcomes", CANDIDATE_POP)
    kw.setdefault("predicate", CANDIDATE_PREDICATE)
    kw.setdefault("excluded", NARROWING)
    return _payload(**kw)


def test_the_pair_is_declared_with_a_bounded_cap():
    entry = DECLARED_PREDICATE_SUCCESSIONS[PAIR]
    assert entry["narrowing"] == "datagolf_opening_timing"
    assert entry["issue"] == 5355
    assert entry["listed"] is False
    # DataGolf was 2.53% of the served population; the cap may not be loose
    # enough to admit a rule that removed some other source's rows wholesale.
    assert 2.53 < entry["max_narrowing_pct"] <= 10.0


def test_the_candidate_digest_is_this_trees_digest():
    """A pair keyed on a digest the code no longer produces admits nothing."""
    from app.tasks.precompute_calibration import population_predicate_fingerprint

    assert population_predicate_fingerprint() == CANDIDATE_PREDICATE


def test_the_published_digest_is_where_the_6275_succession_lands():
    """The chain is contiguous: #6275's candidate is #5355's published side."""
    landed = {b for (_a, b) in DECLARED_PREDICATE_SUCCESSIONS if _a != PUBLISHED_PREDICATE}
    assert PUBLISHED_PREDICATE in landed


def test_the_declared_pair_publishes_across_growth():
    verdict = evaluate_publish(_candidate(), _published())

    assert verdict.ok, verdict.summary()
    assert verdict.observation_codes == [
        "population_growth_acknowledged",
        "population_predicate_succession_declared",
    ]
    record = gate_ledger_record(verdict)["predicate_succession"]
    assert record["admitted"] is True
    assert record["narrowing"] == NARROWING
    assert record["narrowing_listed"] is None
    assert "#5355" in record["cause"]


def test_control_the_same_growth_without_the_declaration_refuses():
    """Non-vacuity: the pair, not the numbers, is what admits the build."""
    verdict = evaluate_publish(
        _candidate(predicate="0" * 32), _published()
    )
    assert verdict.codes == ["population_drift"]
    assert verdict.predicate_succession is None


@pytest.mark.parametrize("excluded", [None, 0])
def test_an_absent_or_zero_narrowing_refuses(excluded):
    verdict = evaluate_publish(_candidate(excluded=excluded), _published())
    assert verdict.codes == ["population_drift"]
    assert verdict.predicate_succession["admitted"] is False


def test_a_narrowing_past_the_cap_refuses():
    cap = DECLARED_PREDICATE_SUCCESSIONS[PAIR]["max_narrowing_pct"]
    too_many = int(CANDIDATE_POP * (cap / 100) * 1.2)
    verdict = evaluate_publish(_candidate(excluded=too_many), _published())
    assert verdict.codes == ["population_drift"]
    assert "cap" in verdict.summary()


def test_the_census_reads_the_section_and_states_no_second_figure():
    stated = census(_candidate())["datagolf_opening_timing"]
    assert stated == {
        "excluded": NARROWING,
        "listed_outcomes": None,
        "section_present": True,
    }
    assert census(None)["datagolf_opening_timing"] is None


def test_the_quarantine_still_needs_its_second_statement():
    """`"listed": False` is per entry; the #6275 entry keeps its cross-check."""
    from app.utils.calibration_publish_gate import _judge_succession

    quarantine = DECLARED_PREDICATE_SUCCESSIONS[
        ("e67d771bbd7a92dfd8d1a0f4bd79b4c2", PUBLISHED_PREDICATE)
    ]
    cand = {"identity_quarantine": {"excluded": 70_000, "listed_outcomes": 69_000}}
    _record, why_not = _judge_succession(quarantine, cand, 747_028, 928_855)
    assert why_not is not None and "disagree" in why_not
