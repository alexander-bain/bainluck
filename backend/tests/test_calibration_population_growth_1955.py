"""#1955 / CAL-P070: the publish gate must tell GROWTH from a METHODOLOGY change.

The defect, measured live on 2026-08-18 and refused once an hour for the twelve
hours it took to write this file: a build that completed every phase for the
first time since 2026-08-02 came in +17.9% (706,290 -> 832,650) and the gate's
symmetric ±5% band refused it, because a count cannot say WHY it moved. The
refusal was not a bug in the guard — it was the guard answering a question it
had never been given the evidence to answer, and getting more certain the longer
the build ran. A build slower than its own freshness budget could therefore never
publish, and the only available response to ordinary time was to keep declaring
new population versions, which drains the version of its meaning.

Every case here is driven through the REAL ``evaluate_publish`` and the REAL
``snapshot_verdict``. The numbers in the growth cases are the production ones off
issue #1968, not invented ones, so a future reader can check the fix against the
incident rather than against a fixture.

Both directions, per gotcha #43: growth publishes AND a changed predicate still
refuses. A guard tested in one direction is half a guard.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.calibration_publish_gate import (
    POPULATION_GROWTH_CEILING,
    POPULATION_TOLERANCE,
    PREDICATE_FIELD,
    census,
    evaluate_publish,
    snapshot_verdict,
)

#: The two real censuses from #1968's count bridge.
PUBLISHED_POP = 706_290
CANDIDATE_POP = 832_650

PREDICATE_A = "3f2a11c0deadbeef3f2a11c0deadbeef"
PREDICATE_B = "99887766554433221100ffeeddccbbaa"


def _payload(
    *,
    outcomes: int,
    version: str = "q268",
    predicate: str | None = PREDICATE_A,
    generated_at: str | None = None,
    categories: dict[str, int] | None = None,
) -> dict:
    """A structurally complete artifact — only the fields under test vary.

    Built as a real dict the gate's own ``census`` can reduce, so a section this
    file forgets shows up as ``incomplete_sections`` rather than as a silent pass
    on a rule that never ran.
    """
    cats = categories or {"baseball": int(outcomes * 0.4), "basketball": int(outcomes * 0.2)}
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
            {"category": name, "outcomes": n, "ece": 1.5} for name, n in cats.items()
        ],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes - 100,
        "total_winners": outcomes // 3,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applied": True},
        "truth_evidence": {"rungs": []},
        "population_version": version,
    }
    if predicate is not None:
        payload[PREDICATE_FIELD] = predicate
    return payload


class TestGrowthOnAnUnchangedPredicatePublishes:
    """Acceptance criterion 1: N days of ordinary growth publishes, no bump."""

    def test_the_2026_08_18_candidate_publishes_unchanged_predicate_no_bump(self):
        published = _payload(outcomes=PUBLISHED_POP)
        candidate = _payload(outcomes=CANDIDATE_POP)

        verdict = evaluate_publish(candidate, published)

        assert verdict.ok, verdict.summary()
        assert verdict.codes == []
        assert not verdict.version_bumped, (
            "the whole point is that this publishes WITHOUT a bump — a test that "
            "let the bump do the work would pass on the unfixed gate"
        )

    def test_the_growth_is_recorded_not_merely_permitted(self):
        """A +17.9% move that decided a publish must appear in the record.

        The fourth instance of uncheckable-read-as-clean in this program was an
        accepted path that reported nothing. An acceptance with no observation is
        indistinguishable from a build that grew 0.1%.
        """
        verdict = evaluate_publish(
            _payload(outcomes=CANDIDATE_POP), _payload(outcomes=PUBLISHED_POP)
        )

        assert verdict.observation_codes == ["population_growth_acknowledged"]
        [obs] = verdict.observations
        assert obs["previous"] == PUBLISHED_POP
        assert obs["candidate"] == CANDIDATE_POP
        assert obs["drift_pct"] == pytest.approx(17.89, abs=0.05)
        assert "706,290 -> 832,650" in obs["detail"]
        assert "same population predicate" in obs["detail"]
        assert "publish gate passed" in verdict.summary()
        assert "17.9%" in verdict.summary()

    def test_growth_inside_the_ordinary_band_records_nothing(self):
        """No observation for a normal beat — the record must stay readable."""
        verdict = evaluate_publish(
            _payload(outcomes=int(PUBLISHED_POP * 1.02)), _payload(outcomes=PUBLISHED_POP)
        )
        assert verdict.ok
        assert verdict.observations == []


class TestAChangedPredicateStillRefuses:
    """Acceptance criterion 2: the hazard the guard exists for, undiminished."""

    def test_same_size_move_refuses_when_the_predicate_moved(self):
        published = _payload(outcomes=PUBLISHED_POP, predicate=PREDICATE_A)
        candidate = _payload(outcomes=CANDIDATE_POP, predicate=PREDICATE_B)

        verdict = evaluate_publish(candidate, published)

        assert not verdict.ok
        assert verdict.codes == ["population_drift"]
        [r] = verdict.rejections
        assert r["same_predicate"] is False
        assert r["published_predicate"] == PREDICATE_A
        assert r["candidate_predicate"] == PREDICATE_B

    def test_the_reason_names_composition_not_volume(self):
        """The refusal must say WHICH rows, not just how many.

        #1955's acceptance criteria are explicit that the message continues to
        state both numbers and the limit — today's message is why the incident
        was diagnosable in one read — and that it now names the qualifying rule.
        """
        verdict = evaluate_publish(
            _payload(outcomes=CANDIDATE_POP, predicate=PREDICATE_B),
            _payload(outcomes=PUBLISHED_POP, predicate=PREDICATE_A),
        )
        detail = verdict.rejections[0]["detail"]

        assert "WHICH rows qualify" in detail
        assert "706,290 -> 832,650" in detail  # both numbers, still
        assert "±5%" in detail  # and the limit
        assert "+17.9%" in detail

    @pytest.mark.parametrize(
        "cand_predicate,prev_predicate",
        [
            (None, PREDICATE_A),  # candidate predates the field
            (PREDICATE_A, None),  # baseline predates the field
            (None, None),  # neither states one
            ("", ""),  # both state an empty one
        ],
    )
    def test_an_unstated_predicate_is_never_a_match(self, cand_predicate, prev_predicate):
        """Absent is not equal. Silence on both sides is not agreement.

        Reading two unstated predicates as "the same" would excuse every drift on
        every pre-#1955 artifact forever — an unchecked read passing as a clean
        one, which is the exact shape this program keeps finding.
        """
        verdict = evaluate_publish(
            _payload(outcomes=CANDIDATE_POP, predicate=cand_predicate),
            _payload(outcomes=PUBLISHED_POP, predicate=prev_predicate),
        )

        assert not verdict.ok
        assert verdict.codes == ["population_drift"]
        assert "unstated" in verdict.rejections[0]["detail"]

    def test_a_version_bump_still_waives_it(self):
        """The operator's escape hatch is untouched."""
        verdict = evaluate_publish(
            _payload(outcomes=CANDIDATE_POP, version="q269", predicate=PREDICATE_B),
            _payload(outcomes=PUBLISHED_POP, version="q268", predicate=PREDICATE_A),
        )
        assert verdict.ok
        assert verdict.version_bumped


class TestShrinkIsNeverExcused:
    """Time only ADDS outcomes, so a shrink is never explained by elapsed time."""

    def test_a_collapse_refuses_even_on_an_identical_predicate(self):
        published = _payload(outcomes=PUBLISHED_POP)
        candidate = _payload(outcomes=PUBLISHED_POP // 3)  # the ~3x collapse

        verdict = evaluate_publish(candidate, published)

        assert not verdict.ok
        assert "population_shrink" in verdict.codes
        assert verdict.rejections[0]["same_predicate"] is True
        assert "only ADDS" in verdict.rejections[0]["detail"]

    def test_the_original_tolerance_is_unchanged_on_the_shrink_side(self):
        published = _payload(outcomes=100_000)
        just_inside = _payload(outcomes=int(100_000 * (1 - POPULATION_TOLERANCE) + 1))
        just_outside = _payload(outcomes=int(100_000 * (1 - POPULATION_TOLERANCE) - 1))

        assert evaluate_publish(just_inside, published).ok
        assert "population_shrink" in evaluate_publish(just_outside, published).codes


class TestTheGrowthCeiling:
    """A matching predicate excuses growth, not any amount of it."""

    def test_a_doubling_refuses_even_on_an_identical_predicate(self):
        published = _payload(outcomes=PUBLISHED_POP)
        candidate = _payload(outcomes=int(PUBLISHED_POP * (2 + POPULATION_GROWTH_CEILING)))

        verdict = evaluate_publish(candidate, published)

        assert not verdict.ok
        assert verdict.codes == ["population_growth_unexplained"]
        assert "duplication" in verdict.rejections[0]["detail"]

    def test_the_ceiling_admits_the_incident_with_room_to_spare(self):
        """Guards against a future tightening that silently re-breaks #1955."""
        incident_growth = (CANDIDATE_POP - PUBLISHED_POP) / PUBLISHED_POP
        assert POPULATION_GROWTH_CEILING > incident_growth * 2


class TestTheOtherRulesStillRun:
    """Splitting rule 2 must not have taken rules 3 and 4 with it."""

    def test_a_category_collapse_still_refuses_under_a_matching_predicate(self):
        published = _payload(
            outcomes=PUBLISHED_POP, categories={"baseball": 200_000, "cricket": 10_000}
        )
        candidate = _payload(
            outcomes=PUBLISHED_POP, categories={"baseball": 200_000, "cricket": 100}
        )

        verdict = evaluate_publish(candidate, published)

        assert not verdict.ok
        assert "category_collapse" in verdict.codes

    def test_an_incomplete_candidate_still_refuses_under_a_matching_predicate(self):
        candidate = _payload(outcomes=CANDIDATE_POP)
        del candidate["truth_evidence"]

        verdict = evaluate_publish(candidate, _payload(outcomes=PUBLISHED_POP))

        assert not verdict.ok
        assert "incomplete_sections" in verdict.codes


class TestThePayloadStatesItsPredicate:
    """The gate's evidence has to be on the artifact, or none of this runs."""

    def test_census_extracts_the_predicate(self):
        assert census(_payload(outcomes=10, predicate=PREDICATE_A))[
            "population_predicate"
        ] == PREDICATE_A
        assert census(_payload(outcomes=10, predicate=None))["population_predicate"] is None

    def test_the_producer_stamps_a_stable_digest_on_what_it_publishes(self):
        """Drive the real producer function, not a copy of its shape.

        A test that asserted the payload builder CONTAINS the string
        ``population_predicate_fingerprint`` would pass on a builder that stamped
        it as ``None`` — the grep-test failure mode this program has now been
        bitten by twice.
        """
        from app.tasks import precompute_calibration as pc

        first = pc.population_predicate_fingerprint()
        assert isinstance(first, str) and len(first) == 32
        assert first == pc.population_predicate_fingerprint(), "must be stable"
        assert not first.startswith("unavailable:")

    def test_the_predicate_digest_is_not_the_carry_fingerprint(self):
        """They answer different questions and must not be merged.

        ``_main_input_fingerprint`` includes the population VERSION and the whole
        payload builder, so using it as the predicate would make every ordinary
        edit — and every version bump — read as "the methodology changed",
        re-arming the strict band on exactly the builds #1955 needs relaxed.
        """
        from app.tasks import precompute_calibration as pc

        assert pc.population_predicate_fingerprint() != pc._main_input_fingerprint()

    def test_the_digest_moves_when_the_population_predicate_moves(self):
        from app.tasks import precompute_calibration as pc

        before = pc.population_predicate_fingerprint()
        original = pc._calibration_population_ctes

        def _changed(*args, **kwargs):  # pragma: no cover - source is what matters
            """A different population."""
            return original(*args, **kwargs)

        pc._calibration_population_ctes = _changed
        try:
            assert pc.population_predicate_fingerprint() != before
        finally:
            pc._calibration_population_ctes = original
        assert pc.population_predicate_fingerprint() == before

    def test_the_digest_does_not_move_on_a_version_bump(self):
        """The one property that makes it a discriminator at all."""
        from app.tasks import precompute_calibration as pc

        before = pc.population_predicate_fingerprint()
        original = pc.CALIBRATION_POPULATION_VERSION
        pc.CALIBRATION_POPULATION_VERSION = "q999-not-a-real-version"
        try:
            assert pc.population_predicate_fingerprint() == before
        finally:
            pc.CALIBRATION_POPULATION_VERSION = original


class TestTheRolloverDeclarationKeepsThePageLit:
    """CAL-P070: a bump must not be an outage (the 2026-08-02 revert).

    The ratified rollover contract's ``deploy-before-candidate`` case has always
    said a predecessor is served ``previous_degraded`` — dated, provenanced,
    read-only. Nothing implemented it, so the corpus passed 26/26 while the page
    would have 503'd. These assert the wire.
    """

    def test_an_undeclared_predecessor_is_still_refused_at_any_age(self):
        """CAL-P017 stands where no declaration exists."""
        verdict = snapshot_verdict(
            _payload(outcomes=10_000, version="q100-ancient"),
            expected_version="q268",
            compatible_versions=(),
        )
        assert verdict.status == "wrong_version"
        assert not verdict.is_servable
        assert not verdict.is_previous_version

    def test_a_declared_predecessor_is_servable_but_never_current(self):
        verdict = snapshot_verdict(
            _payload(outcomes=10_000, version="q267"),
            expected_version="q268",
            compatible_versions=("q267",),
        )
        assert verdict.status == "previous_version"
        assert verdict.is_previous_version
        assert not verdict.is_servable, (
            "'previous' must never satisfy is_servable — every existing tier "
            "treats that as 'this is the current curve' and would serve it "
            "undated and unmarked"
        )
        assert verdict.population_version == "q267"

    def test_an_expired_predecessor_is_refused_not_served(self):
        """The contract's ``previous-expired-refused`` case."""
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        verdict = snapshot_verdict(
            _payload(outcomes=10_000, version="q267", generated_at=old),
            expected_version="q268",
            compatible_versions=("q267",),
            max_age_s=7 * 86400,
        )
        assert verdict.status == "too_old"
        assert not verdict.is_previous_version

    def test_the_current_version_is_still_plain_ok(self):
        verdict = snapshot_verdict(
            _payload(outcomes=10_000, version="q268"),
            expected_version="q268",
            compatible_versions=("q267",),
        )
        assert verdict.status == "ok"
        assert verdict.is_servable
        assert not verdict.is_previous_version

    def test_the_shipped_declaration_covers_the_last_published_artifact(self):
        """The invariant that decides whether THIS deploy goes dark.

        Production's durable ``calibration:main`` is q267. If the shipped
        declaration does not name it, every tier refuses on boot.
        """
        from app.tasks import precompute_calibration as pc

        verdict = snapshot_verdict(
            _payload(outcomes=PUBLISHED_POP, version="q267"),
            expected_version=pc.CALIBRATION_POPULATION_VERSION,
            compatible_versions=tuple(pc.COMPATIBLE_PREVIOUS_POPULATION_VERSIONS),
        )
        assert verdict.status in ("ok", "previous_version"), (
            f"a q267 artifact is {verdict.status!r} under the shipped constants — "
            "/api/calibration 503s from the moment this deploys until the first "
            "build under the new version publishes"
        )


class TestTheContractCorpusStillPasses:
    """The rollover corpus is the spec; the wire must not contradict it."""

    def test_corpus_is_green(self):
        from pathlib import Path

        from scripts.evals.calibration_version_rollover_contract import (
            evaluate_corpus,
            load_corpus,
        )

        fixture = (
            Path(__file__).parent
            / "evals"
            / "fixtures"
            / "calibration_version_rollover_contract.json"
        )
        report = evaluate_corpus(load_corpus(fixture))
        assert report["passed"] == report["total"]

    def test_the_deploy_before_candidate_case_is_what_we_implemented(self):
        """Bind the shipped disposition to the ratified one, by name."""
        from pathlib import Path

        from scripts.evals.calibration_version_rollover_contract import load_corpus

        fixture = (
            Path(__file__).parent
            / "evals"
            / "fixtures"
            / "calibration_version_rollover_contract.json"
        )
        case = next(
            copy.deepcopy(row)
            for row in load_corpus(fixture)["cases"]
            if row["id"] == "deploy-before-candidate"
        )
        result = case["result"]
        assert result["disposition"] == "previous_degraded"
        assert result["degraded"] is True
        assert result["dated"] is True
        assert result["read_only"] is True
        assert result["may_seed_current"] is False


class TestTheAdmittedGrowthReachesTheRunEvidence:
    """An observation nobody can read is not a record.

    The gate object is in-process; ``gate`` in the run summary and
    ``runner.outcome`` are what ``save_phase_ledger`` persists and what an
    operator queries. A pass that excused +17.9% and a pass on a 0.1% beat must
    not be byte-identical there.
    """

    @pytest.mark.asyncio
    async def test_a_real_beat_publishes_the_growth_it_admitted(self):
        """Drive the beat, read the summary it returns. No source-text greps.

        CAL-P066 banked why: a grep passes through the change it exists to catch
        (INT-080 cost a wave slot to the inverse). So this runs the real
        ``_precompute_calibration_main`` against the real gate, on the real
        incident numbers, and asserts the published record — which is the thing
        an operator would actually query.
        """
        import json
        from unittest.mock import patch

        from app.tasks import precompute_calibration as pc
        from tests.test_calibration_publish_gate_297 import (
            _FakeRedis,
            _patch_beat,
            payload,
        )

        def _with_predicate(p: dict) -> dict:
            return {**p, PREDICATE_FIELD: PREDICATE_A}

        published = _with_predicate(payload(outcomes=PUBLISHED_POP))
        candidate = _with_predicate(payload(outcomes=CANDIDATE_POP))
        redis = _FakeRedis(
            {
                pc._MAIN_KEY: json.dumps(published),
                pc._MAIN_LAST_GOOD_KEY: json.dumps(published),
            }
        )

        for p in _patch_beat(candidate, redis):
            p.start()
        try:
            summary = await pc._precompute_calibration_main()
        finally:
            patch.stopall()

        # It published — this is the whole of #1955, end to end.
        assert summary["gate"]["ok"] is True
        assert set(redis.sets) == {pc._MAIN_KEY, pc._MAIN_LAST_GOOD_KEY}
        assert (
            json.loads(redis.store[pc._MAIN_KEY])["total_outcomes"] == CANDIDATE_POP
        )
        # ...and it said what it excused, in the record that gets persisted.
        assert summary["gate"]["observations"] == ["population_growth_acknowledged"]
        [detail] = summary["gate"]["observation_details"]
        assert "706,290 -> 832,650" in detail

    @pytest.mark.asyncio
    async def test_an_ordinary_beat_records_no_observation(self):
        """The other direction: the record stays quiet when nothing was excused."""
        import json
        from unittest.mock import patch

        from app.tasks import precompute_calibration as pc
        from tests.test_calibration_publish_gate_297 import (
            _FakeRedis,
            _patch_beat,
            payload,
        )

        published = payload(outcomes=1_000_000)
        redis = _FakeRedis(
            {
                pc._MAIN_KEY: json.dumps(published),
                pc._MAIN_LAST_GOOD_KEY: json.dumps(published),
            }
        )

        for p in _patch_beat(payload(outcomes=1_020_000), redis):
            p.start()
        try:
            summary = await pc._precompute_calibration_main()
        finally:
            patch.stopall()

        assert summary["gate"]["ok"] is True
        assert summary["gate"]["observations"] == []

    def test_observation_codes_are_stable_and_deduped(self):
        verdict = evaluate_publish(
            _payload(outcomes=CANDIDATE_POP), _payload(outcomes=PUBLISHED_POP)
        )
        assert verdict.observation_codes == sorted(set(verdict.observation_codes))
        assert all(isinstance(o["detail"], str) and o["detail"] for o in verdict.observations)
