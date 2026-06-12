"""Guardrail tests for the Content Understanding v2 writer (#891).

Covers the two writer bugs caught in CU-1 validation:
1. liveness was computed from the rank-1 outcome, which on bundled prop markets
   (esports, etc.) is a settled side-prop at 0%/100% — falsely "dead".
2. temporal_class was written under the key "temporal", so consumers reading
   "temporal_class" saw null on 100% of profiles.
"""

import inspect

from app.tasks.enrich_markets import _compute_liveness, enrich_cu_v2_profiles, CU_WRITER_REV


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
