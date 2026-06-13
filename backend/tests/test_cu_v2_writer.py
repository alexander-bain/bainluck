"""Guardrail tests for the Content Understanding v2 writer (#891).

Covers the two writer bugs caught in CU-1 validation:
1. liveness was computed from the rank-1 outcome, which on bundled prop markets
   (esports, etc.) is a settled side-prop at 0%/100% — falsely "dead".
2. temporal_class was written under the key "temporal", so consumers reading
   "temporal_class" saw null on 100% of profiles.
"""

import inspect

from app.tasks.enrich_markets import (
    _compute_liveness,
    enrich_cu_v2_profiles,
    CU_WRITER_REV,
    _CU_V2_PROMPT,
)


class TestComputeLiveness:
    def test_resolved_status_short_circuits(self):
        assert _compute_liveness([0.5], "resolved") == "resolved"
        assert _compute_liveness([0.5], "closed") == "resolved"

    def test_none_or_empty_is_unknown(self):
        assert _compute_liveness(None, "open") == "unknown"
        assert _compute_liveness([], "open") == "unknown"
        assert _compute_liveness([None, None], "open") == "unknown"

    def test_coinflip_is_active(self):
        assert _compute_liveness([0.52, 0.48], "open") == "active"

    def test_decided_two_way_is_dead(self):
        assert _compute_liveness([0.995, 0.005], "open") == "dead"
        assert _compute_liveness([0.01, 0.99], "open") == "dead"

    def test_near_certain_is_extreme(self):
        # 3% / 97% — decided in practice but not pinned; "extreme" still passes
        # the "dead/extreme" liveness gate for genuinely-dead markets.
        assert _compute_liveness([0.03, 0.97], "open") == "extreme"

    def test_bundled_market_uses_most_competitive_outcome(self):
        # Open match whose rank-1 outcome is a settled prop at 100% (the old bug),
        # but which still has a genuine coin-flip prop -> must read "active".
        bundled = [1.0, 1.0, 1.0, 0.5, 0.1]
        assert _compute_liveness(bundled, "open") == "active"

    def test_fully_settled_bundle_is_dead(self):
        # Every outcome pinned -> nothing in play -> dead.
        assert _compute_liveness([1.0, 1.0, 0.0, 0.999], "open") == "dead"


class TestProfileShape:
    def test_writer_rev_is_bumped_past_one(self):
        # rev 1 == original (implicit) writer; the fix ships as rev >= 2 so old
        # profiles get re-tagged without a schema_version bump.
        assert CU_WRITER_REV >= 2

    def test_profile_uses_temporal_class_key(self):
        # The profile dict must emit temporal_class (not temporal) and writer_rev.
        src = inspect.getsource(enrich_cu_v2_profiles)
        assert '"temporal_class": raw.get("temporal")' in src
        assert '"writer_rev": CU_WRITER_REV' in src
        assert '"temporal":' not in src


class TestWriterV3Rubric:
    """Round-1 grading verdict (#891, cu_grading_round1.md): the v3 prompt must
    carry the explicit rubric rules + calibrated anchors that fixed the failing
    fields (topic 88.5%, temporal 69%, stakes 69%, breadth 69%, oddity 54%).
    """

    def test_writer_rev_is_v3(self):
        # v3 ships with the round-1 rubric; the bump forces a re-tag of rev-2 rows.
        assert CU_WRITER_REV >= 3

    def test_esports_is_a_first_class_topic(self):
        # Rule 2: ALL esports is topic 'esports', never entertainment/sports —
        # so it must be in the topic enum or the model can't emit it.
        assert "esports" in _CU_V2_PROMPT

    def test_prompt_encodes_the_failing_field_rules(self):
        p = _CU_V2_PROMPT
        # oddity baseline 1 (was drifting to 2)
        assert "oddity baseline is 1" in p
        # stakes = real-world consequence, not volume (geopolitics vs esports inversion)
        assert "real-world consequence" in p and "NOT market volume" in p
        # breadth = THIS market's reach, not the topic's fame
        assert "THIS market" in p
        # temporal: deadline for "by [date]?", periodic for recurring, reserve event_tied
        assert "periodic" in p and "deadline" in p and "event_tied" in p
        # geopolitics covers armed conflict regardless of countries
        assert "geopolitics" in p

    def test_prompt_carries_calibrated_anchors(self):
        p = _CU_V2_PROMPT
        # A representative subset of Alex's verbatim anchors.
        assert "ceasefire" in p           # geopolitics / deadline / S4 B4 O1
        assert "Fed Decision" in p        # economics / periodic / S3 B4 O1
        assert "Clavicular pregnancy" in p  # health / oddity 5


class TestWriterV4Rubric:
    """Round-2 sample findings (#891, Queue #47): v3 mis-tagged ATP tennis as
    topic=esports and emitted wild-year event_dates. v4 must guard both.
    """

    def test_writer_rev_is_v4(self):
        # The bump forces a re-tag of rev-3 rows with the corrected prompt.
        assert CU_WRITER_REV >= 4

    def test_esports_is_video_games_only(self):
        p = _CU_V2_PROMPT
        # Rule 2 must scope esports to video games and exclude human-played sports.
        assert "VIDEO-GAME" in p or "video-game" in p
        # tennis (and physical sports) must be called out as NOT esports
        assert "tennis" in p.lower()
        assert "not esports" in p.lower() or "never \"esports\"" in p.lower() \
            or "is NOT automatically esports" in p

    def test_tennis_anchor_present(self):
        # A human-played "X vs Y" match anchored to sports, not esports.
        p = _CU_V2_PROMPT
        assert "Stuttgart Open" in p

    def test_event_date_sanity_guards_past_and_wild_years(self):
        p = _CU_V2_PROMPT
        # Rule 6 must reject distant-past dates, not just far-future ones.
        assert "distant past" in p or "in the past" in p
        assert "13 months" in p
