"""#2280: a DECLARED category re-filing lets the finished bank publish.

lane1b's #2526/#8460 drains moved settled real-tennis Polymarket markets from
``table_tennis`` to ``tennis`` on 2026-09-24/25. The 249-unit bank that finished
at 07:32Z on 2026-09-26 reads the corrected category; the 07:25Z artifact it has
to replace does not. Every beat since 08:15Z was refused on
``category_collapse`` (table_tennis 37,916 -> 4,772) while tennis grew
80,086 -> 119,386 in the same served fold.

Both directions, per gotcha #43: the declared re-filing publishes when the rows
show up in tennis, and every other shape still refuses.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_publish_gate import (
    DECLARED_RECATEGORIZATIONS,
    PREDICATE_FIELD,
    evaluate_publish,
    gate_ledger_record,
)

PREDICATE = "27b49126ac461fce9d5f078b471bb17f"

#: The served 07:25Z artifact and the 249-unit bank's fold (production reads,
#: 2026-09-26 ~13:50Z: `/api/calibration` by_category and the staged cursor's
#: served accumulator over the futures sources).
BASELINE_AT = "2026-09-26T07:25:24.854134+00:00"
CANDIDATE_AT = "2026-09-26T16:17:00+00:00"
TT_BEFORE, TT_AFTER = 37_916, 4_772
TENNIS_BEFORE, TENNIS_AFTER = 80_086, 119_386
SOCCER = 800_000  # the rest of the ~930k population, so totals move like production


def _payload(*, tt: int, tennis: int, generated_at: str | None, soccer: int = SOCCER) -> dict:
    total = tt + tennis + soccer
    payload = {
        "buckets": [
            {
                "bucket_idx": i,
                "n": 5_000,
                "winners": 2_500,
                "sum_prob": 2_500.0,
                "price_moved": i % 2 == 0,
            }
            for i in range(10)
        ],
        "by_category": [
            {"category": "soccer", "outcomes": soccer, "ece": 1.5},
            {"category": "tennis", "outcomes": tennis, "ece": 1.8},
            {"category": "table_tennis", "outcomes": tt, "ece": 2.7},
        ],
        "by_source": [{"source": "polymarket", "outcomes": total}],
        "total_outcomes": total,
        "total_markets": total // 2,
        "total_winners": total // 3,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": "q271",
        PREDICATE_FIELD: PREDICATE,
    }
    if generated_at is not None:
        payload["generated_at"] = generated_at
    return payload


def _published(**kw) -> dict:
    kw.setdefault("tt", TT_BEFORE)
    kw.setdefault("tennis", TENNIS_BEFORE)
    kw.setdefault("generated_at", BASELINE_AT)
    return _payload(**kw)


def _candidate(**kw) -> dict:
    kw.setdefault("tt", TT_AFTER)
    kw.setdefault("tennis", TENNIS_AFTER)
    kw.setdefault("generated_at", CANDIDATE_AT)
    return _payload(**kw)


class TestTheDeclaredRefilingPublishes:
    def test_the_production_candidate_publishes(self):
        verdict = evaluate_publish(_candidate(), _published())

        assert verdict.ok, verdict.summary()
        assert verdict.codes == []
        assert "category_collapse_declared_recategorization" in verdict.observation_codes

    def test_the_admission_says_why_and_is_persisted(self):
        verdict = evaluate_publish(_candidate(), _published())
        [record] = gate_ledger_record(verdict)["declared_recategorizations"]

        assert record["category"] == "table_tennis"
        assert record["into"] == "tennis"
        assert record["lost"] == TT_BEFORE - TT_AFTER
        assert record["gained_into"] == TENNIS_AFTER - TENNIS_BEFORE
        assert record["issue"] == 2280
        assert "#8460" in verdict.summary()

    def test_the_recovery_boundary_is_inclusive(self):
        entry = DECLARED_RECATEGORIZATIONS["table_tennis"]
        lost = TT_BEFORE - TT_AFTER
        needed = entry["min_recovered_share"] * lost
        # Exactly the share passes; one outcome short refuses.
        at = TENNIS_BEFORE + int(needed) + (0 if needed == int(needed) else 1)
        assert evaluate_publish(_candidate(tennis=at), _published()).ok
        refused = evaluate_publish(_candidate(tennis=at - 1), _published())
        assert refused.codes == ["category_collapse"]


class TestEveryOtherShapeStillRefuses:
    def test_a_loss_that_did_not_reappear_in_tennis_refuses(self):
        verdict = evaluate_publish(_candidate(tennis=TENNIS_BEFORE), _published())

        assert not verdict.ok
        assert verdict.codes == ["category_collapse"]
        assert "'tennis' moved +0" in verdict.summary()

    def test_a_loss_larger_than_the_refiling_could_cause_refuses(self):
        cap = DECLARED_RECATEGORIZATIONS["table_tennis"]["max_moved_outcomes"]
        big = cap + 10_000
        verdict = evaluate_publish(
            _candidate(tt=0, tennis=TENNIS_BEFORE + big),
            _published(tt=big, tennis=TENNIS_BEFORE),
        )

        assert verdict.codes == ["category_collapse"]
        assert f"at most {cap:,}" in verdict.summary()

    def test_a_baseline_built_after_the_cutoff_is_not_excused(self):
        """One-shot: once the re-filed curve publishes, the entry goes quiet."""
        cutoff = DECLARED_RECATEGORIZATIONS["table_tennis"]["baseline_built_before"]
        verdict = evaluate_publish(_candidate(), _published(generated_at=cutoff))

        assert verdict.codes == ["category_collapse"]
        assert "recategorization" not in verdict.rejections[0]

    def test_an_undated_baseline_is_not_excused(self):
        verdict = evaluate_publish(_candidate(), _published(generated_at="not-a-date"))

        assert verdict.codes == ["category_collapse"]

    def test_an_undeclared_category_collapsing_beside_growth_refuses(self):
        verdict = evaluate_publish(
            _candidate(tt=TT_BEFORE, tennis=TENNIS_BEFORE + 150_000, soccer=600_000),
            _published(),
        )

        assert "category_collapse" in verdict.codes
        assert any(r.get("category") == "soccer" for r in verdict.rejections)


def test_the_cap_is_the_drains_receipts_at_two_outcomes_a_market():
    # #2526: 15,766 markets; #8460: 51,829 markets (lane1b receipts, 09-24/25).
    assert DECLARED_RECATEGORIZATIONS["table_tennis"]["max_moved_outcomes"] == 2 * (
        15_766 + 51_829
    )


@pytest.mark.parametrize("key", ["into", "cause", "issue", "baseline_built_before"])
def test_every_entry_names_its_destination_cause_issue_and_cutoff(key):
    for entry in DECLARED_RECATEGORIZATIONS.values():
        assert entry[key]
