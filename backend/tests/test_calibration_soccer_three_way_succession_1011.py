"""#1011: soccer graded three-way is a declared WIDENING, and the gate measures it.

Admitting soccer moneyline priced since the 3-way capture changes which rows the
accuracy page counts, so the contract is hashed into
``population_predicate_fingerprint`` and the digest moves ``da21d87f…`` ->
``598e0ed8…``. Every earlier declared move was a narrowing — rows removed, added
back before judging growth. This one ADMITS rows, so the gate takes the
candidate's own count of what it admitted out and judges the rest as
same-predicate growth (``_judge_widening``).

Both directions, per gotcha #43: the declared pair publishes when its widening
is stated, positive and bounded, and every other shape still refuses — and the
existing narrowing successions read exactly as before (their own suites).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

import app.tasks.precompute_calibration as pc
from app.utils import soccer_three_way
from app.utils.calibration_publish_gate import (
    DECLARED_PREDICATE_SUCCESSIONS,
    PREDICATE_FIELD,
    census,
    evaluate_publish,
    gate_ledger_record,
)

PUBLISHED_PREDICATE = "da21d87f0f001c635a813eefb3eb9532"
CANDIDATE_PREDICATE = "598e0ed820277a9748363a4d7a276a63"
PAIR = (PUBLISHED_PREDICATE, CANDIDATE_PREDICATE)

#: The 2026-10-11 23:08Z published size #1010 measured; the candidate grows
#: past the ±5% band so Rule 2 has to consult the succession at all.
PUBLISHED_POP = 1_154_060
CANDIDATE_POP = 1_225_000          # +6.1%
#: Not a measured figure (ruling 134): sized near the build-lane estimate.
EVENTS_INCLUDED = 4_500
BOOKMAKER_INCLUDED = 21_000


def _payload(*, outcomes, predicate, three_way="default"):
    payload = {
        "buckets": [
            {"bucket_idx": i, "n": max(1, outcomes // 20),
             "winners": max(1, outcomes // 40),
             "sum_prob": max(1, outcomes // 40) * 1.0,
             "price_moved": i % 2 == 0}
            for i in range(10)
        ],
        "by_category": [
            {"category": "basketball_nba", "outcomes": int(outcomes * 0.4), "ece": 1.5},
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
        PREDICATE_FIELD: predicate,
    }
    if three_way == "default":
        three_way = {"events_included": EVENTS_INCLUDED,
                     "bookmaker_included": BOOKMAKER_INCLUDED}
    if three_way is not None:
        # The shape compute_calibration_payload emits.
        payload["soccer_2way_filter"] = {
            "applies_to": "odds_api, odds_api_bookmaker",
            "excluded": 50_000,
            "three_way": three_way,
        }
    return payload


def _published():
    return _payload(outcomes=PUBLISHED_POP, predicate=PUBLISHED_PREDICATE,
                    three_way=None)


def _candidate(**kw):
    kw.setdefault("outcomes", CANDIDATE_POP)
    kw.setdefault("predicate", CANDIDATE_PREDICATE)
    return _payload(**kw)


class TestThisTree:
    def test_this_tree_states_the_declared_candidate(self):
        # #938 moved the digest on as a declared narrowing whose predecessor is
        # this widening's candidate, so the chain is unbroken to this tree.
        current = pc.population_predicate_fingerprint()
        assert current == CANDIDATE_PREDICATE or (
            (CANDIDATE_PREDICATE, current) in DECLARED_PREDICATE_SUCCESSIONS
        )
        assert PAIR in DECLARED_PREDICATE_SUCCESSIONS
        assert DECLARED_PREDICATE_SUCCESSIONS[PAIR]["widening"] == "soccer_three_way"

    def test_the_contract_module_is_in_the_digest(self):
        src = inspect.getsource(pc.population_predicate_fingerprint)
        assert "inspect.getsource(_soccer_three_way_module)" in src
        # The cutoff and floor are literals in that module's source, so editing
        # either moves the digest.
        module_src = inspect.getsource(soccer_three_way)
        assert "datetime(2026, 9, 16, 17, 43, 41" in module_src
        assert "SOCCER_DRAW_RESIDUAL_MIN = 0.01" in module_src

    def test_the_reader_predicate_is_in_the_digest(self, monkeypatch):
        before = pc.population_predicate_fingerprint()

        def category_is_soccer_2way_excluded(category):  # a narrowed reader
            return bool(category) and category.startswith("soccer_epl")

        monkeypatch.setattr(
            pc, "category_is_soccer_2way_excluded", category_is_soccer_2way_excluded)
        assert pc.population_predicate_fingerprint() != before

    def test_futures_unit_reuse_is_unaffected(self):
        # #938 moved the unit digest (``dec3026b…`` -> ``5de54fd2…``) with a
        # per-outcome flag in ``_calibration_population_ctes``; this rule did not.
        # #994 then moved it ON PURPOSE (``5de54fd2…`` -> ``74356774…``): Stage B
        # emits each DataGolf cell's members. This rule still does not touch it.
        assert pc.staged_unit_fingerprint() == "7435677428a14a4ecebfe02c9310e101"


class TestTheCensus:
    def test_included_is_the_sum_of_both_arms(self):
        assert census(_candidate())["soccer_three_way"] == {
            "included": EVENTS_INCLUDED + BOOKMAKER_INCLUDED,
            "section_present": True,
        }

    @pytest.mark.parametrize("three_way", [
        None,
        {"events_included": 10},
        {"events_included": 10, "bookmaker_included": -1},
        {"events_included": True, "bookmaker_included": 3},
        {"events_included": 1.5, "bookmaker_included": 3},
    ])
    def test_a_missing_or_malformed_statement_is_none_never_zero(self, three_way):
        assert census(_candidate(three_way=three_way))["soccer_three_way"]["included"] is None


class TestTheDeclaredWideningPublishes:
    def test_growth_past_the_band_publishes_with_the_widening_taken_out(self):
        verdict = evaluate_publish(_candidate(), _published())
        assert verdict.ok, verdict.summary()
        assert verdict.codes == []
        assert verdict.observation_codes == [
            "population_growth_acknowledged",
            "population_predicate_succession_declared",
        ]
        record = gate_ledger_record(verdict)["predicate_succession"]
        included = EVENTS_INCLUDED + BOOKMAKER_INCLUDED
        assert record["admitted"] is True
        assert record["widening"] == included
        assert record["narrowing"] == -included
        assert record["pre_narrowing_population"] == CANDIDATE_POP - included
        assert record["widening_pct"] == pytest.approx(
            included / CANDIDATE_POP * 100, abs=0.01)
        assert "#1011" in record["cause"]
        assert "widening of 25,500 taken out" in verdict.summary()

    def test_growth_inside_the_band_needs_no_succession(self):
        verdict = evaluate_publish(
            _candidate(outcomes=int(PUBLISHED_POP * 1.03)), _published())
        assert verdict.ok, verdict.summary()
        assert verdict.predicate_succession is None

    def test_the_next_build_is_an_ordinary_same_predicate_build(self):
        verdict = evaluate_publish(
            _candidate(outcomes=CANDIDATE_POP + 70_000), _candidate())
        assert verdict.ok, verdict.summary()
        assert verdict.predicate_succession is None


class TestEverythingElseStillRefuses:
    def test_no_three_way_statement_refuses(self):
        verdict = evaluate_publish(_candidate(three_way=None), _published())
        assert verdict.codes == ["population_drift"]
        assert "does not state the declared widening" in verdict.summary()

    def test_a_zero_widening_means_the_cause_is_absent(self):
        verdict = evaluate_publish(
            _candidate(three_way={"events_included": 0, "bookmaker_included": 0}),
            _published())
        assert verdict.codes == ["population_drift"]
        assert "cause the succession declares is absent" in verdict.summary()

    def test_a_widening_past_its_cap_refuses(self):
        cap = DECLARED_PREDICATE_SUCCESSIONS[PAIR]["max_widening_pct"]
        big = int(CANDIDATE_POP * cap / 100) + 100
        verdict = evaluate_publish(
            _candidate(three_way={"events_included": 0, "bookmaker_included": big}),
            _published())
        assert verdict.codes == ["population_drift"]
        assert "cap" in verdict.summary()
        # Control: just inside it publishes.
        ok = int(CANDIDATE_POP * cap / 100) - 100
        assert evaluate_publish(
            _candidate(three_way={"events_included": 0, "bookmaker_included": ok}),
            _published()).ok

    def test_growth_past_the_ceiling_with_the_widening_taken_out_refuses(self):
        cand_pop = int(PUBLISHED_POP * 2.2)
        verdict = evaluate_publish(_candidate(outcomes=cand_pop), _published())
        assert verdict.codes == ["population_growth_unexplained"]
        assert "taken out" in verdict.summary()

    def test_shrink_across_the_pair_stays_strict(self):
        verdict = evaluate_publish(
            _candidate(outcomes=int(PUBLISHED_POP * 0.9)), _published())
        assert verdict.codes == ["population_shrink"]

    @pytest.mark.parametrize("published,candidate", [
        (CANDIDATE_PREDICATE, PUBLISHED_PREDICATE),
        (PUBLISHED_PREDICATE, "0" * 32),
        ("f" * 32, CANDIDATE_PREDICATE),
    ])
    def test_any_other_pair_refuses(self, published, candidate):
        verdict = evaluate_publish(
            _candidate(predicate=candidate),
            _payload(outcomes=PUBLISHED_POP, predicate=published, three_way=None))
        assert verdict.codes == ["population_drift"]
        assert verdict.predicate_succession is None
