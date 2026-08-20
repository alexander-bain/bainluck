"""CAL-P076 — #1912's apply rail: the halt must halt, and a kill must resume.

Two of the three catches Fable returned `C-APPLY-PRE-1912-R2` on, both about the
same thing: a rail whose safety machinery ran too late to be safety machinery.

**Catch 1 — a halt that commits is not a halt.** The canary panel's own words
are *"the cohort predicate moved, so the measurement the MC authorised no longer
describes what is being drained. HALT and re-census."* It was evaluated inside
``progress_read``, which the apply calls **in its return statement** — after
every leg has been committed, one commit per leg. The instruction to stop
arrived on the receipt for the writes it was meant to stop. Now it is a
pre-flight gate that writes nothing, plus a post-loop re-check that reverts.

**Catch 2 — checkpoint durability, proven by kill-and-resume rather than
asserted.** Rows commit per leg (gotcha #13), so a process death mid-loop leaves
them behind. The invalidation obligation was written only AFTER the loop, so a
kill at leg 30 of 200 left 30 committed rows whose calibration debt no record
named — and the next apply of the same plan read ``prior is None`` and believed
nothing was owed. Worse, the retry's own rows failed the compare-and-set and
came back as ``legs_drifted``, so a resume that worked perfectly reported itself
as interference and its drift count defeated ``invalidation_discharged``.

These tests kill the loop for real (the session raises mid-write), then run the
same plan again against the state the kill left behind.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import repair_pm_never_graded as rail
from app.tasks.repair_pm_never_graded import (
    CANARY_CLEAN,
    CANARY_TRIPPED,
    CANARY_UNMEASURED,
    WRITE_SOURCE,
    _apply_reviewed_plan,
    evaluate_canaries,
)
from app.utils.repair_apply_plan import PlannedLeg, build_plan


def _plan(n=4):
    legs = [
        PlannedLeg(
            leg_id=900_000 + i,
            market_id=58_700_000 + (i // 2),
            verdict="winner" if i % 2 == 0 else "loser",
            expected_is_winner=False,
            expected_source=None,
        )
        for i in range(n)
    ]
    return build_plan(legs, context={"owner": "test"})


class _CanaryRow:
    def __init__(self, category, markets):
        self.category = category
        self.markets = markets


class _Res:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Db:
    """A session that models the ROW STATE, not just the rowcounts.

    The existing suite's ``_WriteSession`` hands out a scripted list of
    rowcounts, which cannot express the thing under test here: after a kill, the
    rows this rail already wrote are REALLY there, and the retry's compare-and-set
    has to miss them for the right reason. So this one keeps a dict of
    ``leg_id -> (resolution_source, is_winner)`` and answers every statement from
    it, exactly as Postgres would.
    """

    def __init__(self, *, canaries=None, die_after=None, state=None):
        self.state: dict[int, tuple] = dict(state or {})
        self.canaries = canaries if canaries is not None else {}
        self.die_after = die_after
        self.updates = 0
        self.commits = 0
        self.rollbacks = 0
        self.reverts: list[int] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = dict(params or {})
        if "statement_timeout" in sql:
            return _Res()
        if sql.upper().startswith("SELECT RESOLUTION_SOURCE"):
            row = self.state.get(int(params["leg_id"]))
            return _Res([row] if row else [])
        if "GROUP BY" in sql.upper() and "llm_sport_category" in sql:
            return _Res(
                [_CanaryRow(k, v) for k, v in self.canaries.items() if v]
            )
        if sql.upper().startswith("UPDATE"):
            leg_id = int(params["leg_id"])
            if params.get("src") == WRITE_SOURCE and "prior_src" in params:
                # The compensating revert.
                cur = self.state.get(leg_id)
                if cur and cur[0] == WRITE_SOURCE:
                    self.state[leg_id] = (params["prior_src"], params["prior_wins"])
                    self.reverts.append(leg_id)
                    return _Res(rowcount=1)
                return _Res(rowcount=0)
            # The forward compare-and-set.
            self.updates += 1
            if self.die_after is not None and self.updates > self.die_after:
                raise RuntimeError("SIGKILL: dyno went away mid-apply")
            cur = self.state.get(leg_id)
            if cur is not None and (cur[0] is not None or cur[1] is True):
                return _Res(rowcount=0)
            self.state[leg_id] = (params["src"], params["wins"])
            return _Res(rowcount=1)
        return _Res()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _wire(monkeypatch, *, plan, obligation_store: dict, invalidation=None):
    """Patch the durable edges; keep the row writes real (they are the subject)."""

    async def _load_plan():
        return plan, "ok"

    async def _load_ob():
        rec = obligation_store.get("record")
        return rec, ("ok" if rec is not None else "missing")

    async def _save_ob(rec):
        obligation_store["record"] = rec
        obligation_store.setdefault("saves", []).append(rec)
        return True, "ok"

    async def _inval(_session, _ids):
        return invalidation or {"status": "invalidated"}

    async def _load_progress():
        return None, "missing"

    async def _save_progress(_rec):
        return True, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load_plan)
    monkeypatch.setattr(rail, "_load_obligation", _load_ob)
    monkeypatch.setattr(rail, "_save_obligation", _save_ob)
    monkeypatch.setattr(rail, "_load_progress", _load_progress)
    monkeypatch.setattr(rail, "_save_progress", _save_progress)
    monkeypatch.setattr(
        "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
        _inval,
    )


# ---------------------------------------------------------------------------
# Catch 1 — the halt aborts, and it aborts BEFORE the first row
# ---------------------------------------------------------------------------


class TestTheHaltHalts:
    @pytest.mark.asyncio
    async def test_a_tripped_canary_writes_nothing_at_all(self, monkeypatch):
        """The whole catch, in one assertion: zero UPDATEs, zero commits.

        Before CAL-P076 this same input wrote every approved leg and then
        reported the trip in ``progress.canaries`` on the way out.
        """
        plan = _plan(4)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        db = _Db(canaries={"rodeo": 12})
        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out["halted"] is True
        assert out["wrote"] is False
        assert out["success"] is False
        assert out["refused"] == ["CANARY_NOT_CLEAN"]
        assert db.updates == 0
        assert db.commits == 0
        assert out["canaries_preflight"]["verdict"] == CANARY_TRIPPED
        assert out["canaries_preflight"]["tripped"] == ["rodeo"]

    @pytest.mark.asyncio
    async def test_an_unreadable_canary_panel_also_refuses(self, monkeypatch):
        """``evaluate_canaries``'s own rule, enforced where it costs something:
        "a tripwire that could not be read has NOT been read." An apply is the
        last place an unread tripwire may be attended as a clean one."""
        plan = _plan(2)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        async def _unreadable(_session):
            return evaluate_canaries(None, note="canary_read_failed: TimeoutError")

        monkeypatch.setattr(rail, "_read_canaries", _unreadable)

        db = _Db()
        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out["halted"] is True
        assert out["canaries_preflight"]["verdict"] == CANARY_UNMEASURED
        assert db.updates == 0

    @pytest.mark.asyncio
    async def test_a_clean_panel_lets_the_apply_run(self, monkeypatch):
        """The gate must not be a wall. Non-vacuity for the two tests above."""
        plan = _plan(4)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        db = _Db(canaries={})
        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out["halted"] is False
        assert out["legs_written"] == 4
        assert out["success"] is True
        assert out["canaries_preflight"]["verdict"] == CANARY_CLEAN

    @pytest.mark.asyncio
    async def test_a_trip_during_the_walk_reverts_every_row_it_wrote(
        self, monkeypatch
    ):
        """The population can move DURING the 25 seconds the apply is writing.

        Per-leg commits mean there is no transaction left to abort, so the
        rollback is compensating — and it must restore the plan's OWN recorded
        prior state, not a plausible-looking third value.
        """
        plan = _plan(4)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        panels = [
            evaluate_canaries({}, note="ok"),  # pre-flight: clean
            evaluate_canaries({"rodeo": 3}, note="ok"),  # post-loop: TRIPPED
        ]

        async def _panel(_session):
            # ``progress_read`` reads the panel again on the way out; the last
            # verdict stands rather than raising StopIteration under it.
            return panels.pop(0) if len(panels) > 1 else panels[0]

        monkeypatch.setattr(rail, "_read_canaries", _panel)

        db = _Db()
        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out["halted"] is True
        assert out["success"] is False
        assert out["legs_written"] == 4
        assert out["legs_reverted"] == 4
        assert out["legs_revert_failed"] == 0
        assert sorted(db.reverts) == sorted(plan.leg_ids)
        # Restored to the plan's recorded prior state — NOT to NULL, which the
        # population has never contained (is_winner defaults to False, and
        # CAL-P054 measured zero NULLs in 11,059 outcomes).
        for leg_id in plan.leg_ids:
            assert db.state[leg_id] == (None, False)


# ---------------------------------------------------------------------------
# Catch 2 — kill the apply for real, then resume it
# ---------------------------------------------------------------------------


class TestKillAndResume:
    @pytest.mark.asyncio
    async def test_a_kill_mid_loop_leaves_the_debt_NAMED(self, monkeypatch):
        """The durability property, stated as the thing that can fail.

        Rows are already committed when the process dies. If the obligation is
        written only after the loop, those rows' calibration debt exists in no
        record anywhere — so the intent record is opened BEFORE the first write.
        """
        plan = _plan(4)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        db = _Db(die_after=2)
        with pytest.raises(RuntimeError):
            await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        # Two legs really are on disk...
        written = [k for k, v in db.state.items() if v[0] == WRITE_SOURCE]
        assert len(written) == 2
        # ...and the debt for this plan is open and names it.
        record = store["record"]
        assert record["state"] == "open"
        assert record["plan_hash"] == plan.plan_hash
        assert set(written) <= set(record["leg_ids"])

    @pytest.mark.asyncio
    async def test_the_resume_finishes_the_plan_and_discharges_the_whole_debt(
        self, monkeypatch
    ):
        """Kill, then re-apply the SAME plan_hash against the state the kill left.

        Three properties, each of which was broken before:

        1. the retry is not refused — the open obligation carries the same
           plan_hash, which is the documented "retry the same plan_hash" path;
        2. the two legs the dead run already wrote are recognised as OURS, not
           reported as concurrent drift;
        3. the invalidation covers ALL FOUR legs' markets, not just the two this
           call happened to write.
        """
        plan = _plan(4)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        dead = _Db(die_after=2)
        with pytest.raises(RuntimeError):
            await _apply_reviewed_plan(dead, plan.plan_hash, time.monotonic())

        resumed = _Db(state=dead.state)
        out = await _apply_reviewed_plan(resumed, plan.plan_hash, time.monotonic())

        assert out["legs_written"] == 2
        assert out["legs_already_ours"] == 2
        assert out["legs_drifted"] == 0, (
            "a resumed apply's own prior rows must not be reported as somebody "
            "else's interference"
        )
        assert out["markets_touched"] == 2
        assert out["success"] is True
        assert store["record"]["state"] == "discharged"
        assert all(v[0] == WRITE_SOURCE for v in resumed.state.values())

    @pytest.mark.asyncio
    async def test_a_row_carrying_our_source_with_the_OTHER_verdict_is_drift(
        self, monkeypatch
    ):
        """Ours-versus-drift is decided on BOTH halves.

        A row with this rail's source but the opposite verdict is two plans
        disagreeing about one leg. That is an anomaly, not a resume, and it must
        land in ``legs_drifted`` where a human sees it.
        """
        plan = _plan(2)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        winner_leg = plan.leg_ids[0]
        db = _Db(state={winner_leg: (WRITE_SOURCE, False)})
        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert out["legs_drifted"] == 1
        assert out["legs_already_ours"] == 0

    @pytest.mark.asyncio
    async def test_a_second_kill_still_converges(self, monkeypatch):
        """Resumability is not a one-shot property. Kill twice, finish once."""
        plan = _plan(6)
        store: dict = {}
        _wire(monkeypatch, plan=plan, obligation_store=store)

        first = _Db(die_after=2)
        with pytest.raises(RuntimeError):
            await _apply_reviewed_plan(first, plan.plan_hash, time.monotonic())
        second = _Db(state=first.state, die_after=2)
        with pytest.raises(RuntimeError):
            await _apply_reviewed_plan(second, plan.plan_hash, time.monotonic())
        third = _Db(state=second.state)
        out = await _apply_reviewed_plan(third, plan.plan_hash, time.monotonic())

        assert out["success"] is True
        assert out["legs_already_ours"] + out["legs_written"] == 6
        assert out["legs_drifted"] == 0
        assert store["record"]["state"] == "discharged"


# ---------------------------------------------------------------------------
# The halt is DURABLE — it blocks the NEXT page, in the NEXT process
# ---------------------------------------------------------------------------


class TestTheHaltBlocksTheNextPage:
    """C-APPLY-PRE-1912-R2 re-cert input 1's second half.

    A refusal that lives only in one response stops one call. Every page of this
    wave is a separate HTTP request in a separate process reading a fresh canary
    panel, so page 302 would never learn that page 301 tripped. ~5,661 calls ride
    one authorisation; the halt has to outlive the process that raised it.
    """

    @pytest.mark.asyncio
    async def test_a_raised_halt_refuses_the_dry_run_too(self, monkeypatch):
        """Planning is blocked, not only applying: a plan minted after a trip is
        an appliable artifact describing a population that has moved."""

        async def _halted():
            return {"state": "halted", "reason": "canary_TRIPPED_preflight"}, "halted"

        monkeypatch.setattr(rail, "_wave_halt_state", _halted)
        out = await rail.repair(_Db(), apply=False)
        assert out["halted"] is True
        assert out["refused"] == ["WAVE_HALTED"]
        assert out["wrote"] is False

    @pytest.mark.asyncio
    async def test_an_explicitly_cleared_halt_lets_the_wave_run(self, monkeypatch):
        """Non-vacuity, and it pins the clearing contract: only an explicit
        ``state: cleared`` frees the wave — never time, never a later clean read."""
        from app.utils import durable_state as ds

        cleared = {"schema": rail.WAVE_HALT_SCHEMA, "state": rail.WAVE_HALT_CLEARED}

        class _Read:
            status = "ok"
            ok = True
            envelope = ds.DurableEnvelope(
                identity=rail.WAVE_HALT_IDENTITY,
                schema_version=rail.WAVE_HALT_SCHEMA,
                generation=1,
                generated_at=None,
                payload=cleared,
                checksum="x",
                complete=True,
                source="operator",
            )

        async def _read(identity, **kw):
            return _Read()

        monkeypatch.setattr(
            "app.services.durable_snapshots.read_snapshot_standalone", _read
        )
        state, note = await rail._wave_halt_state()
        assert state is None
        assert "cleared" in note

    @pytest.mark.asyncio
    async def test_an_unreadable_ledger_blocks_the_APPLY_but_not_the_dry_run(
        self, monkeypatch
    ):
        """Unknown is not clear — but it is also not a reason to brick the wave's
        only way of looking at itself. The write refuses; the read does not, and
        SAYS the write will refuse."""

        async def _unknown():
            return {"state": "unknown", "reason": "halt_unreadable: unavailable"}, "unknown"

        monkeypatch.setattr(rail, "_wave_halt_state", _unknown)

        applied = await rail.repair(_Db(), apply=True, plan_hash="whatever")
        assert applied["halted"] is True
        assert applied["refused"] == ["WAVE_HALT_UNREADABLE"]

        seen = {}

        async def _dry(session, limit, started, after_id=None):
            seen["ran"] = True
            return {"mode": "dry_run", "wrote": False}

        monkeypatch.setattr(rail, "_dry_run", _dry)
        planned = await rail.repair(_Db(), apply=False)
        assert seen.get("ran") is True
        assert planned["wave_halt"]["state"] == "unknown"

    @pytest.mark.asyncio
    async def test_a_missing_ledger_is_the_normal_clear_state(self, monkeypatch):
        """An absence with a known meaning, distinguished from an unreadable
        answer — the distinction the whole rail keeps re-teaching."""

        class _Missing:
            status = "missing"
            ok = False
            envelope = None

        async def _read(identity, **kw):
            return _Missing()

        monkeypatch.setattr(
            "app.services.durable_snapshots.read_snapshot_standalone", _read
        )
        state, note = await rail._wave_halt_state()
        assert state is None
        assert note == "no halt recorded"


# ---------------------------------------------------------------------------
# Progress durability is PROVED, not acknowledged
# ---------------------------------------------------------------------------


class TestProgressAfterRead:
    """C-APPLY-PRE-1912-R2 P1 #2, with its own specimen.

    ``_save_progress`` treated the publisher's ``ok``/``superseded`` as proof.
    Codex's no-op publisher — stores nothing, answers ``superseded`` — produced
    two consecutive responses both claiming ``durable: true`` / ``calls: 1`` /
    "READABLE … by any operator in any session", over an identity holding
    nothing. That is the acknowledgement-not-proof class already removed from the
    calibration invalidation.
    """

    @pytest.mark.asyncio
    async def test_a_no_op_publisher_can_no_longer_report_durable(self, monkeypatch):
        async def _publish(_env):
            return {"status": "superseded"}  # acknowledged, stored nothing

        async def _load():
            return None, "missing"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await rail._save_progress(
            {"schema": rail.WAVE_PROGRESS_SCHEMA, "calls": 1}
        )
        assert ok is False
        assert "not readable after write" in note

    @pytest.mark.asyncio
    async def test_a_losing_concurrent_write_is_caught_by_the_counter(
        self, monkeypatch
    ):
        """``superseded`` passes only when the WINNING record subsumes this fold."""

        async def _publish(_env):
            return {"status": "superseded"}

        async def _load():
            return {"schema": rail.WAVE_PROGRESS_SCHEMA, "calls": 4}, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, _ = await rail._save_progress(
            {"schema": rail.WAVE_PROGRESS_SCHEMA, "calls": 9}
        )
        assert ok is False
        # A concurrent writer AHEAD of us saw our fold or a later one: that is fine.
        ok2, note2 = await rail._save_progress(
            {"schema": rail.WAVE_PROGRESS_SCHEMA, "calls": 3}
        )
        assert ok2 is True and "after-read proved" in note2

    @pytest.mark.asyncio
    async def test_an_honest_publisher_still_reports_durable(self, monkeypatch):
        """Non-vacuity: the discipline must not make every write read as lost."""
        store: dict = {}

        async def _publish(env):
            store["record"] = env.payload
            return {"status": "ok"}

        async def _load():
            return store.get("record"), ("ok" if store.get("record") else "missing")

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await rail._save_progress(
            {"schema": rail.WAVE_PROGRESS_SCHEMA, "calls": 1}
        )
        assert ok is True and note == "ok (after-read proved)"
