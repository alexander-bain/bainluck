"""CAL-P062: the two false-green paths C-CERT-1852-R2 blocked on.

R2's sharpest observation was about TEST SHAPE, not about the two defects. The
branch's own finding-4 class was green — 102/102 focused tests passed — because
every one of its cases created a fresh session, made exactly ONE apply call, and
replaced the invalidation function with a preselected result. A suite built that
way cannot express either specimen, because both specimens ARE durable state
across calls:

* **specimen one** is a write whose acknowledgement is believed instead of
  re-read, so the proof has to be a store that still holds the OLD record after
  a publisher said ``ok``;
* **specimen two** is a committed write, a FAILED invalidation, and then a
  RETRY, so the proof has to be two calls sharing one row set and one ledger.

So the harness below is the fix as much as the assertions are. ``_DurableStore``
is a real generation-guarded store that survives across calls and records which
identities were READ — the exact ledger R2 used to show the main checkpoint was
never inspected. ``_CASSession`` holds its rows between calls so the second apply
compare-and-set-drifts on the row the first one committed, which is the whole
mechanism of the laundering.

Every test here fails on the pre-CAL-P062 code. The two control tests say so
explicitly and name the value the old rail returned.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.durable_snapshots import STATUS_CAS_MISS
from app.tasks import repair_kalshi_fabricated_loss as rail
from app.tasks.calibration_main_build import (
    CHECKPOINT_IDENTITY,
    STAGED_FUTURES_IDENTITY,
)
from app.utils.calibration_invalidation import (
    INVALIDATION_OBLIGATION_SCHEMA,
    OBLIGATION_DISCHARGED,
    OBLIGATION_OPEN,
    invalidation_discharged,
    main_checkpoint_is_invalidation,
    new_obligation,
)
from app.utils.calibration_phase_ledger import MAIN_BUILD_TASK, MAIN_CHECKPOINT_SCHEMA
from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA
from app.utils.durable_state import DurableEnvelope, EnvelopeRead
from app.utils.kalshi_fabricated_loss import REPAIRABLE_SOURCE, RETRACTION_SOURCE
from app.utils.repair_apply_plan import PlannedLeg, build_plan

OBLIGATION_IDENTITY = rail.OBLIGATION_IDENTITY


# =============================================================================
# Harness — a store and a session that OUTLIVE a single call
# =============================================================================


class _DurableStore:
    """A generation-guarded durable store with a read-identity ledger.

    Three levers, each modelling a real failure the rail must survive:

    * ``no_op`` — a publisher that ANSWERS without persisting (specimen one);
    * ``forced_status`` — a publish that reports a status of our choosing, so
      ``superseded`` can be produced against a store we control;
    * ``unreadable`` — a read that fails, which must never read as "absent".
    """

    def __init__(self) -> None:
        self.rows: dict[str, DurableEnvelope] = {}
        self.reads: list[str] = []
        self.publishes: list[str] = []
        self.no_op: set[str] = set()
        self.forced_status: dict[str, str] = {}
        self.unreadable: dict[str, str] = {}

    # -- installation ------------------------------------------------------
    def install(self, monkeypatch) -> "_DurableStore":
        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "read_snapshot_standalone", self.read)
        monkeypatch.setattr(ds, "publish_snapshot_standalone", self.publish)
        # CAL-P1008-R3: the apply now stages its undo receipt in the caller's
        # transaction (`publish_snapshot_in_txn`) so rows and receipt commit
        # together. Unpatched, these reach a real database and every apply in
        # this file refuses. The pair here takes effect IMMEDIATELY — atomicity
        # itself is the subject of `test_kalshi_fabricated_loss_p1008.py`, which
        # installs a session-aware version over the top of this one.
        monkeypatch.setattr(ds, "read_snapshot", self.read_in_txn)
        monkeypatch.setattr(ds, "publish_snapshot_in_txn", self.publish_in_txn)
        # #3191: the obligation ledger's two writers are read-modify-writes, so
        # they go through the COMPARE-AND-SET publishers. Unpatched, they reach a
        # real database and every apply in this file refuses.
        monkeypatch.setattr(ds, "publish_cas_snapshot_standalone", self.publish_cas)
        monkeypatch.setattr(ds, "publish_cas_snapshot_in_txn", self.publish_cas_in_txn)
        return self

    async def read_in_txn(self, db, identity, **kwargs):
        return await self.read(identity, **kwargs)

    async def publish_in_txn(self, db, envelope):
        return await self.publish(envelope)

    async def publish_cas_in_txn(self, db, envelope, *, expected_generation):
        return await self.publish_cas(envelope, expected_generation=expected_generation)

    async def publish_cas(self, envelope: DurableEnvelope, *, expected_generation):
        """Compare-and-set, plus the same three levers.

        The predicate is equality between the generation the caller SAYS it read
        and the one in the slot NOW — never against the generation the caller
        proposes. A fake that compared the proposed value would agree with the
        very bug this models (#3191): two writers that both read `g` and both
        propose `g+1` would both be told they won.
        """
        self.publishes.append(envelope.identity)
        status = self.forced_status.get(envelope.identity, "ok")
        if status != "ok":
            # A forced status is a store that ANSWERED without doing the write.
            return {
                "status": status,
                "identity": envelope.identity,
                "generation": envelope.generation,
            }
        existing = self.rows.get(envelope.identity)
        stored = existing.generation if existing is not None else None
        if stored != expected_generation:
            return {
                "status": STATUS_CAS_MISS,
                "identity": envelope.identity,
                "generation": envelope.generation,
                "expected_generation": expected_generation,
            }
        if envelope.identity not in self.no_op:
            self.rows[envelope.identity] = envelope
        return {
            "status": "ok",
            "identity": envelope.identity,
            "generation": envelope.generation,
        }

    # -- inspection --------------------------------------------------------
    def seed(self, identity: str, schema: str, payload) -> None:
        self.rows[identity] = DurableEnvelope.build(
            identity=identity, schema_version=schema, payload=payload, source="seed"
        )

    def payload(self, identity: str):
        env = self.rows.get(identity)
        return env.payload if env else None

    # -- the substrate -----------------------------------------------------
    async def read(self, identity, *, expected_version=None, max_age_s=None):
        self.reads.append(identity)
        if identity in self.unreadable:
            return EnvelopeRead(status=self.unreadable[identity], tier="durable")
        env = self.rows.get(identity)
        if env is None:
            return EnvelopeRead(status="missing", tier="durable")
        if expected_version is not None and env.schema_version != expected_version:
            return EnvelopeRead(status="version_mismatch", tier="durable")
        return EnvelopeRead(status="ok", tier="durable", envelope=env)

    async def publish(self, envelope: DurableEnvelope):
        self.publishes.append(envelope.identity)
        status = self.forced_status.get(envelope.identity, "ok")
        persists = envelope.identity not in self.no_op and status in ("ok", "superseded")
        if persists:
            existing = self.rows.get(envelope.identity)
            if existing is not None and existing.generation > envelope.generation:
                status = "superseded"
            else:
                self.rows[envelope.identity] = envelope
        return {
            "status": status,
            "identity": envelope.identity,
            "generation": envelope.generation,
        }


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _CASSession:
    """PostgreSQL's UPDATE semantics for the two shapes this rail emits.

    Deliberately NOT re-created between calls in the two-call tests: the row the
    first apply commits is the row the second apply must drift on.
    """

    def __init__(self, rows) -> None:
        self.rows = {r["id"]: dict(r) for r in rows}
        self.commits = 0
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "SELECT COUNT(*)" in sql:
            return SimpleNamespace(
                one=lambda: SimpleNamespace(
                    retracted_now=sum(
                        1
                        for r in self.rows.values()
                        if r["resolution_source"] == RETRACTION_SOURCE
                    ),
                    winners_now=sum(1 for r in self.rows.values() if r["is_winner"]),
                )
            )
        if "SELECT id, source FROM futures_markets" in sql:
            return SimpleNamespace(all=lambda: [])
        if "UPDATE futures_outcomes" not in sql:
            return _FakeResult(0)

        row = self.rows.get(params["id"])
        if row is None:
            return _FakeResult(0)
        if row["is_winner"] != params["prior_winner"]:
            return _FakeResult(0)
        if row["resolution_source"] != params["prior_source"]:
            return _FakeResult(0)
        if "SET is_winner = true" in sql:
            row["is_winner"] = True
            row["resolution_source"] = REPAIRABLE_SOURCE
        else:
            row["resolution_source"] = params["retraction"]
        return _FakeResult(1)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    def updates(self) -> list[str]:
        return [s for s in self.statements if "UPDATE futures_outcomes" in s]


def _banked_checkpoint(*, phases=("futures",), terminal="partial") -> dict:
    """A main checkpoint that CARRIES banked phase output — the dangerous shape."""
    return {
        "schema": MAIN_CHECKPOINT_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "version": "pop-v1",
        "generation": 1,
        "owner": "calibration_main_build",
        "lease_expires_at": 0.0,
        "input_fingerprint": "fp-1",
        "completed_phases": list(phases),
        "phase_outputs": {p: {"stored": True, "values": {"n": 1}} for p in phases},
        "terminal": terminal,
    }


def _staged_cursor_payload(units) -> dict:
    return {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": "vm_id",
        "population_version": "pop-v1",
        "input_fingerprint": "fp-1",
        "generation_fingerprint": "gf-1",
        "generation": 1,
        "owner": "calibration_main_build",
        "lease_expires_at": 0.0,
        "committed_units": list(units),
        "accumulator": {},
        "terminal": "partial",
        "unit_digests": {},
        "roster_drift_units": 0,
    }


def _seeded_store(monkeypatch, *, units=("u1", "u2", "u3"), checkpoint=None):
    store = _DurableStore().install(monkeypatch)
    store.seed(
        STAGED_FUTURES_IDENTITY, STAGED_FUTURES_SCHEMA, _staged_cursor_payload(units)
    )
    store.seed(
        CHECKPOINT_IDENTITY,
        MAIN_CHECKPOINT_SCHEMA,
        checkpoint if checkpoint is not None else _banked_checkpoint(),
    )
    return store


# =============================================================================
# SPECIMEN ONE — the main checkpoint is AFTER-READ, not acknowledged
# =============================================================================


class TestSpecimenOneMainCheckpointAfterRead:
    """R2: ``checkpoint_ok = res.get("status") in ("ok", "superseded")``.

    The adversarial no-op publisher returned ``status=invalidated`` and its
    read-identity ledger was ``[staged_futures, staged_futures]`` — the main
    checkpoint was never inspected. These tests drive the real
    ``invalidate_calibration_generation`` against a store that keeps the old
    record, so believing the acknowledgement is visible as a wrong answer.
    """

    @pytest.mark.asyncio
    async def test_a_no_op_publisher_cannot_report_invalidated(self, monkeypatch):
        """THE CONTROL. Pre-CAL-P062 this returned ``status: invalidated``."""
        store = _seeded_store(monkeypatch)
        store.no_op.add(CHECKPOINT_IDENTITY)  # answers ok, persists nothing

        verdict = await rail.invalidate_calibration_generation(_CASSession([]), {500})

        assert verdict["main_checkpoint_publish_status"] == "ok", (
            "the publisher must still be ANSWERING ok — otherwise this test is "
            "no longer reproducing the false-green it exists to catch"
        )
        assert verdict["status"] == "failed"
        assert verdict["main_checkpoint_after_read"]["is_invalidation"] is False
        assert "BANKED_PHASES" in verdict["main_checkpoint_after_read"]["why"]

    @pytest.mark.asyncio
    async def test_the_read_identity_ledger_contains_the_main_checkpoint(
        self, monkeypatch
    ):
        """R2's exact diagnostic, asserted directly: the identity IS inspected."""
        store = _seeded_store(monkeypatch)
        await rail.invalidate_calibration_generation(_CASSession([]), {500})
        assert CHECKPOINT_IDENTITY in store.reads
        assert store.reads.count(STAGED_FUTURES_IDENTITY) == 2, "before and after"

    @pytest.mark.asyncio
    async def test_superseded_by_a_record_that_still_carries_phases_is_a_failure(
        self, monkeypatch
    ):
        """The sharper half: ``superseded`` is the case where the banked phases
        the invalidation exists to discard are demonstrably still there."""
        store = _seeded_store(monkeypatch)
        store.no_op.add(CHECKPOINT_IDENTITY)
        store.forced_status[CHECKPOINT_IDENTITY] = "superseded"

        verdict = await rail.invalidate_calibration_generation(_CASSession([]), {500})

        assert verdict["main_checkpoint_publish_status"] == "superseded"
        assert verdict["status"] == "failed"

    @pytest.mark.asyncio
    async def test_superseded_by_an_equivalent_invalidation_is_accepted(
        self, monkeypatch
    ):
        """And the honest converse — a winning record proven equivalent passes.

        Without this the fix would just be "superseded always fails", which is a
        different bug: a legitimate concurrent clear would wedge the rail.
        """
        store = _seeded_store(
            monkeypatch,
            units=(),
            checkpoint=_banked_checkpoint(phases=(), terminal="complete"),
        )
        store.no_op.add(CHECKPOINT_IDENTITY)
        store.forced_status[CHECKPOINT_IDENTITY] = "superseded"

        verdict = await rail.invalidate_calibration_generation(_CASSession([]), {500})

        assert verdict["status"] == "invalidated"
        assert "EQUIVALENT_INVALIDATION" in verdict["main_checkpoint_after_read"]["why"]

    @pytest.mark.asyncio
    async def test_the_honest_path_still_invalidates(self, monkeypatch):
        store = _seeded_store(monkeypatch)
        verdict = await rail.invalidate_calibration_generation(_CASSession([]), {500})

        assert verdict["status"] == "invalidated"
        assert verdict["banked_units_before"] == 3
        assert verdict["banked_units_after"] == 0
        assert verdict["banked_units_discarded"] == 3
        stored = store.payload(CHECKPOINT_IDENTITY)
        assert stored["terminal"] == "invalidated"
        assert stored["completed_phases"] == [] and stored["phase_outputs"] == {}

    @pytest.mark.asyncio
    async def test_an_unreadable_checkpoint_is_unknown_not_cleared(self, monkeypatch):
        store = _seeded_store(monkeypatch)
        store.no_op.add(CHECKPOINT_IDENTITY)
        store.unreadable[CHECKPOINT_IDENTITY] = "unavailable"

        verdict = await rail.invalidate_calibration_generation(_CASSession([]), {500})

        assert verdict["status"] == "failed"
        assert "UNREADABLE" in verdict["main_checkpoint_after_read"]["why"]


class TestMainCheckpointPredicate:
    """The pure rule, driven by a table. Zero banked phases is the test."""

    def test_the_rails_own_invalidation_record_passes(self):
        ok, why = main_checkpoint_is_invalidation(
            _banked_checkpoint(phases=(), terminal="invalidated")
        )
        assert ok and "IS_THE_INVALIDATION_RECORD" in why

    @pytest.mark.parametrize(
        "payload,fragment",
        [
            (_banked_checkpoint(), "STILL_CARRIES_BANKED_PHASES"),
            (
                _banked_checkpoint(phases=(), terminal="partial"),
                "NOT_AN_INVALIDATION",
            ),
            ({"completed_phases": [], "phase_outputs": {}}, "NOT_AN_INVALIDATION"),
            ({"terminal": "invalidated"}, "SHAPE_UNREADABLE"),
            ("not a record", "NOT_A_RECORD"),
        ],
    )
    def test_the_shapes_that_must_fail(self, payload, fragment):
        ok, why = main_checkpoint_is_invalidation(payload)
        assert ok is False and fragment in why

    def test_a_terminal_rename_alone_cannot_buy_a_pass(self):
        """Naming a record 'invalidated' while it still banks a phase fails."""
        ok, _ = main_checkpoint_is_invalidation(
            _banked_checkpoint(phases=("futures",), terminal="invalidated")
        )
        assert ok is False


# =============================================================================
# SPECIMEN TWO — the obligation outlives the response
# =============================================================================


class _ScriptedInvalidation:
    """The real function's CONTRACT, scripted. Empty ids => nothing_written.

    Modelling that branch faithfully is what makes the laundering reproducible:
    the old rail's retry called this with an empty set and the honest answer to
    an empty set is ``nothing_written``.
    """

    def __init__(self, statuses) -> None:
        self.statuses = list(statuses)
        self.calls: list[list[int]] = []

    async def __call__(self, session, market_ids):
        ids = sorted(int(i) for i in market_ids)
        self.calls.append(ids)
        if not ids:
            return {"status": "nothing_written", "banked_units_discarded": 0}
        status = self.statuses.pop(0) if self.statuses else "invalidated"
        return {
            "status": status,
            "banked_units_discarded": 3 if status == "invalidated" else None,
        }


class TestSpecimenTwoRetryCannotLaunderAFailure:
    """R2's exact two-call output, reproduced:

    ``first: legs_written=1, invalidation=failed, success=False``
    ``second: legs_written=0, concurrent_drift=1, invalidation=nothing_written,
    success=True`` — with no calibration state invalidated on either call.

    One session and one store span both calls, which is the only shape in which
    the second call can drift on the first call's committed row.
    """

    LEGS = (PlannedLeg(1, 500, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-1"),)

    def _install(self, monkeypatch, statuses):
        store = _seeded_store(monkeypatch)
        plan = build_plan(self.LEGS)

        async def _load():
            return plan, "ok"

        inv = _ScriptedInvalidation(statuses)
        monkeypatch.setattr(rail, "_load_plan", _load)
        monkeypatch.setattr(rail, "invalidate_calibration_generation", inv)
        session = _CASSession(
            [{"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE}]
        )
        return store, plan, inv, session

    @pytest.mark.asyncio
    async def test_the_retry_after_a_failed_invalidation_is_not_success(
        self, monkeypatch
    ):
        """THE CONTROL. Pre-CAL-P062 the second call returned ``success: True``."""
        store, plan, inv, session = self._install(monkeypatch, ["failed", "failed"])

        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        second = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        # The specimen's own numbers, unchanged — the setup still reproduces.
        assert first["legs_written"] == 1 and first["success"] is False
        assert second["legs_written"] == 0
        assert second["concurrent_drift_count"] == 1

        # ...and the two things that were wrong about it.
        assert inv.calls == [[500], [500]], (
            "the retry must invalidate the OBLIGATION's markets, not this "
            "call's empty written set"
        )
        assert second["calibration_invalidation"]["status"] == "failed"
        assert second["success"] is False

    @pytest.mark.asyncio
    async def test_the_debt_is_persisted_before_the_invalidation_is_attempted(
        self, monkeypatch
    ):
        store, plan, inv, session = self._install(monkeypatch, ["failed"])
        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert first["invalidation_obligation"]["state"] == "open"
        ledger = store.payload(OBLIGATION_IDENTITY)
        assert ledger["state"] == OBLIGATION_OPEN
        assert ledger["plan_hash"] == plan.plan_hash
        assert ledger["market_ids"] == [500] and ledger["leg_ids"] == [1]

    @pytest.mark.asyncio
    async def test_the_retry_discharges_the_obligation_when_it_finally_works(
        self, monkeypatch
    ):
        store, plan, inv, session = self._install(
            monkeypatch, ["failed", "invalidated"]
        )
        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        second = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert first["success"] is False
        assert second["success"] is True
        assert second["invalidation_obligation"]["carried_in"]["open"] is True
        assert second["invalidation_obligation"]["state"] == "discharged"
        assert store.payload(OBLIGATION_IDENTITY)["state"] == OBLIGATION_DISCHARGED

    @pytest.mark.asyncio
    async def test_a_second_plan_is_refused_while_a_debt_is_open(self, monkeypatch):
        """A new page must not compound an unpaid debt against the curve."""
        store, plan, inv, session = self._install(monkeypatch, ["failed"])
        await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        other = build_plan(
            (PlannedLeg(9, 900, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-9"),)
        )

        async def _load_other():
            return other, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load_other)
        fresh = _CASSession(
            [{"id": 9, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE}]
        )
        out = await rail.repair(fresh, apply=True, plan_hash=other.plan_hash)

        assert out["refused"] == ["OUTSTANDING_INVALIDATION"]
        assert out["success"] is False
        assert fresh.updates() == [], "nothing may be written while a debt is open"
        assert out["outstanding_obligation"]["market_ids"] == [500]

    @pytest.mark.asyncio
    async def test_an_unreadable_ledger_refuses_before_writing_anything(
        self, monkeypatch
    ):
        store, plan, inv, session = self._install(monkeypatch, ["invalidated"])
        store.unreadable[OBLIGATION_IDENTITY] = "unavailable"

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["OBLIGATION_LEDGER_UNREADABLE"]
        assert out["success"] is False
        assert session.updates() == []
        assert inv.calls == [], "the invalidation is never reached"

    @pytest.mark.asyncio
    async def test_an_unrecorded_debt_writes_no_rows_at_all(self, monkeypatch):
        """If the ledger write itself fails, the run has no retry handle.

        CAL-P1009-R (CERT-1872) hardens what that costs. It used to commit the
        rows and report the missing debt honestly — but an honest report of a
        stale curve nothing can pay is not a substitute for not creating one, so
        the debt is now staged in the row transaction and a staging failure
        rolls the whole thing back. The atomicity itself is proved in
        ``test_kalshi_fabricated_loss_p1008.py``, whose session models an
        in-transaction durable write; this store applies writes immediately, so
        what it can say is that the apply REFUSES and reaches neither the commit
        nor the invalidation.
        """
        store, plan, inv, session = self._install(monkeypatch, ["invalidated"])
        store.forced_status[OBLIGATION_IDENTITY] = "error"

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["INVALIDATION_DEBT_NOT_STAGED"]
        assert out["legs_written"] == 0 and out["rolled_back"] is True
        assert session.commits == 0, "rows committed owing an unrecorded debt"
        assert inv.calls == [], "the invalidation is never reached"
        assert out["success"] is False

    @pytest.mark.asyncio
    async def test_drift_alone_defeats_nothing_written(self, monkeypatch):
        """No prior debt, but a leg that moved: 'never wrote' is UNPROVEN."""
        # The call installs the durable fakes; nothing here reads the store back.
        _seeded_store(monkeypatch)
        plan = build_plan(self.LEGS)

        async def _load():
            return plan, "ok"

        inv = _ScriptedInvalidation([])
        monkeypatch.setattr(rail, "_load_plan", _load)
        monkeypatch.setattr(rail, "invalidate_calibration_generation", inv)
        # The row already moved — a concurrent grader, not us.
        session = _CASSession(
            [{"id": 1, "is_winner": False, "resolution_source": "some_other_source"}]
        )

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["legs_written"] == 0 and out["concurrent_drift_count"] == 1
        assert out["calibration_invalidation"]["status"] == "nothing_written"
        assert out["success"] is False
        assert "not proven" in out["invalidation_obligation"]["discharge_note"].lower()

    @pytest.mark.asyncio
    async def test_nothing_written_is_unreachable_as_a_success_through_apply(
        self, monkeypatch
    ):
        """Where the honest ``nothing_written`` actually lives — and does not.

        Measured while writing this suite, and worth stating because it bounds
        the blast radius of the rule: inside the apply path every planned leg
        either writes or drifts, and an EMPTY plan is refused one step earlier by
        ``bind_apply`` (``PLAN_HAS_NOTHING_TO_APPLY``, pre-existing). So the
        ``nothing_written`` branch can never carry ``success: true`` here — it is
        reachable only through the standalone invalidation called with no ids,
        which is where :class:`TestTheDischargeRule` proves it.
        """
        store = _seeded_store(monkeypatch)
        plan = build_plan(())

        async def _load():
            return plan, "ok"

        inv = _ScriptedInvalidation([])
        monkeypatch.setattr(rail, "_load_plan", _load)
        monkeypatch.setattr(rail, "invalidate_calibration_generation", inv)

        out = await rail.repair(_CASSession([]), apply=True, plan_hash=plan.plan_hash)

        assert out["refused"] == ["PLAN_HAS_NOTHING_TO_APPLY"]
        assert out["success"] is False
        assert inv.calls == []
        assert store.payload(OBLIGATION_IDENTITY) is None, "no debt, no ledger row"


class TestBothSpecimensOnTheRealInvalidation:
    """One durable trace, no scripted invalidation: the write fails because the
    main checkpoint genuinely did not clear, and the retry succeeds once it can.

    This is the end-to-end the two classes above dissect. It is here because a
    fix proven only against a fake invalidation is a fix proven against a fake.
    """

    LEGS = (PlannedLeg(1, 500, "retract_fabricated", False, REPAIRABLE_SOURCE, "T-1"),)

    @pytest.mark.asyncio
    async def test_failed_then_retried_then_discharged(self, monkeypatch):
        store = _seeded_store(monkeypatch)
        store.no_op.add(CHECKPOINT_IDENTITY)  # the checkpoint publish lies
        plan = build_plan(self.LEGS)

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        session = _CASSession(
            [{"id": 1, "is_winner": False, "resolution_source": REPAIRABLE_SOURCE}]
        )

        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert first["legs_written"] == 1
        assert session.rows[1]["resolution_source"] == RETRACTION_SOURCE
        assert first["calibration_invalidation"]["status"] == "failed"
        assert first["success"] is False
        assert store.payload(OBLIGATION_IDENTITY)["state"] == OBLIGATION_OPEN

        # The operator fixes the publisher and re-applies the SAME plan_hash.
        store.no_op.discard(CHECKPOINT_IDENTITY)
        second = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert second["legs_written"] == 0, "the row is already repaired"
        assert second["concurrent_drift_count"] == 1
        assert second["calibration_invalidation"]["status"] == "invalidated"
        assert second["success"] is True
        assert store.payload(OBLIGATION_IDENTITY)["state"] == OBLIGATION_DISCHARGED
        assert store.payload(CHECKPOINT_IDENTITY)["terminal"] == "invalidated"


class TestTheDischargeRule:
    """The pure rule, so the table is readable without a store."""

    def test_invalidated_is_always_a_discharge(self):
        ok, _ = invalidation_discharged(
            status="invalidated", wrote_rows=True, drift_count=3,
            prior_obligation_open=True,
        )
        assert ok is True

    @pytest.mark.parametrize("status", ["failed", "not_run", "", "unknown"])
    def test_anything_else_is_named_not_folded(self, status):
        ok, why = invalidation_discharged(
            status=status, wrote_rows=False, drift_count=0,
            prior_obligation_open=False,
        )
        assert ok is False and repr(status) in why

    @pytest.mark.parametrize(
        "wrote_rows,drift,prior",
        [(False, 0, True), (True, 0, False), (False, 2, False)],
    )
    def test_nothing_written_is_only_for_a_plan_proven_never_to_have_written(
        self, wrote_rows, drift, prior
    ):
        ok, _ = invalidation_discharged(
            status="nothing_written", wrote_rows=wrote_rows, drift_count=drift,
            prior_obligation_open=prior,
        )
        assert ok is False

    def test_the_one_case_it_is_allowed(self):
        ok, why = invalidation_discharged(
            status="nothing_written", wrote_rows=False, drift_count=0,
            prior_obligation_open=False,
        )
        assert ok is True and "proven never to have written" in why


class TestObligationRecord:
    def test_a_new_obligation_is_open_and_carries_the_union(self):
        rec = new_obligation(
            plan_hash="abc", market_ids=[3, 1, 1], leg_ids=[9, 2], owner="rail"
        )
        assert rec["schema"] == INVALIDATION_OBLIGATION_SCHEMA
        assert rec["state"] == OBLIGATION_OPEN
        assert rec["market_ids"] == [1, 3] and rec["leg_ids"] == [2, 9]

    def test_an_unparseable_state_reads_as_open(self):
        from app.utils.calibration_invalidation import obligation_is_open

        assert obligation_is_open({"state": "who knows"}) is True
        assert obligation_is_open({}) is True
        assert obligation_is_open({"state": OBLIGATION_DISCHARGED}) is False
