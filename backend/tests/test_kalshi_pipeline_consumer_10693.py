"""#10693 — the Kalshi consumer writes each price phase through its run's pipeline.

THE SHIP. Coherent Kalshi game prices arrive sooner: a phase's consecutive rows
of one shape become one driver round trip on the supported SQLAlchemy/asyncpg
pair (`app/utils/kalshi_price_pipeline.py`, whose own tests own that path).

WHAT THIS FILE PROVES — the consumer's half, against the FROZEN pre-#10693
flush (`fixtures/kalshi_flush_before_10693.py.txt`, never edited to match):

1. After removing the five exact, independently reviewed #10702 observer
   statements and the exact #10090 flush budget (one statement, one keyword),
   `flush_prices` differs in exactly ONE statement, the price loop. The 500 ms phase budget, 55P03-only continuation,
   pending-debt grouping, newest-tick retention, commit-before-publication,
   receipts and the timeout-free final drain are the same code, not a rewrite.
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


# -------------------------------------------- 1. one statement changed ----


def _without_docstring(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        fn.body = body[1:]
    return fn


def _replace_statement(fn, predicate, replacement):
    for parent in ast.walk(fn):
        for _field, value in ast.iter_fields(parent):
            if isinstance(value, list):
                for i, stmt in enumerate(value):
                    if isinstance(stmt, ast.stmt) and predicate(stmt):
                        value[i] = replacement
                        return
    raise AssertionError("statement not found")


def _frozen_loop():
    return next(
        n for n in ast.walk(frozen_flush_ast())
        if isinstance(n, ast.For) and ast.unparse(n.target) == FROZEN_LOOP_TARGET
    )


# #10702 adds optional observers around the transaction. Exclude only these
# exact accepted ASTs, never arbitrary `if exact_trace` blocks: a changed body,
# exception guard, or price/commit operation must still fail this comparison.
TRACE_OBSERVERS = (
    'exact_trace = getattr(tail_receipts, "exact_trace", None)',
    'written_observations: dict = {}',
    'if exact_trace is not None:\n    with contextlib.suppress(Exception):\n        exact_trace.snapshot(batch_marks.values())',
    'if exact_trace is not None:\n    with contextlib.suppress(Exception):\n        exact_trace.write_failed(\n            [batch_marks[oid] for oid in phase if oid in batch_marks],\n            "LOCK_TIMEOUT" if lock_timed_out else "ROLLED_BACK",\n        )',
    'if exact_trace is not None:\n    with contextlib.suppress(Exception):\n        for oid, observed_at in written_observations.items():\n            exact_trace.committed(batch_marks.get(oid), observed_at)\n        exact_trace.write_failed(\n            [batch_marks[oid] for oid in phase\n             if oid not in written_outcome_ids and oid in batch_marks],\n            "NO_WRITE_UNCHANGED_SETTLED_OR_MISSING",\n        )',
)


def _without_reviewed_repeat_guard(fn):
    # #10090: exclude only the reviewed first-commit accounting statements.
    # The whole original transaction/debt/rollback body remains pinned.
    sources = (
        "first_declined = sum(oid not in prices.committed_outcome_ids and oid not in written_outcome_ids for oid in phase)",
        'stats["settled_declined"] += first_declined',
        'if declined > first_declined:\n    stats["repeat_or_settled_declined"] = stats.get("repeat_or_settled_declined", 0) + declined - first_declined',
        "prices.committed_outcome_ids.update(written_outcome_ids)",
    )
    accepted = {ast.dump(ast.parse(source).body[0]): index for index, source in enumerate(sources)}
    removed = []
    class NormalizeRepeatGuard(ast.NodeTransformer):
        def visit(self, node):
            if isinstance(node, ast.stmt) and ast.dump(node) in accepted:
                index = accepted[ast.dump(node)]
                removed.append(index)
                return ast.parse('stats["settled_declined"] += declined').body[0] if index == 1 else None
            return super().visit(node)
    result = NormalizeRepeatGuard().visit(fn)
    assert sorted(removed) == list(range(len(sources)))
    return result


def _without_reviewed_observers(fn):
    fn = _without_reviewed_repeat_guard(fn)
    accepted = {ast.dump(ast.parse(source).body[0]) for source in TRACE_OBSERVERS}
    snapshot = ast.dump(ast.parse(TRACE_OBSERVERS[2]).body[0])
    # Pin only the writer's snapshot, under the original buffer lock, before
    # another callback can supersede it. The exact hook elsewhere is not approved.
    locks = [node for node in ast.walk(fn) if isinstance(node, ast.AsyncWith)
             and len(node.items) == 1
             and isinstance(node.items[0].context_expr, ast.Name)
             and node.items[0].context_expr.id == "buffer_lock"]
    locations = [(lock, index) for lock in locks
                 for index, statement in enumerate(lock.body)
                 if ast.dump(statement) == snapshot]
    assert len(locations) == 1
    lock, index = locations[0]
    assert index == len(lock.body) - 1 and index > 0
    preceding = lock.body[index - 1]
    assert isinstance(preceding, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "batch_marks"
        for target in preceding.targets
    )
    removed = []

    class RemoveExactObservers(ast.NodeTransformer):
        def visit(self, node):
            if isinstance(node, ast.stmt) and ast.dump(node) in accepted:
                removed.append(ast.dump(node))
                return None
            return super().visit(node)

    result = RemoveExactObservers().visit(fn)
    assert len(removed) == len(accepted) and set(removed) == accepted
    return _without_reviewed_tail_rotation(_without_reviewed_preemption(
        _without_reviewed_budget(_without_reviewed_pipelined_stamps(result))
    ))


# #10090 coalesced stamps: only these exact reviewed controls are removed
# for the frozen serial comparison; every write/commit/publication remains.
PIPELINE_DECLARATIONS = (
    """stamping = None""",
    """stamping_events = set()""",
    """stamping_fresh = set()""",
    """queued_events = set()""",
    """queued_marks = {}""",
    """queued_refresh = False""",
    """cancelled = False""",
    """async def stamp_done(*, cancel=False):
    nonlocal stamping, stamping_events, stamping_fresh
    if stamping is None:
        return
    if cancel and (not stamping.cancelling()):
        stamping.cancel()
    interrupted = None
    while not stamping.done():
        try:
            await asyncio.wait({stamping})
        except asyncio.CancelledError as exc:
            interrupted = exc
            if not stamping.cancelling():
                stamping.cancel()
    task, stamping = (stamping, None)
    fresh, stamping_fresh = (stamping_fresh, set())
    stamping_events = set()
    if task.cancelled() or task.exception() is not None:
        blend_refresher.adopt_pending(fresh)
        if not task.cancelled():
            logger.error('Kalshi WS: blend refresh raised after its write committed', exc_info=task.exception())
    if interrupted is not None:
        raise interrupted""",
    """async def stamp_start():
    nonlocal stamping, stamping_events, stamping_fresh, queued_refresh
    stamping_fresh = set(queued_events)
    stamping_events = stamping_fresh | set(blend_refresher.pending_event_ids())
    with contextlib.suppress(Exception):
        tail_receipts.stage(list(queued_marks.values()))
    stamping = asyncio.create_task(blend_refresher.refresh(stamping_fresh, flush_started=flush_started))
    queued_events.clear()
    queued_marks.clear()
    queued_refresh = False
    await asyncio.sleep(0)""",
    """def keep_queued():
    nonlocal queued_refresh
    blend_refresher.adopt_pending(queued_events)
    queued_events.clear()
    queued_marks.clear()
    queued_refresh = False""",
    """def queue_committed(index, phase, written_outcome_ids, *, registered=None):
    nonlocal queued_refresh
    blend_outcomes = written_outcome_ids if final_drain else (oid for oid in written_outcome_ids if oid not in non_blend_outcome_ids)
    linked_events = event_ids_for_outcomes(event_id_by_outcome, blend_outcomes)
    new_events = linked_events if registered is None else linked_events - registered
    if (index == 0 and registered is None) or new_events:
        queued_events.update(new_events)
        queued_marks.update({oid: batch_marks[oid] for oid in written_outcome_ids if oid in batch_marks and (registered is None or event_id_by_outcome.get(oid) in new_events)})
        queued_refresh = True
    return linked_events""",
)
PIPELINE_HANDLER = """try:
    pass
except asyncio.CancelledError:
    cancelled = True
    raise
finally:
    if cancelled:
        try:
            await stamp_done(cancel=True)
        finally:
            keep_queued()
    else:
        try:
            await stamp_done()
            if queued_refresh:
                await stamp_start()
                await stamp_done()
        except asyncio.CancelledError:
            try:
                await stamp_done(cancel=True)
            finally:
                keep_queued()
            raise"""
PIPELINE_FENCE = (
    """if stamping is not None and stamping.done():
    await stamp_done()
    if queued_refresh:
        await stamp_start()""",
    """if not stamping_events.isdisjoint(event_ids_for_outcomes(event_id_by_outcome, phase.keys())):
    await stamp_done()""",
)
COMMITTED_STAMP_QUEUE = (
    "registered = queue_committed(index, phase, written_outcome_ids)",
    "queue_committed(index, phase, written_outcome_ids, registered=registered)",
)
SERIAL_EVENT_PREFIX = """blend_outcomes = written_outcome_ids if final_drain else (oid for oid in written_outcome_ids if oid not in non_blend_outcome_ids)
linked_events = event_ids_for_outcomes(event_id_by_outcome, blend_outcomes)"""
_STAGE = (
    "with contextlib.suppress(Exception):\n"
    "    tail_receipts.stage(\n"
    "        [batch_marks[oid] for oid in written_outcome_ids if oid in batch_marks]\n"
    "    )\n"
)
PIPELINED_REFRESH = """await stamp_done()
if queued_refresh:
    await stamp_start()"""
SERIAL_REFRESH = (
    _STAGE + "await blend_refresher.refresh(linked_events, flush_started=flush_started)"
)


def _dumps(source):
    return [ast.dump(s) for s in ast.parse(source).body]


def _without_reviewed_pipelined_stamps(fn):
    declarations = {d for source in PIPELINE_DECLARATIONS for d in _dumps(source)}
    kept = [s for s in fn.body if ast.dump(s) not in declarations]
    assert len(kept) == len(fn.body) - len(declarations), (
        "the #10090 stamp declarations are not the exact reviewed ones"
    )
    (handler,) = ast.parse(PIPELINE_HANDLER).body
    tries = [s for s in kept if isinstance(s, ast.Try)
             and any(isinstance(n, ast.For) and ast.unparse(n.target) == "(index, phase)"
                     for n in s.body)]
    assert len(tries) == 1
    (owner,) = tries
    assert [ast.dump(h) for h in owner.handlers] == [ast.dump(h) for h in handler.handlers]
    assert [ast.dump(s) for s in owner.finalbody] == [ast.dump(s) for s in handler.finalbody]
    assert not owner.orelse
    index = kept.index(owner)
    fn.body = kept[:index] + owner.body + kept[index + 1:]
    (loop,) = [n for n in owner.body if isinstance(n, ast.For)]
    # The fences sit right after the budget and the preemption (loop.body[0:2]).
    # Pinning their place keeps those two checks ahead of any stamp await: the
    # later budget/preemption reads run after the fences are gone and could not
    # see a move across them on their own.
    for source in PIPELINE_FENCE:
        expected = _dumps(source)
        matches = [i for i, s in enumerate(loop.body) if ast.dump(s) == expected[0]]
        assert matches == [2], "the same-event stamp fence changed or moved"
        del loop.body[matches[0]]
    for source in COMMITTED_STAMP_QUEUE:
        expected = _dumps(source)
        matches = [i for i, statement in enumerate(loop.body)
                   if ast.dump(statement) == expected[0]]
        assert len(matches) == 1, "the committed or late-bridge stamp queue changed"
        del loop.body[matches[0]]
    branches = [n for n in loop.body if isinstance(n, ast.If)
                and ast.unparse(n.test) == "stamping is None or stamping.done()"]
    assert len(branches) == 2
    for candidate in branches:
        assert [ast.dump(s) for s in candidate.body] == _dumps(PIPELINED_REFRESH)
    # Remove the new early launch and restore serial refresh at its old boundary.
    loop.body.remove(branches[0])
    branch = branches[1]
    serial_branch = ast.parse("if index == 0 or linked_events:\n    pass").body[0]
    serial_branch.body = ast.parse(SERIAL_REFRESH).body
    index = loop.body.index(branch)
    loop.body[index:index + 1] = ast.parse(SERIAL_EVENT_PREFIX).body + [serial_branch]
    return fn


# #10090 adds the flush budget: the planner learns the run's live set, and a
# periodic flush stops STARTING non-live phases once its budget is spent. Only
# these exact ASTs, in these exact places, are excluded: a changed condition, a
# body that touches the buffer, or either piece moved must still fail.
BUDGET_STATEMENT = (
    'if not final_drain and flush_budget_spent(\n'
    '    flush_started, phase, event_id_by_outcome, live_event_ids,\n'
    '    flush_budget,\n'
    '):\n'
    '    stats["budget_deferred"] += sum(len(p) for p in phases[index:])\n'
    '    break'
)
BUDGET_KEYWORD = "live_events=live_event_ids"


def _without_reviewed_budget(fn):
    statement = ast.dump(ast.parse(BUDGET_STATEMENT).body[0])
    (loop,) = [n for n in ast.walk(fn) if isinstance(n, ast.For)
               and ast.unparse(n.target) == "(index, phase)"]
    assert loop.body and ast.dump(loop.body[0]) == statement, (
        "the #10090 budget is not the exact first statement of the phase loop"
    )
    loop.body = loop.body[1:]
    (planner,) = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == "linked_first_phases"]
    kept = [kw for kw in planner.keywords if ast.unparse(kw) != BUDGET_KEYWORD]
    assert len(kept) == len(planner.keywords) - 1, "the planner lost its live set"
    planner.keywords = kept
    return fn


async def test_the_flush_changed_in_exactly_the_price_loop():
    current = _without_reviewed_observers(_without_docstring(flush_ast()))
    handoff = pipeline_handoff(current)
    _replace_statement(current, lambda s: s is handoff, _frozen_loop())
    frozen = _without_docstring(frozen_flush_ast())
    assert ast.dump(current) == ast.dump(frozen), (
        "kalshi_ws.flush_prices changed outside the price loop and reviewed observers; #10693 moves "
        "only the per-row write into the pipeline"
    )


async def test_strawman_any_other_edit_is_seen():
    """The comparison is not vacuous: one changed constant elsewhere fails it."""
    current = _without_reviewed_observers(_without_docstring(flush_ast()))
    handoff = pipeline_handoff(current)
    _replace_statement(current, lambda s: s is handoff, _frozen_loop())
    budget = next(
        n for n in ast.walk(current)
        if isinstance(n, ast.Name) and n.id == "PRICE_PHASE_LOCK_TIMEOUT_MS"
    )
    budget.id = "SOME_OTHER_BUDGET"
    assert ast.dump(current) != ast.dump(_without_docstring(frozen_flush_ast()))


async def test_changed_observer_cannot_hide_a_price_write():
    current = _without_docstring(flush_ast())
    observer = next(
        node for node in ast.walk(current)
        if isinstance(node, ast.If) and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "committed"
            for child in ast.walk(node)
        )
    )
    observer.body.append(ast.parse("price_buffer.clear()").body[0])
    with pytest.raises(AssertionError):
        _without_reviewed_observers(current)


# #10090 live input preempts the non-live tail: one counter before the loop
# and one statement right after the budget. Only these exact ASTs, in these
# exact places, are excluded; anything else in or around them must still fail.
PREEMPT_DECLARATION = "nonlive_started = 0"
PREEMPT_STATEMENT = (
    "if live_event_ids and not final_drain and not any(\n"
    "    event_id_by_outcome.get(oid) in live_event_ids for oid in phase\n"
    "):\n"
    "    if live_preempts_tail(\n"
    "        flush_started, flush_period, nonlive_started, price_buffer,\n"
    "        batch, event_id_by_outcome, live_event_ids,\n"
    "    ):\n"
    '        stats["live_preempted"] += sum(len(p) for p in phases[index:])\n'
    "        break\n"
    "    nonlive_started += 1"
)


def _without_reviewed_preemption(fn):
    (declaration,) = _dumps(PREEMPT_DECLARATION)
    kept = [s for s in fn.body if ast.dump(s) != declaration]
    assert len(kept) == len(fn.body) - 1, "the #10090 preempt counter is not the reviewed one"
    fn.body = kept
    (loop,) = [n for n in ast.walk(fn) if isinstance(n, ast.For)
               and ast.unparse(n.target) == "(index, phase)"]
    assert loop.body and ast.dump(loop.body[0]) == _dumps(PREEMPT_STATEMENT)[0], (
        "the #10090 preemption is not the exact statement after the budget"
    )
    loop.body = loop.body[1:]
    return fn


@pytest.mark.parametrize("mutation", ["body", "condition", "placement"])
async def test_only_the_exact_10090_preemption_is_reviewed(mutation):
    current = _without_docstring(flush_ast())
    (loop,) = [n for n in ast.walk(current) if isinstance(n, ast.For)
               and ast.unparse(n.target) == "(index, phase)"]
    preempt = loop.body[1]
    if mutation == "body":
        preempt.body.insert(0, ast.parse("price_buffer.clear()").body[0])
    elif mutation == "condition":
        preempt.test = preempt.test.values[0]  # the final drain loses its exemption
    else:
        loop.body.remove(preempt)
        loop.body.insert(2, preempt)
    with pytest.raises(AssertionError):
        _without_reviewed_observers(current)


@pytest.mark.parametrize("mutation", ["body", "condition", "placement", "keyword"])
async def test_only_the_exact_10090_budget_is_reviewed(mutation):
    current = _without_docstring(flush_ast())
    (loop,) = [n for n in ast.walk(current) if isinstance(n, ast.For)
               and ast.unparse(n.target) == "(index, phase)"]
    budget = loop.body[0]
    if mutation == "body":
        budget.body.insert(0, ast.parse("price_buffer.clear()").body[0])
    elif mutation == "condition":
        budget.test = budget.test.values[1]  # the final drain loses its exemption
    elif mutation == "placement":
        loop.body.remove(budget)
        loop.body.insert(1, budget)
    else:
        (planner,) = [n for n in ast.walk(current) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name)
                      and n.func.id == "linked_first_phases"]
        planner.keywords = [kw for kw in planner.keywords
                            if kw.arg != "live_events"]
    with pytest.raises(AssertionError):
        _without_reviewed_observers(current)


@pytest.mark.parametrize("mutation", ["argument", "body", "exception_guard", "condition", "placement"])
async def test_only_the_exact_locked_snapshot_hook_is_reviewed(mutation):
    current = _without_docstring(flush_ast())
    approved = ast.dump(ast.parse(TRACE_OBSERVERS[2]).body[0])
    observer = next(node for node in ast.walk(current)
                    if isinstance(node, ast.If) and ast.dump(node) == approved)
    guarded = observer.body[0]
    if mutation == "argument":
        call = guarded.body[0].value
        call.args[0] = ast.parse("input_marks.values()", mode="eval").body
    elif mutation == "body":
        guarded.body.append(ast.parse("price_buffer.clear()").body[0])
    elif mutation == "exception_guard":
        guarded.items[0].context_expr.args[0].id = "BaseException"
    elif mutation == "condition":
        observer.test = ast.parse("exact_trace", mode="eval").body
    else:
        lock = next(node for node in ast.walk(current)
                    if isinstance(node, ast.AsyncWith) and observer in node.body)
        lock.body.remove(observer)
        current.body.append(observer)
    with pytest.raises(AssertionError):
        _without_reviewed_observers(current)


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


# #10090 fairness: only this exact call, under the original removal lock.
TAIL_ROTATION_CALL = """if live_event_ids and not final_drain:
    yield_written_nonlive_tail(
        price_buffer, phase, written_outcome_ids,
        event_id_by_outcome, live_event_ids, final_drain,
    )"""


def _without_reviewed_tail_rotation(fn):
    (expected,) = _dumps(TAIL_ROTATION_CALL)
    locks = [node for node in ast.walk(fn) if isinstance(node, ast.AsyncWith)
             and len(node.items) == 1
             and isinstance(node.items[0].context_expr, ast.Name)
             and node.items[0].context_expr.id == "buffer_lock"]
    places = [(lock, index) for lock in locks
              for index, statement in enumerate(lock.body)
              if ast.dump(statement) == expected]
    assert len(places) == 1, "the fairness call is not the exact reviewed one"
    lock, index = places[0]
    assert index == 1 and len(lock.body) == 2, "fairness must follow locked removal"
    lock.body.pop(index)
    return fn


@pytest.mark.parametrize("mutation", ["body", "keyword", "placement"])
async def test_only_the_exact_locked_tail_rotation_is_reviewed(mutation):
    current = _without_docstring(flush_ast())
    call = next(n for n in ast.walk(current) if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "yield_written_nonlive_tail")
    rotation = next(n for n in ast.walk(current) if isinstance(n, ast.If)
                    and call in n.body)
    lock = next(n for n in ast.walk(current) if isinstance(n, ast.AsyncWith)
                and rotation in n.body)
    if mutation == "body":
        call.value.func.id = "clear_buffer"
    elif mutation == "keyword":
        call.value.args[-1] = ast.Constant(False)
    else:
        lock.body.remove(rotation)
        lock.body.insert(0, rotation)
    with pytest.raises(AssertionError):
        _without_reviewed_observers(current)
