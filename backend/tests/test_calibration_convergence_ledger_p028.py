"""CAL-P028 — the beat states where the build is on EVERY terminal, including a dead one.

Why this exists. ``_run_staged_futures`` records ``staged:units_done`` and
``staged:beats_to_publish`` at the END of its unit loop, which a beat that dies
in the loop never reaches. The futures phase was cancelled at its deadline on
essentially every beat from 2026-08-02 onward, so those stages were absent from
**181 consecutive ledgers** — and an absent stage reads as "fine" (gotcha #53).

"20 of 128 units banked, and going backwards" had to be reconstructed by hand out
of ``durable_state_snapshots`` by someone who thought to look. Twice, in two
different cycles. The number the operator needs most is the one the failing run
was least able to report.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_main_build import (
    STAGED_FUTURES_BUCKETS,
    _record_staged_convergence,
)


class _Ledger:
    def __init__(self):
        self.stages: dict[str, int] = {}

    def record_stage(self, name: str, value: int) -> None:
        self.stages[name] = value


class _Runner:
    def __init__(self):
        self.ledger = _Ledger()


@pytest.fixture
def runner():
    return _Runner()


def _patch_read(monkeypatch, result):
    async def _read(*_args, **_kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _read, raising=False)


@pytest.mark.asyncio
async def test_a_failed_beat_still_reports_where_the_build_is(monkeypatch, runner):
    """The whole point: this runs on the failure path."""
    _patch_read(
        monkeypatch,
        {"payload": {"committed_units": ["a"] * 20, "roster_drift_units": 16}},
    )
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_banked"] == 20
    assert runner.ledger.stages["staged:units_partition"] == STAGED_FUTURES_BUCKETS
    assert runner.ledger.stages["staged:units_drifted"] == 16


@pytest.mark.asyncio
async def test_zero_banked_is_recorded_rather_than_omitted(monkeypatch, runner):
    """A beat that banked NOTHING is the most important one to be able to see.

    Omitting the stage would make the worst beat indistinguishable from a
    healthy one that simply had nothing to say.
    """
    _patch_read(monkeypatch, {"payload": {"committed_units": []}})
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:units_banked"] == 0


@pytest.mark.asyncio
async def test_an_unreadable_cursor_never_costs_the_ledger(monkeypatch, runner):
    """Best-effort by construction — this must not become a new failure mode.

    It runs immediately before the durable ledger write, on a path that is
    already failing. A throw here would lose the whole ledger, which is the
    measurement it exists to protect.
    """
    _patch_read(monkeypatch, RuntimeError("durable read exploded"))
    await _record_staged_convergence(runner)  # must not raise
    assert runner.ledger.stages == {}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"payload": None},
        {"payload": {"committed_units": "not-a-list"}},
        {"payload": {}},
    ],
)
@pytest.mark.asyncio
async def test_a_shapeless_cursor_records_nothing_rather_than_guessing(
    monkeypatch, runner, payload
):
    _patch_read(monkeypatch, payload)
    await _record_staged_convergence(runner)
    assert "staged:units_banked" not in runner.ledger.stages


@pytest.mark.parametrize("bad", [-1, "16", True, None, 1.5])
@pytest.mark.asyncio
async def test_a_malformed_drift_value_is_dropped_not_coerced(monkeypatch, runner, bad):
    """A drift of 0 must mean measured-zero. Coercing junk to 0 invents a fact."""
    _patch_read(
        monkeypatch, {"payload": {"committed_units": ["a"], "roster_drift_units": bad}}
    )
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:units_banked"] == 1
    assert "staged:units_drifted" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_it_writes_nothing_to_production(monkeypatch, runner):
    """Read-only. The build is already failing; this must not mutate anything."""
    import app.services.durable_snapshots as ds

    async def _boom(*_a, **_k):
        raise AssertionError("convergence recording must never publish")

    monkeypatch.setattr(ds, "publish_snapshot_standalone", _boom, raising=False)
    _patch_read(monkeypatch, {"payload": {"committed_units": ["a", "b"]}})
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:units_banked"] == 2
