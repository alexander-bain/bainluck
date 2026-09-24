"""#8458: a DECLARED predicate succession lets the finished bank publish.

The #6275 identity quarantine moved ``population_predicate_fingerprint`` from
``e67d771b…`` to ``27b49126…`` on 2026-09-15 with no version bump, so every
candidate after it was refused on ``population_drift``. The 140-unit rebuild
completed on 2026-09-24 (747,028 -> 928,855) and was refused every beat. The
gate was right; it just had no way to be told the move was the ruled one.

Both directions, per gotcha #43: the declared pair publishes when its narrowing
is measured and bounded, and every other shape still refuses.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.utils.calibration_publish_gate import (
    DECLARED_PREDICATE_SUCCESSIONS,
    POPULATION_GROWTH_CEILING,
    PREDICATE_FIELD,
    evaluate_publish,
    gate_ledger_record,
)

#: The production pair off #8458's beat-38 log line.
PUBLISHED_PREDICATE = "e67d771bbd7a92dfd8d1a0f4bd79b4c2"
CANDIDATE_PREDICATE = "27b49126ac461fce9d5f078b471bb17f"
PUBLISHED_POP = 747_028
CANDIDATE_POP = 928_855

#: Not a measured figure: the candidate's real count is read at evaluate time.
#: Sized near the ~7.4% point estimate the cap is derived from.
QUARANTINE = 70_000


def _payload(
    *,
    outcomes: int,
    predicate: str | None,
    quarantine: int | None = None,
    listed: int | None = "same",  # type: ignore[assignment]
) -> dict:
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
            {"category": "tennis", "outcomes": int(outcomes * 0.2), "ece": 1.5},
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
    }
    if predicate is not None:
        payload[PREDICATE_FIELD] = predicate
    if quarantine is not None:
        # The shape `compute_calibration_payload` emits (22a99a734d).
        payload["identity_quarantine_filter"] = {
            "applies_to": "all",
            "excluded": quarantine,
            "excluded_markets": quarantine // 10,
            "excluded_cells": [],
        }
        n_listed = quarantine if listed == "same" else listed
        payload["quarantine"] = (
            [
                {
                    "reason": "r",
                    "outcomes": n_listed,
                    "status": "under_review",
                    "markets": 1,
                }
            ]
            if n_listed
            else []
        )
    return payload


def _published() -> dict:
    return _payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE)


def _candidate(**kw) -> dict:
    kw.setdefault("outcomes", CANDIDATE_POP)
    kw.setdefault("predicate", CANDIDATE_PREDICATE)
    kw.setdefault("quarantine", QUARANTINE)
    return _payload(**kw)


class TestTheDeclaredPairPublishes:
    def test_the_beat_38_candidate_publishes_on_the_declared_pair(self):
        verdict = evaluate_publish(_candidate(), _published())

        assert verdict.ok, verdict.summary()
        assert verdict.codes == []
        assert not verdict.version_bumped
        assert verdict.observation_codes == [
            "population_growth_acknowledged",
            "population_predicate_succession_declared",
        ]

    def test_the_admission_says_why_and_is_persisted(self):
        verdict = evaluate_publish(_candidate(), _published())
        record = gate_ledger_record(verdict)["predicate_succession"]

        assert record["admitted"] is True
        assert record["published_predicate"] == PUBLISHED_PREDICATE
        assert record["candidate_predicate"] == CANDIDATE_PREDICATE
        assert record["narrowing"] == QUARANTINE
        assert record["pre_narrowing_population"] == CANDIDATE_POP + QUARANTINE
        assert record["narrowing_pct"] == pytest.approx(
            QUARANTINE / (CANDIDATE_POP + QUARANTINE) * 100, abs=0.01
        )
        assert "#6275" in record["cause"]
        assert "#6275" in verdict.summary()
        assert "declared predicate succession" in verdict.summary()

    def test_the_next_build_after_publishing_is_an_ordinary_same_predicate_build(self):
        """One-shot: the served artifact now states the new digest."""
        served = _candidate()
        verdict = evaluate_publish(_candidate(outcomes=CANDIDATE_POP + 70_000), served)

        assert verdict.ok, verdict.summary()
        assert verdict.observation_codes == ["population_growth_acknowledged"]
        assert verdict.predicate_succession is None


class TestEverythingElseStillRefuses:
    def test_no_quarantine_section_refuses(self):
        verdict = evaluate_publish(_candidate(quarantine=None), _published())
        assert not verdict.ok
        assert verdict.codes == ["population_drift"]
        assert "does not state the declared narrowing" in verdict.summary()
        assert gate_ledger_record(verdict)["predicate_succession"]["admitted"] is False

    def test_a_zero_quarantine_means_the_declared_cause_is_absent(self):
        verdict = evaluate_publish(_candidate(quarantine=0), _published())
        assert verdict.codes == ["population_drift"]
        assert "cause the succession declares is absent" in verdict.summary()

    def test_the_two_statements_of_the_narrowing_must_agree(self):
        verdict = evaluate_publish(_candidate(listed=QUARANTINE - 1), _published())
        assert verdict.codes == ["population_drift"]
        assert "disagree" in verdict.summary()

    def test_a_narrowing_past_its_cap_refuses(self):
        cap = DECLARED_PREDICATE_SUCCESSIONS[
            (PUBLISHED_PREDICATE, CANDIDATE_PREDICATE)
        ]["max_narrowing_pct"]
        # Just past the cap of the pre-narrowing population.
        q = int(CANDIDATE_POP * (cap / 100) / (1 - cap / 100)) + 100
        verdict = evaluate_publish(_candidate(quarantine=q), _published())
        assert verdict.codes == ["population_drift"]
        assert "cap" in verdict.summary()

        # Control: just inside it publishes.
        q_ok = int(CANDIDATE_POP * (cap / 100) / (1 - cap / 100)) - 100
        assert evaluate_publish(_candidate(quarantine=q_ok), _published()).ok

    def test_growth_past_the_ceiling_once_the_narrowing_is_added_back_refuses(self):
        # Raw growth +94.1% is under the ceiling; with the narrowing back it is not.
        cand_pop = 1_450_000
        assert (cand_pop - PUBLISHED_POP) / PUBLISHED_POP < POPULATION_GROWTH_CEILING
        q = 60_000
        assert (
            cand_pop + q - PUBLISHED_POP
        ) / PUBLISHED_POP > POPULATION_GROWTH_CEILING

        verdict = evaluate_publish(
            _candidate(outcomes=cand_pop, quarantine=q), _published()
        )
        assert verdict.codes == ["population_growth_unexplained"]

    def test_shrink_across_the_declared_pair_stays_strict(self):
        verdict = evaluate_publish(
            _candidate(outcomes=int(PUBLISHED_POP * 0.90)), _published()
        )
        assert verdict.codes == ["population_shrink"]
        assert verdict.predicate_succession is None

    @pytest.mark.parametrize(
        "published_predicate,candidate_predicate",
        [
            # reversed
            (CANDIDATE_PREDICATE, PUBLISHED_PREDICATE),
            # the right source, a different destination
            (PUBLISHED_PREDICATE, "0" * 32),
            # a different source, the right destination
            ("f" * 32, CANDIDATE_PREDICATE),
            # unstated baseline
            (None, CANDIDATE_PREDICATE),
        ],
    )
    def test_any_other_pair_refuses_exactly_as_before(
        self, published_predicate, candidate_predicate
    ):
        verdict = evaluate_publish(
            _candidate(predicate=candidate_predicate),
            _payload(outcomes=PUBLISHED_POP, predicate=published_predicate),
        )
        assert verdict.codes == ["population_drift"]
        assert verdict.predicate_succession is None
        assert "DECLARED" not in verdict.summary()


class TestTheBankSurvives:
    def test_the_declaration_is_not_inside_any_fingerprinted_source(self):
        """Declaring the pair must not re-key the 140-unit served bank."""
        import app.tasks.precompute_calibration as pc
        from app.utils import market_identity

        hashed = (
            inspect.getsource(pc.compute_calibration_payload)
            + inspect.getsource(pc._calibration_population_ctes)
            + inspect.getsource(pc._virtual_market_ctes)
            + inspect.getsource(pc._main_futures_sql)
            + inspect.getsource(pc._roster_pushdown_predicates)
            + inspect.getsource(market_identity.identity_quarantine_ctes)
            + inspect.getsource(pc._main_input_fingerprint)
            + inspect.getsource(pc.population_predicate_fingerprint)
        )
        for symbol in ("DECLARED_PREDICATE_SUCCESSIONS", "calibration_publish_gate"):
            assert symbol not in hashed


#: (CALIBRATION_POPULATION_VERSION, population_predicate_fingerprint()) on this tree.
PINNED_PREDICATE = ("q271", CANDIDATE_PREDICATE)


def test_population_predicate_is_pinned_8458():
    """The process guard #8458 names: the predicate never moves unannounced.

    `22a99a734d` changed `_calibration_population_ctes`, moved this digest, and
    nothing asked for a bump, so the gate refused every build for nine days
    before anyone could see why. This fails at merge instead.
    """
    from app.tasks.precompute_calibration import (
        CALIBRATION_POPULATION_VERSION,
        population_predicate_fingerprint,
    )

    current = (CALIBRATION_POPULATION_VERSION, population_predicate_fingerprint())
    assert current == PINNED_PREDICATE, (
        f"the population predicate moved: {PINNED_PREDICATE} -> {current}. This "
        "changes WHICH rows the accuracy page counts, and the publish gate will "
        "refuse every candidate until it is told why. Either bump "
        "CALIBRATION_POPULATION_VERSION (with a CALIBRATION_POPULATION_DECLARATIONS "
        "entry; discards the staged bank), or, for a ruled narrowing that must "
        "keep a finished bank, declare the exact digest pair in "
        "calibration_publish_gate.DECLARED_PREDICATE_SUCCESSIONS. Then re-pin "
        "PINNED_PREDICATE here."
    )
