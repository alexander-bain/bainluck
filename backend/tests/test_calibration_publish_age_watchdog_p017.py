"""CAL-P017 — watch the OUTPUT, and degrade instead of going dark.

Named failure: an eight-day silent calibration publish failure that ended in a
503 on 2026-08-09. `precompute_calibration_main` ran every hour and failed every
hour (phase `futures`, stage `read:futures_population`, statement timeout at
22.5 min); nothing published after 2026-08-02 03:23Z; /api/calibration served a
progressively staler curve for a week and then went fully dark when the
last-good copy crossed SERVE_MAX_AGE_S.

Two defects, pinned here:
  1. Nothing watched the OUTPUT. Every other watchdog check watches an input or
     a process, and a task that runs on schedule and fails on schedule looks
     healthy to all of them.
  2. SERVE_MAX_AGE_S alone decided when the page went dark, because every serve
     tier is bounded by it and there was no tier below.
"""

from __future__ import annotations

import pytest

from app.tasks.data_quality_watchdog import CHECKS, passes_threshold
from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S, snapshot_verdict


def _check(name: str) -> dict:
    found = [c for c in CHECKS if c["name"] == name]
    assert found, f"{name} is not registered in CHECKS"
    return found[0]


class TestThePublishAgeHeartbeatExists:
    def test_the_check_is_registered_and_watches_output_not_process(self):
        check = _check("calibration_publish_age")
        assert check["severity"] == "P1"
        assert check["comparison"] == "lte"
        assert check["threshold"] == 2, "two beats of an hourly precompute"
        # The witness must be the PUBLISHED artifact, not a task-run counter:
        # the failing task ran on schedule for eight days.
        assert "durable_state_snapshots" in check["query"]
        assert "calibration:main" in check["query"]

    def test_a_fresh_publish_passes_and_a_stale_one_fails(self):
        check = _check("calibration_publish_age")
        assert passes_threshold(0.1, check), "just published"
        assert passes_threshold(2.0, check), "exactly two beats is still fine"
        assert not passes_threshold(2.5, check), "past two beats must fire"
        # The real incident, in the units the check reads.
        assert not passes_threshold(7 * 24.0, check)

    def test_a_missing_snapshot_fails_rather_than_passing(self):
        """The subtle one, and the reason the query COALESCEs.

        `passes_threshold` treats a NULL under `lte` as a PASS — correct for
        coverage checks ("0 resolved markets = nothing to cover"), exactly wrong
        here, where "no snapshot has ever been published" is the worst state of
        all. The sentinel age is what keeps it a failure.
        """
        check = _check("calibration_publish_age")
        assert passes_threshold(None, check), (
            "documenting the trap: a bare NULL would PASS this comparison"
        )
        assert "COALESCE" in check["query"].upper()
        assert "99999" in check["query"]
        assert not passes_threshold(99999, check)

    def test_the_failing_phase_is_attached_to_the_alert(self):
        """Alex's ask: the P1 names the failing phase, not just the symptom."""
        check = _check("calibration_publish_age")
        ctx = check.get("context_query")
        assert ctx, "no context_query — the issue would only restate the symptom"
        assert "calibration:main:phase_ledger" in ctx
        # It must select phases that did NOT succeed; a ledger dump of the
        # healthy ones tells the reader nothing.
        assert "'complete'" in ctx and "NOT IN" in ctx


class TestTheContextQueryCannotSuppressAnAlert:
    """Diagnostic garnish must never turn a fired alert into a swallowed one."""

    @pytest.mark.asyncio
    async def test_a_broken_context_query_returns_empty_and_rolls_back(self):
        from app.tasks.data_quality_watchdog import _run_context_query

        class _Session:
            def __init__(self):
                self.rolled_back = False

            async def execute(self, *_a, **_k):
                raise RuntimeError("relation does not exist")

            async def rollback(self):
                self.rolled_back = True

        session = _Session()
        out = await _run_context_query(session, {"name": "x", "context_query": "SELECT 1"})
        assert out == ""
        # #1001's cascade: a failed statement aborts the asyncpg transaction, so
        # without this rollback every LATER check dies too.
        assert session.rolled_back is True

    @pytest.mark.asyncio
    async def test_a_check_with_no_context_query_is_a_clean_no_op(self):
        from app.tasks.data_quality_watchdog import _run_context_query

        class _Session:
            async def execute(self, *_a, **_k):  # pragma: no cover - must not run
                raise AssertionError("must not query when no context_query is declared")

        assert await _run_context_query(_Session(), {"name": "x"}) == ""


class TestTheLastResortTierServesDatedRatherThanDark:
    """SERVE_MAX_AGE_S must stop being the thing that decides the page is gone."""

    @staticmethod
    def _payload(age_hours: float, version: str = "q267") -> dict:
        """A shape-valid payload, built from the gate's OWN required-section
        list so this test cannot drift out of contract with it."""
        from datetime import datetime, timedelta, timezone

        from app.utils.calibration_publish_gate import REQUIRED_SECTIONS

        generated = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        payload: dict = {section: {} for section in REQUIRED_SECTIONS}
        payload.update(
            {
                "generated_at": generated.isoformat(),
                "population_version": version,
                "buckets": [{"bucket": 0, "n": 1}],
                "total_outcomes": 1,
                "total_markets": 1,
                "total_winners": 1,
            }
        )
        return payload

    def test_an_over_age_snapshot_is_refused_by_the_bounded_tiers(self):
        """The state that produced the 503: past the bound, every tier says no."""
        payload = self._payload(age_hours=7 * 24 + 2)
        verdict = snapshot_verdict(
            payload, expected_version="q267", max_age_s=SERVE_MAX_AGE_S
        )
        assert not verdict.is_servable
        assert verdict.status == "too_old"

    def test_the_same_snapshot_is_servable_once_only_the_age_bound_is_lifted(self):
        payload = self._payload(age_hours=7 * 24 + 2)
        verdict = snapshot_verdict(
            payload, expected_version="q267", max_age_s=float("inf")
        )
        assert verdict.is_servable
        # And it still knows how old it is, which is what the banner renders.
        assert verdict.age_s > 7 * 24 * 3600
        assert verdict.generated_at

    def test_lifting_the_age_bound_does_not_lift_the_version_check(self):
        """The line this change must not cross.

        A payload built under a different population contract is not servable at
        ANY age: its numbers do not mean what the page says they mean, and no
        banner fixes that. Only the age is relaxed, because only the age is
        disclosed.
        """
        payload = self._payload(age_hours=1, version="q999")
        verdict = snapshot_verdict(
            payload, expected_version="q267", max_age_s=float("inf")
        )
        assert not verdict.is_servable

    def test_a_future_dated_snapshot_is_still_refused(self):
        """Infinity lifts the ceiling, not the floor — a clock-skewed or
        corrupt future timestamp is malformed, not merely old."""
        payload = self._payload(age_hours=-48)
        verdict = snapshot_verdict(
            payload, expected_version="q267", max_age_s=float("inf")
        )
        assert not verdict.is_servable
        assert verdict.status == "malformed"

    def test_the_route_has_a_tier_below_the_age_bounded_ones(self):
        """Pinned against the shape of the incident: before CAL-P017 the route
        fell from the last age-bounded tier straight to `_unavailable`."""
        import inspect

        from app.routes import calibration as route

        src = inspect.getsource(route)
        # The tier exists, and it is reached only after the bounded ones.
        assert '_degraded(payload, "durable_over_age", verdict)' in src
        assert 'max_age_s=float("inf")' in src
        assert src.index("durable_over_age") < src.index('_unavailable("no_trustworthy_snapshot")')
        # provenance must still report the canonical source, so `dated` stays True.
        assert "served_from=SOURCE_DURABLE" in src
