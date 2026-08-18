"""CAL-P069 — ``staged:units_drifted: 0`` must not cover units nobody could check.

Why this exists, measured rather than reasoned. Production, 2026-08-18 03:32Z::

    committed_units                119
    unit_digests                   113
    committed with no digest         6      <- outside roster_drift()'s reach
    ledger staged:units_drifted      0      <- published anyway, bare

``roster_drift`` is CORRECT to skip those six. Its docstring says exactly why:

    A unit with no stored digest is not counted, because "we cannot tell" must
    not be published as "it did not drift" — that is the empty-200 mistake of
    gotcha #53 one table over.

The rule is right, is written down, and is defeated by the shape of its own
output: a lone integer cannot say how much of the population it looked at, so
0-because-nothing-drifted and 0-because-nothing-was-checkable render
identically — and only one of them is an all-clear. This is the fourth
appearance of that class in four windows (CAL-P067's ``infeasible_phases: []``
off a cancelled elapsed, CAL-P068's ``graded_share = 1.0`` on an absent
denominator, and the mixed unit-cost mean before them), which is why the fix is
a coverage pair recorded beside the verdict rather than a smarter verdict.

Deliberately MECHANISM-INDEPENDENT. The six uncovered units equalled that
beat's ``staged:units_this_beat`` exactly, which points at a digest landing one
beat after the commit that banks it — but this rail is owed under a lag, a
prune, or a pre-CAL-P028 cursor tail alike. Refusing to render an unmeasured
population as a measured zero does not require knowing why it went unmeasured.

Both directions are asserted throughout (gotcha #43): the gap is reported AND a
fully-covered cursor still reports its coverage, because a rail that only ever
fires on the bad case teaches a reader to treat its silence as good news.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tasks.calibration_main_build import (
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


def _ok(payload) -> EnvelopeRead:
    return EnvelopeRead(
        status="ok",
        tier="durable",
        envelope=DurableEnvelope.build(
            identity=STAGED_FUTURES_IDENTITY,
            schema_version=STAGED_FUTURES_SCHEMA,
            payload=payload,
            generated_at=datetime.now(timezone.utc),
            source="test",
        ),
    )


def _patch_read(monkeypatch, result):
    async def _read(*_args, **_kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _read, raising=False)


def _cursor(committed: int, digested: int, **extra):
    """A cursor with ``committed`` banked units of which ``digested`` carry digests."""
    units = [f"u{i}" for i in range(committed)]
    return {
        "committed_units": units,
        "unit_digests": {name: f"d{name}" for name in units[:digested]},
        **extra,
    }


@pytest.mark.asyncio
async def test_the_production_specimen_is_reported_as_a_gap(monkeypatch, runner):
    """119 banked, 113 digested, drift 0 — the reading that motivated this file.

    The assertion that matters is the LAST one: ``units_drifted`` still says 0,
    unchanged, and the coverage pair now sits beside it saying that 0 was
    reached by looking at 113 of 119 units. The verdict is not corrected — it
    is qualified, because this function holds no digests and cannot honestly
    do anything else.
    """
    _patch_read(monkeypatch, _ok(_cursor(119, 113, roster_drift_units=0)))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_banked"] == 119
    assert runner.ledger.stages["staged:units_drift_checkable"] == 113
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 6
    assert runner.ledger.stages["staged:units_drifted"] == 0


@pytest.mark.asyncio
async def test_a_fully_covered_cursor_says_so_rather_than_going_quiet(
    monkeypatch, runner
):
    """The other direction (gotcha #43), and the reason the pair is a PAIR.

    If the rail only appeared when coverage was short, its absence would be the
    all-clear — and an absent stage reads as fine (gotcha #53), which is the
    defect this file exists to close, reintroduced one level up.
    """
    _patch_read(monkeypatch, _ok(_cursor(128, 128, roster_drift_units=0)))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_drift_checkable"] == 128
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 0
    assert "staged:drift_coverage_reason:no_digest_map" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_zero_coverage_is_stated_not_omitted(monkeypatch, runner):
    """Banked units, not one digest between them: the loudest case, and 0/N.

    Distinct from "no digest map" below — here the map exists and is empty, so
    the honest reading is that drift was checkable for none of the 40.
    """
    _patch_read(monkeypatch, _ok(_cursor(40, 0, roster_drift_units=0)))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_drift_checkable"] == 0
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 40


@pytest.mark.parametrize("absent", [None, [], "digests", 7])
@pytest.mark.asyncio
async def test_a_missing_digest_map_records_a_reason_not_a_coverage_number(
    monkeypatch, runner, absent
):
    """No map at all is a different fact from a partial map, and must read so.

    Falling through to ``checkable = 0`` would be defensible arithmetic and the
    wrong answer: it reports a measurement over a structure that was not there.
    A pre-CAL-P028 cursor is the real specimen.
    """
    payload = {"committed_units": ["a", "b"], "roster_drift_units": 0}
    if absent is not None:
        payload["unit_digests"] = absent
    _patch_read(monkeypatch, _ok(payload))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:drift_coverage_reason:no_digest_map"] == 1
    assert "staged:units_drift_checkable" not in runner.ledger.stages
    assert "staged:units_drift_uncheckable" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_these_are_gauges_not_counters(monkeypatch, runner):
    """CAL-P024c's rule, which this lane has now broken once and must not again.

    ``save_phase_ledger`` can run more than once in a build. Through
    ``record_stage`` a second terminal would publish 12 uncheckable units out of
    238 banked — numbers not merely wrong but not in the right unit.
    """
    _patch_read(monkeypatch, _ok(_cursor(119, 113, roster_drift_units=0)))
    await _record_staged_convergence(runner)
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_drift_checkable"] == 113
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 6


@pytest.mark.asyncio
async def test_coverage_never_invents_a_drift_verdict(monkeypatch, runner):
    """A cursor with a malformed drift value gets coverage and STILL no verdict.

    ``_record_staged_convergence`` already drops junk rather than coercing it to
    0 (CAL-P028). Coverage must not become a back door that reintroduces the
    zero it refused: reporting how much was checkable is not a licence to say
    what the check found.
    """
    _patch_read(monkeypatch, _ok(_cursor(10, 4, roster_drift_units="nonsense")))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_drift_checkable"] == 4
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 6
    assert "staged:units_drifted" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_coverage_costs_the_ledger_nothing_when_the_cursor_is_junk(
    monkeypatch, runner
):
    """It runs immediately before the durable write; a raise here loses the beat.

    The whole convergence block is best-effort by construction, and adding a
    reader to it must not turn a survivable cursor into a lost ledger.
    """
    _patch_read(monkeypatch, _ok({"committed_units": ["a"], "unit_digests": {1: "x"}}))
    await _record_staged_convergence(runner)  # must not raise

    assert runner.ledger.stages["staged:units_banked"] == 1
    assert runner.ledger.stages["staged:units_drift_uncheckable"] == 1


@pytest.mark.asyncio
async def test_it_writes_nothing_to_production(monkeypatch, runner):
    """Read-only, like every sibling in this block."""
    import app.services.durable_snapshots as ds

    async def _boom(*_a, **_k):
        raise AssertionError("drift coverage must never publish")

    monkeypatch.setattr(ds, "publish_snapshot_standalone", _boom, raising=False)
    _patch_read(monkeypatch, _ok(_cursor(5, 5)))
    await _record_staged_convergence(runner)

    assert runner.ledger.stages["staged:units_drift_checkable"] == 5
