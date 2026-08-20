"""CAL-P038 (#1597): a beat must stop BEFORE its window runs out, not after.

Why this file exists, measured in production on 2026-08-11.

``precompute_calibration_main`` had ``consecutive_failures = 199`` and had not
succeeded since 2026-08-02. The failing statement was always the chunk read, the
verdict always ``thrown``/``DBAPIError``, and the phase status always ``timeout``.
The staged design already has the right answer for a beat that runs out of room —
:class:`~app.tasks.calibration_main_build.StagedFuturesIncomplete`, which
``classify_failure`` deliberately maps to ``cancelled`` rather than ``failed`` so
"a working build does not page anybody RED for doing exactly what it was designed
to do".

**That path had never once been reached.** ``incompletes_24h`` was 0 against 199
consecutive failures, and the reason is one line: the loop's gate was
``deadline_exceeded()`` — *is there any time left* — when the question it needed
to ask is *is there enough time left for a unit*. Units cost ~70s. A beat that
started one with 30s remaining got a ``statement_timeout`` of 27s (the inner
margin scales down proportionally rather than refusing), Postgres cancelled it,
and ``QueryCanceledError`` propagated out of the phase. So the LAST unit of every
deadline-reaching beat was guaranteed to be cancelled.

The cost was not only the wrong verdict. ``_record_convergence_projection`` runs
AFTER the loop, so a throw skipped it — which is why ``staged:beats_to_publish``,
the one number that says whether the build will ever finish, was absent from
every ledger the lane has read.

The tests below drive the real loop against a fake database that **cancels a
statement exactly the way PostgreSQL does** — if the window left is smaller than
the unit's cost. That is what makes them non-vacuous: reverting the guard to
``deadline_exceeded()`` makes the mutation tests raise instead of returning a
clean partial, which is precisely the production failure.
"""

from __future__ import annotations

import contextlib
import types

import pytest

from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf


# --- the pure predicate ------------------------------------------------------


@pytest.mark.parametrize(
    "remaining_ms,worst_unit_ms,expected",
    [
        # No time left is the old question, and it still answers the same way.
        (0, 0.0, False),
        (-5, 100.0, False),
        # No observation yet: a beat must be allowed to attempt one unit, or the
        # build can never progress. Refusing here on a number we do not have is
        # the invented constant this module keeps refusing to write.
        (1, 0.0, True),
        (10_000, 0.0, True),
        # With an observation, the bound is the worst unit plus the safety
        # margin — 100ms observed needs 125ms of room.
        (125, 100.0, True),
        (124, 100.0, False),
        (1_000, 100.0, True),
        # The production shape: ~70s units, ~30s left. This is the exact case
        # that threw on every beat.
        (30_000, 70_000.0, False),
        (90_000, 70_000.0, True),
    ],
)
def test_the_window_check_asks_whether_a_unit_fits_not_whether_time_remains(
    remaining_ms, worst_unit_ms, expected
):
    assert pc._unit_fits_in_window(remaining_ms, worst_unit_ms) is expected


def test_the_safety_margin_is_above_one_so_the_next_unit_may_be_worse():
    """The bound is the worst unit SO FAR; the next one may exceed it.

    Pinned as its own assertion because a margin of exactly 1.0 reads as
    correct and is not: it admits a unit that is one millisecond slower than
    every unit before it, which is the common case, not the rare one.
    """
    assert pc.STAGED_UNIT_WINDOW_SAFETY > 1.0


# --- the loop ----------------------------------------------------------------


class _StatementCancelled(Exception):
    """Stands in for ``asyncpg.exceptions.QueryCanceledError``.

    Named and raised by the fake database under the same condition PostgreSQL
    cancels under, so a test that sees it has reproduced the production failure
    rather than modelled one.
    """


class _FakeLedger:
    def __init__(self, window_ms: int):
        self._window_ms = window_ms
        self.stages: dict[str, int] = {}

    def remaining_ms(self, *, elapsed_ms: int) -> int:
        return self._window_ms - elapsed_ms

    def record_stage(self, name: str, duration_ms: int) -> None:
        self.stages[name] = self.stages.get(name, 0) + duration_ms

    def record_gauge(self, name: str, value: int) -> None:
        self.stages[name] = value


class _FakeRunner:
    """Only the surface ``_run_staged_futures`` actually touches.

    The clock is explicit and advanced by the fake database, so a unit's cost is
    a property of the test rather than of the machine it runs on — the
    clock-branching trap gotcha #44 names.
    """

    def __init__(self, *, window_ms: int, unit_cost_ms: int):
        self.ledger = _FakeLedger(window_ms)
        self.unit_cost_ms = unit_cost_ms
        self._elapsed = 0
        self.population_version = "q267"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = 1
        self.timeouts_applied: list[int] = []

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += ms

    def deadline_exceeded(self) -> bool:
        return self.ledger.remaining_ms(elapsed_ms=self._elapsed) <= 0

    @contextlib.contextmanager
    def stage(self, _name: str):
        yield

    async def commit(self, _db) -> None:
        return None

    async def apply_statement_timeout(self, _db, _phase) -> int:
        left = self.ledger.remaining_ms(elapsed_ms=self._elapsed)
        self.timeouts_applied.append(left)
        return left

    # -- CAL-P081 (#2052) -----------------------------------------------------
    # The loop now asks the runner for the PREVIOUS beat's measured unit cost and
    # arms a UNIT-scoped timeout rather than the phase's. This fake answers "no
    # carried measurement", which is the state these tests were written in and
    # keeps every assertion below about the within-beat fence, unchanged.
    # See ``test_calibration_unit_admission_p081.py`` for the carried-cost cases.

    def measured_unit_ms(self, _phase):
        return None

    async def apply_unit_statement_timeout(self, _db, _phase, *, unit_ms=None) -> int:
        left = self.ledger.remaining_ms(elapsed_ms=self._elapsed)
        self.timeouts_applied.append(left)
        return left


class _FakeDb:
    """A database that cancels a statement it cannot finish inside its timeout.

    This is the whole point of the file. PostgreSQL does not politely return
    early when ``statement_timeout`` is short — it cancels, and the driver
    raises. Modelling the timeout as "the read succeeds anyway" would make every
    test here pass under the defect.

    The first read is the generation scan and is free; every read after it is a
    unit and costs ``unit_cost_ms`` of the beat's window.
    """

    def __init__(self, runner: _FakeRunner, roster):
        self.runner = runner
        self.roster = roster
        self.reads = 0
        self._generation_read_done = False

    async def execute(self, _sql, _params=None):
        if not self._generation_read_done:
            self._generation_read_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        self.runner.advance(self.runner.unit_cost_ms)
        left = self.runner.ledger.remaining_ms(elapsed_ms=self.runner.elapsed_ms())
        if left < 0:
            raise _StatementCancelled(
                "canceling statement due to statement timeout"
            )
        self.reads += 1
        return types.SimpleNamespace(all=lambda: [])


def _roster(n_markets: int):
    return [
        types.SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False)
        for i in range(1, n_markets + 1)
    ]


@pytest.fixture
def staged_env(monkeypatch):
    """Wire the real planner/cursor to fake persistence and a fake database."""
    saved: list = []

    async def _load(**kwargs):
        return (
            sf.new_staged_cursor(
                population_version=kwargs["population_version"],
                input_fingerprint=kwargs["input_fingerprint"],
                generation_fingerprint=kwargs["generation_fingerprint"],
                owner=kwargs["owner"],
                generation=kwargs["generation"],
            ),
            "resume",
            "resumable",
        )

    async def _save(cursor, terminal=None):
        saved.append(len(cursor.committed_units))
        return True

    from app.tasks import calibration_main_build as cmb

    monkeypatch.setattr(cmb, "load_staged_cursor", _load)
    monkeypatch.setattr(cmb, "save_staged_cursor", _save)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", 4)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")

    def _build(*, window_ms: int, unit_cost_ms: int, n_markets: int = 8):
        runner = _FakeRunner(window_ms=window_ms, unit_cost_ms=unit_cost_ms)
        db = _FakeDb(runner, _roster(n_markets))
        # The loop times a unit with ``time.monotonic()``. Anchor that to the
        # SAME fake clock the window is measured against, or the guard compares
        # a fake window to a real wall-clock duration and the test proves
        # nothing (gotcha #44: a test anchor must not read the wall clock).
        monkeypatch.setattr(
            pc, "time", types.SimpleNamespace(monotonic=lambda: runner.elapsed_ms() / 1000.0)
        )
        return runner, db

    _build.saved = saved
    return _build


async def _run(runner, db):
    return await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")


@pytest.mark.asyncio
async def test_a_beat_stops_cleanly_instead_of_starting_a_unit_it_cannot_finish(staged_env):
    """The production failure, reproduced and then absent.

    Window 250ms, units 100ms, 4 units planned. Two fit. The third would start
    with 50ms left and be cancelled — which is what the build did on every beat
    for nine days. The loop must stop instead, and say why.
    """
    runner, db = staged_env(window_ms=250, unit_cost_ms=100)

    result = await _run(runner, db)

    assert result is None, "an incomplete generation publishes nothing"
    assert db.reads == 2, f"only two units fit in the window, got {db.reads}"
    assert runner.ledger.stages.get("staged:window_stop:unit_too_large") == 0, (
        "the loop must record WHY it stopped — an absent stage reads as fine"
    )
    assert "staged:window_stop:deadline" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_the_convergence_projection_survives_the_stop(staged_env):
    """A throw skipped it; a clean break must not.

    ``staged:beats_to_publish`` is the single number that says whether the build
    will ever finish, and it was absent from every production ledger because the
    beat always threw before reaching it.
    """
    runner, db = staged_env(window_ms=250, unit_cost_ms=100)

    await _run(runner, db)

    stages = runner.ledger.stages
    assert "staged:units_done" in stages
    assert "staged:units_planned" in stages
    assert "staged:beats_to_publish" in stages, (
        "the projection is the reason the stop has to be clean"
    )
    assert stages["staged:unit_ms_worst"] > 0


@pytest.mark.asyncio
async def test_the_old_gate_would_have_thrown_on_the_same_beat(staged_env, monkeypatch):
    """MUTATION PROOF — restore ``deadline_exceeded()`` and the beat burns a unit.

    Without this the tests above would pass over a loop that never learned
    anything: any guard that stops early satisfies them. This one pins that the
    guard is load-bearing by putting the OLD predicate back and asserting the
    production failure returns.

    **AMENDED BY CAL-P081 (#2052), and the amendment is the point.** This test
    used to assert ``pytest.raises(_StatementCancelled)`` — the cancellation
    escaping the phase, which is what made the beat terminate ``failed``. CAL-P081
    catches a cancellation at the unit boundary and skips the unit, so the same
    defective gate now produces a WASTED UNIT instead of a RED BEAT. Both halves
    are asserted: the waste still happens (the gate is still load-bearing) and it
    no longer costs the beat its verdict.
    """
    runner, db = staged_env(window_ms=250, unit_cost_ms=100)
    monkeypatch.setattr(
        pc, "_unit_fits_in_window", lambda remaining, worst, prior=0.0: remaining > 0
    )

    await _run(runner, db)
    assert runner.ledger.stages.get("staged:units_cancelled", 0) >= 1


@pytest.mark.asyncio
async def test_the_real_gate_burns_no_units_on_that_same_beat(staged_env):
    """The control for the mutation above — same beat, real predicate, no waste."""
    runner, db = staged_env(window_ms=250, unit_cost_ms=100)
    await _run(runner, db)
    assert "staged:units_cancelled" not in runner.ledger.stages


@pytest.mark.asyncio
async def test_a_beat_with_a_full_window_still_banks_every_unit(staged_env):
    """The guard must not cost throughput on a healthy beat.

    The other direction of the cap, which this repo's own lesson says a guard's
    tests must assert: the flood stays capped AND the adjacent surface stays
    populated. Here — the doomed unit is refused AND a beat with room finishes.
    """
    runner, db = staged_env(window_ms=100_000, unit_cost_ms=100)

    result = await _run(runner, db)

    assert db.reads == 4, "every planned unit fits and must run"
    assert result is not None, "a complete generation returns merged rows"
    assert "staged:window_stop:unit_too_large" not in runner.ledger.stages
    assert "staged:window_stop:deadline" not in runner.ledger.stages
