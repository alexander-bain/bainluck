"""#6599: a cursor we could not READ is not a cursor we may DESTROY.

PILLAR: TRUTH. SHIP: the accuracy page finishes a complete rebuild without
repeatedly discarding still-valid work.

## What this is about

``load_staged_cursor`` classifies the durable staged-futures cursor into the
four actions the build understands. Seven read statuses reach it, and
``app.utils.durable_state`` already models the one that matters separately:
``unavailable`` is its named UNKNOWN — *the database did not answer* — and it is
returned both by :func:`~app.utils.durable_state.failed_read` and by the
``except`` around the read itself.

Before this file, ``load_staged_cursor`` collapsed that UNKNOWN into
``INVALIDATE`` with a blank cursor, and the docstring beside it said so out
loud: *"an unreadable cursor is a fresh one"*. It is not. A blank cursor is not
merely a lost resume — the beat then runs, banks or cancels a unit, and
``save_staged_cursor`` writes that blank-derived cursor **over** the durable row
it could not read. One statement timeout on a ~12 KB read therefore converts
into the permanent loss of every unit banked so far. #6599's ring shows a bank
reaching 122 of 128 and then starting again from 0 on an **unchanged**
``input_fingerprint`` (comment 5708286334, the 09-16 ~12:00Z reset) — this is
one mechanism that produces exactly that row, and it is the only one of the
seven statuses with no evidence of incompatibility behind it.

That is gotcha #53 one table over, and it is the same shape as the durable
tier's own rule: UNKNOWN may never be reported as the reassuring reading, and it
may never be *acted on* as the destructive one either.

## What is NOT changed, deliberately

Every genuine invalidator still wipes the bank whole, and that is the point of
the control class below. ``population_version``, ``input_fingerprint``
(the emitted statement's own digest — the calculation version), a wrong schema,
a wrong task, a torn payload, an incomplete envelope, a stale envelope: each of
those is a row we HAVE and can prove we may not resume. Only the status that
means "we do not know what is on disk" changes, and it changes to the action the
build already has for that case — ``REFUSE``, the lease-held stand-down, whose
contract is precisely *doing nothing is correct*.

So this narrows no invalidation. It stops one destructive write that no evidence
supports.

## The second half, and why it is in the same file

``_run_staged_futures`` returned on ``REFUSE`` **before** recording the action or
the reason, so a stood-down beat was invisible in the ledger — indistinguishable
from a beat that never ran. That was tolerable while REFUSE meant only "another
worker holds the lease"; it is not tolerable now that it also means "the durable
read failed", which is the thing an operator has to be able to count. The two
``record_stage`` calls move above the return. Nothing else in that function
moves.
"""

from __future__ import annotations

import contextlib
import types
from datetime import datetime, timezone

import pytest

from app.services import durable_snapshots as ds
from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    FRESH,
    INVALIDATE,
    PHASE_FUTURES,
    REFUSE,
    RESUME,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

BUCKETS = 8
VMS_PER_SLOT = 4
#: Comfortably inside any bound the build arms, so beats BANK and the durable
#: payload under test is a real one rather than a hand-built fixture.
HEALTHY_VM_MS = 4_000
#: Deliberately small: a beat must bank SOME units and leave the rest, because a
#: bank that completes inside one beat promotes to the served slot and there is
#: then no partial bank to lose — which is the state production is always in.
WINDOW_MS = 60_000


# =============================================================================
# The rig — the real load, the real save, the real codec, a fake database
# =============================================================================


class _Durable:
    """The durable row, plus a switch for what the next READ does to it.

    Patched in at ``app.services.durable_snapshots`` rather than at
    ``calibration_main_build``, so the REAL ``load_staged_cursor`` and the REAL
    ``save_staged_cursor`` are what the tests drive. Those two functions are the
    subject; a stand-in for them would test the stand-in.
    """

    def __init__(self):
        self.payload: dict | None = None
        #: ``None`` = answer honestly. Otherwise a status string to fail with,
        #: or the string ``"raise"`` for the exception path.
        self.next_read: str | None = None
        self.writes = 0

    async def read(self, identity, *, expected_version=None, max_age_s=None):
        failure, self.next_read = self.next_read, None
        if failure == "raise":
            raise RuntimeError("canceling statement due to statement timeout")
        if failure is not None:
            return EnvelopeRead(
                status=failure,
                tier=ds.TIER_DURABLE,
                error_class="OperationalError",
                error="the database did not answer",
            )
        if self.payload is None:
            return EnvelopeRead(status="missing", tier=ds.TIER_DURABLE)
        return EnvelopeRead(
            status="ok",
            tier=ds.TIER_DURABLE,
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=sf.STAGED_FUTURES_SCHEMA,
                payload=self.payload,
                generated_at=datetime.now(timezone.utc),
                source=cmb.MAIN_BUILD_TASK,
            ),
        )

    async def publish(self, envelope):
        self.writes += 1
        self.payload = envelope.payload
        return {"status": "ok"}

    @property
    def banked(self) -> int:
        return len((self.payload or {}).get("committed_units") or [])


class _Runner:
    """One beat. The clock is advanced by the database (gotcha #44)."""

    def __init__(self, *, generation: int):
        plan = PhasePlan(
            budgets=(
                PhaseBudget(
                    name=PHASE_FUTURES,
                    required=True,
                    budget_ms=None,
                    statement_timeout_ms=None,
                    measured_input=True,
                    unit_ms=HEALTHY_VM_MS * VMS_PER_SLOT,
                    units_total=BUCKETS,
                    units_done=0,
                ),
            ),
            soft_limit_ms=WINDOW_MS + 120_000,
            cleanup_margin_ms=120_000,
        )
        self.ledger = PhaseLedger(
            plan=plan,
            population_version="q268",
            owner="test:1",
            generation=generation,
            input_fingerprint="fp",
            phases=(PHASE_FUTURES,),
        )
        self._elapsed = 0
        self.population_version = "q268"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = generation
        self.armed: list[int] = []
        self.deferred = False

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += int(ms)

    def measured_unit_ms(self, phase: str):
        return self.ledger.measured_unit_ms(phase)

    def defer_rebuild(self) -> None:
        self.deferred = True

    @contextlib.contextmanager
    def stage(self, _name: str):
        yield

    async def commit(self, _db) -> None:
        return None

    async def apply_statement_timeout(self, _db, phase) -> int:
        return self.ledger.statement_timeout_for(phase, elapsed_ms=self._elapsed)

    async def apply_unit_statement_timeout(
        self, _db, phase, *, unit_ms=None, deferred_rebuild=False
    ) -> int:
        armed = self.ledger.statement_timeout_for_unit(
            phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
        )
        self.armed.append(armed)
        return armed


class _Db:
    """Every unit completes. This file is about the CURSOR, not about slowness."""

    def __init__(self, runner: _Runner, roster):
        self.runner = runner
        self.roster = roster
        self.by_market = {int(r.market_id): str(r.vm_id) for r in roster}
        self.completed: list[frozenset[str]] = []
        self._gen_done = False

    async def execute(self, _sql, params=None):
        if not self._gen_done:
            self._gen_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        market_ids = list((params or {}).get(pc.VM_ROSTER_MARKET_IDS_PARAM) or ())
        vm_ids = frozenset(self.by_market[int(m)] for m in market_ids)
        self.runner.advance(HEALTHY_VM_MS * len(vm_ids))
        self.completed.append(vm_ids)
        return types.SimpleNamespace(all=lambda: [])

    async def rollback(self) -> None:
        return None


def _roster(n: int):
    return [
        types.SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False
        )
        for i in range(1, n + 1)
    ]


@pytest.fixture
def beat(monkeypatch):
    """Run one beat against a shared durable row. Returns ``(run, durable)``."""
    durable = _Durable()
    monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", durable.publish)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    monkeypatch.setattr(pc, "staged_unit_fingerprint", lambda: "unit-fp")
    roster = _roster(BUCKETS * VMS_PER_SLOT)

    async def _beat(generation: int):
        runner = _Runner(generation=generation)
        db = _Db(runner, roster)
        monkeypatch.setattr(
            pc,
            "time",
            types.SimpleNamespace(monotonic=lambda r=runner: r.elapsed_ms() / 1000.0),
        )
        rows = await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")
        return types.SimpleNamespace(
            rows=rows,
            runner=runner,
            db=db,
            stages=dict(runner.ledger.stage_counts),
        )

    return _beat, durable


async def _load(durable, **over):
    kw = dict(
        population_version="q268",
        input_fingerprint="unit-fp",
        generation_fingerprint="gen-fp",
        owner="test:1",
        generation=1,
    )
    kw.update(over)
    return await cmb.load_staged_cursor(**kw)


# =============================================================================
# 1. THE SUBJECT — UNKNOWN is a stand-down, not an invalidation
# =============================================================================


class TestAnUnreadableCursorIsRefusedNotInvalidated:
    """The two ways the database can decline to answer, and one verdict."""

    @pytest.mark.asyncio
    async def test_an_unavailable_read_stands_the_beat_down(self, monkeypatch):
        """``unavailable`` is ``durable_state``'s own UNKNOWN, by name.

        Not inferred from an empty result and not one of six sibling statuses
        that mean "we have it and it is unusable" — a distinct, named tier.
        """
        durable = _Durable()
        durable.payload = {"committed_units": ["4:0"]}
        durable.next_read = "unavailable"
        monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)

        _cursor, action, reason = await _load(durable)

        assert action == REFUSE, (
            "a read that did not answer says nothing about what is on disk, so "
            "the only safe action is the one that writes nothing"
        )
        assert reason == "envelope_unavailable", (
            "the reason token is unchanged so the beat ring stays comparable "
            "across this fix; only the ACTION moves"
        )

    @pytest.mark.asyncio
    async def test_a_raising_read_stands_the_beat_down(self, monkeypatch):
        """The ``except`` path is the same fact arriving by a different route."""
        durable = _Durable()
        durable.payload = {"committed_units": ["4:0"]}
        durable.next_read = "raise"
        monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)

        _cursor, action, reason = await _load(durable)

        assert action == REFUSE
        assert reason == sf.REASON_READ_FAILED

    @pytest.mark.asyncio
    async def test_the_stand_down_is_recorded_so_it_can_be_counted(self, beat):
        """A silent refusal is a diagnosis hole, and now it is the common one.

        ``_run_staged_futures`` returned on REFUSE before recording anything, so
        a stood-down beat read identically to a beat that never ran. With REFUSE
        now covering "the durable read failed", the operator's first question —
        *how often is this happening* — has to be answerable from the ledger.
        """
        run_beat, durable = beat
        first = await run_beat(1)
        assert durable.banked > 0, "the rig must bank something, or nothing is at risk"

        durable.next_read = "unavailable"
        second = await run_beat(2)

        assert second.rows is None, "a stood-down beat runs no units"
        assert f"staged:cursor_{REFUSE}" in second.stages, (
            "the action must be recorded BEFORE the refusal returns"
        )
        assert "staged:cursor_reason:envelope_unavailable" in second.stages, (
            "and the reason with it — five causes share one action, exactly as "
            "CAL-P024 says for INVALIDATE"
        )
        assert f"staged:cursor_{REFUSE}" not in first.stages


class TestTheBankSurvivesAReadThatDidNotAnswer:
    """The cost, measured end to end through the real save."""

    @pytest.mark.asyncio
    async def test_a_failed_read_does_not_overwrite_the_banked_units(self, beat):
        """THE regression. One timeout must not cost the rebuild its bank.

        Before the fix this beat started blank, ran units, and wrote a cursor
        carrying its own handful of units over the durable row it could not
        read. The assertion is on the DURABLE PAYLOAD rather than on the action,
        because the loss is a write, not a classification.
        """
        run_beat, durable = beat
        await run_beat(1)
        banked_before = durable.banked
        writes_before = durable.writes
        assert banked_before > 0

        durable.next_read = "unavailable"
        await run_beat(2)

        assert durable.banked == banked_before, (
            f"the bank went {banked_before} -> {durable.banked} on a read that "
            "returned no evidence of anything being wrong with it"
        )
        assert durable.writes == writes_before, (
            "and nothing was written at all — a beat that cannot read the "
            "cursor must not author one"
        )

    @pytest.mark.asyncio
    async def test_the_next_healthy_beat_resumes_the_same_bank(self, beat):
        """A stand-down is a pause, not a state. The bank must still resume.

        Fail-closed is only correct if it is also self-clearing: if REFUSE left
        the build unable to continue, the fix would trade one loss for a worse
        one.
        """
        run_beat, durable = beat
        await run_beat(1)
        banked_before = durable.banked

        durable.next_read = "unavailable"
        await run_beat(2)
        third = await run_beat(3)

        _cursor, action, _reason = await _load(durable)
        assert action == RESUME
        assert durable.banked >= banked_before, (
            "the third beat reads the same durable row and carries on from it"
        )
        assert third.rows is not None or durable.banked > 0


# =============================================================================
# 2. THE CONTROLS — every genuine invalidator still wipes the bank whole
# =============================================================================


class TestNothingElseIsNarrowed:
    """If these go green by accident the fix has become a fail-open one."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status, arm",
        [
            ("malformed", "a torn or truncated payload — we HAVE it and it is junk"),
            ("wrong_version", "a schema we cannot read is a row, not a silence"),
            ("wrong_type", "the envelope is not an envelope"),
            ("stale", "outside the age bound is a judgement on a row we read"),
        ],
    )
    async def test_a_row_we_read_and_cannot_use_still_invalidates(
        self, monkeypatch, status, arm
    ):
        durable = _Durable()
        durable.payload = {"committed_units": ["4:0"]}
        durable.next_read = status
        monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)

        _cursor, action, reason = await _load(durable)

        assert action == INVALIDATE, arm
        assert reason == f"envelope_{status}"

    @pytest.mark.asyncio
    async def test_an_absent_cursor_is_still_fresh(self, monkeypatch):
        """Nothing on disk is a real answer, and it is not a refusal.

        This is the boundary the whole fix turns on: ``missing`` and
        ``unavailable`` are one branch's width apart and mean opposite things.
        """
        durable = _Durable()
        monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)

        _cursor, action, reason = await _load(durable)

        assert action == FRESH
        assert reason == sf.REASON_ABSENT

    @pytest.mark.asyncio
    async def test_a_changed_calculation_version_still_wipes_the_whole_bank(
        self, beat
    ):
        """The directive's line, pinned: a global input change invalidates all.

        ``input_fingerprint`` is the emitted futures statement's own digest, so
        this is the calculation version moving. Per-unit reuse across it would
        publish a census half-computed by two different statements, and nothing
        in this file may make that possible.
        """
        run_beat, durable = beat
        await run_beat(1)
        assert durable.banked > 0

        _cursor, action, reason = await _load(durable, input_fingerprint="moved")

        assert action == INVALIDATE
        assert reason == sf.REASON_INPUT_FINGERPRINT

    @pytest.mark.asyncio
    async def test_a_changed_population_version_still_wipes_the_whole_bank(self, beat):
        run_beat, durable = beat
        await run_beat(1)
        assert durable.banked > 0

        _cursor, action, reason = await _load(durable, population_version="q269")

        assert action == INVALIDATE
        assert reason == sf.REASON_POPULATION_VERSION

    @pytest.mark.asyncio
    async def test_a_lease_held_by_another_worker_still_refuses(self, beat):
        """REFUSE's original meaning is untouched, and still reports as itself."""
        run_beat, durable = beat
        await run_beat(1)
        # The lease is stamped by ``advance``, and this rig's beats hold one
        # only for their own duration; an unexpired one is set here rather than
        # waited for, because the subject is the DECODER's branch, not the clock.
        durable.payload = dict(durable.payload, owner="test:2", lease_expires_at=2**40)

        _cursor, action, reason = await _load(durable, owner="test:1", generation=2)

        assert action == REFUSE
        assert reason == sf.REASON_LEASE_HELD, (
            "the two refusals must stay tellable apart — one is another worker, "
            "the other is a database that did not answer"
        )
