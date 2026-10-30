"""#994 — DataGolf bucket drill-in: real examples, one request budget.

THE READER DEFECT
-----------------
``/calibration/examples`` sampled the canonical population only for
``{"kalshi", "polymarket"}``; DataGolf fell through to "No examples available for
this source" whatever its bucket held, so a reader who clicked a DataGolf point
always got an empty panel. DataGolf now takes the canonical branch, with
``market_info`` scoped to its own markets.

THE BUDGET DEFECT (Root's provisional review, 2026-10-15 18:50Z)
----------------------------------------------------------------
The first scoped draft armed ONE ``statement_timeout = 20000`` and ran two
statements under it — a closure check, then the sample. Each could take just
under 20 s and the route answered at ~40 s, past the 30 s Heroku router. Root
reproduced it offline (both statements under their cap, route over its wall).
The route now re-arms every statement with what is LEFT of one wall measured
from handler entry, and an event-loop backstop bounds what ``statement_timeout``
cannot see, including the cleanup after it cancels.

HOW THIS FILE PROVES IT WITHOUT A STOPWATCH
-------------------------------------------
The fake session below honours ``SET LOCAL statement_timeout`` the way Postgres
does: a statement whose simulated duration exceeds the armed budget advances the
fake clock by the budget and raises SQLSTATE 57014. The route's clock is the
module's ``_examples_clock``, driven here, so "the request stayed inside its
wall" is an exact assertion, not a timing race. Only the two backstop tests use
the real event loop, and they assert containment against a generous bound.

What rows the canonical chain ADMITS (timing, void, field exclusions) is a
Postgres question: ``tests/integration/test_calibration_examples_datagolf_994_pg.py``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.routes import calibration as cal


class QueryCanceledError(Exception):
    """Shaped like asyncpg's 57014 — ``is_query_canceled`` reads both marks."""

    sqlstate = "57014"


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class _Result:
    def __init__(self, *, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar(self):
        return self._scalar

    def all(self):
        return list(self._rows)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _dg_row(mid: int, oid: int, *, price: float, won: bool) -> _Row:
    return _Row(
        market_id=mid,
        outcome_id=oid,
        market_name=f"Test Open {mid} - Make the Cut",
        outcome_name=f"Player {oid}",
        price=price,
        is_winner=won,
        settle_date=None,
    )


class _FakeDB:
    """Honours ``statement_timeout`` like the server: over budget ⇒ 57014."""

    def __init__(self, clock: _Clock, durations=(), *, shares_identity=False, rows=()):
        self.clock = clock
        self.durations = list(durations)
        self.shares_identity = shares_identity
        self.rows = list(rows)
        self.timeout_ms: int | None = None
        self.armed: list[int] = []
        self.statements: list[tuple[str, dict | None]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.strip().startswith("SET LOCAL statement_timeout"):
            self.timeout_ms = int(sql.split("=")[1])
            self.armed.append(self.timeout_ms)
            return _Result()
        self.statements.append((sql, params))
        duration = self.durations.pop(0) if self.durations else 0.0
        if self.timeout_ms is not None and duration * 1000 > self.timeout_ms:
            self.clock.advance(self.timeout_ms / 1000)
            raise QueryCanceledError("canceling statement due to statement timeout")
        self.clock.advance(duration)
        if "shares_identity" in sql:
            return _Result(scalar=self.shares_identity)
        if "SELECT market_id, vm_id, is_grouped" in sql:
            return _Result(rows=self.roster())
        chunk = set((params or {}).get("vm_roster_market_ids") or ())
        return _Result(rows=[r for r in self.rows if r.market_id in chunk])

    def roster(self):
        """One ``m:`` question per market the rows name (market 1 when empty),
        so every chunk statement runs and returns its own markets' rows."""
        mids = sorted({r.market_id for r in self.rows}) or [1]
        return [_Row(market_id=m, vm_id=f"m:{m}", is_grouped=False) for m in mids]


class _Untouchable:
    """The REQUEST's session in the ownership tests: the scoped branch must
    never execute on it, because the dependency closes it at teardown while an
    abandoned sample could still be running."""

    def __init__(self, owned):
        self.owned = owned

    async def execute(self, stmt, params=None):
        raise AssertionError(f"the scoped branch used the request session: {stmt}")


class _OwnedCM:
    """Stands in for ``_owned_examples_session``: opens and closes the fake."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.opened = getattr(self.session, "opened", 0) + 1
        return self.session

    async def __aexit__(self, *exc):
        self.session.closed = getattr(self.session, "closed", 0) + 1
        return False


@pytest.fixture(autouse=True)
def _owned_session(monkeypatch):
    monkeypatch.setattr(
        cal,
        "_owned_examples_session",
        lambda db: _OwnedCM(getattr(db, "owned", db)),
        raising=False,
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    cal._examples_cache.clear()
    yield
    cal._examples_cache.clear()


@pytest.fixture(autouse=True)
def _no_published_membership(monkeypatch):
    """Every test here is about the LIVE path — the fallback when no published
    membership can answer. The published path has its own file
    (``test_calibration_examples_membership_994.py``); here it reports absent
    without touching the fake session, so the statement and budget accounting
    below stays the live path's alone."""

    async def _absent(db, **kwargs):
        return None, None, "absent"

    monkeypatch.setattr(cal, "_published_membership_examples", _absent)


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(cal, "_examples_clock", c, raising=False)
    return c


def _wall_ms() -> int:
    return int(cal._EXAMPLES_SCOPED_STATEMENT_WALL_S * 1000)


async def _call(db, source="datagolf", *, bucket=6, well_traded=1, limit=5):
    return await cal.calibration_examples(
        db=db, source=source, bucket=bucket, well_traded=well_traded, limit=limit
    )


async def _bounded(coro, seconds: float = 5.0):
    """Fail, never hang: ``asyncio.wait_for`` would itself wait out a cleanup
    that does not return — the very defect the backstop tests look for."""
    task = asyncio.ensure_future(coro)
    done, _ = await asyncio.wait({task}, timeout=seconds)
    if task not in done:
        task.cancel()
        pytest.fail(f"the route did not answer within {seconds}s")
    return task.result()


def _status(res) -> int:
    return getattr(res, "status_code", 200)


def _body(res) -> dict:
    if hasattr(res, "body"):
        import json

        return json.loads(res.body)
    return res


# ---------------------------------------------------------------------------
# The reader defect: DataGolf reaches the canonical branch.
# ---------------------------------------------------------------------------
class TestDataGolfIsSampled:
    async def test_datagolf_returns_its_rows_with_audit_ids(self, clock):
        db = _FakeDB(
            clock,
            rows=[
                _dg_row(77001, 77001000, price=0.64, won=True),
                _dg_row(77002, 77002003, price=0.61, won=False),
            ],
        )
        res = await _call(db)
        assert _status(res) == 200
        body = _body(res)
        assert body["note"] is None
        # Random order (the single statement's ORDER BY RANDOM()), so compared as a set.
        assert sorted(
            (e["market_id"], e["outcome_id"], e["result"]) for e in body["examples"]
        ) == [(77001, 77001000, "Yes"), (77002, 77002003, "No")]
        # Readable columns are unchanged for the drill-in.
        first = next(e for e in body["examples"] if e["market_id"] == 77001)
        assert first["market_name"] == "Test Open 77001 - Make the Cut"
        assert first["price"] == 0.64

    async def test_datagolf_is_no_longer_the_unsupported_fallback(self, clock):
        res = await _call(_FakeDB(clock))
        body = _body(res)
        assert body["note"] != "No examples available for this source."
        # An empty canonical bucket says so in the existing empty-bucket words.
        assert body["note"] == "No examples matched this bucket for the current view."

    async def test_the_sample_reads_the_canonical_chain_scoped_to_datagolf(self, clock):
        db = _FakeDB(clock)
        await _call(db, well_traded=1)
        from app.tasks import precompute_calibration as pc

        roster_sql, roster_params = db.statements[1]
        assert cal._EXAMPLES_SCOPED_MARKET_INFO_EXTRA in roster_sql
        assert roster_params == {"source": "datagolf"}
        sample_sql, params = db.statements[-1]
        assert "FROM deduped d" in sample_sql
        assert "LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) = :bucket" in sample_sql
        # A chunk replays the chain on a frozen roster of this source's markets.
        assert pc.VM_ROSTER_MARKET_INFO_EXTRA in sample_sql
        assert "frozen_vm_roster AS" in sample_sql
        assert params[pc.VM_ROSTER_MARKET_IDS_PARAM] == [1]
        # The page's default cohort: the price moved off its open.
        assert "AND d.price_moved = true" in sample_sql
        assert params["source"] == "datagolf"

    async def test_the_all_outcomes_toggle_drops_only_the_cohort_clause(self, clock):
        db = _FakeDB(clock)
        await _call(db, well_traded=0)
        sample_sql, _ = db.statements[-1]
        assert "d.price_moved = true" not in sample_sql
        assert "frozen_vm_roster AS" in sample_sql

    async def test_sampling_names_the_live_basis_and_unverified_membership(self, clock):
        body = _body(await _call(_FakeDB(clock), well_traded=1))
        s = body["sampling"]
        assert s["basis"] == "live_canonical_population"
        assert s["scope"] == "source_markets"
        assert s["cohort"] == "price_moved"
        assert s["published_generation_membership"] == "unverified"
        body0 = _body(await _call(_FakeDB(clock), well_traded=0))
        assert body0["sampling"]["cohort"] == "all"

    async def test_a_success_is_cached(self, clock):
        db = _FakeDB(clock, rows=[_dg_row(1, 1000, price=0.65, won=True)])
        await _call(db)
        n = len(db.statements)
        await _call(db)
        assert len(db.statements) == n


class TestRosterChunks:
    """#994 cost: the scoped chain runs per frozen roster chunk, never whole."""

    @staticmethod
    def _roster(spec):
        return [_Row(market_id=m, vm_id=vm, is_grouped=vm.startswith("g:")) for m, vm in spec]

    def test_a_virtual_question_is_never_split_and_the_cap_holds(self, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_CHUNK_MARKETS", 3)
        roster = self._roster([
            (1, "m:1"), (2, "g:x"), (3, "m:3"), (4, "g:x"), (5, "m:5"), (6, "g:x"),
            (7, "m:7"), (8, "g:big"), (9, "g:big"), (10, "g:big"), (11, "g:big"),
        ])
        chunks = cal._examples_roster_chunks(roster)
        flat = [r.market_id for c in chunks for r in c]
        assert sorted(flat) == list(range(1, 12)), "every market exactly once"
        for vm in ("g:x", "g:big"):
            holding = [i for i, c in enumerate(chunks) if any(r.vm_id == vm for r in c)]
            assert len(holding) == 1, f"{vm} was split across chunks {holding}"
        # Only a question larger than the cap may exceed it, alone.
        for c in chunks:
            assert len(c) <= 3 or {r.vm_id for r in c} == {"g:big"}

    def test_an_empty_roster_runs_no_chunk(self):
        assert cal._examples_roster_chunks([]) == []

    async def test_the_sample_is_drawn_once_from_every_chunk(self, clock, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_CHUNK_MARKETS", 1)
        rows = [_dg_row(m, m * 10, price=0.65, won=m % 2 == 0) for m in (11, 12, 13)]
        db = _FakeDB(clock, rows=rows)
        seen = set()
        for _ in range(40):
            cal._examples_cache.clear()
            body = _body(await _call(db, limit=2))
            ids = [e["outcome_id"] for e in body["examples"]]
            assert len(ids) == 2 and len(set(ids)) == 2, "without replacement, at the limit"
            seen.update(ids)
        # Three chunks, one statement each, every one reachable by the sample.
        assert seen == {110, 120, 130}
        chunk_params = [p for _, p in db.statements if p and "vm_roster_market_ids" in p]
        assert [p["vm_roster_market_ids"] for p in chunk_params[:3]] == [[11], [12], [13]]

    async def test_every_chunk_is_armed_and_a_slow_one_is_a_503(self, clock, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_CHUNK_MARKETS", 1)
        rows = [_dg_row(m, m * 10, price=0.65, won=True) for m in (11, 12, 13)]
        wall = cal._EXAMPLES_SCOPED_STATEMENT_WALL_S
        db = _FakeDB(clock, durations=[0.0, 0.0, wall * 0.5, wall * 0.6], rows=rows)
        start = clock.t
        res = await _call(db)
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_query_timeout"
        assert db.armed[:3] == [_wall_ms(), _wall_ms(), _wall_ms()]
        assert db.armed[3] == _wall_ms() - int(wall * 0.5 * 1000)
        assert clock.t - start <= wall + 1e-9


class TestControlsAreUnchanged:
    @pytest.mark.parametrize("source", ["kalshi", "polymarket"])
    async def test_kalshi_and_polymarket_keep_the_unscoped_chain(self, clock, source):
        db = _FakeDB(clock)
        body = _body(await _call(db, source=source))
        # No closure check, no budget armed: their path is not this change's.
        assert db.armed == []
        assert len(db.statements) == 1
        assert cal._EXAMPLES_SCOPED_MARKET_INFO_EXTRA not in db.statements[0][0]
        assert body["sampling"]["scope"] == "full_population"

    @pytest.mark.parametrize("wt,expect", [(1, True), (0, False)])
    async def test_kalshi_cohort_toggle_still_selects_price_moved(self, clock, wt, expect):
        db = _FakeDB(clock)
        await _call(db, source="kalshi", well_traded=wt)
        assert ("AND d.price_moved = true" in db.statements[0][0]) is expect

    async def test_an_unknown_source_keeps_its_note(self, clock):
        db = _FakeDB(clock)
        body = _body(await _call(db, source="made_up"))
        assert body["examples"] == [] and body["sampling"] is None
        assert body["note"] == "No examples available for this source."
        assert db.statements == []


# ---------------------------------------------------------------------------
# The budget defect: one wall for the whole request.
# ---------------------------------------------------------------------------
class TestOneRequestBudget:
    async def test_roots_reproduction_two_statements_under_a_per_statement_cap(self, clock):
        """Root's control, unscaled. Each statement takes 60% of the wall — under
        the old 20 s per-statement cap — so the old draft answered 200 at 120% of
        the wall. Now the sample is armed with the 40% the closure check left,
        the server cancels it, and the route answers 503 inside the wall."""
        each = cal._EXAMPLES_SCOPED_STATEMENT_WALL_S * 0.6
        assert each * 1000 < 20000  # the old cap would have let both run
        db = _FakeDB(clock, durations=[each, each], rows=[_dg_row(1, 1000, price=0.65, won=True)])
        start = clock.t
        res = await _call(db)
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_query_timeout"
        assert clock.t - start <= cal._EXAMPLES_SCOPED_STATEMENT_WALL_S + 1e-9

    async def test_every_statement_is_armed_with_what_is_left(self, clock):
        db = _FakeDB(clock, durations=[5.0, 3.0, 2.0], rows=[_dg_row(1, 1000, price=0.65, won=True)])
        res = await _call(db)
        assert _status(res) == 200
        # Closure check, roster read, one chunk: each armed with what is LEFT.
        assert db.armed == [_wall_ms(), _wall_ms() - 5000, _wall_ms() - 8000]

    async def test_time_spent_before_the_first_statement_counts(self, clock, monkeypatch):
        """The wall starts at handler entry, not at the first statement: a slow
        session checkout is spent out of the same budget."""

        class SlowCheckout(_OwnedCM):
            async def __aenter__(self):
                clock.advance(4.0)
                return await super().__aenter__()

        monkeypatch.setattr(cal, "_owned_examples_session", lambda db: SlowCheckout(db))
        db = _FakeDB(clock, durations=[0.0, 0.0, 0.0])
        await _call(db)
        assert db.armed[0] == _wall_ms() - 4000

    async def test_time_building_sql_between_statements_counts(self, clock, monkeypatch):
        """Rendering the chain is spent too: the chunk is armed with what the
        closure check, the roster read AND the rendering left."""
        from app.tasks import precompute_calibration as pc

        orig = pc._calibration_population_ctes

        def slow_ctes(*a, **k):
            clock.advance(2.0)
            return orig(*a, **k)

        monkeypatch.setattr(pc, "_calibration_population_ctes", slow_ctes)
        db = _FakeDB(clock, durations=[0.0, 0.0, 0.0])
        await _call(db)
        # Roster SQL is rendered after its arm; chunk SQL before the chunk's.
        assert db.armed == [_wall_ms(), _wall_ms(), _wall_ms() - 4000]

    async def test_a_spent_budget_never_starts_the_sample(self, clock):
        db = _FakeDB(clock, durations=[cal._EXAMPLES_SCOPED_STATEMENT_WALL_S - 0.05])
        res = await _call(db)
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_query_timeout"
        assert len(db.statements) == 1  # the closure check only

    async def test_a_closure_check_over_budget_is_a_503(self, clock):
        db = _FakeDB(clock, durations=[cal._EXAMPLES_SCOPED_STATEMENT_WALL_S + 5])
        res = await _call(db)
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_query_timeout"
        assert clock.t - 1000.0 <= cal._EXAMPLES_SCOPED_STATEMENT_WALL_S + 1e-9

    async def test_a_timeout_is_not_cached(self, clock):
        db = _FakeDB(clock, durations=[30.0])
        await _call(db)
        n = len(db.statements)
        db.durations = [0.0, 0.0]
        res = await _call(db)
        assert _status(res) == 200
        assert len(db.statements) > n

    async def test_a_real_query_error_is_not_dressed_as_a_timeout(self, clock):
        class Broken(_FakeDB):
            async def execute(self, stmt, params=None):
                if "shares_identity" in str(stmt):
                    raise ValueError("syntax error at or near")
                return await super().execute(stmt, params)

        with pytest.raises(ValueError):
            await _call(Broken(clock))

    async def test_a_shared_identity_refuses_and_is_not_cached(self, clock):
        db = _FakeDB(clock, shares_identity=True)
        res = await _call(db)
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_scope_not_closed"
        assert len(db.statements) == 1  # the sample never ran
        await _call(db)
        assert len(db.statements) == 2


class _Hangs:
    """An owned session whose statement never returns (pool checkout, a lost
    socket). Records whether it was cancelled and whether it was closed."""

    def __init__(self, release: asyncio.Event | None = None):
        self.release = release  # set ⇒ cleanup waits for it (overrun)
        self.cancelled = asyncio.Event()
        self.entered = asyncio.Event()
        self.opened = 0
        self.closed = 0

    async def execute(self, stmt, params=None):
        if str(stmt).strip().startswith("SET LOCAL"):
            return _Result()
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            if self.release is not None:
                await self.release.wait()  # a cleanup that does not come back
            raise


class TestBackstop:
    """What ``statement_timeout`` cannot see: a hang before the server is asked
    (pool checkout), and a cancellation whose cleanup does not return."""

    async def test_a_hang_outside_any_statement_answers_at_the_deadline(self, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 0.05, raising=False)
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 0.5, raising=False)
        owned = _Hangs()
        res = await _bounded(_call(_Untouchable(owned)))
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_deadline"
        assert owned.cancelled.is_set(), "the hung work was never cancelled"
        assert owned.closed == 1, "the sample's own session was not closed"

    async def test_cleanup_after_the_cancel_is_bounded_too(self, monkeypatch):
        """``asyncio.wait_for`` would wait for this cleanup however long it took."""
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 0.05, raising=False)
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 0.1, raising=False)
        release = asyncio.Event()
        owned = _Hangs(release)
        t0 = time.monotonic()
        res = await _bounded(_call(_Untouchable(owned)))
        elapsed = time.monotonic() - t0
        assert _status(res) == 503
        assert _body(res)["reason"] == "examples_deadline"
        # Deadline + cleanup bound is 0.15 s; 3 s only rules out "waited it out".
        assert elapsed < 3.0
        # Overrun: the sample is still unwinding — on ITS session, held by a
        # strong reference — and closes that session when it gets there.
        assert owned.closed == 0
        live = [t for t in getattr(cal, "_examples_inflight", ()) if not t.done()]
        assert len(live) == 1
        release.set()
        await asyncio.wait(live, timeout=2)
        assert owned.closed == 1
        assert not getattr(cal, "_examples_inflight", ())

    def test_the_bounds_fit_inside_the_router(self):
        assert cal._EXAMPLES_SCOPED_STATEMENT_WALL_S < cal._EXAMPLES_SCOPED_DEADLINE_S
        assert cal._EXAMPLES_SCOPED_DEADLINE_S + cal._EXAMPLES_SCOPED_CLEANUP_S < 30.0


class TestOwnership:
    """Root's parent-cancel review (2026-10-15, b21169716d): cancelling the
    REQUEST while it waited left the sample running on the request's session.
    The request now owns its sample on every exit, and the sample owns its
    session."""

    async def test_the_scoped_branch_never_touches_the_request_session(self, clock):
        owned = _FakeDB(clock, rows=[_dg_row(1, 1000, price=0.65, won=True)])
        res = await _call(_Untouchable(owned))
        assert _status(res) == 200
        # Closure check + roster + one chunk, all on the OWNED one.
        assert len(owned.statements) == 3
        assert (owned.opened, owned.closed) == (1, 1)

    async def test_roots_parent_cancel_control_on_the_helper(self, monkeypatch):
        """Root's control verbatim in shape: cancel the parent while it waits."""
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 10, raising=False)
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 0.1, raising=False)
        entered = asyncio.Event()
        child = None

        async def work():
            nonlocal child
            child = asyncio.current_task()
            entered.set()
            await asyncio.Event().wait()

        parent = asyncio.create_task(cal._within_examples_deadline(work, time.monotonic()))
        await entered.wait()
        parent.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parent
        pending = not child.done()
        if pending:  # leave nothing running whatever the verdict
            child.cancel()
            await asyncio.wait({child}, timeout=1)
        assert not pending, "the request exited while its sample was still running"

    async def test_a_cancelled_request_cancels_and_closes_its_sample(self, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 10, raising=False)
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 0.5, raising=False)
        owned = _Hangs()
        parent = asyncio.create_task(_call(_Untouchable(owned)))
        await asyncio.wait_for(owned.entered.wait(), timeout=2)
        parent.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parent
        assert owned.cancelled.is_set()
        assert owned.closed == 1, "the sample's session outlived the cancelled request"
        assert not [t for t in getattr(cal, "_examples_inflight", ()) if not t.done()]

    async def test_a_cancelled_request_with_an_overrunning_cleanup_is_bounded(self, monkeypatch):
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 10, raising=False)
        monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 0.1, raising=False)
        release = asyncio.Event()
        owned = _Hangs(release)
        parent = asyncio.create_task(_call(_Untouchable(owned)))
        await asyncio.wait_for(owned.entered.wait(), timeout=2)
        t0 = time.monotonic()
        parent.cancel()
        done, _ = await asyncio.wait({parent}, timeout=3)
        elapsed = time.monotonic() - t0
        assert parent in done and parent.cancelled(), "the request did not exit"
        assert elapsed < 3.0
        assert owned.cancelled.is_set()
        # Still unwinding, on its OWN session, strongly referenced; the request
        # session (``_Untouchable``) was never executed on.
        live = [t for t in getattr(cal, "_examples_inflight", ()) if not t.done()]
        assert len(live) == 1 and owned.closed == 0
        release.set()
        await asyncio.wait(live, timeout=2)
        assert owned.closed == 1

    async def test_the_owned_session_binds_the_request_sessions_engine(self, monkeypatch):
        """A NEW session on the request's engine — never the request session."""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        monkeypatch.undo()  # the real factory, not the fixture's stand-in
        engine = create_async_engine("postgresql+asyncpg://nobody@127.0.0.1:1/none")
        try:
            request = AsyncSession(bind=engine)
            owned = cal._owned_examples_session(request)
            assert owned is not request
            assert owned.bind is engine
            await owned.close()
            await request.close()
        finally:
            await engine.dispose()


class TestLogLinesCarryNoRequestValues:
    """CodeQL py/log-injection (#4044–#4048) on PR #11072: the scoped branch's
    warnings interpolated the request's ``source`` and ``bucket``. A log line in
    this handler carries trusted literals only; ``reason`` is chosen from two
    in-code literals and may stay."""

    def test_no_logger_call_in_the_handler_reads_source_or_bucket(self):
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(cal.calibration_examples)))
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "logger"
        ]
        assert len(calls) >= 3, "the scoped branch's three warnings went missing"
        tainted = sorted({
            (c.lineno, name.id)
            for c in calls
            for arg in [*c.args, *(k.value for k in c.keywords)]
            for name in ast.walk(arg)
            if isinstance(name, ast.Name) and name.id in {"source", "bucket"}
        })
        assert tainted == [], f"request-derived value in a log line: {tainted}"
