"""#10693 — the Kalshi consumer writes each price phase through its run's pipeline.

THE SHIP. Coherent Kalshi game prices arrive sooner: a phase's consecutive rows
of one shape become one driver round trip on the supported SQLAlchemy/asyncpg
pair (`app/utils/kalshi_price_pipeline.py`, whose own tests own that path).

WHAT THIS FILE PROVES — the consumer's half, against the FROZEN pre-#10693
flush (`fixtures/kalshi_flush_before_10693.py.txt`, never edited to match):

1. The price loop's span: `flush_prices` writes prices only through its one
   `prices.phase` hand-off (no direct price execute remains), and each returned
   row keeps the frozen loop's unchanged-quote skip and market invalidation.
   (The earlier whole-flush structural identity was retired on 10/10; the
   persistent #10090 stamp owner made it irreducible. Part 2 carries the
   whole-flush comparison.)
2. Executed: the current and the frozen flush, each on its own copy of the
   #10655 rig, produce the same return values, transaction trace, commits,
   surviving buffer, stats and market invalidations — plain, settled refusal,
   failure, lock timeout, cancellation, newer tick, unchanged quotes, mixed
   book shapes and the final drain. One reviewed reorder is read back to the
   frozen order first: #10090 starts a phase's event refresh before its MARKET
   publication (`_with_frozen_market_order`).
3. The hand-off: `_KalshiPriceOwner.phase` issues the frozen loop's statements,
   binds and order on a session with no driver cursor — the ordinary path every
   pair takes for singletons and every unsupported pair takes for runs.
4. Lifetime: installed lazily, at most once per run, on the engine the run
   lent; removed before that engine is disposed, on a recycle and on a hard
   cancellation; a run that writes no price installs nothing; a failed or
   cancelled phase leaves the owner closable.

Real row locks and the supported pair's pipelined path:
`tests/integration/test_kalshi_price_lock_budget_pg_10661.py`.
"""

import ast
import asyncio
import contextlib
import inspect
from types import SimpleNamespace

import pytest

import app.tasks.kalshi_ws as kalshi_task
import app.utils.kalshi_price_pipeline as pipeline_mod
from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)
from tests._kalshi_price_session import (
    bind_session,
    consumer_engine,
    pre_10693_write_phase,
    returned,
)
from tests.kalshi_price_statement_support import (
    FROZEN_FLUSH,
    flush_ast,
    frozen_flush_ast,
    pipeline_handoff,
)
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_price_lock_budget_10661 import with_drain

pytestmark = pytest.mark.asyncio

FROZEN_LOOP_TARGET = "(outcome_id, (prob, yes_bid, yes_ask))"


# ------------------------------------- 1. the price loop's hand-off ----
#
# Retired 10/10 (Root 0416Z, #10693 option A): the whole-flush structural
# identity ("after removing each reviewed change, the flush differs from the
# frozen one in exactly one statement"). The run's persistent stamp owner
# (`prices.stamping` / `join_stamp`, `stamp_admit`) replaced most of the
# statements that reduction removed, so it could no longer be reduced, and its
# mutation controls passed only because the unmutated reduction already failed.
# What #10693 changed is the price loop; that span is asserted here, part 3
# executes it, and part 2 compares the whole flush's behaviour.

FROZEN_HANDOFF = (
    "contextlib.aclosing(prices.phase(session, phase, force_observation=final_drain))"
)


def _frozen_loop():
    return next(
        n for n in ast.walk(frozen_flush_ast())
        if isinstance(n, ast.For) and ast.unparse(n.target) == FROZEN_LOOP_TARGET
    )


def _price_executes(node):
    """Every direct execute of the price statement under `node`."""
    return [
        n for n in ast.walk(node)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "session.execute"
        and n.args and "KALSHI_PRICE_STATEMENTS" in ast.unparse(n.args[0])
    ]


def _only(node, predicate):
    (found,) = [n for n in ast.walk(node) if predicate(n)]
    return ast.dump(found)


def _market_change(node):
    return _only(node, lambda n: isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "queue_market_change")


def _unchanged_skip(node):
    return _only(node, lambda n: isinstance(n, ast.If)
                 and ast.unparse(n.test) == "not row.quote_moved")


def _assert_prices_only_through_the_handoff(flush):
    handoffs = [
        n for n in ast.walk(flush)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "prices.phase"
    ]
    assert len(handoffs) == 1, "the flush has more than one price hand-off"
    handoff = pipeline_handoff(flush)
    assert ast.unparse(handoff.items[0].context_expr) == FROZEN_HANDOFF
    assert _price_executes(flush) == [], "a price write bypasses the pipeline"
    # Per returned row, the frozen loop's own publication rule, unchanged.
    loop = _frozen_loop()
    assert _unchanged_skip(handoff) == _unchanged_skip(loop)
    assert _market_change(handoff) == _market_change(loop)


async def test_the_flush_writes_prices_only_through_the_pipeline():
    # Non-vacuity: the detector sees the frozen loop's one direct write.
    assert len(_price_executes(_frozen_loop())) == 1
    _assert_prices_only_through_the_handoff(flush_ast())


@pytest.mark.parametrize("mutation", ["direct_execute", "invalidation", "unchanged_skip"])
async def test_strawman_a_changed_price_span_is_seen(mutation):
    flush = flush_ast()
    _assert_prices_only_through_the_handoff(flush)  # the unmutated tree passes
    handoff = pipeline_handoff(flush)
    if mutation == "direct_execute":
        (write,) = [s for s in _frozen_loop().body if isinstance(s, ast.Assign)
                    and ast.unparse(s.targets[0]) == "result"]
        handoff.body.insert(0, write)
    elif mutation == "invalidation":
        call = next(n for n in ast.walk(handoff) if isinstance(n, ast.Call)
                    and ast.unparse(n.func) == "queue_market_change")
        (source,) = [kw for kw in call.keywords if kw.arg == "source"]
        source.value = ast.Constant("polymarket")
    else:
        skip = next(n for n in ast.walk(handoff) if isinstance(n, ast.If)
                    and ast.unparse(n.test) == "not row.quote_moved")
        skip.body = [s for s in skip.body if not isinstance(s, ast.Continue)]
    with pytest.raises(AssertionError):
        _assert_prices_only_through_the_handoff(flush)


async def test_the_frozen_fixture_is_the_pre_10693_flush():
    """The comparator's provenance: its header names the frozen commit."""
    assert "2cafa8f56a" in FROZEN_FLUSH.read_text().splitlines()[0]
    assert ast.unparse(_frozen_loop().target) == FROZEN_LOOP_TARGET


# ------------------------------------------ 2. executed, same as frozen ----


def _pair(**controls):
    """(current, frozen) — two independent rigs, the second on the frozen flush."""
    current, frozen = rig(**controls), rig(**controls)
    exec(compile(FROZEN_FLUSH.read_text(), str(FROZEN_FLUSH), "exec"), frozen.ns)
    frozen.flush = frozen.ns["flush_prices"]
    for r in (current, frozen):
        # Market invalidations are part of the observation, in trace order.
        def _queue(_session, *, _trace=r.trace, **kwargs):
            _trace.append((
                "queue", kwargs["market_id"], kwargs["source"],
                tuple(sorted(kwargs["outcome_observed_at"].items())),
            ))

        r.ns["queue_market_change"] = _queue
    return current, frozen


def _observe(r, results):
    return {
        "results": results,
        "trace": list(r.trace),
        "committed": list(r.committed),
        "batch": dict(r.batch),
        "stats": dict(r.stats),
    }


# #10090 (2959d4bc51) starts a phase's event refresh before awaiting its MARKET
# notification. The only reviewed reorder: a publish moves back over the
# receipt/refresh entries directly before it, nothing else. The frozen trace
# has every publish right after its own commit, so a publish that lands
# anywhere else, a missing one, or one past a write still differs.
STAMP_BEFORE_PUBLISH = {"receipt", "refresh"}


def _with_frozen_market_order(trace):
    trace = list(trace)
    for i, entry in enumerate(trace):
        if entry[0] != "publish":
            continue
        j = i - 1
        while j >= 0 and trace[j][0] in STAMP_BEFORE_PUBLISH:
            j -= 1
        trace[j + 1:i + 1] = [entry] + trace[j + 1:i]
    return trace


def _frozen_order(observation):
    return {**observation, "trace": _with_frozen_market_order(observation["trace"])}


async def _plain(r):
    r.release.set()
    return [await asyncio.wait_for(r.flush(), 2)]


async def _twice(r, between):
    r.release.set()
    first = await asyncio.wait_for(r.flush(), 2)
    between(r)
    return [first, await asyncio.wait_for(r.flush(), 2)]


async def _cancelled(r):
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    r.release.set()
    return ["cancelled", await asyncio.wait_for(r.flush(), 2)]


async def _newer_tick(r):
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)
    r.batch[3] = (.8, .79, .81)
    r.release.set()
    return [await asyncio.wait_for(task, 2), await asyncio.wait_for(r.flush(), 2)]


async def _final_drain_waits(r):
    r.release.set()
    task = asyncio.create_task(r.flush(final_drain=True))
    for _ in range(100):
        if ("lock-wait", 1) in r.trace:
            break
        await asyncio.sleep(0.01)
    r.lock_released.set()
    return [await asyncio.wait_for(task, 2)]


async def _drain(r):
    drain = with_drain(r)
    r.release.set()
    r.lock_released.set()
    await asyncio.wait_for(drain(), 2)
    return ["drained"]


def _lock_released_after_retry_delay(r):
    # #10090 (a5b06f85fa): a lock-failed cohort now waits out the failed-retry
    # delay before its next attempt; the frozen flush retried on the next call.
    # The second flush here stands for one after that delay, so the retry itself
    # is compared. The delay is guarded by test_kalshi_lock_retry_isolation_10090.
    r.lock_released.set()
    getattr(r.ns["prices"], "lock_retry_until", {}).clear()


def _reshape(**rows):
    def apply(r):
        for oid, value in rows.items():
            r.batch[int(oid.lstrip("o"))] = value
    return apply


SCENARIOS = {
    "plain": ({}, _plain),
    "settled_refusal": ({"declined": 2}, _plain),
    "unchanged_quotes": ({"unchanged": {2, 9}}, _plain),
    "failure_then_retry": (
        {"failed": 3}, lambda r: _twice(r, lambda r: r.control.update(failed=None)),
    ),
    "lock_timeout_then_retry": (
        {"locked": {1}}, lambda r: _twice(r, _lock_released_after_retry_delay),
    ),
    "lock_timeout_on_the_second_row_of_a_run": (
        {"locked": {2}}, lambda r: _twice(r, _lock_released_after_retry_delay),
    ),
    "cancellation": ({}, _cancelled),
    "newer_tick_beside_refusal": ({"declined": 2}, _newer_tick),
    "final_drain_waits_for_the_lock": ({"locked": {1}}, _final_drain_waits),
    "drain": ({"locked": {1}}, _drain),
}

LOCK_RETRY_SCENARIOS = frozenset({
    "lock_timeout_then_retry", "lock_timeout_on_the_second_row_of_a_run",
})

#: Book shapes the pipeline groups by: a no-book run, a full/no-book split and a
#: half book (written as no book, #8753), each applied before the first flush.
SHAPES = {
    "full_books": {},
    "no_book_run": {"o1": (.6, None, None), "o2": (.4, None, None)},
    "split_run": {"o2": (.4, None, None)},
    "half_book": {"o1": (.6, .59, None), "o2": (.4, None, .41)},
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
async def test_the_flush_behaves_exactly_as_the_frozen_flush(scenario, shape):
    controls, drive = SCENARIOS[scenario]
    current, frozen = _pair(**controls)
    observed = []
    for r in (current, frozen):
        _reshape(**SHAPES[shape])(r)
        observed.append(_observe(r, await drive(r)))
    current = _frozen_order(observed[0])
    if scenario in LOCK_RETRY_SCENARIOS:
        # #10090 (a5b06f85fa): a handled lock no longer returns False to slow the
        # whole cadence; its cohort holds its own retry delay. The only reviewed
        # difference: the lock-failed flush's own result.
        assert (current["results"][0], observed[1]["results"][0]) == (True, False)
        current = {**current, "results": [False, *current["results"][1:]]}
    assert current == observed[1]
    # Non-vacuity: the scenario wrote prices through the price statement.
    assert any(t[0] == "write" for t in observed[0]["trace"]), observed[0]


async def test_strawman_the_comparator_sees_a_dropped_invalidation():
    """A pipeline consumer that forgot one market invalidation would differ."""
    current, frozen = _pair()
    results = [await _plain(r) for r in (current, frozen)]
    dropped = [t for t in current.trace if t[0] == "queue"][0]
    current.trace.remove(dropped)
    assert _observe(current, results[0]) != _observe(frozen, results[1])


def _displace_first_publish(trace, where):
    publish = next(t for t in trace if t[0] == "publish")
    trace.remove(publish)
    if where == "dropped":
        return
    commit = trace.index(("commit", publish[1]))
    if where == "before_commit":
        trace.insert(commit, publish)
    else:  # past the next phase's first write
        nxt = next(i for i in range(commit, len(trace)) if trace[i][0] == "write")
        trace.insert(nxt + 1, publish)


@pytest.mark.parametrize("where", ["dropped", "before_commit", "past_next_write"])
async def test_strawman_the_reviewed_reorder_cannot_hide_a_moved_publish(where):
    """Only publish-after-its-own-stamp is accepted; every other move differs."""
    current, frozen = _pair()
    results = [await _plain(r) for r in (current, frozen)]
    assert _frozen_order(_observe(current, results[0])) == _observe(frozen, results[1])
    _displace_first_publish(current.trace, where)
    assert _frozen_order(_observe(current, results[0])) != _observe(frozen, results[1])


# --------------------------------------------------- 3. the hand-off ----


class _Recording:
    """Records every price execute; returns a row only for a landed write."""

    def __init__(self, landed, unchanged=()):
        self.landed = set(landed)
        self.unchanged = set(unchanged)
        self.executes = []

    async def execute(self, stmt, params=None):
        self.executes.append((stmt, dict(params)))
        oid = params["kalshi_outcome_id"]
        rows = (
            [returned(oid, market_id=oid * 10, quote_moved=oid not in self.unchanged)]
            if oid in self.landed else []
        )
        return SimpleNamespace(rowcount=len(rows), all=lambda: list(rows))


PHASES = [
    {7: (.5, .49, .51)},
    {7: (.5, None, None)},
    {1: (.6, .59, .61), 2: (.4, .39, .41), 3: (.7, None, None),
     4: (.3, .2, None), 5: (.2, .19, .21)},
    {1: (.6, None, None), 2: (.4, None, None), 3: (.7, None, None)},
]


@pytest.mark.parametrize("phase", PHASES, ids=lambda p: "-".join(map(str, p)))
async def test_the_owner_issues_the_frozen_loops_statements_in_order(phase):
    landed = [oid for oid in phase if oid != 2]
    frozen_session, owner_session = _Recording(landed, {3}), _Recording(landed, {3})
    frozen_stats = {"quotes_unchanged": 0}
    queued = []
    declined, written = await pre_10693_write_phase(
        frozen_session, phase, stats=frozen_stats,
        queue_market_change=lambda _s, **kw: queued.append(kw),
    )

    owner = kalshi_task._KalshiPriceOwner()
    bind_session(owner_session, consumer_engine())
    results = []
    try:
        async with contextlib.aclosing(
            owner.phase(owner_session, phase)
        ) as stream:
            async for result in stream:
                results.append(result)
    finally:
        owner.close()

    assert [(id(s), p) for s, p in owner_session.executes] == [
        (id(s), p) for s, p in frozen_session.executes
    ]
    assert all(
        any(s is t for t in KALSHI_PRICE_STATEMENTS.values())
        for s, _p in owner_session.executes
    )
    assert sum(r.attempted for r in results) == len(phase)
    assert sum(r.attempted - r.rowcount for r in results) == declined
    assert [row.id for r in results for row in r.all()] == written
    assert [
        row.id for r in results for row in r.all() if row.quote_moved
    ] == [next(iter(kw["outcome_observed_at"])) for kw in queued]


async def test_the_owner_binds_each_row_exactly_as_the_factory_does():
    session = _Recording(landed=[1, 2])
    owner = kalshi_task._KalshiPriceOwner()
    bind_session(session, consumer_engine())
    phase = {1: (.6, .59, .61), 2: (.4, None, None)}
    try:
        async with contextlib.aclosing(owner.phase(session, phase)) as s:
            async for _ in s:
                pass
    finally:
        owner.close()
    assert [p for _s, p in session.executes] == [
        kalshi_price_parameters(1, .6, .59, .61),
        kalshi_price_parameters(2, .4, None, None),
    ]


# ------------------------------------------------------ 4. lifetime ----


async def test_the_lifetime_owner_sits_inside_the_engine_owner():
    """Decorator order IS the cleanup order: listener removed, then disposed."""
    tree = ast.parse(inspect.getsource(kalshi_task))
    (consumer,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_kalshi_ws_consumer"
    ]
    assert [ast.unparse(d) for d in consumer.decorator_list] == [
        "owns_consumer_sessions('kalshi')", "_owns_kalshi_price_lifetime",
    ]


async def test_an_owner_that_never_wrote_installs_nothing_and_closes():
    owner = kalshi_task._KalshiPriceOwner()
    owner.close()
    assert owner.pipeline is None


async def test_one_install_per_owner_on_the_sessions_engine():
    engine = consumer_engine()
    owner = kalshi_task._KalshiPriceOwner()
    for oid in (1, 2, 3):
        session = bind_session(_Recording(landed=[oid]), engine)
        async with contextlib.aclosing(
            owner.phase(session, {oid: (.5, None, None)})
        ) as s:
            async for _ in s:
                pass
    first = owner.pipeline
    assert first is not None and first.engine is engine
    assert getattr(engine.sync_engine, pipeline_mod._OWNER) is first
    owner.close()
    assert not hasattr(engine.sync_engine, pipeline_mod._OWNER)


class _Failing(_Recording):
    def __init__(self, exc):
        super().__init__(landed=[1])
        self.exc = exc

    async def execute(self, stmt, params=None):
        if params["kalshi_outcome_id"] == 2:
            raise self.exc
        return await super().execute(stmt, params)


@pytest.mark.parametrize("exc", [RuntimeError("write failed"), asyncio.CancelledError()])
async def test_a_failed_or_cancelled_phase_leaves_the_owner_closable(exc):
    engine = consumer_engine()
    owner = kalshi_task._KalshiPriceOwner()
    session = bind_session(_Failing(exc), engine)
    with pytest.raises(type(exc)):
        async with contextlib.aclosing(
            owner.phase(session, {1: (.5, None, None), 2: (.4, None, None)})
        ) as s:
            async for _ in s:
                pass
    owner.close()  # raises if a phase were still counted active
    assert not hasattr(engine.sync_engine, pipeline_mod._OWNER)


async def test_a_caller_error_mid_phase_closes_the_phase_before_cleanup():
    """The consumer's own processing error (e.g. queue_market_change raising)
    closes the stream through `aclosing`, so the owner can still close."""
    engine = consumer_engine()
    owner = kalshi_task._KalshiPriceOwner()
    session = bind_session(_Recording(landed=[1, 2]), engine)
    with pytest.raises(LookupError):
        async with contextlib.aclosing(
            owner.phase(session, {1: (.5, None, None), 2: (.4, None, None)})
        ) as s:
            async for _ in s:
                raise LookupError("caller processing failed")
    owner.close()
    assert not hasattr(engine.sync_engine, pipeline_mod._OWNER)


# The real consumer, over the #2471 rig's fake engine (a real sync half).


async def test_a_run_installs_once_and_removes_the_listener_before_disposal(
    monkeypatch,
):
    from tests import test_ws_consumer_session_lifetime_2471 as lifetime

    installs = []
    real_install = pipeline_mod.install_kalshi_price_pipeline

    def counting(engine):
        installs.append(engine)
        return real_install(engine)

    monkeypatch.setattr(pipeline_mod, "install_kalshi_price_pipeline", counting)
    rig2471 = lifetime._Rig(lifetime.KALSHI_SLATE)
    await lifetime._run_kalshi(
        monkeypatch,
        [lifetime._kalshi_tick("0.40", "0.44"), lifetime._kalshi_tick("0.50", "0.54")],
        rig2471,
    )
    (engine,) = rig2471.engines
    assert rig2471.writes, "no price was written; the run proves nothing"
    assert installs and all(e is engine for e in installs)
    assert engine.pipeline_at_dispose == [None], (
        "the price listener was still installed when the engine was disposed"
    )


async def test_a_hard_cancelled_run_removes_the_listener_before_disposal(
    monkeypatch,
):
    from tests import test_ws_consumer_session_lifetime_2471 as lifetime

    rig2471 = lifetime._Rig(lifetime.KALSHI_SLATE)
    task = asyncio.create_task(lifetime._run_kalshi(
        monkeypatch, [lifetime._kalshi_tick("0.40", "0.44")], rig2471, recycle=30,
    ))
    for _ in range(200):
        if rig2471.writes:
            break
        await asyncio.sleep(0.01)
    assert rig2471.writes, "no flush landed before the cancel"
    (engine,) = rig2471.engines
    assert getattr(engine.sync_engine, pipeline_mod._OWNER, None) is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert engine.disposed == 1
    assert engine.pipeline_at_dispose == [None]


async def test_a_run_that_writes_no_price_installs_nothing(monkeypatch):
    from tests import test_ws_consumer_session_lifetime_2471 as lifetime

    installs = []
    monkeypatch.setattr(
        pipeline_mod, "install_kalshi_price_pipeline",
        lambda engine: installs.append(engine),
    )
    rig2471 = lifetime._Rig(lifetime.KALSHI_SLATE)
    await lifetime._run_kalshi(monkeypatch, [], rig2471, recycle=0.2)
    assert rig2471.calls, "the run opened no session; nothing was exercised"
    assert installs == [] and rig2471.writes == []
    (engine,) = rig2471.engines
    assert engine.pipeline_at_dispose == [None]


async def test_an_empty_batch_returns_before_any_phase_is_planned():
    """The lab's first-phase invocation assumes no empty phase reaches the
    pipeline: the flush returns on an empty batch before planning phases."""
    flush = flush_ast()
    returns_early = next(
        n for n in ast.walk(flush)
        if isinstance(n, ast.If) and ast.unparse(n.test) == "not batch"
    )
    planned = next(
        n for n in ast.walk(flush)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "linked_first_phases"
    )
    assert any(isinstance(s, ast.Return) for s in returns_early.body)
    assert returns_early.lineno < planned.lineno
    batch = {1: "a", 3: "c", 9: "z", 2: "b"}
    for markets in ({1: 10, 2: 10, 3: 20, 9: 90}, {1: 10}):
        assert all(kalshi_task.linked_first_phases(batch, markets, {1: 100, 3: 200}))
