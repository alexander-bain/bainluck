"""#3782 — the beat gauge sampler called every successful bank a failure.

`_WRITE_OK` read `("stored", "unchanged")`. `"stored"` is a status
`publish_snapshot_standalone` has never returned — its contract is
`ok` / `superseded` / `error`, plus `occupied` and `cas-miss`. So the only
member of the accept set that could ever match was `"unchanged"`, which the
sampler sets on its OWN no-op branch. The classification was exactly inverted:

    appended a new beat   -> "ok"          -> failed  (history_write_failed: ok)
    benign newer copy     -> "superseded"  -> failed
    nothing new to record -> "unchanged"   -> complete/partial

Measured on production 2026-09-07T03:44Z, from a run that did everything right:
`{"appended": true, "history_write": "ok", "history_generation": 1788749276158,
"terminal": "failed", "reason": "history_write_failed: ok"}`, with
`failures_24h: 6`.

WHY THE EXISTING TESTS AGREED WITH IT
-------------------------------------
Every test fed `write_status` one of the accept set's own literals — the #3733
suite even faked the writer as returning `{"status": "stored"}`. A test that
takes its input vocabulary from the code under test cannot see a vocabulary
error. So the tests here take their vocabulary from the WRITER, and the central
one is parameterised over statuses discovered from `durable_snapshots` rather
than written down again below.

WHAT IT COST
------------
It silently undid CAL-P1042 (#3733), live at v4245. `self_ok` is computed from
`_WRITE_OK`, and `clears_failure_streak` needs `partial` AND `self_ok`. An
appending run was `failed`/`self_ok: False`, so it took `record_task_failure`
and the streak it had just cleared climbed back to `critical`. #3733 only
appeared to hold because the producer had stopped and the sampler was idling
down the no-op path; the first recovered beat would have re-reddened it.
"""

import pytest

import app.services.durable_snapshots as durable_snapshots
from app.services.durable_snapshots import (
    PUBLISH_STATUS_DURABLE,
    STATUS_CAS_MISS,
    STATUS_ERROR,
    STATUS_OCCUPIED,
    STATUS_OK,
    STATUS_SUPERSEDED,
)
from app.tasks.calibration_beat_gauge_sampler import (
    WRITE_NOOP,
    decide_terminal,
    sampler_did_its_job,
)

SAMPLER = "calibration_beat_gauge_sampler"

#: A ledger row good enough that the write status is the only thing under test.
_OBS = {"generation": 1788749276158}

#: How the sampler must treat each status the writer can emit. The point of the
#: table is that its keys come from `durable_snapshots`, asserted below.
_EXPECTED_NON_FAILING = {
    STATUS_OK: True,
    STATUS_SUPERSEDED: True,
    STATUS_ERROR: False,
    STATUS_OCCUPIED: False,
    STATUS_CAS_MISS: False,
}


def _writer_statuses() -> set[str]:
    """Every status constant the writer module publishes. Discovered, not typed.

    This is the anti-drift half: add a `STATUS_*` to `durable_snapshots` and the
    completeness test below fails until it is classified here, where somebody
    has to decide whether it means the beat is safely on disk.
    """
    return {
        v
        for k, v in vars(durable_snapshots).items()
        if k.startswith("STATUS_") and isinstance(v, str)
    }


class TestTheAcceptSetIsTheWriterContract:
    def test_the_phantom_status_is_gone(self):
        """`"stored"` matched nothing, so it could only ever mislead a reader."""
        from app.tasks.calibration_beat_gauge_sampler import _WRITE_OK

        assert "stored" not in _WRITE_OK

    def test_stored_is_not_something_the_writer_can_return(self):
        """The premise of this whole issue, asserted rather than asserted-about."""
        assert "stored" not in _writer_statuses()

    def test_the_accept_set_is_derived_and_not_restated(self):
        from app.tasks.calibration_beat_gauge_sampler import _WRITE_OK

        assert PUBLISH_STATUS_DURABLE <= set(_WRITE_OK)
        # ...plus exactly one sampler-local sentinel, and nothing else.
        assert set(_WRITE_OK) - set(PUBLISH_STATUS_DURABLE) == {WRITE_NOOP}

    def test_every_writer_status_is_classified_here(self):
        """Anti-drift. A new `STATUS_*` must be judged, not silently defaulted."""
        unclassified = _writer_statuses() - set(_EXPECTED_NON_FAILING)
        assert not unclassified, (
            f"durable_snapshots grew {sorted(unclassified)}; decide whether each "
            "means the beat is safely banked and add it to _EXPECTED_NON_FAILING "
            "(and to PUBLISH_STATUS_DURABLE if it does)"
        )


@pytest.mark.parametrize("status,non_failing", sorted(_EXPECTED_NON_FAILING.items()))
class TestEveryWriterStatusIsJudgedCorrectly:
    """The central guard: real statuses in, correct terminal out."""

    def test_terminal(self, status, non_failing):
        terminal, reason = decide_terminal(
            read_status="ok", observation=_OBS, write_status=status, ledger_age_s=60
        )
        if non_failing:
            assert terminal != "failed", (
                f"a durable write reported {status!r} was recorded {terminal!r} "
                f"({reason}) — the sampler is calling a successful bank a failure"
            )
        else:
            assert terminal == "failed"
            assert reason == f"history_write_failed: {status}"

    def test_self_ok(self, status, non_failing):
        assert sampler_did_its_job(observation=_OBS, write_status=status) is non_failing


class TestTheNoOpPathStillPasses:
    """`unchanged` is the job done — the beat was banked by an earlier sample."""

    def test_unchanged_is_not_a_failure(self):
        terminal, _ = decide_terminal(
            read_status="ok", observation=_OBS, write_status=WRITE_NOOP, ledger_age_s=60
        )
        assert terminal == "complete"
        assert sampler_did_its_job(observation=_OBS, write_status=WRITE_NOOP) is True

    def test_a_missing_status_is_still_a_failure(self):
        """`None` means the write never reported. Never a success."""
        terminal, _ = decide_terminal(
            read_status="ok", observation=_OBS, write_status=None, ledger_age_s=60
        )
        assert terminal == "failed"
        assert sampler_did_its_job(observation=_OBS, write_status=None) is False


class TestTheRealRunThatBanksABeat:
    """End to end, because the unit tests above could not have caught the
    ORIGINAL defect either if the sampler stopped calling `decide_terminal`."""

    @staticmethod
    def _run(monkeypatch, *, publish_status, gauges_absent=True):
        import asyncio
        import datetime

        import app.tasks.calibration_beat_gauge_sampler as mod

        stages = {
            g: 0
            for g in mod.REQUIRED_DISCLOSURE_GAUGES
            if not (gauges_absent and g == "staged:served_at")
        }
        ledger = {
            "generation": 1788749276158,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "complete": True,
            "payload": {"terminal": "cancelled", "stages": stages},
            "status": "ok",
        }

        async def _rl():
            return ledger, "ok"

        async def _rh():
            return {}, "ok"

        async def _pub(_envelope):
            return {"status": publish_status}

        monkeypatch.setattr(mod, "_read_ledger", _rl)
        monkeypatch.setattr(mod, "_read_history", _rh)
        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _pub
        )
        return asyncio.run(mod.run_beat_gauge_sample())

    def test_an_appending_run_is_not_recorded_as_a_failure(self, monkeypatch):
        """The exact production shape: appended, history_write ok, was `failed`."""
        from app.utils.task_verdict import SELF_OK_FIELD

        art = self._run(monkeypatch, publish_status=STATUS_OK)

        assert art["history_write"] == STATUS_OK
        assert art["appended"] is True
        assert art["terminal"] != "failed", (
            f"regression of #3782: {art['reason']}"
        )
        assert art[SELF_OK_FIELD] is True

    def test_a_superseded_write_is_also_not_a_failure(self, monkeypatch):
        from app.utils.task_verdict import SELF_OK_FIELD

        art = self._run(monkeypatch, publish_status=STATUS_SUPERSEDED)
        assert art["terminal"] != "failed"
        assert art[SELF_OK_FIELD] is True

    def test_a_genuinely_failed_write_still_fails(self, monkeypatch):
        """The other direction, so this is a fix and not a blanket pass."""
        from app.utils.task_verdict import SELF_OK_FIELD

        art = self._run(monkeypatch, publish_status=STATUS_ERROR)
        assert art["terminal"] == "failed"
        assert art["reason"] == f"history_write_failed: {STATUS_ERROR}"
        assert art[SELF_OK_FIELD] is False


class TestItNoLongerUndoes3733:
    """The composition that matters, and the one nobody had written.

    #3733 clears a false `consecutive_failures` streak on a sampler-owned
    partial. #3782 meant the runs that do real work never reached that path. So
    assert the two together: a run that BANKS A BEAT and finds the producer at
    fault must still take a 78-deep streak out of `critical`.
    """

    def test_an_appending_run_with_a_producer_fault_clears_the_streak(
        self, monkeypatch
    ):
        from app.tasks import redis_state
        from app.utils.task_verdict import verdict_for
        from tests.test_sampler_partial_clears_observer_failure_streak_3733 import (
            _KEY,
            _SEEDED_78,
            _fake,
        )

        art = TestTheRealRunThatBanksABeat._run(
            monkeypatch, publish_status=STATUS_OK, gauges_absent=True
        )
        verdict = verdict_for(SAMPLER, art)

        # The producer IS at fault, so this is a partial — but a partial the
        # sampler earned by working, not one it was handed by a phantom status.
        assert verdict.verdict == "partial"
        assert art["appended"] is True

        _fake(monkeypatch, hashes={_KEY: dict(_SEEDED_78)})
        redis_state.record_task_incomplete(
            SAMPLER,
            470.0,
            verdict=verdict.verdict,
            verdict_reason=verdict.reason,
            result_summary=art,
        )
        out = redis_state.get_task_metrics(SAMPLER)

        assert out["consecutive_failures"] == "0"
        assert out["health"] == "degraded", (
            "the sampler banked a beat and the producer is at fault, so health is "
            "degraded — `critical` here means #3782 has undone #3733 again"
        )

    def test_a_clean_appending_run_is_green(self, monkeypatch):
        """No producer fault and a real write: nothing left to complain about."""
        from app.utils.task_verdict import verdict_for

        art = TestTheRealRunThatBanksABeat._run(
            monkeypatch, publish_status=STATUS_OK, gauges_absent=False
        )
        assert art["terminal"] == "complete"
        assert verdict_for(SAMPLER, art).is_green is True
