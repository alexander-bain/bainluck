"""CAL-P080 (#2007) — the in-dyno twin's honest-failure contract.

The twin's ONLY way to lie is to read nothing and report agreement over zero
rows. Every test here is aimed at that, because ``agrees`` is the gate's pass
value and three separate broken states can reach it by accident:

* the fold raised (no rows, and we know why),
* the published payload could not be read (nothing to compare against),
* the fold "succeeded" and returned zero rows (nothing to compare WITH).

``build_artifact`` is pure, so all three are reachable here with no database, no
Redis and no clock — which is the point of having split it out of the I/O.
"""

import pytest

from app.tasks.calibration_published_twin_worker import (
    DEFAULT_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    build_artifact,
    clamp_timeout_ms,
)
from app.utils.task_verdict import ENFORCED_TASKS, verdict_for


def _payload(**over):
    """A published payload shaped like the real one, with a measured bank."""
    base = {
        "generated_at": "2026-08-20T17:17:43+00:00",
        "availability": "stale",
        "buckets": [],
        "staged": {
            "measured": True,
            "units_banked": 128,
            "units_drifted": 0,
            "units_drift_unknown": 0,
        },
    }
    base.update(over)
    return base


def _artifact(**over):
    kwargs = {
        "rows": [],
        "fold_duration_s": 1.0,
        "fold_error": None,
        "payload": _payload(),
        "payload_error": None,
        "timeout_ms": DEFAULT_TIMEOUT_MS,
    }
    kwargs.update(over)
    return build_artifact(**kwargs)


class TestTheGateCannotPassWithoutReading:
    def test_a_fold_error_is_unmeasurable_and_named(self):
        art = _artifact(fold_error="QueryCanceledError: statement timeout")
        assert art["verdict"] == "unmeasurable"
        assert "statement timeout" in art["unmeasurable_reason"]

    def test_an_unreadable_published_payload_is_unmeasurable_and_named(self):
        art = _artifact(payload={}, payload_error="published_absent: key is not set")
        assert art["verdict"] == "unmeasurable"
        assert "published_absent" in art["unmeasurable_reason"]

    def test_a_zero_row_fold_is_unmeasurable_even_with_no_error(self):
        # THE ONE THAT MATTERS. Nothing raised, the SELECT returned, and the
        # comparison has an empty left-hand side — so there is nothing to
        # disagree with and `reconcile` has no reason to object. A gate that
        # said `agrees` here would be reporting a broken read as a pass, which
        # is gotcha #53 aimed at the instrument itself.
        art = _artifact(rows=[], fold_error=None, payload_error=None)
        assert art["db_rows"] == 0
        assert art["verdict"] == "unmeasurable"
        assert "zero rows" in art["unmeasurable_reason"]

    @pytest.mark.parametrize(
        "over",
        [
            {"fold_error": "boom"},
            {"payload": {}, "payload_error": "published_absent: x"},
            {"rows": []},
        ],
    )
    def test_every_unmeasurable_route_terminates_failed(self, over):
        # Enrolment in ENFORCED_TASKS is a no-op without a terminal — the trap
        # `task_verdict` documents at length. This is the assertion that the
        # terminal is really there and really discriminates.
        art = _artifact(**over)
        assert art["terminal"] == "failed"
        assert art["measured"] is False

    def test_an_unmeasurable_run_cannot_read_green(self):
        art = _artifact(fold_error="boom")
        verdict = verdict_for("calibration_published_twin", art)
        assert verdict.authoritative is True
        assert verdict.verdict != "complete"

    def test_the_task_is_actually_enrolled(self):
        # Without this, every assertion above describes a contract that the
        # runner does not consult.
        assert "calibration_published_twin" in ENFORCED_TASKS


class TestTheBudgetThisWorkerExistsToSpend:
    def test_the_default_is_the_instruments_own_budget(self):
        # 240s — the number the admin db-query rail's hardcoded 10s could not
        # accommodate, which is the whole reason this worker exists.
        assert DEFAULT_TIMEOUT_MS == 240_000

    def test_the_default_far_exceeds_the_db_query_rails_cap(self):
        # The rail's row path hardcodes 10s; its documented operator ceiling is
        # 25s. Both are pinned here as the falsification's measured fact, so a
        # future change that "just routes it through db-query" reds.
        assert DEFAULT_TIMEOUT_MS > 25_000

    @pytest.mark.parametrize(
        "given,expected",
        [
            (None, DEFAULT_TIMEOUT_MS),
            ("nonsense", DEFAULT_TIMEOUT_MS),
            (0, MIN_TIMEOUT_MS),
            (-5, MIN_TIMEOUT_MS),
            (10**9, MAX_TIMEOUT_MS),
            (60_000, 60_000),
        ],
    )
    def test_operator_budgets_are_clamped_not_rejected(self, given, expected):
        assert clamp_timeout_ms(given) == expected

    def test_the_ceiling_stays_under_the_tasks_soft_limit(self):
        # soft_time_limit is 1500s. A statement allowed to outlive it would be
        # killed mid-flight with no artifact written — worse than a timeout,
        # because a timeout is recorded.
        assert MAX_TIMEOUT_MS < 1_500_000


class TestTheArtifactSaysWhatItRead:
    def test_it_records_the_budget_it_actually_spent(self):
        art = _artifact(timeout_ms=60_000)
        assert art["timeout_ms"] == 60_000

    def test_it_names_its_payload_source(self):
        # The comparison's subject must be the PUBLISHED artifact readers get,
        # not a recompute — so which one it read is on the record.
        art = _artifact()
        assert art["payload_source"] == "bainluck:calibration:main"
        assert art["runner"] == "in_dyno_worker"

    def test_the_bound_is_carried_even_when_unmeasurable(self):
        # CAL-P079 separated the BOUND from the VERDICT precisely because the
        # bound is reachable when the fold is not. That separation must survive
        # here: a run that could not fold still reports the tolerance the
        # payload's own disclosure earns.
        art = _artifact(fold_error="boom")
        assert art["verdict"] == "unmeasurable"
        assert art["tolerance_pp"] is not None

    def test_an_undisclosed_bank_earns_no_bound(self):
        art = _artifact(payload=_payload(staged={"measured": False}))
        assert art["tolerance_pp"] is None
        assert art["verdict"] == "unmeasurable"
