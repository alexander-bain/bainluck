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

INT-034 — WHY THIS FILE WAS REWRITTEN AGAINST REAL TYPES
=========================================================
The first version of this suite had six passing tests over a function that
recorded **nothing, on every beat, in production**. It passed because both of
its test doubles modelled a contract production does not have:

* ``_patch_read`` returned a **dict**, so the production line
  ``(read or {}).get("payload")`` looked correct. The real
  ``read_snapshot_standalone`` returns a frozen ``EnvelopeRead`` dataclass with
  no ``.get``, so that line raised ``AttributeError`` on every real beat and the
  best-effort ``except`` swallowed it.
* the fake ledger's ``record_stage`` **replaced** the value. The real one
  **accumulates** (CAL-P024c), which is why these three readings are gauges.

Two fakes, each independently wrong in the direction that hid the bug. So the
doubles are gone: this suite drives the REAL ``PhaseLedger`` and builds REAL
``EnvelopeRead``/``DurableEnvelope`` values, and
``test_the_reader_consumes_the_type_the_producer_returns`` pins the seam that
actually broke. A test double is a claim about a contract; when it is the only
thing asserting that contract, it cannot also be the thing that verifies it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tasks.calibration_main_build import (
    STAGED_FUTURES_BUCKETS,
    STAGED_FUTURES_IDENTITY,
    _record_staged_convergence,
)
from app.utils.calibration_phase_ledger import PhaseLedger, derive_plan
from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA
from app.utils.durable_state import DurableEnvelope, EnvelopeRead


class _Runner:
    """Carries a REAL ledger — accumulating ``record_stage`` semantics included."""

    def __init__(self):
        self.ledger = PhaseLedger(
            plan=derive_plan({}),
            population_version="test",
            owner="test",
            generation=1,
            input_fingerprint="fp",
        )


@pytest.fixture
def runner():
    return _Runner()


def _envelope(payload) -> DurableEnvelope:
    return DurableEnvelope.build(
        identity=STAGED_FUTURES_IDENTITY,
        schema_version=STAGED_FUTURES_SCHEMA,
        payload=payload,
        generated_at=datetime.now(timezone.utc),
        source="test",
    )


def _ok(payload) -> EnvelopeRead:
    return EnvelopeRead(status="ok", tier="durable", envelope=_envelope(payload))


def _patch_read(monkeypatch, result):
    """Patch where the function LOOKS IT UP, and hand back a real EnvelopeRead."""

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
        monkeypatch, _ok({"committed_units": ["a"] * 20, "roster_drift_units": 16})
    )
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_banked"] == 20
    assert runner.ledger.stages["staged:units_partition"] == STAGED_FUTURES_BUCKETS
    assert runner.ledger.stages["staged:units_drifted"] == 16


@pytest.mark.asyncio
async def test_the_reader_consumes_the_type_the_producer_returns(monkeypatch, runner):
    """THE REGRESSION TEST. Pins the seam CAL-P028 got wrong.

    The defect was not a wrong number, it was a wrong TYPE — and the old suite
    could not see it because its double returned the wrong type too. So this
    asserts against the real producer's real return value: whatever
    ``read_snapshot_standalone`` is annotated to return, this function must be
    able to consume without raising, and must actually record from.
    """
    import typing

    from app.services.durable_snapshots import read_snapshot_standalone

    # The producer's contract, read off the producer itself rather than assumed.
    # ``get_type_hints`` rather than ``signature``: that module uses
    # ``from __future__ import annotations``, so the raw annotation is the
    # STRING "EnvelopeRead" and an identity check against it silently passes
    # for any type that happens to share the name.
    assert (
        typing.get_type_hints(read_snapshot_standalone)["return"] is EnvelopeRead
    ), "if this changes, the consumer below must change with it"

    # An EnvelopeRead is a frozen dataclass: no .get, and always truthy, so
    # `(read or {}).get(...)` is an AttributeError rather than a fallback.
    assert not hasattr(EnvelopeRead(status="ok", tier="durable"), "get")
    assert bool(EnvelopeRead(status="missing", tier="durable")) is True

    _patch_read(monkeypatch, _ok({"committed_units": ["a", "b", "c"]}))
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:units_banked"] == 3


@pytest.mark.asyncio
async def test_these_are_gauges_not_counters(monkeypatch, runner):
    """CAL-P024c's rule. ``save_phase_ledger`` can run more than once per build.

    Recorded through ``record_stage`` a second terminal would publish 40 units
    banked out of 256 — numbers that are not merely wrong but not even in the
    right unit. A level must survive being observed twice.
    """
    _patch_read(monkeypatch, _ok({"committed_units": ["a"] * 20}))
    await _record_staged_convergence(runner)
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_banked"] == 20
    assert runner.ledger.stages["staged:units_partition"] == STAGED_FUTURES_BUCKETS


@pytest.mark.asyncio
async def test_zero_banked_is_recorded_rather_than_omitted(monkeypatch, runner):
    """A beat that banked NOTHING is the most important one to be able to see.

    Omitting the stage would make the worst beat indistinguishable from a
    healthy one that simply had nothing to say.
    """
    _patch_read(monkeypatch, _ok({"committed_units": []}))
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
    assert "staged:units_banked" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_a_broken_read_says_so_instead_of_going_quiet(monkeypatch, runner):
    """Gotcha #53, applied to this function's own failure path.

    Silence is what made the original defect survive eight days: no
    ``units_banked`` looked exactly like a healthy beat with nothing to report.
    A reader that cannot read must leave a mark saying which of the two it was.
    """
    _patch_read(monkeypatch, RuntimeError("durable read exploded"))
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:convergence_reason:read_raised"] == 1


@pytest.mark.parametrize("status", ["missing", "stale", "unavailable"])
@pytest.mark.asyncio
async def test_a_refused_envelope_records_which_refusal(monkeypatch, runner, status):
    """"Never published" and "too old to trust" are different operator actions."""
    _patch_read(monkeypatch, EnvelopeRead(status=status, tier="durable"))
    await _record_staged_convergence(runner)

    assert "staged:units_banked" not in runner.ledger.stages
    assert runner.ledger.stages[f"staged:convergence_reason:{status}"] == 1


@pytest.mark.parametrize(
    "payload, reason",
    [
        (None, "payload_shape"),
        ("not-a-dict", "payload_shape"),
        ({"committed_units": "not-a-list"}, "no_committed_units"),
        ({}, "no_committed_units"),
    ],
)
@pytest.mark.asyncio
async def test_a_shapeless_cursor_records_nothing_rather_than_guessing(
    monkeypatch, runner, payload, reason
):
    _patch_read(monkeypatch, _ok(payload))
    await _record_staged_convergence(runner)

    assert "staged:units_banked" not in runner.ledger.stages
    assert runner.ledger.stages[f"staged:convergence_reason:{reason}"] == 1


@pytest.mark.parametrize("bad", [-1, "16", True, None, 1.5])
@pytest.mark.asyncio
async def test_a_malformed_drift_value_is_dropped_not_coerced(monkeypatch, runner, bad):
    """A drift of 0 must mean measured-zero. Coercing junk to 0 invents a fact."""
    _patch_read(
        monkeypatch, _ok({"committed_units": ["a"], "roster_drift_units": bad})
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
    _patch_read(monkeypatch, _ok({"committed_units": ["a", "b"]}))
    await _record_staged_convergence(runner)
    assert runner.ledger.stages["staged:units_banked"] == 2
