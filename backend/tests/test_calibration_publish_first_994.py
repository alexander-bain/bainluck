"""CAL-P994 / D45(A) — the curve publishes BEFORE the rebuild, not after it.

The measured problem (calibration-029, 2026-09-03, over the 168-beat ring):

    published beats, elapsed_ms      median 1,267,836   (~21 min)
    a beat that banked zero units      360,857 ms       (~6 min)
    mid-unit deaths                    23, of which 21 had a Heroku release
                                       inside the beat's own window

Every merge to master cycles ``worker-heavy``. The beat spent ~87% of its window
on the rolling restage BEFORE it published, so a restart anywhere in those 21
minutes cost the publish — and the census being rebuilt is not the one that
publishes anyway (``collect_unit_results`` prefers the SERVED bank). D45 was
ruled A: a narrow ruling-009 exception for the publish ordering only. Publish
from the served bank first; rebuild with whatever window is left.

**What this file is careful about.** The reorder is easy to fake three ways, and
each has its own arm here:

* by never rebuilding at all (that is option B, which Alex has NOT ruled) —
  :class:`TestTheRebuildIsStillFunded`;
* by deferring when there is nothing to publish from, which takes the curve dark
  — :class:`TestTheControlsThatMustNotDefer`;
* by turning a killed rebuild back into a killed beat, which would leave the
  freeze score exactly where it was — :class:`TestAKilledRebuildIsNotAKilledBeat`.

Every test executes the real coroutine. None asserts on the text of anything
except the fingerprint guard at the bottom, which is a claim ABOUT source by
construction.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.utils.calibration_staged_futures import (
    decode_staged_cursor_detailed,
    new_staged_cursor,
    stamp_served_at,
)

VERSION = "q994"
INPUT_FP = "fp-994"
OWNER = "owner-994"


# =============================================================================
# The harness — the same shape CAL-P078's uses, because it drives the same loop
# =============================================================================


def _population_row(*, bucket_idx, n=3, winners=1):
    """One bucket row shaped like the population statement's output.

    DECLARED columns only: the fold refuses a column whose kind it was not told
    (``UndeclaredColumnError``). Same shape CAL-P078's harness uses, because it
    is the same fold.
    """
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source="kalshi",
        category="sports",
        price_moved=False,
        is_nonexclusive_bundle=False,
        n=n,
        winners=winners,
        sum_prob=1.5,
        sum_sq_err=0.25,
        avg_prob=0.5,
        published_questions=n,
        representative_tie_broken=0,
    )


def _roster(n):
    return [
        SimpleNamespace(market_id=i, vm_id=f"vm-{i}", is_grouped=False)
        for i in range(1, n + 1)
    ]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Answers the two statements the loop issues, and counts the unit reads."""

    def __init__(self, roster, *, unit_n=3):
        self.roster = roster
        self.unit_n = unit_n
        self.unit_reads = 0
        self.unit_reads_before_publish = 0

    async def execute(self, statement, params=None):
        if params is None:
            return _FakeResult(self.roster)
        self.unit_reads += 1
        return _FakeResult([_population_row(bucket_idx=1, n=self.unit_n, winners=1)])


class _FakeLedger:
    def __init__(self, window_ms):
        self.window_ms = window_ms
        self.stages: dict[str, int] = {}
        self.gauges: dict[str, int] = {}

    def record_stage(self, name, duration_ms=0):
        self.stages[name] = self.stages.get(name, 0) + int(duration_ms)

    def record_gauge(self, name, value):
        self.gauges[name] = int(value)

    def remaining_ms(self, *, elapsed_ms=0):
        return max(0, self.window_ms - elapsed_ms)


class _FakeStage:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeRunner:
    """The PhaseRunner surface the loop and the deferred rebuild actually touch."""

    def __init__(self, *, window_ms, generation=1):
        self.ledger = _FakeLedger(window_ms)
        self.population_version = VERSION
        self.fingerprint = INPUT_FP
        self.owner = OWNER
        self.generation = generation
        self._elapsed = 0
        self.rebuild_deferred = False
        self.outcome = {"published": False}
        self.tagged = 0

    def defer_rebuild(self):
        self.rebuild_deferred = True

    def stage(self, _name):
        self._elapsed += 100
        return _FakeStage()

    def elapsed_ms(self):
        return self._elapsed

    async def commit(self, _db):
        return None

    async def apply_statement_timeout(self, _db, _phase):
        return None

    def measured_unit_ms(self, _phase):
        return None

    async def apply_unit_statement_timeout(self, _db, _phase, *, unit_ms=None, deferred_rebuild=False):
        return None

    async def tag_session(self, _db):
        self.tagged += 1
        return {}

    async def tag_rebuild_session(self, _db):
        self.rebuild_tagged = getattr(self, "rebuild_tagged", 0) + 1
        return {}


@pytest.fixture
def wiring(monkeypatch):
    """The real loop over an in-memory cursor store. Nothing about the loop, the
    cursor codec, the promotion or the fold is stubbed — only the durable read
    and write, which are I/O."""
    from app.tasks import calibration_main_build as mb
    from app.tasks import precompute_calibration as pc

    store: dict[str, object] = {"cursor": None}

    async def fake_load(**kwargs):
        from app.utils.calibration_phase_ledger import FRESH

        raw = store["cursor"]
        if raw is None:
            return (
                new_staged_cursor(
                    population_version=kwargs["population_version"],
                    input_fingerprint=kwargs["input_fingerprint"],
                    generation_fingerprint=kwargs["generation_fingerprint"],
                    owner=kwargs["owner"],
                    generation=kwargs["generation"],
                ),
                FRESH,
                "absent",
            )
        return decode_staged_cursor_detailed(
            raw,
            expected_population_version=kwargs["population_version"],
            expected_input_fingerprint=kwargs["input_fingerprint"],
            expected_generation_fingerprint=kwargs["generation_fingerprint"],
            owner=kwargs["owner"],
            generation=kwargs["generation"],
            now=0.0,
        )

    async def fake_save(cursor, *, terminal):
        store["cursor"] = stamp_served_at(cursor, now=1_700_000_000.0).as_payload()
        return True

    monkeypatch.setattr(mb, "load_staged_cursor", fake_load)
    monkeypatch.setattr(mb, "save_staged_cursor", fake_save)
    monkeypatch.setattr(mb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    return pc, store


async def _publish_pass(pc, *, roster, window_ms, unit_n=3, db=None, runner=None):
    db = db or _FakeDB(roster, unit_n=unit_n)
    runner = runner or _FakeRunner(window_ms=window_ms)
    merged = await pc._run_staged_futures(db, runner, lambda frozen: "SELECT 2")
    db.unit_reads_before_publish = db.unit_reads
    return merged, runner, db


async def _rebuild_pass(pc, db, runner):
    return await pc._run_staged_futures(
        db, runner, lambda frozen: "SELECT 2", rebuild_only=True
    )


async def _serving_state(pc, roster):
    """Drive real beats until a census is complete and promoted to SERVED.

    Returns nothing: the fixture's cursor store carries the state. This is the
    precondition every deferral test needs, and it is produced by running the
    build rather than by hand-writing a cursor — a hand-written one could
    satisfy ``served_covers`` in a way the producer never actually reaches.
    """
    for _ in range(40):
        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=10_000_000)
        if runner.rebuild_deferred:
            return
        if merged is not None:
            # The census completed and promoted inside this beat's own loop.
            # One more beat is what turns that into "a complete SERVED bank was
            # already there when the beat started".
            continue
    raise AssertionError("never reached a serving bank — the harness is wrong")


# =============================================================================
# The reorder
# =============================================================================


class TestTheCurvePublishesFirst:
    @pytest.mark.asyncio
    async def test_a_complete_served_bank_publishes_without_running_the_loop(self, wiring):
        """THE SHIP. Before D45(A) this pass ran the whole unit loop and only
        then folded the served bank — ~21 minutes of exposure buying a census
        that was not the one about to publish."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=10_000_000)

        assert merged is not None, "the served bank must still publish"
        assert db.unit_reads == 0, (
            "the publish pass ran the unit loop — the exposure this queue "
            "removes is still there"
        )
        assert runner.rebuild_deferred is True

    @pytest.mark.asyncio
    async def test_the_publish_pass_leaves_the_window_it_did_not_spend(self, wiring):
        """Not merely "it skipped the loop" — it must skip it CHEAPLY. A pass
        that consumed the window some other way would publish just as early and
        leave the rebuild nothing, which is option B by accident."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        window = 10_000_000
        merged, runner, _db = await _publish_pass(pc, roster=roster, window_ms=window)

        assert merged is not None
        left = runner.ledger.remaining_ms(elapsed_ms=runner.elapsed_ms())
        assert left > window * 0.9, (
            f"the publish pass burned {window - left} ms of a {window} ms window "
            "without running a unit"
        )

    @pytest.mark.asyncio
    async def test_the_deferral_is_recorded_and_the_projection_is_not_faked(self, wiring):
        """An absent stage reads as "fine" (gotcha #53), and a convergence
        projection built from a loop that did not run would report the reorder
        as a build that has stopped converging."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        _merged, runner, _db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )

        assert "staged:rebuild_deferred" in runner.ledger.stages
        assert runner.ledger.gauges.get("staged:projection_deferred") == 1
        assert "staged:units_this_beat" not in runner.ledger.stages, (
            "the publish pass claimed a units-this-beat number for a loop it "
            "never ran"
        )


class TestTheRebuildIsStillFunded:
    """D45(A), not D45(B). The rebuild moves; it is not defunded."""

    @pytest.mark.asyncio
    async def test_the_rebuild_pass_banks_units(self, wiring):
        pc, store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        # A window that admits some units but not the whole plan, so the bank
        # being built is still visible afterwards. On an unbounded window the
        # rebuild finishes and ``promote_if_complete`` empties ``committed_units``
        # into the serving slot — which is the right behaviour and the wrong
        # instrument for "did it bank anything".
        _merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=1300)
        assert db.unit_reads == 0
        banked_before = len(store["cursor"]["committed_units"])

        await _rebuild_pass(pc, db, runner)

        assert db.unit_reads > 0, "the deferred rebuild never ran — that is option B"
        assert len(store["cursor"]["committed_units"]) > banked_before

    @pytest.mark.asyncio
    async def test_the_rebuild_pass_finalizes_nothing(self, wiring):
        """Its product is banked units, not a payload. Returning a fold here
        would invite a caller to publish a second time in one beat."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        _merged, runner, db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )
        result = await _rebuild_pass(pc, db, runner)

        assert result is None
        assert runner.ledger.gauges.get("staged:rebuild_units_this_beat") == db.unit_reads

    @pytest.mark.asyncio
    async def test_the_rebuild_pass_records_the_real_projection(self, wiring):
        """The projection the publish pass declined to fake is owed, and the
        pass that ran real units is the one that pays it."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        _merged, runner, db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )
        await _rebuild_pass(pc, db, runner)

        assert runner.ledger.stages.get("staged:units_this_beat", 0) > 0

    @pytest.mark.asyncio
    async def test_the_rebuild_pass_never_defers_itself(self, wiring):
        """A pass that deferred again would run the loop nowhere, forever."""
        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        _merged, runner, db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )
        runner.rebuild_deferred = False
        await _rebuild_pass(pc, db, runner)

        assert runner.rebuild_deferred is False
        assert db.unit_reads > 0


class TestTheControlsThatMustNotDefer:
    """Both arms green under the control, or the predicate is not the subject."""

    @pytest.mark.asyncio
    async def test_a_cold_cursor_rebuilds_inline_exactly_as_before(self, wiring):
        """There is nothing to publish from, so deferring would take the curve
        dark. This is the pre-994 path and it must be untouched."""
        pc, _store = wiring
        roster = _roster(60)

        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=10_000_000)

        assert runner.rebuild_deferred is False
        assert db.unit_reads > 0, "a cold beat must run its loop inline"
        assert merged is not None, "and it publishes the census it just completed"

    @pytest.mark.asyncio
    async def test_a_partial_cold_beat_still_publishes_nothing(self, wiring):
        """Partial is still not done. The reorder must not have turned an
        incomplete first census into a publishable one."""
        pc, _store = wiring
        roster = _roster(60)

        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=450)

        assert runner.rebuild_deferred is False
        assert 0 < db.unit_reads < len(roster)
        assert merged is None

    @pytest.mark.asyncio
    async def test_a_complete_building_bank_is_not_deferred(self, wiring, monkeypatch):
        """The predicate's SECOND clause, and the only branch here that needs a
        hand to reach.

        When the bank being BUILT already covers the plan, ``collect_unit_results``
        prefers it over the served one — the freshness rule, "a census finished
        this beat beats the census finished five beats ago". Deferring in that
        state would cost a roster read and hand readers the OLDER census for
        nothing.

        In the production path the state is transient: ``retain_planned_units``
        promotes a complete building bank at the top of the beat and ``advance``
        promotes on the last unit, so ``covers`` is almost never still true when
        the predicate is read. Almost is not never, and a defensive clause with
        no arm is a clause nobody can tell is working — so the promotion is
        suppressed for one call to hold the state still. Nothing else is stubbed:
        the cursor, the predicate and the fold are all real.
        """
        import app.utils.calibration_staged_futures as sf

        pc, _store = wiring
        roster = _roster(60)
        await _serving_state(pc, roster)

        real_retain = sf.retain_planned_units

        def retain_without_promoting(cursor, chunks):
            kept, dropped = real_retain(cursor, chunks)
            # Both banks now cover the plan, which is exactly the state the
            # promotion would otherwise have collapsed a moment ago.
            return replace(kept, committed_units=tuple(kept.served_units)), dropped

        monkeypatch.setattr(sf, "retain_planned_units", retain_without_promoting)

        merged, runner, db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )

        assert runner.rebuild_deferred is False, (
            "deferred while holding a census finished this beat — the older one "
            "would have gone out"
        )
        assert merged is not None
        assert db.unit_reads == 0, "every unit was already banked; none may re-run"

    @pytest.mark.asyncio
    async def test_an_empty_population_is_not_deferred(self, wiring):
        """An empty roster is complete by definition and publishes ``[]``. It
        has no served bank and no units, so there is nothing to reorder."""
        pc, _store = wiring

        merged, runner, db = await _publish_pass(pc, roster=[], window_ms=10_000_000)

        assert merged == []
        assert db.unit_reads == 0
        assert runner.rebuild_deferred is False


# =============================================================================
# The orchestrator half — WHEN the deferred rebuild runs, and what a kill costs
# =============================================================================


class _Recorder:
    """Stands in for the rebuild pass and photographs the beat's state at the
    moment it is entered. This is how "after the publish" is proved: not by
    reading the source order, but by asking the publish's own outcome."""

    def __init__(self):
        self.calls = []

    async def __call__(self, db, runner, sql_builder, *, rebuild_only=False):
        self.calls.append(
            {
                "rebuild_only": rebuild_only,
                "published": runner.outcome.get("published"),
                "durable": runner.outcome.get("durable"),
                "gate": runner.outcome.get("gate"),
            }
        )
        return None


@pytest.fixture
def orchestrator(monkeypatch):
    """Drive the REAL ``_run_calibration_main_build`` over stubbed I/O.

    Everything stubbed here is a boundary — a session, Redis, the durable store,
    the gate's verdict. The ordering under test is the function's own.
    """
    import app.services.durable_snapshots as ds
    import app.tasks.base as base
    import app.tasks.redis_state as rs
    import app.tasks.task_checkpoint as tc
    import app.utils.calibration_publish_gate as gate
    import app.utils.durable_state as dstate
    from app.tasks import precompute_calibration as pc

    sessions = {"opened": 0}

    class _Session:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, params=None):
            self.statements.append(str(statement))
            return _FakeResult([])

        async def commit(self):
            return None

    class _SessionCtx:
        async def __aenter__(self):
            sessions["opened"] += 1
            return _Session()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(base, "get_task_session", lambda: _SessionCtx())
    monkeypatch.setattr(tc, "try_acquire_overlap_lock", _async_true)
    monkeypatch.setattr(tc, "release_overlap_lock", _async_none)
    monkeypatch.setattr(rs, "get_redis_client", lambda: object())

    async def fake_compute(db, runner=None):
        return {
            "buckets": [{"bucket_idx": 1, "n": 10}],
            "total_outcomes": 10,
            "generated_at": "2026-09-03T12:00:00+00:00",
        }

    monkeypatch.setattr(pc, "compute_calibration_payload", fake_compute)
    monkeypatch.setattr(pc, "_read_published_baseline", lambda rc: None)
    monkeypatch.setattr(pc, "_publish_calibration_main", lambda rc, j: {"main": "ok"})

    verdict = SimpleNamespace(
        ok=True,
        first_publish=True,
        version_bumped=False,
        codes=[],
        fingerprint="fp",
        candidate={},
        published={},
        baseline_source="cold_start",
        baseline_probe={},
        observation_codes=[],
        observations=[],
        summary=lambda: "ok",
    )
    monkeypatch.setattr(gate, "evaluate_publish", lambda response, baseline: verdict)
    monkeypatch.setattr(gate, "gate_ledger_record", lambda v: {})
    monkeypatch.setattr(gate, "_parse_generated_at", lambda s: None)
    monkeypatch.setattr(
        dstate,
        "DurableEnvelope",
        SimpleNamespace(build=lambda **kw: SimpleNamespace(generation=1)),
    )

    async def fake_publish(envelope):
        return {"status": "ok"}

    monkeypatch.setattr(ds, "publish_snapshot_standalone", fake_publish)
    return pc, sessions


async def _async_true(*a, **k):
    return True


async def _async_false(*a, **k):
    return False


async def _async_none(*a, **k):
    return None


class TestTheRebuildRunsAfterThePublish:
    @pytest.mark.asyncio
    async def test_the_deferred_rebuild_sees_a_published_curve(
        self, orchestrator, monkeypatch
    ):
        """The ordering claim, executed. If the rebuild ran before the publish,
        ``published`` would be False at the moment it was entered — which is
        exactly the state every pre-994 beat was killed in."""
        pc, _sessions = orchestrator
        recorder = _Recorder()
        monkeypatch.setattr(pc, "_run_staged_futures", recorder)

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        summary = await pc._run_calibration_main_build(runner)

        assert summary["status"] == "ok"
        assert summary["deferred_rebuild"]["status"] == "ran"
        assert [c["rebuild_only"] for c in recorder.calls] == [True]
        assert recorder.calls[0]["published"] is True, (
            "the rebuild ran before the curve was durable — the reorder is "
            "upside down"
        )
        assert recorder.calls[0]["durable"] == "ok"

    @pytest.mark.asyncio
    async def test_a_beat_that_did_not_defer_opens_no_second_session(
        self, orchestrator, monkeypatch
    ):
        """"The rebuild banked nothing" and "there was no deferral" are
        different facts about a beat, and only one of them costs a session."""
        pc, sessions = orchestrator
        recorder = _Recorder()
        monkeypatch.setattr(pc, "_run_staged_futures", recorder)

        runner = _FakeRunner(window_ms=10_000_000)
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        summary = await pc._run_calibration_main_build(runner)

        assert summary["deferred_rebuild"] == {"status": "not_deferred"}
        assert recorder.calls == []
        assert sessions["opened"] == 1, "a non-deferring beat opened a rebuild session"


class TestAKilledRebuildIsNotAKilledBeat:
    """The crux. Before this queue a ``worker-heavy`` restart during the loop
    published nothing and scored a freeze-score miss; now it costs the rebuild
    and nothing else."""

    @pytest.mark.asyncio
    async def test_a_cancelled_rebuild_is_swallowed_and_named(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=asyncio.CancelledError())

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result["status"] == "interrupted"
        assert "staged:rebuild_stop:interrupted" in runner.ledger.stages
        assert runner.ledger.gauges.get("staged:rebuild_interrupted") == 1

    @pytest.mark.asyncio
    async def test_the_beat_that_lost_its_rebuild_still_terminates_complete(self):
        """The freeze score reads ``terminal``/``published``/``gate``. Asserted
        against the REAL ``terminal_for`` with the arguments the orchestrator
        passes, so this cannot drift from the producer."""
        from app.utils.calibration_phase_ledger import terminal_for

        assert (
            terminal_for(
                all_required_done=True, published=True, error=False, cancelled=False
            )
            == "complete"
        )
        # And the shape it USED to have, kept beside it so the difference is
        # legible rather than asserted about in prose.
        assert (
            terminal_for(
                all_required_done=False, published=False, error=False, cancelled=True
            )
            == "cancelled"
        )

    @pytest.mark.asyncio
    async def test_a_rebuild_that_raises_does_not_fail_the_beat(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=RuntimeError("boom"))

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result["status"] == "error"
        assert "staged:rebuild_stop:error" in runner.ledger.stages

    @pytest.mark.asyncio
    async def test_it_stands_down_when_another_run_holds_the_lock(self, monkeypatch):
        """Single writer. The next beat starting while this one rebuilds must
        not produce two writers advancing one cursor."""
        import app.tasks.task_checkpoint as tc
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=None)
        monkeypatch.setattr(tc, "try_acquire_overlap_lock", _async_false)

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result == {"status": "overlap_lock_not_acquired"}
        assert "staged:rebuild_stop:overlap_lock" in runner.ledger.stages

    @pytest.mark.asyncio
    async def test_no_window_left_is_recorded_rather_than_silent(self, monkeypatch):
        """A beat that never rebuilds is a stalled census wearing a green
        terminal, and it must be findable."""
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=None)

        runner = _FakeRunner(window_ms=0)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result["status"] == "no_window"
        assert "staged:rebuild_stop:no_window_after_publish" in runner.ledger.stages

    @pytest.mark.asyncio
    async def test_a_beat_that_never_deferred_runs_no_rebuild(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        calls = await _install_rebuild_session(monkeypatch, raises=None)

        runner = _FakeRunner(window_ms=10_000_000)

        assert await pc._run_deferred_rebuild(runner) == {"status": "not_deferred"}
        assert calls["n"] == 0


async def _install_rebuild_session(monkeypatch, *, raises):
    """Stub the rebuild pass's boundaries and report how often it was called."""
    import app.tasks.base as base
    import app.tasks.task_checkpoint as tc
    from app.tasks import precompute_calibration as pc

    calls = {"n": 0, "released": 0}

    class _Session:
        async def execute(self, statement, params=None):
            return _FakeResult([])

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *exc):
            return False

    async def fake_release(*a, **k):
        calls["released"] += 1

    monkeypatch.setattr(base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(tc, "try_acquire_overlap_lock", _async_true)
    monkeypatch.setattr(tc, "release_overlap_lock", fake_release)

    async def fake_loop(db, runner, sql_builder, *, rebuild_only=False):
        calls["n"] += 1
        if raises is not None:
            raise raises
        return None

    monkeypatch.setattr(pc, "_run_staged_futures", fake_loop)
    return calls


class TestTheLockIsAlwaysReleased:
    @pytest.mark.asyncio
    async def test_a_cancelled_rebuild_still_releases_the_overlap_lock(self, monkeypatch):
        """A lock held past a cancellation would block every later beat. The
        session dies with the process either way, but the ``finally`` is what
        makes that not the only thing standing between here and a wedge."""
        from app.tasks import precompute_calibration as pc

        calls = await _install_rebuild_session(
            monkeypatch, raises=asyncio.CancelledError()
        )

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()
        await pc._run_deferred_rebuild(runner)

        assert calls["released"] == 1


# =============================================================================
# CERT-821's repair — a REFUSAL is the other exit, and it funds the rebuild too
# =============================================================================


def _total_n(merged) -> int:
    """The population the fold is about to publish, summed over its rows.

    The census identity this file needs is not the unit keys — those are the
    plan, and the plan does not move between the beats under test. It is what
    the units COUNTED.
    """
    rows = list(merged or [])
    return sum(int(row["n"] if isinstance(row, dict) else row.n) for row in rows)


def _refuse_the_gate(monkeypatch, *, codes=("population_shrink",)):
    """Make the publish gate reject, and keep the filing off the network.

    The refusal this models is the ordinary one the module was built to expect:
    a candidate the gate judges wrong, filed and refused, prior snapshot left
    serving. Nothing here is an exotic failure.
    """
    import app.utils.calibration_publish_gate as gate
    from app.tasks import precompute_calibration as pc

    verdict = SimpleNamespace(
        ok=False,
        first_publish=False,
        version_bumped=False,
        codes=list(codes),
        fingerprint="fp-refused",
        candidate={"population": 700_000},
        published={"population": 930_149},
        baseline_source="found",
        baseline_probe={},
        observation_codes=[],
        observations=[],
        summary=lambda: "population fell 24.7% against a 5% limit",
    )
    monkeypatch.setattr(gate, "evaluate_publish", lambda response, baseline: verdict)
    monkeypatch.setattr(
        pc, "_file_publish_gate_rejection", lambda v: {"action": "commented"}
    )
    return verdict


class TestAGateRefusalStillFundsTheRebuild:
    """CERT-821, repaired.

    The reorder shipped with ONE discharge, after ``runner.complete``. A
    publish-gate refusal raises before that line, and on a deferred beat the
    unit loop had not run yet — so the beat that was refused banked nothing, the
    served bank it would have replaced stayed exactly as it was, and the next
    beat rebuilt the same candidate and earned the same refusal. Refuse ->
    rebuild nothing -> same bank -> refuse, with readers pinned to the old curve
    for as long as the cause held.

    What must be true now, and each of these is an arm below: the rebuild runs
    on the refusal path, the refusal is still the terminal, nothing is
    published, a non-deferring beat still costs nothing, and — the one that
    proves the fixed point is actually broken — the NEXT beat judges a bank this
    one advanced.
    """

    @pytest.mark.asyncio
    async def test_a_refused_beat_runs_the_rebuild_and_still_raises(
        self, orchestrator, monkeypatch
    ):
        pc, _sessions = orchestrator
        _refuse_the_gate(monkeypatch)
        recorder = _Recorder()
        monkeypatch.setattr(pc, "_run_staged_futures", recorder)

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        with pytest.raises(RuntimeError, match="publish gate rejected"):
            await pc._run_calibration_main_build(runner)

        assert [c["rebuild_only"] for c in recorder.calls] == [True], (
            "the gate refused and the deferred rebuild never ran — the beat is "
            "back in the CERT-821 fixed point"
        )
        assert recorder.calls[0]["gate"] == "refuse"
        assert runner.outcome["deferred_rebuild"]["status"] == "ran"

    @pytest.mark.asyncio
    async def test_the_refusal_publishes_nothing_and_keeps_the_prior_snapshot(
        self, orchestrator, monkeypatch
    ):
        """The repair must not buy the rebuild with the thing refusal protects."""
        import app.services.durable_snapshots as ds

        pc, _sessions = orchestrator
        _refuse_the_gate(monkeypatch)
        monkeypatch.setattr(pc, "_run_staged_futures", _Recorder())

        writes = {"durable": 0, "redis": 0}

        async def counting_durable(envelope):
            writes["durable"] += 1
            return {"status": "ok"}

        monkeypatch.setattr(ds, "publish_snapshot_standalone", counting_durable)
        monkeypatch.setattr(
            pc,
            "_publish_calibration_main",
            lambda rc, j: writes.__setitem__("redis", writes["redis"] + 1) or {},
        )

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        with pytest.raises(RuntimeError):
            await pc._run_calibration_main_build(runner)

        assert writes == {"durable": 0, "redis": 0}
        assert runner.outcome["published"] is False

    @pytest.mark.asyncio
    async def test_a_refused_beat_that_never_deferred_opens_no_second_session(
        self, orchestrator, monkeypatch
    ):
        """The control, and it is GREEN on both arms by construction — it says
        what must not change, so a version of this file that only ever went red
        on the unrepaired code would not contain it.

        Refusal is common; the rebuild is not free (a session, an engine setup
        and a roster read of ~33 s). Only a beat that DEFERRED is owed one, and
        this is what fails if the repair discharges blindly.
        """
        pc, sessions = orchestrator
        _refuse_the_gate(monkeypatch)
        recorder = _Recorder()
        monkeypatch.setattr(pc, "_run_staged_futures", recorder)

        runner = _FakeRunner(window_ms=10_000_000)
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        with pytest.raises(RuntimeError, match="publish gate rejected"):
            await pc._run_calibration_main_build(runner)

        assert recorder.calls == []
        assert sessions["opened"] == 1
        assert runner.outcome.get("deferred_rebuild") in (
            None,  # the unrepaired shape: nothing was asked
            {"status": "not_deferred"},
        )

    @pytest.mark.asyncio
    async def test_the_refused_beat_advances_the_bank_the_next_beat_judges(
        self, wiring, orchestrator, monkeypatch
    ):
        """THE sequence, end to end, with nothing about the loop stubbed:

        complete served bank + partial building bank -> the gate refuses ->
        the rebuild-only pass advances the staged cursor -> the refusal still
        propagates -> the NEXT beat publishes a census only the refused beat
        could have produced.

        The last line is the one that needs an instrument, because the unit KEYS
        do not move — the plan is the same plan. What moves is the census
        inside the bank, so the refused beat's units are read at a population
        size no earlier beat ever saw (``unit_n``), and the next beat is asked
        what it is about to publish. Before the repair it published the old
        number, every hour, forever.
        """
        import app.tasks.base as base

        pc, store = wiring
        _refuse_the_gate(monkeypatch)

        roster = _roster(4)
        await _serving_state(pc, roster)
        assert store["cursor"]["served_units"], (
            "the harness never reached a complete served bank"
        )
        assert not store["cursor"]["committed_units"], (
            "the building bank is not empty — this is not the deferring shape "
            "CERT-821 is about"
        )

        # What the fixed point would keep serving: the bank as it stands now.
        stale, stale_runner, _db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )
        assert stale_runner.rebuild_deferred is True
        stale_n = _total_n(stale)

        db = _FakeDB(roster, unit_n=7)

        class _Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(base, "get_task_session", lambda: _Ctx())

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()
        runner.begin = lambda phase: None
        runner.complete = lambda phase, committed=True: 0

        with pytest.raises(RuntimeError, match="publish gate rejected"):
            await pc._run_calibration_main_build(runner)

        assert db.unit_reads > 0, "the refused beat banked no units"

        merged, _next_runner, _db = await _publish_pass(
            pc, roster=roster, window_ms=10_000_000
        )
        assert merged is not None, "the next beat had nothing complete to publish"
        assert _total_n(merged) != stale_n, (
            "the next beat published the same census the gate just refused — "
            "the CERT-821 fixed point survived the repair"
        )
        assert _total_n(merged) == stale_n // 3 * 7, (
            "the next beat's census is not the one the refused beat's rebuild "
            "banked"
        )


class TestASoftKilledRebuildIsAnInterruption:
    """CERT-821's named follow-up, ``CAL-P994-SOFT-TIME-LIMIT-CLASSIFICATION``.

    ``staged:rebuild_error`` and ``staged:rebuild_interrupted`` answer different
    operator questions — "is the unit loop broken?" and "is the deploy cadence
    eating the rebuild?". Celery's ``SoftTimeLimitExceeded`` is a plain
    ``Exception``, so every soft kill was answering the first one, which is the
    one this queue's evidence is about.
    """

    @pytest.mark.asyncio
    async def test_a_soft_time_limit_is_interrupted_not_error(self, monkeypatch):
        from celery.exceptions import SoftTimeLimitExceeded

        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=SoftTimeLimitExceeded())

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result["status"] == "interrupted"
        assert runner.ledger.gauges.get("staged:rebuild_interrupted") == 1
        assert "staged:rebuild_error" not in runner.ledger.gauges

    @pytest.mark.asyncio
    async def test_an_ordinary_failure_is_still_an_error(self, monkeypatch):
        """The other arm: widening the predicate must not swallow real breakage
        into the deploy-cadence bucket."""
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=ValueError("bad row"))

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        result = await pc._run_deferred_rebuild(runner)

        assert result["status"] == "error"
        assert runner.ledger.gauges.get("staged:rebuild_error") == 1
        assert "staged:rebuild_interrupted" not in runner.ledger.gauges

    @pytest.mark.asyncio
    async def test_a_shutdown_is_not_the_rebuilds_to_swallow(self, monkeypatch):
        """``KeyboardInterrupt``/``SystemExit`` are not the runtime reclaiming a
        worker mid-task; nothing about a census is worth holding a shutdown."""
        from app.tasks import precompute_calibration as pc

        await _install_rebuild_session(monkeypatch, raises=KeyboardInterrupt())

        runner = _FakeRunner(window_ms=10_000_000)
        runner.defer_rebuild()

        with pytest.raises(KeyboardInterrupt):
            await pc._run_deferred_rebuild(runner)


# =============================================================================
# The bank must survive this queue
# =============================================================================


class TestTheUnitBoundSurvivesTheReorder:
    """The hazard the reorder creates, and the only part of it that is not
    ordering.

    Moving the loop out of the ``futures`` phase makes that phase cheap — a
    roster read and a fold, ~35 s — and ``derive_plan`` budgets a phase from its
    own observed completions. Within about ten beats the futures budget would
    converge on ~50 s while a unit costs 70 s mean / 277 s worst (measured
    2026-09-03), and ``min(phase_bound, unit_bound)`` would cancel every unit at
    a bound belonging to work it no longer contains. The rebuild would stop dead
    a week after the reorder shipped, and quietly: a unit cancelled at its own
    bound is a known outcome the loop skips past.
    """

    @staticmethod
    def _ledger_with_a_collapsed_futures_budget():
        """A REAL ledger and a REAL plan, with one number moved: the futures
        phase's statement bound, set to what a fold-only phase would earn."""
        from dataclasses import replace as _replace

        from app.utils.calibration_phase_ledger import (
            PHASE_FUTURES,
            PhaseLedger,
            derive_plan,
        )

        plan = _replace(derive_plan({}), soft_limit_ms=1_380_000, cleanup_margin_ms=0)
        ledger = PhaseLedger(
            plan=plan,
            population_version=VERSION,
            owner=OWNER,
            generation=1,
            input_fingerprint=INPUT_FP,
        )
        ledger.records[PHASE_FUTURES].statement_timeout_ms = 50_000
        return ledger, PHASE_FUTURES

    def test_the_collapsed_budget_would_cancel_a_measured_unit(self):
        """The hazard is REAL, asserted before the fix is asserted against it —
        otherwise the arm below proves only that a flag exists."""
        ledger, phase = self._ledger_with_a_collapsed_futures_budget()

        bound = ledger.statement_timeout_for_unit(
            phase, elapsed_ms=400_000, unit_ms=70_474
        )

        assert bound <= 50_000, (
            "the phase budget is no longer the binding term — this test has "
            "stopped describing the hazard it guards"
        )
        assert bound < 70_474, "a 70 s unit would survive a 50 s fence"

    def test_the_deferred_pass_is_bounded_by_the_deadline_not_the_phase(self):
        ledger, phase = self._ledger_with_a_collapsed_futures_budget()

        bound = ledger.statement_timeout_for_unit(
            phase, elapsed_ms=400_000, unit_ms=70_474, ignore_phase_budget=True
        )

        assert bound > 70_474, "the measured unit still does not fit"

    def test_it_is_a_bound_and_not_an_escape(self):
        """A unit may no more outlive the beat than before: with the window
        nearly gone, the deadline term still binds."""
        ledger, phase = self._ledger_with_a_collapsed_futures_budget()

        bound = ledger.statement_timeout_for_unit(
            phase, elapsed_ms=1_379_000, unit_ms=70_474, ignore_phase_budget=True
        )

        assert bound <= 1_000, f"a unit was handed {bound} ms of a 1,000 ms window"

    def test_the_default_is_unchanged_for_every_other_caller(self):
        """Control. The inline path must be bit-for-bit what it was."""
        ledger, phase = self._ledger_with_a_collapsed_futures_budget()

        assert ledger.statement_timeout_for_unit(
            phase, elapsed_ms=400_000, unit_ms=70_474
        ) == ledger.statement_timeout_for_unit(
            phase, elapsed_ms=400_000, unit_ms=70_474, ignore_phase_budget=False
        )


class TestTwoBackendsAreBothNamed:
    """The rebuild runs on a SECOND session, so the run now has two backends.

    ``session_identity`` exists so a ``pg_stat_activity`` row seen weeks later
    joins back to a named run — the wedged-backend hunt of #1479. Its contract
    ("captured once and kept") assumed one session per run, which the reorder
    ends. Written over, the ledger would name the backend that was REBUILDING
    while the one that published, the one whose wedge costs a curve, went
    unrecorded. So there are two fields.
    """

    @staticmethod
    def _runner():
        from app.tasks.calibration_main_build import PhaseRunner
        from app.utils.calibration_phase_ledger import FRESH, derive_plan

        return PhaseRunner(
            plan=derive_plan({}),
            checkpoint=None,
            checkpoint_action=FRESH,
            population_version=VERSION,
            owner=OWNER,
            generation=1,
            fingerprint=INPUT_FP,
        )

    @pytest.mark.asyncio
    async def test_the_rebuild_tag_does_not_overwrite_the_builds(self, monkeypatch):
        import app.tasks.base as base

        runner = self._runner()

        async def tag(db, *, task, run_generation, owner):
            return {
                "application_name": f"{task}:{db}",
                "backend_pid": db,
                "applied": True,
            }

        monkeypatch.setattr(base, "tag_task_session", tag)

        await runner.tag_session(111)
        await runner.tag_rebuild_session(222)

        assert runner.session_identity["backend_pid"] == 111, (
            "the publishing backend was overwritten by the rebuilding one"
        )
        assert runner.rebuild_session_identity["backend_pid"] == 222, (
            "the rebuild's backend is anonymous — an orphan from it could not be "
            "joined back to this run"
        )


def test_the_reorder_did_not_move_the_build_input_fingerprint():
    """``_main_input_fingerprint`` hashes the source of four build functions.
    Every line this queue changed lives outside all four, so the 46-unit staged
    bank and the carried phase outputs are NOT discarded on deploy. Asserted
    rather than assumed: getting it wrong costs a ~20 hour rebuild.
    """
    import inspect

    import app.tasks.precompute_calibration as pc

    hashed = (
        inspect.getsource(pc.compute_calibration_payload)
        + inspect.getsource(pc._calibration_population_ctes)
        + inspect.getsource(pc._virtual_market_ctes)
        + inspect.getsource(pc._main_futures_sql)
    )

    for name in ("_run_staged_futures", "_run_deferred_rebuild", "_run_calibration_main_build"):
        assert f"def {name}" not in hashed, (
            f"{name} landed inside a fingerprinted function — that resets the "
            "checkpoint cursor and bins the staged-futures bank"
        )
    for symbol in ("rebuild_only", "rebuild_deferred", "defer_rebuild"):
        assert symbol not in hashed, (
            f"{symbol} reached the hashed source — the deploy would discard the bank"
        )


def test_the_staged_unit_digest_is_untouched_by_the_reorder():
    """The banked UNITS key off the emitted statement, not off this file's
    control flow (CAL-P205). A reorder that moved that digest would throw the
    bank away on the deploy that shipped it — the one thing this queue must not
    do, since its entire purpose is to protect what the beat has earned."""
    import app.tasks.precompute_calibration as pc

    assert pc.staged_unit_fingerprint() == pc.staged_unit_fingerprint()
