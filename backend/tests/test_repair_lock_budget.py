"""#2016 — bound the STATEMENT, not the gap between rows.

WHAT IS BEING PROVED, AND WHAT THIS FILE DELIBERATELY DOES NOT CLAIM

The defect is not arithmetic. ``APPLY_TIME_BUDGET_S`` was correct about the
number and wrong about the PLACE: a check at the top of a loop is not running
while a statement is in flight, so a single ``UPDATE`` that queues behind
another transaction's row lock sails past the 20 s budget and past Heroku's 30 s
wall. Measured on the queue-377 mapping apply: the rail's UPDATE waited 3 m 52 s
behind a Celery transaction held open **8 m 59 s**; the next apply call then
waited 2 m 39 s behind the first call's advisory lock. One operator got a lost
response over 21 committed rows, the next got a 503 over zero. Those two read
identically, which is the whole defect — per-row commits already made the data
safe.

**There is no local Postgres in this sandbox** (``initdb`` dies on ``shmget``),
so nothing below is a real row-lock test. What it is instead is a double that
models the ONE Postgres behaviour under discussion — a blocker is holding the
row; ``lock_timeout`` decides whether we wait for it — and models it honestly in
three ways that each disarm a way this guard could ship dead:

* the blocker holds for the **measured** 8 m 59 s, so an unbounded statement
  overruns the wall by a factor of eighteen rather than by a token amount;
* ``lock_timeout`` is cleared on every commit and rollback, because that is its
  real transaction scope — a double that let one setting survive a commit would
  keep passing after somebody hoisted the ``set_config`` above the per-row loop;
* the unbounded path **succeeds** (rowcount 1, far too late) rather than
  raising, so a rail that "passes" only because the double throws for it cannot
  exist.

:class:`TestTheDoubleActuallyBlocks` is the committed negative control: it
removes the timeout and asserts the overrun, so the guard tests above it are
known to be measuring something.
"""

import pytest
from sqlalchemy.exc import OperationalError

from app.utils.repair_apply_plan import (
    REASON_CREATE_ROW_LOCK_TIMEOUT,
    REASON_MAPPING_BEFORE_DRIFT,
    REASON_MAPPING_ROW_LOCK_TIMEOUT,
    PlannedCreate,
    PlannedMappingRepair,
    build_create_plan,
    build_mapping_repair_plan,
)
from app.utils.repair_lock_budget import (
    LOCK_NOT_AVAILABLE_SQLSTATE,
    LOCK_TIMEOUT_CEILING_MS,
    LOCK_TIMEOUT_FLOOR_MS,
    MIN_ROW_BUDGET_S,
    ApplyBudget,
    is_lock_timeout,
    lock_timeout_value,
)

#: Heroku's HTTP wall. Not a config value in this repo — it is the platform's,
#: and it is the thing every assertion below is ultimately about.
HEROKU_WALL_S = 30.0

MLB = 33178


# ---------------------------------------------------------------------------
# The pure helper
# ---------------------------------------------------------------------------


class TestIsLockTimeout:
    """Classified by SQLSTATE, never by message text."""

    def test_the_wrapped_driver_error_is_recognised(self):
        assert is_lock_timeout(_lock_not_available()) is True

    def test_a_bare_driver_error_is_recognised(self):
        assert is_lock_timeout(_LockNotAvailableError("nope")) is True

    def test_a_deadlock_is_not_a_lock_timeout(self):
        """40P01 is a different fact with a different next move."""
        orig = type("DeadlockDetected", (Exception,), {"sqlstate": "40P01"})("boom")
        assert is_lock_timeout(OperationalError("UPDATE x", {}, orig)) is False

    def test_an_ordinary_error_is_not_a_lock_timeout(self):
        assert is_lock_timeout(ValueError("something else entirely")) is False

    def test_a_message_that_merely_says_lock_timeout_is_not_enough(self):
        """The whole point of classifying by code: prose is not a contract."""
        assert is_lock_timeout(RuntimeError("canceling statement due to lock timeout")) is False


class TestApplyBudget:
    def test_it_measures_from_construction_not_from_first_use(self):
        clock = _Clock()
        budget = ApplyBudget(20.0, clock=clock)
        clock.advance(5.0)
        assert budget.elapsed_s() == pytest.approx(5.0)
        assert budget.remaining_s() == pytest.approx(15.0)

    def test_a_row_is_not_started_on_the_last_scraps_of_the_budget(self):
        clock = _Clock()
        budget = ApplyBudget(20.0, clock=clock)
        clock.advance(20.0 - MIN_ROW_BUDGET_S - 0.01)
        assert budget.has_room_for_a_row() is True
        clock.advance(0.02)
        assert budget.has_room_for_a_row() is False

    def test_the_timeout_is_a_share_of_what_is_LEFT_not_a_constant(self):
        clock = _Clock()
        budget = ApplyBudget(20.0, clock=clock)
        first = budget.lock_timeout_ms()
        clock.advance(18.0)
        later = budget.lock_timeout_ms()
        assert later < first

    def test_it_is_clamped_at_both_ends(self):
        assert ApplyBudget(600.0, clock=_Clock()).lock_timeout_ms() == LOCK_TIMEOUT_CEILING_MS
        assert ApplyBudget(0.0, clock=_Clock()).lock_timeout_ms() == LOCK_TIMEOUT_FLOOR_MS

    def test_the_timeout_never_exceeds_the_remaining_request(self):
        """Otherwise the guard is a second way to overrun the wall."""
        clock = _Clock()
        for spent in (0.0, 5.0, 10.0, 15.0, 18.5, 19.0):
            budget = ApplyBudget(20.0, clock=clock)
            clock.advance(spent)
            if budget.has_room_for_a_row():
                assert budget.lock_timeout_ms() / 1000.0 <= budget.remaining_s()

    def test_the_value_carries_its_unit(self):
        assert lock_timeout_value(2500) == "2500ms"


# ---------------------------------------------------------------------------
# The double
# ---------------------------------------------------------------------------


class _Clock:
    """A monotonic clock a test owns, so nothing here sleeps or reads the wall."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class _LockNotAvailableError(Exception):
    """Stands in for ``asyncpg.exceptions.LockNotAvailableError``."""

    sqlstate = LOCK_NOT_AVAILABLE_SQLSTATE


def _lock_not_available():
    """What SQLAlchemy hands the rail when ``lock_timeout`` fires."""
    return OperationalError(
        "UPDATE …", {}, _LockNotAvailableError("canceling statement due to lock timeout")
    )


class _R:
    def __init__(self, rows=(), rowcount=0, mappings=False):
        self._rows = list(rows)
        self.rowcount = rowcount
        self._mappings = mappings

    def mappings(self):
        return _R(self._rows, self.rowcount, mappings=True)

    def all(self):
        return self._rows


class _BlockingPostgres:
    """The one Postgres behaviour this file is about.

    ``BLOCKER_HOLDS_S`` is the measured q377 blocker, not a round number: a
    Celery task ran a sequence of fast per-event ``SELECT events…`` inside a
    single transaction and held it open 8 m 59 s. The unbounded path returns
    SUCCESSFULLY after that wait — that is what Postgres does — so no rail can
    pass these tests merely because the double raised on its behalf.
    """

    BLOCKER_HOLDS_S = 539.0

    def __init__(self, clock, *, contended=(), advisory_contended=()):
        self.clock = clock
        self.contended = set(contended)
        self.advisory_contended = set(advisory_contended)
        self.lock_timeout_ms = None
        self.timeouts_issued = []
        self.commits = 0
        self.rollbacks = 0
        self.locks = []

    # -- session protocol ---------------------------------------------------

    async def commit(self):
        self.commits += 1
        self.lock_timeout_ms = None  # SET LOCAL dies with its transaction

    async def rollback(self):
        self.rollbacks += 1
        self.lock_timeout_ms = None

    # -- the modelled behaviour --------------------------------------------

    def _set_config(self, params):
        raw = params["ms"]
        assert raw.endswith("ms"), f"the timeout must carry its unit, got {raw!r}"
        self.lock_timeout_ms = int(raw[:-2])
        self.timeouts_issued.append(self.lock_timeout_ms)

    def _wait(self, contended):
        """Model waiting for the blocker. Returns iff the lock is acquired."""
        if not contended:
            return
        if self.lock_timeout_ms is None:
            # Nobody bounded the statement. Postgres waits it out — all 8m59s of
            # it — and then succeeds, long after the client has gone.
            self.clock.advance(self.BLOCKER_HOLDS_S)
            return
        waited = min(self.BLOCKER_HOLDS_S, self.lock_timeout_ms / 1000.0)
        self.clock.advance(waited)
        if waited < self.BLOCKER_HOLDS_S:
            raise _lock_not_available()


class _MappingPG(_BlockingPostgres):
    """…speaking the mapping rail's five SQL shapes."""

    def __init__(self, clock, observed, *, contended=(), advisory_contended=()):
        super().__init__(clock, contended=contended, advisory_contended=advisory_contended)
        self.observed = dict(observed)
        self.updates = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = params or {}

        if "set_config('lock_timeout'" in sql:
            self._set_config(params)
            return _R()
        if sql.strip() == "SELECT 1":
            # The negative control's stand-in for the removed ``set_config``: a
            # statement that runs and sets nothing, which is exactly the pre-fix
            # world.
            return _R()
        if "pg_advisory_xact_lock" in sql:
            self.locks.append(params)
            self._wait(params["key"] in self.advisory_contended)
            return _R()
        if sql.strip().startswith("SELECT id, team_id"):
            return _R(rows=[(k, v) for k, v in self.observed.items()])
        if "UPDATE team_identity_mapping" in sql:
            mid = int(params["mapping_id"])
            self._wait(mid in self.contended)
            if self.observed.get(mid) != int(params["before_team_id"]):
                return _R(rowcount=0)
            self.observed[mid] = int(params["after_team_id"])
            self.updates.append(params)
            return _R(rowcount=1)
        if "FROM team_identity_mapping m" in sql:
            return _R(
                rows=[
                    {"id": mid, "team_id": tid, "source": "polymarket",
                     "sport_key": "baseball_mlb", "source_name": "San Diego Padres",
                     "club": "San Diego Padres" if tid == 867 else "Chicago White Sox"}
                    for mid, tid in sorted(self.observed.items())
                ],
                mappings=True,
            )
        raise AssertionError(f"unexpected SQL in double: {sql[:120]}")


class _CreatePG(_BlockingPostgres):
    """…speaking the create rail's four SQL shapes."""

    def __init__(self, clock, *, present=(), contended=()):
        super().__init__(clock, contended=contended)
        self.events = {t: {"espn_id": t, "id": 500 + i} for i, t in enumerate(present)}
        self.inserted = []

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = params or {}

        if "set_config('lock_timeout'" in sql:
            self._set_config(params)
            return _R()
        if "pg_advisory_xact_lock" in sql:
            self.locks.append(params)
            return _R()
        if "SELECT DISTINCT espn_id" in sql:
            wanted = set(params["ids"])
            return _R(rows=[(t,) for t in self.events if t in wanted])
        if "INSERT INTO events" in sql:
            tid = params["truth_id"]
            self._wait(tid in self.contended)
            if tid in self.events:
                return _R(rowcount=0)
            self.events[tid] = {
                "espn_id": tid, "id": 900 + len(self.events),
                "sport_id": params["sport_id"],
                "home_team_id": params["home_team_id"],
                "away_team_id": params["away_team_id"],
                "home_team_name": params["home_name"],
                "away_team_name": params["away_name"],
                "commence_time": params["commence_time"],
                "status": "scheduled",
            }
            self.inserted.append(tid)
            return _R(rowcount=1)
        if "FROM events" in sql and "ORDER BY espn_id" in sql:
            wanted = set(params["ids"])
            return _R(
                rows=[
                    {"espn_id": e["espn_id"], "id": e["id"], "sport_id": e.get("sport_id", MLB),
                     "home_team_id": e.get("home_team_id", 1),
                     "away_team_id": e.get("away_team_id", 2),
                     "home_team_name": e.get("home_team_name", "H"),
                     "away_team_name": e.get("away_team_name", "A"),
                     "commence_time": e.get("commence_time", "t"),
                     "status": e.get("status", "scheduled")}
                    for t, e in sorted(self.events.items()) if t in wanted
                ],
                mappings=True,
            )
        raise AssertionError(f"unexpected SQL in double: {sql[:120]}")


# ---------------------------------------------------------------------------
# Fixtures / plan builders
# ---------------------------------------------------------------------------


def _mapping_row(mapping_id):
    return PlannedMappingRepair(
        mapping_id=mapping_id,
        source="polymarket",
        sport_key="baseball_mlb",
        source_name="San Diego Padres",
        before_team_id=851,
        before_club="Chicago White Sox",
        after_team_id=867,
        after_club="San Diego Padres",
    )


def _create_row(truth_id):
    return PlannedCreate(
        truth_id=truth_id,
        provider="espn",
        label=f"game {truth_id}",
        sport_id=MLB,
        home_team_id=101,
        home_name="Home Club",
        away_team_id=202,
        away_name="Away Club",
        commence_time="2026-08-19T23:05:00+00:00",
    )


def _mapping_rail(monkeypatch, plan, clock):
    """Point the mapping rail at ``plan`` and ``clock``, and hand it back."""
    from unittest.mock import AsyncMock

    import app.tasks.repair_team_identity_mapping as rail

    monkeypatch.setattr(rail, "_load_plan", AsyncMock(return_value=(plan, "ok")))
    monkeypatch.setattr(rail, "_monotonic", clock)
    return rail


def _create_rail(monkeypatch, plan, clock):
    from unittest.mock import AsyncMock

    import app.tasks.create_events_from_truth as rail
    import app.utils.feed_cache as fc

    async def _fake_invalidate(reason):
        return {"status": "ok", "deleted": 0, "reason": reason}

    monkeypatch.setattr(fc, "invalidate_feed_response_cache", _fake_invalidate, raising=False)
    monkeypatch.setattr(rail, "_load_plan", AsyncMock(return_value=(plan, "ok")))
    monkeypatch.setattr(rail, "_monotonic", clock)
    return rail


# ---------------------------------------------------------------------------
# THE NEGATIVE CONTROL — proving the double is measuring something
# ---------------------------------------------------------------------------


class TestTheDoubleActuallyBlocks:
    """Remove the timeout and the guard tests below must fail. Shown, not assumed.

    A guard test that has never been seen to fail is not a guard. This removes
    exactly one thing — the ``set_config`` statement — and asserts BOTH halves of
    the pre-fix behaviour: the call runs eighteen times past the wall, AND no row
    is named, so the operator is handed a 503 over a write that may or may not
    have happened.
    """

    async def test_without_the_lock_timeout_the_call_runs_far_past_the_wall(self, monkeypatch):
        from sqlalchemy import text

        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        # The ONE removal. Everything else is the shipped path.
        monkeypatch.setattr(rail, "SET_LOCK_TIMEOUT_SQL", text("SELECT 1"))
        session = _MappingPG(clock, observed={1: 851}, contended={1})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert clock.t > HEROKU_WALL_S, (
            "the double is not modelling a blocker — every guard below is vacuous"
        )
        assert clock.t == pytest.approx(_BlockingPostgres.BLOCKER_HOLDS_S)
        # And the pre-fix reporting: the row was written, eventually, and NOTHING
        # in the response says the operator waited nine minutes for it.
        assert out["stopped_on_lock"] == []
        assert out["lock_timeouts"] == []


# ---------------------------------------------------------------------------
# The mapping rail
# ---------------------------------------------------------------------------


class TestMappingRailUnderContention:
    async def test_a_contended_row_returns_inside_the_wall_and_is_NAMED(self, monkeypatch):
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851}, contended={1})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert clock.t < HEROKU_WALL_S
        assert out["stopped_on_lock"] == [1]
        assert out["lock_timeouts"][0]["reason_code"] == REASON_MAPPING_ROW_LOCK_TIMEOUT
        assert out["lock_timeouts"][0]["lock_timeout_ms"] <= LOCK_TIMEOUT_CEILING_MS
        # Nothing was written and the aborted transaction was rolled back.
        assert session.updates == []
        assert session.rollbacks >= 1
        # And it does not claim to be finished (gotcha #53).
        assert out["exhausted"] is False
        assert out["repointed_count"] == 0

    async def test_a_contended_ADVISORY_lock_is_bounded_too(self, monkeypatch):
        """pid 1998635 in the q377 reading was waiting on the advisory lock, not
        the UPDATE — so the timeout must be set BEFORE the lock, not between it
        and the write."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        key = rail._lock_key(1)
        session = _MappingPG(clock, observed={1: 851}, advisory_contended={key})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert clock.t < HEROKU_WALL_S
        assert out["stopped_on_lock"] == [1]

    async def test_one_contended_row_does_not_cancel_its_siblings(self, monkeypatch):
        """The behaviour the rail already has for drift, extended to contention."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1), _mapping_row(2), _mapping_row(3)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851, 2: 851, 3: 851}, contended={2})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert clock.t < HEROKU_WALL_S
        assert out["repointed_count"] == 2
        assert sorted(e["mapping_id"] for e in out["repointed"]) == [1, 3]
        assert out["stopped_on_lock"] == [2]
        assert out["remaining"] == 1

    async def test_the_timeout_is_re_issued_inside_EVERY_rows_transaction(self, monkeypatch):
        """Hoisting the ``set_config`` above the loop protects row 1 and nothing
        after the first commit, because SET LOCAL is transaction-scoped. Row 1 is
        clean (so it commits), row 2 is contended — a hoisted setting would be
        gone by then and row 2 would block for nine minutes."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1), _mapping_row(2)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851, 2: 851}, contended={2})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert len(session.timeouts_issued) == 2, "the timeout was not re-issued per row"
        assert clock.t < HEROKU_WALL_S
        assert out["stopped_on_lock"] == [2]

    async def test_a_contended_row_is_still_actionable_on_the_next_call(self, monkeypatch):
        """Resumability. The apply has no cursor — the gate is what makes it
        resumable — so a timed-out row must be left in its ``before`` state."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851}, contended={1})

        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert first["stopped_on_lock"] == [1]
        assert session.observed[1] == 851, "a timed-out row must be untouched"

        # The blocker goes away; the SAME plan_hash finishes the job.
        session.contended.clear()
        session.clock = clock = _Clock()
        monkeypatch.setattr(rail, "_monotonic", clock)
        second = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert second["repointed_count"] == 1
        assert second["exhausted"] is True
        assert session.observed[1] == 867

    async def test_contention_is_not_reported_as_drift(self, monkeypatch):
        """Two different facts, two different next moves: drift means re-derive
        and get re-reviewed; contention means re-invoke the same plan."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851}, contended={1})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["lost_cas"] == []
        assert out["gate_drifted"] == []
        assert out["lock_timeouts"][0]["reason_code"] != REASON_MAPPING_BEFORE_DRIFT

    async def test_a_non_lock_error_is_re_raised_not_dressed_up_as_contention(self, monkeypatch):
        """Gotcha #36, one table over: a catch-all here would turn a genuine write
        failure into a row that merely 'timed out' and would be retried forever."""
        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)
        session = _MappingPG(clock, observed={1: 851})

        async def _boom(stmt, params=None):
            if "UPDATE team_identity_mapping" in str(stmt):
                raise OperationalError(
                    "UPDATE …", {},
                    type("SerializationFailure", (Exception,), {"sqlstate": "40001"})("boom"),
                )
            return await _MappingPG.execute(session, stmt, params)

        session.execute = _boom
        with pytest.raises(OperationalError):
            await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

    async def test_the_budget_starts_at_REQUEST_entry_not_at_loop_entry(self, monkeypatch):
        """The pre-loop plan load and gate query are charged against it. Under the
        old placement this call would have written the row after the wall."""
        from unittest.mock import AsyncMock

        clock = _Clock()
        plan = build_mapping_repair_plan([_mapping_row(1)])
        rail = _mapping_rail(monkeypatch, plan, clock)

        slow = AsyncMock(return_value=(plan, "ok"))

        async def _slow_load():
            clock.advance(rail.APPLY_REQUEST_BUDGET_S - 0.5)
            return await slow()

        monkeypatch.setattr(rail, "_load_plan", _slow_load)
        session = _MappingPG(clock, observed={1: 851})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["stopped_on_time_budget"] is True
        assert out["repointed_count"] == 0
        assert session.updates == []
        assert out["exhausted"] is False


# ---------------------------------------------------------------------------
# The create rail — the identical shape, one table over
# ---------------------------------------------------------------------------


class TestCreateRailUnderContention:
    async def test_a_contended_row_returns_inside_the_wall_and_is_NAMED(self, monkeypatch):
        clock = _Clock()
        plan = build_create_plan([_create_row("A1")])
        rail = _create_rail(monkeypatch, plan, clock)
        session = _CreatePG(clock, contended={"A1"})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

        assert clock.t < HEROKU_WALL_S
        assert out["stopped_on_lock"] == ["A1"]
        assert out["lock_timeouts"][0]["reason_code"] == REASON_CREATE_ROW_LOCK_TIMEOUT
        assert session.inserted == []
        assert out["exhausted"] is False

    async def test_one_contended_row_does_not_cancel_its_siblings(self, monkeypatch):
        clock = _Clock()
        plan = build_create_plan([_create_row("A1"), _create_row("A2"), _create_row("A3")])
        rail = _create_rail(monkeypatch, plan, clock)
        session = _CreatePG(clock, contended={"A2"})

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

        assert clock.t < HEROKU_WALL_S
        assert session.inserted == ["A1", "A3"]
        assert out["census"]["created"] == 2
        assert out["census"]["contended"] == 1
        assert out["stopped_on_lock"] == ["A2"]

    async def test_the_timeout_is_re_issued_inside_EVERY_rows_transaction(self, monkeypatch):
        clock = _Clock()
        plan = build_create_plan([_create_row("A1"), _create_row("A2")])
        rail = _create_rail(monkeypatch, plan, clock)
        session = _CreatePG(clock, contended={"A2"})

        await rail.repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

        assert len(session.timeouts_issued) == 2
        assert clock.t < HEROKU_WALL_S

    async def test_a_contended_id_is_still_missing_and_still_actionable(self, monkeypatch):
        clock = _Clock()
        plan = build_create_plan([_create_row("A1")])
        rail = _create_rail(monkeypatch, plan, clock)
        session = _CreatePG(clock, contended={"A1"})

        first = await rail.repair(session, apply=True, plan_hash=plan.plan_hash, population="2")
        assert first["stopped_on_lock"] == ["A1"]

        session.contended.clear()
        session.clock = clock = _Clock()
        monkeypatch.setattr(rail, "_monotonic", clock)
        second = await rail.repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

        assert second["census"]["created"] == 1
        assert second["exhausted"] is True


# ---------------------------------------------------------------------------
# The binding rail — the structurally DIFFERENT sibling
# ---------------------------------------------------------------------------


class TestBindingRailIsBoundedToo:
    """One transaction, one commit, no advisory lock — so it has no per-row
    retirement to offer. A contended row aborts the whole plan, which is correct
    here precisely BECAUSE nothing has been committed: the refusal is named and
    the same plan_hash re-applies cleanly once the blocker clears."""

    async def test_it_sets_a_lock_timeout_before_its_updates(self):
        import inspect

        import app.tasks.repair_event_team_binding as rail

        src = inspect.getsource(rail._apply_reviewed_plan)
        set_at = src.index("SET_LOCK_TIMEOUT_SQL")
        update_at = src.index("_UPDATE_SQL[row.side]")
        assert set_at < update_at, "the timeout must be set before the first UPDATE"

    async def test_a_contended_row_is_a_NAMED_refusal_with_nothing_committed(self, monkeypatch):
        from unittest.mock import AsyncMock

        from app.utils.repair_apply_plan import (
            REASON_BINDING_LOCK_TIMEOUT,
            PlannedBinding,
            build_binding_plan,
        )

        import app.tasks.repair_event_team_binding as rail

        plan = build_binding_plan(
            [
                PlannedBinding(
                    event_id=7, side="home",
                    expected_before_id=855, before_name="Minnesota Twins",
                    after_id=10739, after_name="Minnesota Twins",
                    defect="cross_registry", matchup="A @ B", sport_id=MLB,
                )
            ]
        )
        monkeypatch.setattr(rail, "_load_plan", AsyncMock(return_value=(plan, "ok")))

        state = {"commits": 0, "rollbacks": 0, "timeout": None}

        class _Session:
            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "set_config('lock_timeout'" in sql:
                    state["timeout"] = (params or {})["ms"]
                    return _R()
                if "UPDATE events" in sql:
                    assert state["timeout"] is not None
                    raise _lock_not_available()
                raise AssertionError(f"unexpected SQL: {sql[:120]}")

            async def commit(self):
                state["commits"] += 1

            async def rollback(self):
                state["rollbacks"] += 1

        out = await rail.repair(_Session(), apply=True, plan_hash=plan.plan_hash)

        assert out["applied"] is False
        assert out["refused"] is True
        assert out["reason_codes"] == [REASON_BINDING_LOCK_TIMEOUT]
        assert out["contended_row"]["event_id"] == 7
        assert state["commits"] == 0
        assert state["rollbacks"] == 1
