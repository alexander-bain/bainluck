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


class TestTheAlertNamesTheStageNotOnlyThePhase:
    """CAL-P023 — the drill ran, and the alert stopped one level short.

    Issue #1604 (auto-filed 2026-08-09 09:46 PT) is this check's FIRST live
    firing, and it worked: value 181.36h against a 2h threshold, P1, deduped,
    with the phase attached. But the body read ``phase: futures, phase_status:
    cancelled, duration_ms: 726557`` and then ``detail: ''``.

    Empty, because a phase CANCELLED by the build's own budget writes no detail
    — only a phase that dies on a statement timeout does. CAL-P017 promised
    "phase futures, stage ``read:futures_population``"; production delivered the
    phase and not the stage, and the stage is the half that says WHERE the time
    went.

    It was never in ``phases[]`` to be read. ``record_stage`` accumulates into a
    TOP-LEVEL ``stages`` map, so no query over ``phases[]`` could ever have
    named a stage, whatever the terminal state.
    """

    def test_the_stage_map_is_read_not_only_the_phase_array(self):
        check = _check("calibration_publish_age")
        ctx = check.get("context_query")
        # Non-vacuity: the pre-CAL-P023 query read ONLY `phases`, so both of
        # these fail against it.
        assert "'stages'" in ctx, "the top-level stage map is where the stage names live"
        assert "jsonb_each" in ctx, "the stage map is an object, not an array"
        # The phase half must SURVIVE the addition — this is additive evidence,
        # not a replacement.
        assert "jsonb_array_elements" in ctx and "'complete'" in ctx

    def test_stages_are_ordered_by_cost_so_the_expensive_one_leads(self):
        ctx = _check("calibration_publish_age")["context_query"]
        assert "ORDER BY" in ctx and "DESC" in ctx

    @pytest.mark.asyncio
    async def test_a_cancelled_phase_with_no_detail_still_yields_a_stage(self):
        """The exact #1604 shape: empty detail, and the evidence is still useful."""
        from app.tasks.data_quality_watchdog import _run_context_query

        # Rows as production returns them post-fix: the cancelled phase (whose
        # `detail` is blank, exactly as #1604 showed) followed by the stage map.
        rows = [
            {"terminal": "cancelled", "published": "false", "phase": "futures",
             "phase_status": "cancelled", "detail": "", "duration_ms": "726557"},
            {"terminal": "cancelled", "published": "false",
             "phase": "stage:read:futures_unit", "duration_ms": "626242"},
            {"terminal": "cancelled", "published": "false",
             "phase": "stage:staged:cursor_invalidate", "duration_ms": "0"},
        ]

        class _Session:
            async def execute(self, *_a, **_k):
                class _R:
                    def mappings(self_inner):
                        class _M:
                            def all(self_m):
                                return rows
                        return _M()
                return _R()

        out = await _run_context_query(
            _Session(), {"name": "calibration_publish_age", "context_query": "SELECT 1"}
        )
        assert "futures" in out
        # The two lines that make the alert actionable rather than restating it:
        # where the time went, and that the cursor did not carry over.
        assert "read:futures_unit" in out
        assert "cursor_invalidate" in out


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
