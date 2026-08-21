"""CAL-P084 (#2076) — Gate 0's twin could not produce a verdict, for TWO reasons.

CAL-P083 filed #2076 against the fold's budget: ``fold_duration_s 241.18``
against 240 s, ``db_rows 0``, ``QueryCanceledError``. That was real. It was also
**not the only blocker**, and the second one could not be seen from behind it,
because a run that never gets past the fold never reaches the comparison.

**Blocker 2, measured 2026-08-21 16:55:05Z on generation 1787331305993:** the
twin took its agreement bound from ``payload.get("staged")`` on the Redis key
``bainluck:calibration:main`` — and **the producer has never written a ``staged``
block there.** ``routes/calibration.py:1000`` composes it at REQUEST time onto a
copy (``out = dict(payload)``). So the field was always ``None``,
``tolerance_pp(None)`` is ``None`` by design, and :func:`reconcile` returns
``unmeasurable``.

The artifact from that run is the proof and it is unambiguous, because the
payload read SUCCEEDED: ``payload_error`` null, ``published_generated_at``
``2026-08-21T16:35:07.919Z``, ``staged`` JSON ``null`` — while
``GET /api/calibration`` over the same producer output served a measured block
earning a 100.0 pp bound. **Gate 0's twin would have returned ``unmeasurable``
over a fold that finished perfectly.**

``TestBlockerTwo`` is that finding, stated as a test in both directions: with the
disclosure supplied the verdict is real, and with it absent the verdict is
unmeasurable — so the fix cannot be reverted without turning one of them red.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import calibration_published_twin_worker as worker
from app.tasks.calibration_published_twin_worker import (
    DEFAULT_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    build_artifact,
    clamp_timeout_ms,
    wider_disclosure,
)


def _staged(*, banked=128, drifted=0, unknown=0):
    """A disclosure of the shape ``build_disclosure`` returns."""
    return {
        "measured": True,
        "staged_at": "2026-08-21T12:28:50+00:00",
        "units_banked": banked,
        "units_drifted": drifted,
        "units_drift_unknown": unknown,
    }


class _Row:
    """A driver-shaped row, so the fold reducer is exercised as it is in prod."""

    def __init__(self, source, category, bucket_idx, n, winners, sum_prob):
        self._mapping = {
            "source": source, "category": category, "bucket_idx": bucket_idx,
            "n": n, "winners": winners, "sum_prob": sum_prob,
        }


def _rows():
    # bucket 7 -> db rate 0.70; the payload below agrees exactly.
    return [_Row("kalshi", "quantity", 7, 100, 70, 72.5)]


def _payload(*, rate=0.70, staged=None):
    payload = {
        "generated_at": "2026-08-21T16:35:07.919320+00:00",
        "buckets": [
            {"source": "kalshi", "category": "quantity", "bucket_idx": 7,
             "actual_rate": rate}
        ],
    }
    if staged is not None:
        payload["staged"] = staged
    return payload


# ---------------------------------------------------------------------------
# Blocker 2 — the one no fold budget would have fixed
# ---------------------------------------------------------------------------

class TestBlockerTwo:
    def test_a_verdict_is_reachable_when_the_disclosure_is_supplied(self):
        art = build_artifact(
            rows=_rows(), fold_duration_s=12.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=240_000,
            staged=_staged(drifted=0),
        )
        assert art["verdict"] == "agrees"
        assert art["measured"] is True
        assert art["terminal"] == "complete"
        assert art["tolerance_pp"] == pytest.approx(0.5)

    def test_the_published_payload_carries_no_staged_block_and_that_is_recorded(self):
        """The production fact, kept visible on every artifact.

        Not merely "we no longer read it": the artifact states that the payload
        did not carry one, so the day the producer starts writing a ``staged``
        block the change is visible rather than silently preferred over the
        composed disclosure.
        """
        art = build_artifact(
            rows=_rows(), fold_duration_s=12.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=240_000,
            staged=_staged(),
        )
        assert art["payload_carries_staged"] is False
        assert art["payload_staged"] is None
        assert art["staged"] is not None

    def test_without_a_disclosure_the_verdict_is_unmeasurable_over_a_PERFECT_fold(self):
        """The pre-fix behaviour, pinned as the thing that must stay broken.

        This is exactly what production did: a clean fold, a clean payload read,
        and ``unmeasurable`` anyway. If a future edit reintroduces
        ``payload.get("staged")`` as the bound's source, this test keeps passing
        and the one above turns red — which is the pair that makes the fix
        irreversible by accident.
        """
        art = build_artifact(
            rows=_rows(), fold_duration_s=12.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=240_000,
            staged=None,
        )
        assert art["verdict"] == "unmeasurable"
        assert art["terminal"] == "failed"
        assert art["db_rows"] == 100  # the fold WORKED; the bound was the problem

    def test_an_unreadable_disclosure_is_named_separately_from_a_silent_payload(self):
        art = build_artifact(
            rows=_rows(), fold_duration_s=12.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=240_000,
            staged=None, staged_error="phase_ledger_unreadable: missing",
        )
        assert art["verdict"] == "unmeasurable"
        assert art["unmeasurable_reason"] == "phase_ledger_unreadable: missing"

    def test_a_fold_error_still_dominates_a_good_disclosure(self):
        art = build_artifact(
            rows=[], fold_duration_s=901.96,
            fold_error="DBAPIError: QueryCanceledError: canceling statement",
            payload=_payload(), payload_error=None, timeout_ms=900_000,
            staged=_staged(),
        )
        assert art["verdict"] == "unmeasurable"
        assert "QueryCanceledError" in art["unmeasurable_reason"]
        assert art["terminal"] == "failed"

    def test_a_real_disagreement_still_reads_as_a_working_gate(self):
        art = build_artifact(
            rows=_rows(), fold_duration_s=12.0, fold_error=None,
            payload=_payload(rate=0.20), payload_error=None, timeout_ms=240_000,
            staged=_staged(drifted=0),
        )
        assert art["verdict"] == "disagrees"
        # `disagrees` is COMPLETE on purpose — the gate ran and found something.
        assert art["terminal"] == "complete"
        assert art["outside"]


class TestTheTwinReadsTheDisclosureTheRouteReads:
    def test_it_uses_the_same_two_durable_identities_as_the_route(self):
        """A source-level pin, because the failure was a DIFFERENT SOURCE.

        The bug was not a wrong value — it was reading the bound from the wrong
        place. So the invariant worth guarding is *which artifact the bound comes
        from*, and the only thing that expresses it is the pair of identities.
        """
        src = inspect.getsource(worker.read_served_disclosure)
        assert "STAGED_FUTURES_IDENTITY" in src
        assert "LEDGER_IDENTITY" in src
        assert "build_disclosure" in src

    def test_the_bound_is_no_longer_taken_from_the_redis_payload(self):
        src = inspect.getsource(worker.build_artifact)
        assert 'staged=staged' in src
        assert 'staged=payload.get("staged")' not in src


# ---------------------------------------------------------------------------
# The sawtooth's trough — a 22-minute fold can outlive its own subject
# ---------------------------------------------------------------------------

class TestRotationDuringTheFold:
    def test_the_wider_bound_wins_when_the_subject_rotated(self):
        """Wider, never tighter. CAL-P083's trough is one beat in sixteen.

        A fold that starts at the promotion beat (0.5 pp) and ends after the
        next publish (85.94 pp) must not grade today's database against the
        trough's bound — borrowing a tight bound from a generation nobody is
        served is the flattering direction and is the shape of the very defect
        this gate exists to catch.
        """
        trough = _staged(drifted=0)              # 0.5 pp
        reclimbed = _staged(drifted=110)         # 85.9375 pp
        chosen, note = wider_disclosure(trough, reclimbed)
        assert chosen is reclimbed
        assert "wider" in note

        chosen, note = wider_disclosure(reclimbed, trough)
        assert chosen is reclimbed
        assert "wider" in note

    def test_an_unmeasurable_side_is_the_widest_of_all(self):
        chosen, note = wider_disclosure(_staged(), {"measured": False, "reason": "x"})
        assert chosen == {"measured": False, "reason": "x"}
        assert "unmeasurable" in note

    def test_rotation_is_named_on_the_artifact_not_inferred_from_generations(self):
        art = build_artifact(
            rows=_rows(), fold_duration_s=1200.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=1_350_000,
            staged=_staged(drifted=110),
            rotation_note="rotated: kept the wider post-fold bound 85.9375 > 0.5",
            ledger_generation_before=1_787_315_424_367,
            ledger_generation_after=1_787_319_024_367,
        )
        assert art["subject_rotated_during_fold"] is True
        assert art["ledger_generation_before"] != art["ledger_generation_after"]
        assert art["tolerance_pp"] == pytest.approx(85.9375)

    def test_a_run_that_did_not_rotate_says_so_explicitly(self):
        art = build_artifact(
            rows=_rows(), fold_duration_s=120.0, fold_error=None,
            payload=_payload(), payload_error=None, timeout_ms=240_000,
            staged=_staged(),
            ledger_generation_before=7, ledger_generation_after=7,
        )
        assert art["subject_rotated_during_fold"] is False
        assert art["rotation_note"] is None


# ---------------------------------------------------------------------------
# Blocker 1 — the budget, and the limit that has to honour it
# ---------------------------------------------------------------------------

class TestBudgetCeiling:
    def test_the_ceiling_was_raised_past_the_measured_900s_cancellation(self):
        """900 s was MEASURED insufficient (901.96 s, db_rows 0). 240 s too."""
        assert MAX_TIMEOUT_MS > 900_000
        assert DEFAULT_TIMEOUT_MS == 240_000  # unchanged on purpose; see the module

    def test_the_ceiling_fits_inside_the_task_soft_limit_with_real_headroom(self):
        """A statement outliving the soft limit is killed with NO artifact.

        That is worse than a timeout, because a timeout leaves a diagnosis and a
        SIGKILL leaves nothing — which is how #2076 would become unfileable. The
        headroom has to cover two disclosure reads, the payload read and the
        durable write, so it is asserted as a margin rather than as ``<``.
        """
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.calibration_published_twin"]
        soft = task.soft_time_limit
        assert soft is not None
        headroom_s = soft - (MAX_TIMEOUT_MS / 1000.0)
        assert headroom_s >= 300, f"only {headroom_s}s of headroom above the fold"
        assert task.time_limit > soft

    def test_clamp_honours_the_new_ceiling_rather_than_rejecting(self):
        assert clamp_timeout_ms(10_000_000) == MAX_TIMEOUT_MS
        assert clamp_timeout_ms(0) == 1_000
        assert clamp_timeout_ms("nonsense") == DEFAULT_TIMEOUT_MS
        assert clamp_timeout_ms(1_350_000) == 1_350_000
