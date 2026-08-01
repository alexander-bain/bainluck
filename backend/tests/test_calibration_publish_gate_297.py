"""Queue 297 Item 0/3: the atomic calibration publish gate.

Fixture-first. These encode the semantics the publisher must have:

    candidate -> validate -> publish main + last_good

The published artifact is untouched until a candidate is BOTH complete and
consistent with what it is replacing. Before this queue, `_publish_calibration_main`
wrote whatever it was handed as long as it was non-empty, so a build that lost
two thirds of the population, or one whose well-traded/thin ordering inverted,
replaced the good copy silently. Alex found both by reading the public page.

Required scenarios (Item 0 acceptance): complete healthy build, partial category
build, main-key loss with valid last-good, population shrink, population growth,
explicit version bump, liquidity-rank inversion, category collapse, malformed
payload, cancellation/OOM before publish, one poison category.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.precompute_calibration as pc
from app.utils.calibration_publish_gate import (
    CATEGORY_MIN_N,
    COHORT_MIN_N,
    PublishVerdict,
    census,
    evaluate_publish,
    rejection_issue_body,
)

# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _buckets(*, well_error_pp: float, thin_error_pp: float, well_n: int, thin_n: int):
    """Ten deciles per cohort with a controlled |actual - predicted| gap.

    ``price_moved`` follows the page's own split: the well-traded curve is
    ``price_moved !== false``; the thin curve is ``price_moved === false``.
    """
    rows = []
    for moved, err_pp, total_n in (
        (True, well_error_pp, well_n),
        (False, thin_error_pp, thin_n),
    ):
        per = max(total_n // 10, 1)
        for idx in range(10):
            avg_prob = (idx + 0.5) / 10
            actual = min(max(avg_prob + err_pp / 100, 0.0), 1.0)
            winners = round(actual * per)
            rows.append(
                {
                    "bucket_idx": idx,
                    "source": "kalshi",
                    "category": "politics",
                    "price_moved": moved,
                    "n": per,
                    "winners": winners,
                    "avg_prob": round(avg_prob, 4),
                    "sum_prob": round(avg_prob * per, 4),
                    "sum_sq_err": 0.0,
                    "ci_lower": 0.0,
                    "ci_upper": 1.0,
                }
            )
    return rows


def payload(
    *,
    outcomes: int = 1_000_000,
    version: str = "q267",
    categories: dict[str, int] | None = None,
    well_error_pp: float = 1.0,
    thin_error_pp: float = 4.0,
    well_n: int = 600_000,
    thin_n: int = 400_000,
    generated_at: str = "2026-08-01T12:00:00+00:00",
    drop_sections: tuple[str, ...] = (),
) -> dict:
    cats = categories if categories is not None else {
        "politics": 400_000,
        "sports": 350_000,
        "cricket": 50_000,
        "economics": 200_000,
    }
    full = {
        "buckets": _buckets(
            well_error_pp=well_error_pp,
            thin_error_pp=thin_error_pp,
            well_n=well_n,
            thin_n=thin_n,
        ),
        "by_category": [
            {"category": name, "outcomes": n} for name, n in sorted(cats.items())
        ],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "generated_at": generated_at,
        "population_version": version,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
    }
    for key in drop_sections:
        full.pop(key, None)
    return full


# ---------------------------------------------------------------------------
# Scenario 1 — a complete healthy build publishes
# ---------------------------------------------------------------------------


def test_complete_healthy_build_is_accepted():
    published = payload()
    candidate = payload(outcomes=1_010_000, generated_at="2026-08-01T13:00:00+00:00")

    verdict = evaluate_publish(candidate, published)

    assert verdict.ok, verdict.summary()
    assert verdict.rejections == []
    assert not verdict.first_publish


def test_organic_hourly_growth_inside_tolerance_is_accepted():
    """Resolution genuinely adds outcomes every hour — that must not alarm."""
    published = payload(outcomes=1_000_000)
    candidate = payload(outcomes=1_040_000)  # +4%, inside ±5%

    assert evaluate_publish(candidate, published).ok


# ---------------------------------------------------------------------------
# Scenario 2 — partial / incomplete builds are refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    ["by_category", "by_source", "truth_evidence", "liquidity_filter", "total_markets"],
)
def test_partial_build_missing_a_required_section_is_rejected(missing):
    verdict = evaluate_publish(payload(drop_sections=(missing,)), payload())

    assert not verdict.ok
    assert "incomplete_sections" in verdict.codes
    assert missing in verdict.summary()


def test_empty_curve_is_rejected():
    candidate = payload()
    candidate["buckets"] = []

    verdict = evaluate_publish(candidate, payload())

    assert not verdict.ok
    assert "empty_curve" in verdict.codes


def test_malformed_candidate_is_rejected_without_raising():
    for bad in (None, [], "not a payload", 42, {}):
        verdict = evaluate_publish(bad, payload())
        assert not verdict.ok, bad
        assert verdict.codes


def test_zero_population_is_rejected_even_with_buckets():
    candidate = payload()
    candidate["total_outcomes"] = 0

    verdict = evaluate_publish(candidate, payload())

    assert not verdict.ok
    assert "empty_population" in verdict.codes


# ---------------------------------------------------------------------------
# Scenario 3 — population shrink / growth beyond tolerance
# ---------------------------------------------------------------------------


def test_population_collapse_is_rejected():
    """The observed failure: ~1M outcomes fell to roughly a third."""
    verdict = evaluate_publish(payload(outcomes=340_000), payload(outcomes=1_000_000))

    assert not verdict.ok
    assert "population_drift" in verdict.codes
    assert "-66.0%" in verdict.summary()


def test_unexplained_population_explosion_is_rejected():
    """A gate that only catches shrinkage misses a double-count just as bad."""
    verdict = evaluate_publish(payload(outcomes=1_500_000), payload(outcomes=1_000_000))

    assert not verdict.ok
    assert "population_drift" in verdict.codes


# ---------------------------------------------------------------------------
# Scenario 4 — an explicit version bump authorises the change
# ---------------------------------------------------------------------------


def test_version_bump_authorises_a_population_change():
    verdict = evaluate_publish(
        payload(outcomes=340_000, version="q297"), payload(outcomes=1_000_000, version="q267")
    )

    assert verdict.ok, verdict.summary()
    assert verdict.version_bumped


def test_version_bump_does_not_excuse_an_incomplete_build():
    """A bump says 'this population change is intended', never 'ship a broken build'."""
    verdict = evaluate_publish(
        payload(outcomes=340_000, version="q297", drop_sections=("by_category",)),
        payload(outcomes=1_000_000, version="q267"),
    )

    assert not verdict.ok
    assert "incomplete_sections" in verdict.codes


# ---------------------------------------------------------------------------
# Scenario 5 — category collapse and one poison category
# ---------------------------------------------------------------------------


def test_single_category_collapse_is_rejected_while_the_total_looks_fine():
    """The cricket canary: totals inside tolerance, one cohort gutted."""
    published = payload(
        outcomes=1_000_000,
        categories={"politics": 400_000, "sports": 350_000, "cricket": 50_000, "economics": 200_000},
    )
    candidate = payload(
        outcomes=990_000,  # -1%, inside the population tolerance
        categories={"politics": 400_000, "sports": 350_000, "cricket": 5_000, "economics": 235_000},
    )

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes
    assert "cricket" in verdict.summary()


def test_a_poison_category_vanishing_entirely_is_rejected():
    published = payload(categories={"politics": 400_000, "cricket": 50_000})
    candidate = payload(categories={"politics": 400_000})

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_collapse" in verdict.codes


def test_category_ece_regression_is_rejected_on_a_stable_sample():
    """The cricket shape: the sample held, the accuracy fell off a cliff."""
    published = payload()
    candidate = payload()
    for row in candidate["by_category"]:
        if row["category"] == "cricket":
            row["ece"] = 24.0
    for row in published["by_category"]:
        if row["category"] == "cricket":
            row["ece"] = 3.0

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "category_ece_regression" in verdict.codes
    assert "cricket" in verdict.summary()


def test_a_duplicated_category_is_rejected():
    """A double-counted category makes every ratio below it wrong."""
    candidate = payload()
    candidate["by_category"].append(dict(candidate["by_category"][0]))

    verdict = evaluate_publish(candidate, payload())

    assert not verdict.ok
    assert "duplicate_category" in verdict.codes


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_values_are_contained(bad):
    candidate = payload()
    candidate["by_category"][0]["ece"] = bad

    verdict = evaluate_publish(candidate, payload())

    assert not verdict.ok
    assert "nonfinite_value" in verdict.codes


def test_boundary_changes_are_inclusive_and_publish():
    """Exactly at the limit is allowed; the contract's boundaries are inclusive."""
    published = payload(outcomes=1_000_000, categories={"politics": 40_000})
    exactly_5pct = payload(outcomes=1_050_000, categories={"politics": 40_000})
    exactly_20pct_drop = payload(outcomes=1_000_000, categories={"politics": 32_000})

    assert evaluate_publish(exactly_5pct, published).ok
    assert evaluate_publish(exactly_20pct_drop, published).ok


def test_tiny_category_churn_is_not_an_alarm():
    """Below CATEGORY_MIN_N, ordinary resolution churn swamps the percentage."""
    published = payload(categories={"politics": 400_000, "curling": CATEGORY_MIN_N - 1})
    candidate = payload(categories={"politics": 400_000, "curling": 1})

    assert evaluate_publish(candidate, published).ok


def test_a_new_category_appearing_is_not_a_collapse():
    published = payload(categories={"politics": 400_000})
    candidate = payload(categories={"politics": 400_000, "cycling": 9_000})

    assert evaluate_publish(candidate, published).ok


# ---------------------------------------------------------------------------
# Scenario 6 — liquidity rank inversion
# ---------------------------------------------------------------------------


def test_liquidity_rank_inversion_is_rejected():
    """Thin markets suddenly beating well-traded ones is the reported symptom."""
    published = payload(well_error_pp=1.0, thin_error_pp=5.0)   # well-traded better
    candidate = payload(well_error_pp=5.0, thin_error_pp=1.0)   # thin better

    verdict = evaluate_publish(candidate, published)

    assert not verdict.ok
    assert "liquidity_rank_inversion" in verdict.codes
    assert "well_traded_better -> thin_better" in verdict.summary()


def test_ordering_noise_inside_sampling_tolerance_is_not_an_inversion():
    """The tolerance is the Wilson interval, so a sub-noise wobble is silent."""
    published = payload(well_error_pp=1.0, thin_error_pp=1.05)
    candidate = payload(well_error_pp=1.05, thin_error_pp=1.0)

    assert evaluate_publish(candidate, published).ok


def test_inversion_is_not_asserted_on_a_tiny_cohort():
    """Below COHORT_MIN_N the rendered comparison is not a claim worth gating."""
    published = payload(well_error_pp=1.0, thin_error_pp=8.0, well_n=500, thin_n=500)
    candidate = payload(well_error_pp=8.0, thin_error_pp=1.0, well_n=500, thin_n=500)

    verdict = evaluate_publish(candidate, published)

    assert "liquidity_rank_inversion" not in verdict.codes


def test_version_bump_authorises_a_deliberate_ordering_change():
    published = payload(well_error_pp=1.0, thin_error_pp=5.0, version="q267")
    candidate = payload(well_error_pp=5.0, thin_error_pp=1.0, version="q297")

    assert evaluate_publish(candidate, published).ok


# ---------------------------------------------------------------------------
# Scenario 7 — no trustworthy baseline (cold Redis / first publish)
# ---------------------------------------------------------------------------


def test_first_publish_with_no_prior_artifact_is_allowed():
    """Refusing the first publish would leave the page permanently dark."""
    verdict = evaluate_publish(payload(), None)

    assert verdict.ok
    assert verdict.first_publish


def test_a_malformed_prior_artifact_does_not_block_a_good_candidate():
    verdict = evaluate_publish(payload(), {"buckets": [], "total_outcomes": 0})

    assert verdict.ok
    assert verdict.first_publish


def test_first_publish_still_enforces_completeness():
    verdict = evaluate_publish(payload(drop_sections=("truth_evidence",)), None)

    assert not verdict.ok
    assert "incomplete_sections" in verdict.codes


# ---------------------------------------------------------------------------
# The implementation must not drift from the committed contract corpus
# ---------------------------------------------------------------------------


def test_policy_constants_match_the_contract_corpus():
    """`calibration_publish_gate_contract.json` is the spec; this module is the
    production wiring. The two carry the same numbers or the corpus is a lie.

    (The artifact SHAPES differ on purpose — the corpus uses a synthetic
    `categories`/`sources` schema, production uses `by_category`/`by_source` —
    but the policy thresholds are one contract.)
    """
    import json
    from pathlib import Path

    import app.utils.calibration_publish_gate as gate

    fixture = (
        Path(__file__).parent
        / "evals"
        / "fixtures"
        / "calibration_publish_gate_contract.json"
    )
    policy = json.loads(fixture.read_text())["policy"]

    assert gate.CONTRACT_VERSION == policy["contract_version"]
    assert gate.POPULATION_TOLERANCE * 100 == policy["population_change_limit_pct"]
    assert gate.CATEGORY_DROP_TOLERANCE * 100 == policy["category_drop_limit_pct"]
    assert gate.CATEGORY_MIN_N == policy["category_min_n"]
    assert gate.CATEGORY_ECE_REGRESSION_PP == policy["category_ece_regression_pp"]
    assert (
        gate.TIER_INVERSION_TOLERANCE_FLOOR_PP == policy["tier_inversion_tolerance_pp"]
    )


def test_inversion_tolerance_is_never_looser_than_the_contract_floor():
    """The queue wants a CI-derived tolerance; the corpus fixes a 0.5pp floor.
    The effective value is the wider of the two, so neither is violated."""
    from app.utils.calibration_publish_gate import (
        TIER_INVERSION_TOLERANCE_FLOOR_PP,
        _ordering,
    )

    # A huge, tight cohort drives the Wilson half-width far below the floor; a
    # sub-floor gap must still read as "no ordering claim".
    well = {"n": 5_000_000, "mce_pp": 1.00, "tolerance_pp": 0.001}
    thin = {"n": 5_000_000, "mce_pp": 1.00 + TIER_INVERSION_TOLERANCE_FLOOR_PP - 0.01,
            "tolerance_pp": 0.001}

    assert _ordering(well, thin) is None


# ---------------------------------------------------------------------------
# Determinism, fingerprints, and the evidence packet
# ---------------------------------------------------------------------------


def test_verdict_is_deterministic():
    published, candidate = payload(outcomes=1_000_000), payload(outcomes=300_000)

    first = evaluate_publish(candidate, published)
    second = evaluate_publish(candidate, published)

    assert first.codes == second.codes
    assert first.fingerprint == second.fingerprint


def test_fingerprint_is_stable_across_repeats_of_the_same_failure_class():
    """No alert storm: an hourly beat reproducing the same bad shape dedupes."""
    published = payload(outcomes=1_000_000)
    a = evaluate_publish(payload(outcomes=300_000), published)
    b = evaluate_publish(payload(outcomes=310_000), published)  # different counts

    assert a.fingerprint == b.fingerprint


def test_fingerprint_differs_across_failure_classes():
    published = payload(outcomes=1_000_000)
    drift = evaluate_publish(payload(outcomes=300_000), published)
    inversion = evaluate_publish(
        payload(well_error_pp=5.0, thin_error_pp=1.0), payload(well_error_pp=1.0, thin_error_pp=5.0)
    )

    assert drift.fingerprint != inversion.fingerprint


def test_rejection_body_carries_the_count_bridge():
    verdict = evaluate_publish(payload(outcomes=300_000), payload(outcomes=1_000_000))
    body = rejection_issue_body(verdict, fingerprint_marker="calibration-publish-gate")

    assert "1,000,000" in body and "300,000" in body
    assert "Count bridge" in body
    assert "CALIBRATION_POPULATION_VERSION" in body
    assert verdict.fingerprint in body


def test_census_reads_the_cohort_split_the_page_renders():
    """price_moved null (sportsbook consensus) counts as well-traded, per the page."""
    p = payload(well_n=600_000, thin_n=400_000)
    p["buckets"].append(
        {
            "bucket_idx": 0, "source": "odds_api", "category": "sports",
            "price_moved": None, "n": 100_000, "winners": 50_000,
            "avg_prob": 0.5, "sum_prob": 50_000.0, "sum_sq_err": 0.0,
            "ci_lower": 0.0, "ci_upper": 1.0,
        }
    )
    c = census(p)

    assert c["cohorts"]["well_traded"]["n"] == 700_000
    assert c["cohorts"]["thin"]["n"] == 400_000


# ---------------------------------------------------------------------------
# Publisher wiring — atomicity, cancellation, and preservation of last-good
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Records SETs and can be told which key write should blow up."""

    def __init__(self, initial: dict | None = None, fail_on: str | None = None):
        self.store = dict(initial or {})
        self.fail_on = fail_on
        self.sets: list[str] = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        if self.fail_on == key:
            raise RuntimeError("redis SET failed")
        self.sets.append(key)
        self.store[key] = value


class _FakeCM:
    """Task-session stand-in; the beat arms a statement_timeout on it (Queue 274)."""

    async def __aenter__(self):
        from unittest.mock import AsyncMock

        return AsyncMock()

    async def __aexit__(self, *a):
        return False


def _patch_beat(response, redis):
    """Patch the beat's compute + Redis so only publication semantics are under test."""
    from unittest.mock import AsyncMock

    return (
        patch("app.tasks.base.get_task_session", return_value=_FakeCM()),
        patch.object(pc, "compute_calibration_payload", AsyncMock(return_value=response)),
        patch("app.tasks.redis_state.get_redis_client", return_value=redis),
    )


@pytest.mark.asyncio
async def test_rejected_candidate_touches_neither_main_nor_last_good():
    """The core atomicity claim: a bad build cannot reach either published key."""
    good = payload(outcomes=1_000_000)
    redis = _FakeRedis(
        {
            pc._MAIN_KEY: json.dumps(good),
            pc._MAIN_LAST_GOOD_KEY: json.dumps(good),
        }
    )
    bad = payload(outcomes=300_000)

    with patch.object(pc, "_file_publish_gate_rejection", MagicMock()):
        for p in _patch_beat(bad, redis):
            p.start()
        try:
            with pytest.raises(RuntimeError, match="publish gate"):
                await pc._precompute_calibration_main()
        finally:
            patch.stopall()

    assert redis.sets == [], "a rejected candidate must not write any key"
    assert json.loads(redis.store[pc._MAIN_KEY])["total_outcomes"] == 1_000_000
    assert json.loads(redis.store[pc._MAIN_LAST_GOOD_KEY])["total_outcomes"] == 1_000_000


@pytest.mark.asyncio
async def test_accepted_candidate_publishes_both_keys():
    good = payload(outcomes=1_000_000)
    redis = _FakeRedis({pc._MAIN_KEY: json.dumps(good), pc._MAIN_LAST_GOOD_KEY: json.dumps(good)})
    better = payload(outcomes=1_020_000)

    for p in _patch_beat(better, redis):
        p.start()
    try:
        summary = await pc._precompute_calibration_main()
    finally:
        patch.stopall()

    assert set(redis.sets) == {pc._MAIN_KEY, pc._MAIN_LAST_GOOD_KEY}
    assert summary["gate"]["ok"] is True
    assert json.loads(redis.store[pc._MAIN_KEY])["total_outcomes"] == 1_020_000


@pytest.mark.asyncio
async def test_rejection_files_one_deduped_issue_with_the_diff():
    good = payload(outcomes=1_000_000)
    redis = _FakeRedis({pc._MAIN_KEY: json.dumps(good)})
    filed = MagicMock()

    with patch.object(pc, "_file_publish_gate_rejection", filed):
        for p in _patch_beat(payload(outcomes=300_000), redis):
            p.start()
        try:
            with pytest.raises(RuntimeError):
                await pc._precompute_calibration_main()
        finally:
            patch.stopall()

    assert filed.call_count == 1
    verdict = filed.call_args.args[0]
    assert isinstance(verdict, PublishVerdict)
    assert "population_drift" in verdict.codes


@pytest.mark.asyncio
async def test_a_cancelled_compute_never_reaches_the_gate_or_the_keys():
    """OOM/SIGKILL/statement_timeout mid-build: nothing published, last-good intact."""
    import asyncio
    from unittest.mock import AsyncMock

    good = payload()
    redis = _FakeRedis({pc._MAIN_KEY: json.dumps(good), pc._MAIN_LAST_GOOD_KEY: json.dumps(good)})

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM()), patch.object(
        pc, "compute_calibration_payload", AsyncMock(side_effect=asyncio.CancelledError())
    ), patch("app.tasks.redis_state.get_redis_client", return_value=redis):
        with pytest.raises(asyncio.CancelledError):
            await pc._precompute_calibration_main()

    assert redis.sets == []
    assert json.loads(redis.store[pc._MAIN_LAST_GOOD_KEY])["total_outcomes"] == 1_000_000


@pytest.mark.asyncio
async def test_main_key_loss_with_a_valid_last_good_still_gates_against_last_good():
    """Main evicted (a 50MB allkeys-lru instance does this) — last-good is the baseline.

    Without this the gate would see 'no prior artifact', call it a first publish,
    and wave through exactly the collapsed population it exists to stop.
    """
    good = payload(outcomes=1_000_000)
    redis = _FakeRedis({pc._MAIN_LAST_GOOD_KEY: json.dumps(good)})  # main absent

    with patch.object(pc, "_file_publish_gate_rejection", MagicMock()):
        for p in _patch_beat(payload(outcomes=300_000), redis):
            p.start()
        try:
            with pytest.raises(RuntimeError, match="publish gate"):
                await pc._precompute_calibration_main()
        finally:
            patch.stopall()

    assert redis.sets == []


@pytest.mark.asyncio
async def test_both_keys_cold_publishes_the_first_good_build():
    """A total cache loss must recover, not deadlock behind its own gate."""
    redis = _FakeRedis({})

    for p in _patch_beat(payload(outcomes=1_000_000), redis):
        p.start()
    try:
        summary = await pc._precompute_calibration_main()
    finally:
        patch.stopall()

    assert set(redis.sets) == {pc._MAIN_KEY, pc._MAIN_LAST_GOOD_KEY}
    assert summary["gate"]["first_publish"] is True


@pytest.mark.asyncio
async def test_an_unreadable_baseline_does_not_block_publication():
    """A corrupt prior value is a cache problem, not a reason to stop publishing."""
    redis = _FakeRedis({pc._MAIN_KEY: "{not json", pc._MAIN_LAST_GOOD_KEY: "{not json"})

    for p in _patch_beat(payload(), redis):
        p.start()
    try:
        summary = await pc._precompute_calibration_main()
    finally:
        patch.stopall()

    assert set(redis.sets) == {pc._MAIN_KEY, pc._MAIN_LAST_GOOD_KEY}
    assert summary["gate"]["first_publish"] is True
