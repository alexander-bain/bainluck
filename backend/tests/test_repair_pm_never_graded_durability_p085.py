"""CAL-P085 durability round 2 — consuming `C-APPLY-PRE-1912-R3-R2`'s BLOCK.

Codex's verdict: *"BLOCK — the intent gate still trusts the publisher's
acknowledgement, so a no-op publisher can permit every row to commit with no
durable obligation."*

**This is CAL-P081's finding one layer down, and the reason it survived CAL-P081
is worth stating plainly, because it is a lesson about test construction rather
than about durability.** CAL-P081 closed the intent gate: force
``_save_obligation`` to return ``(False, ...)`` and the apply now writes nothing.
That test passes. It has always passed. What it cannot see is a
``_save_obligation`` that returns ``(True, "ok")`` *wrongly* — because the test
patches ``_save_obligation`` **itself**, so the function whose honesty is in
question is the one the test replaced with an honest stub.

Codex's specimen went under it: patch the real ``publish_snapshot_standalone``
to store nothing and answer ``{"status": "ok"}``, then drive the REAL
``_save_obligation``. Both ``ok`` and ``superseded`` variants performed
**4 UPDATEs, 4 commits, returned `success: true`, `obligation_persisted: true`**
— and the durable store received nothing. The `INTENT_NOT_DURABLE` branch
CAL-P081 added is real and correct and simply **unreachable**.

So every test in this file patches the **publisher**, never the saver. That is
the whole design:

    a test that stubs the layer under audit can only prove the stub

The same hole in ``_save_plan`` [P2] does not write wrong rows — a later apply
fails when ``_load_plan`` cannot read the plan — but it hands Alex a dry-run
receipt saying an approved ``plan_hash`` is durable when no such artifact exists,
which can waste an attended window.

Fifth publisher call site in this family; halt and progress already carried the
after-read discipline (CAL-P076/CAL-P081). Obligation and plan did not. As with
the halt, the rule was in the file — the reach was not.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.tasks import repair_pm_never_graded as rail
from app.tasks.repair_pm_never_graded import (
    OBLIGATION_IDENTITY,
    _apply_reviewed_plan,
    _load_obligation,
    _load_plan,
    _save_obligation,
    _save_plan,
)
from app.utils.calibration_invalidation import (
    OBLIGATION_DISCHARGED,
    discharge_obligation,
    new_obligation,
)
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

from tests.test_repair_pm_never_graded_durability_p081 import _Db, _plan


# ---------------------------------------------------------------------------
# The adversarial publisher, and the honest one, over one fake store
# ---------------------------------------------------------------------------


class FakeDurableStore:
    """A durable store you can make lie in exactly the ways that matter.

    ``mode``:

    * ``honest``     — writes what it is given and says so.
    * ``no_op``      — writes NOTHING and says ``ok``. Codex's specimen.
    * ``superseded`` — writes NOTHING and says ``superseded``. The second variant,
      kept separate because ``superseded`` is an *expected* status in this rail
      and therefore the more plausible disguise.
    * ``wrong_body`` — writes a DIFFERENT record and says ``ok``. Not in codex's
      report; added because an after-read that only checks readability would pass
      it, and "something is there" is not "my record is there".
    """

    def __init__(self, mode: str = "honest") -> None:
        self.mode = mode
        self.rows: dict[str, DurableEnvelope] = {}
        self.publishes = 0
        self.reads = 0
        self.substitute: Any = None

    async def publish(self, envelope: DurableEnvelope) -> dict:
        self.publishes += 1
        if self.mode == "honest":
            self.rows[envelope.identity] = envelope
            return {"status": "ok"}
        if self.mode == "wrong_body":
            self.rows[envelope.identity] = DurableEnvelope.build(
                identity=envelope.identity,
                schema_version=envelope.schema_version,
                payload=self.substitute,
                complete=True,
                source="somebody-else",
            )
            return {"status": "ok"}
        if self.mode == "superseded":
            return {"status": "superseded"}
        return {"status": "ok"}  # no_op

    async def read(
        self, identity: str, *, expected_version: str | None = None, max_age_s: float = 0
    ) -> EnvelopeRead:
        self.reads += 1
        env = self.rows.get(identity)
        if env is None:
            return EnvelopeRead(status="missing", tier="fake")
        return EnvelopeRead(status="ok", tier="fake", envelope=env)


@pytest.fixture
def store(monkeypatch):
    """Install a store and return a factory that sets its mode.

    Patches ``app.services.durable_snapshots`` — **the layer under the saver** —
    because that is the only place from which a no-op publisher is visible.
    """
    holder = FakeDurableStore()

    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", holder.publish
    )
    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", holder.read
    )
    return holder


def _obligation(plan_hash="hash-a", markets=(1, 2), legs=(10, 11)):
    return new_obligation(
        plan_hash=plan_hash, market_ids=markets, leg_ids=legs, owner=rail._OWNER
    )


# =============================================================================
# [P1] — the obligation
# =============================================================================


class TestTheObligationMustBeProvedNotAcknowledged:
    """The RED test. Before the fix, every assertion here reads the other way."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["no_op", "superseded"])
    async def test_a_no_op_publisher_cannot_make_an_obligation_durable(self, store, mode):
        """Codex's specimen, both variants, against the REAL `_save_obligation`.

        Before CAL-P085 this returned ``(True, "ok")`` for both. The publisher
        was asked whether it had worked and it said yes; nothing asked the store.
        """
        store.mode = mode
        ok, note = await _save_obligation(_obligation())

        assert ok is False, f"a {mode!r} no-op publisher was accepted as durable"
        assert "UNPROVED" in note
        assert store.rows == {}, "the fake store must really be storing nothing"

    @pytest.mark.asyncio
    async def test_an_honest_publisher_still_passes(self, store):
        """The control. A refuse-everything gate is not a fix.

        Named because it is the failure mode of every after-read added under
        time pressure: the cheapest way to pass an adversarial cert is to refuse
        the honest case too, and it looks identical in the diff.
        """
        store.mode = "honest"
        ok, note = await _save_obligation(_obligation())

        assert ok is True, note
        assert "after-read proved" in note
        record, read_note = await _load_obligation()
        assert read_note == "ok"
        assert record["plan_hash"] == "hash-a"

    @pytest.mark.asyncio
    async def test_a_readable_record_belonging_to_a_DIFFERENT_plan_is_refused(self, store):
        """Readability is not identity.

        An after-read that only asked "did something come back" would pass this,
        and the record it accepted would be some other wave's debt. Discharging
        that one later would silently drop OUR debt — the same shape as the halt
        finding, where a raised halt belonging to another trip was still a stop
        but was not proof that THIS trip was recorded.
        """
        store.mode = "wrong_body"
        store.substitute = _obligation(plan_hash="hash-SOMEBODY-ELSE")
        ok, note = await _save_obligation(_obligation(plan_hash="hash-a"))

        assert ok is False
        assert "UNPROVED" in note
        assert "hash-a" in note

    @pytest.mark.asyncio
    async def test_a_TRUNCATED_id_set_is_refused(self, store):
        """The complete ID sets, per codex's fix-sketch — not just the hash.

        `new_obligation` names the union of everything the plan has ever written,
        and that union IS the fix it was added for: on a retry the rows are
        already committed, so `written` is empty and this record is the only
        surviving statement of what must be invalidated. A store that kept the
        right plan_hash and a SHORTER `market_ids` would leave part of the debt
        unnamed while reading, in every field a lazy check looks at, correct.
        """
        store.mode = "wrong_body"
        store.substitute = _obligation(markets=(1,), legs=(10,))
        ok, note = await _save_obligation(_obligation(markets=(1, 2), legs=(10, 11)))

        assert ok is False
        assert "UNPROVED" in note

    @pytest.mark.asyncio
    async def test_the_state_must_match_so_a_discharge_cannot_be_proved_by_an_open_record(
        self, store
    ):
        """The discharge write is the third call site and the most dangerous one.

        If a discharge is proved by reading back the still-OPEN record, the rail
        reports the debt paid while the store says it is outstanding — which is
        the one direction that loses money, because an open debt at least
        re-triggers the repair.
        """
        store.mode = "wrong_body"
        store.substitute = _obligation()  # still OPEN
        ok, note = await _save_obligation(
            discharge_obligation(_obligation(), proof={"status": "invalidated"})
        )

        assert ok is False
        assert "UNPROVED" in note
        assert OBLIGATION_DISCHARGED in note

    @pytest.mark.asyncio
    async def test_an_unreadable_store_is_refused_not_assumed_absent(self, store):
        """`unavailable` is not `missing`, and neither is proof of a write.

        Gotcha #53 at the durability layer: the read failing and the record being
        absent must not reach the caller as the same value, and NEITHER of them
        may satisfy a claim that the record is there.
        """
        store.mode = "honest"

        async def _unavailable(identity, **_kw):
            return EnvelopeRead(status="unavailable", tier="fake", error="down")

        import app.services.durable_snapshots as ds

        ds.read_snapshot_standalone = _unavailable
        try:
            ok, note = await _save_obligation(_obligation())
        finally:
            ds.read_snapshot_standalone = store.read

        assert ok is False
        assert "UNPROVED" in note


class TestTheApplyRefusesOverANoOpPublisher:
    """The finding as codex stated it: 4 UPDATEs, 4 commits, `success: true`."""

    def _wire_around_the_publisher(self, monkeypatch, plan):
        """Everything EXCEPT the obligation path is stubbed.

        `_save_obligation`, `_load_obligation` and the publisher are left real so
        the gate is exercised end to end. That is the entire difference from
        CAL-P081's `_wire`, and it is the difference between a test that catches
        this and one that cannot.
        """
        async def _load_plan_():
            return plan, "ok"

        async def _inval(_session, _ids):
            return {"status": "invalidated"}

        async def _load_progress():
            return None, "missing"

        async def _save_progress_ok(_rec):
            return True, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load_plan_)
        monkeypatch.setattr(rail, "_load_progress", _load_progress)
        monkeypatch.setattr(rail, "_save_progress", _save_progress_ok)
        monkeypatch.setattr(
            "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
            _inval,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["no_op", "superseded"])
    async def test_zero_updates_and_zero_commits_over_a_store_nothing_publisher(
        self, store, monkeypatch, mode
    ):
        """The headline assertion. Codex measured 4/4; the bar is 0/0."""
        store.mode = mode
        plan = _plan(4)
        self._wire_around_the_publisher(monkeypatch, plan)
        db = _Db()

        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert db.updates == 0, f"{db.updates} rows were written with no durable debt"
        assert db.commits == 0
        assert out["success"] is False
        assert out["refused"] == ["INTENT_NOT_DURABLE"]
        assert out["legs_written"] == 0
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_an_honest_publisher_still_lets_the_apply_through(
        self, store, monkeypatch
    ):
        """The over-reach control, at the apply level.

        Without this, the cheapest way to pass the cert is an apply that never
        applies — and the durability tests would all still be green.
        """
        store.mode = "honest"
        plan = _plan(4)
        self._wire_around_the_publisher(monkeypatch, plan)
        db = _Db()

        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out.get("refused") != ["INTENT_NOT_DURABLE"]
        assert db.updates == 4
        assert OBLIGATION_IDENTITY in store.rows


# =============================================================================
# [P2] — the plan
# =============================================================================


class TestThePlanMustBeProvedNotAcknowledged:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["no_op", "superseded"])
    async def test_a_no_op_publisher_cannot_make_a_plan_durable(self, store, mode):
        """The dry-run receipt is a promise to an operator.

        This one writes no wrong rows — a later apply simply fails when
        `_load_plan` finds nothing. The cost is an attended window spent on an
        approved `plan_hash` that names an artifact which never existed.
        """
        store.mode = mode
        ok, note = await _save_plan(_plan(4))

        assert ok is False, f"a {mode!r} no-op publisher was accepted as durable"
        assert "UNPROVED" in note
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_an_honest_publisher_still_passes_and_the_plan_reads_back(self, store):
        store.mode = "honest"
        plan = _plan(4)
        ok, note = await _save_plan(plan)

        assert ok is True, note
        assert "after-read proved" in note
        loaded, read_note = await _load_plan()
        assert read_note == "ok"
        assert loaded.plan_hash == plan.plan_hash

    @pytest.mark.asyncio
    async def test_a_DIFFERENT_plan_in_the_store_is_refused_by_hash(self, store):
        """Codex's fix-sketch: re-digest and require the exact attempted hash.

        Re-digesting rather than comparing the stored `plan_hash` FIELD matters:
        a payload can carry a hash that does not describe its own body, and the
        field would then agree with us about a plan whose legs are somebody
        else's.
        """
        other = _plan(2)
        store.mode = "wrong_body"
        store.substitute = other.as_payload()
        ok, note = await _save_plan(_plan(4))

        assert ok is False
        assert "UNPROVED" in note
        assert other.plan_hash[:8] in note or "hash" in note

    @pytest.mark.asyncio
    async def test_an_undecodable_plan_body_is_refused(self, store):
        """`_load_plan` re-digests from content, so a corrupt body cannot decode.

        A saver that treated "decode failed" as anything other than UNPROVED
        would report durability for an artifact no apply can ever read.
        """
        store.mode = "wrong_body"
        store.substitute = {"not": "a plan"}
        ok, note = await _save_plan(_plan(4))

        assert ok is False
        assert "UNPROVED" in note


# =============================================================================
# The census — so the sixth call site cannot repeat this
# =============================================================================


class TestEveryPublisherCallSiteInThisRailHasAnAfterRead:
    """The finding is "the fifth call site in this family". Make it the last.

    CAL-P076 added the discipline to progress, CAL-P081 to the halt, CAL-P085 to
    the obligation and the plan. Each time it was added to the site that had just
    been caught. This test fails on the NEXT one instead, which is the only
    version of the rule that does not need somebody to remember it.
    """

    def test_no_publish_call_returns_on_status_alone(self):
        import inspect

        source = inspect.getsource(rail)
        # Each `publish_snapshot_standalone(` call must be followed, before the
        # enclosing function can return True, by a read-back. The cheap, robust
        # proxy: the rail's publisher call count and its after-read count agree.
        publishes = source.count("publish_snapshot_standalone(\n")
        proved = source.count("after-read proved")
        assert publishes >= 4, "the census moved — re-derive it, do not lower it"
        assert proved == publishes, (
            f"{publishes} publisher call sites but only {proved} claim an after-read. "
            "A new durable write was added without one — that is the "
            "C-APPLY-PRE-1912-R3-R2 finding, again."
        )

    def test_the_acknowledgement_statuses_are_still_only_a_precondition(self):
        """`ok`/`superseded` may gate the after-read; they may never replace it."""
        import inspect

        for fn in (_save_obligation, _save_plan, rail._raise_wave_halt, rail._save_progress):
            src = inspect.getsource(fn)
            assert '("ok", "superseded")' in src or '"ok", "superseded"' in src
            assert "after-read" in src, f"{fn.__name__} has no after-read"
