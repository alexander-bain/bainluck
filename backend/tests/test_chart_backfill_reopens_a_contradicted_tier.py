"""live/056 — CERT-831: the reopen that reported success and wrote nothing.

THE CHAIN, one more link. CERT-794/795 found a tier that could hold
`done='drained'` beside a non-empty retry hash — a pair that cannot both be
true — and made every later trigger walk straight past the owed event behind a
verdict saying the drain had finished. CERT-798 shipped the forward fix (a
retry's write DELETES the marker in its own transaction) plus a REPAIR for the
tiers already sitting in that state: on reading the contradictory pair, drop the
marker and drain what is owed. live/055 then made the fence a real WATCH/MULTI
compare-and-swap, which changed the callback contract from `apply(client)` to
`apply(pipe, observed)`.

Three callbacks were updated. The repair's was not:

    _fenced(tier.name, lock, lambda client: client.delete(TIER_DONE_KEY...))

`_fenced` calls `apply(pipe, observed)`. That raises `TypeError` INSIDE
`_with_redis`, whose whole job is to swallow — a Redis outage must cost a
re-scan, not a crashed drain — so `refused` stayed empty and `_fenced` answered
`True`. The pass believed it had reopened the tier. Nothing had been deleted.

🔴 WHY THAT IS A SHIP FAILURE AND NOT A TIDINESS ONE, which is the part worth
being precise about, because on most paths the stale marker is harmlessly
cleaned up a moment later. Follow the one path where it is not:

  1. Tier holds `done='drained'` and owes event 7007. The repair "fires" and
     deletes nothing. The pass sets `state.done = None` in memory only.
  2. The retry SUCCEEDS. `_record_attempts` therefore only DROPS a field; its
     own `delete(done_key)` is queued only when it ADDS one, and it added none.
  3. The page behind the retry is not exhausted, so `_settle_tier` reports
     `in_progress` and writes no marker — correctly, there is nothing to write.
  4. Redis now holds `done='drained'` beside an EMPTY retry hash. The
     self-contradiction that made the repair fire is gone, so the repair will
     never fire again, and the next trigger's `state.done` short-circuit skips
     the rest of the tier. Permanently: nothing re-scans a tier marked done.

The owed event was answered and the thousands behind it never will be. Step 2 is
the trap — the SUCCESSFUL retry is what erases the evidence.

WHAT THIS FILE GUARDS, in the order the cert asked for it:

  1. The end-to-end recovery, `done + retry` → successful retry → unfinished
     page → the next invocation does NOT short-circuit. The named guard.
  2. The reopen write itself: the marker is gone from Redis, and a lost lease
     refuses the delete instead of pretending.
  3. THE CLASS, not just the instance. A callback that does not take
     `(pipe, observed)` now fails LOUDLY at the call that made it, rather than
     being swallowed into `held=True`. This is the guard that would have caught
     the defect the day it was written, and the reason it did not exist is that
     the contract check lived inside the swallow.

Every test resolves the module lazily, for the reason its sibling files give.
"""

from datetime import datetime, timezone

import pytest

from tests.lib_tier_redis import FakeTierRedis

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
TIER = "us_open"
#: The chain's specimen id, kept verbatim across CERT-773/794/798/831.
EVENT = 7007


def _drain():
    import app.tasks.chart_backfill_thirty_day as module

    return module


def _is_terminal(marker) -> bool:
    """Both terminal markers, plus the legacy bare `"1"` that `_read_checkpoint`
    still reads as the clean verdict it meant."""
    return marker in ("drained", "drained_with_failures", "1")


def _contradicted(drain, *, marker=None):
    """The state CERT-794/795 could leave behind and CERT-798 must repair:
    a terminal marker beside an event that is still owed a retry."""
    drain_marker = marker or drain.DONE_CLEAN
    redis = FakeTierRedis({
        drain.GAVE_UP_KEY.format(tier=TIER): 0,
        drain.TIER_DONE_KEY.format(tier=TIER): drain_marker,
    })
    redis.hashes[drain.RETRY_KEY.format(tier=TIER)] = {str(EVENT): "1"}
    redis.observations.clear()
    redis._publish()
    return redis


# ---------------------------------------------------------------------------
# 1. THE NAMED GUARD — the whole recovery, end to end
# ---------------------------------------------------------------------------


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Row:
    def __init__(self, event_id):
        self.id = event_id


class _Session:
    def __init__(self, present):
        self._present = set(present)

    async def execute(self, statement):
        for param in statement.compile().params.values():
            if param in self._present:
                return _ScalarResult(_Row(param))
        return _ScalarResult(None)

    async def commit(self):
        return None


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _Svc:
    async def close(self):
        return None


def _wire_recovering_runner(monkeypatch, drain, redis, pages):
    """A tier whose owed retry SUCCEEDS and whose scan is NOT finished.

    `pages` is consumed one entry per call to `select_thirty_day_page`, so the
    two triggers can be handed different pages — which is the only way to tell
    "the second trigger scanned" apart from "the second trigger skipped".
    """
    import app.tasks.event_chart_backfill as engine

    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )
    monkeypatch.setattr(drain, "INTER_EVENT_SLEEP_SECONDS", 0)
    monkeypatch.setattr(
        "app.tasks.base.get_task_session", lambda: _SessionCtx(_Session(pages.present))
    )
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", _Svc)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", _Svc)

    async def _tiers(_session):
        return {tier.name: [1] for tier in drain.TIERS}

    monkeypatch.setattr(drain, "tier_sport_ids", _tiers)

    async def _page(_session, **_kw):
        pages.calls.append(True)
        return pages.next()

    monkeypatch.setattr(drain, "select_thirty_day_page", _page)

    async def _fill(_session, event, **_kw):
        pages.filled.append(event.id)
        return {
            "status": "ok",
            "sources": {"polymarket": {"status": "written", "points_written": 12}},
            "points_written": 12,
            "errors": [],
        }

    monkeypatch.setattr(engine, "backfill_event_chart", _fill)


class _Pages:
    def __init__(self, drain, present):
        # 🔴 NOT EXHAUSTED, either time. That is the condition under which the
        # settlement writes no marker of its own, so the ONLY thing that can
        # clear the stale one is the reopen.
        self._queue = [
            drain.DrainPage([], (BASE, EVENT), False, 3),
            drain.DrainPage([EVENT + 1], (BASE, EVENT + 1), False, 4),
        ]
        self.present = present
        self.calls: list = []
        self.filled: list = []

    def next(self):
        return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]


async def test_a_successful_retry_on_a_reopened_tier_does_not_leave_it_done(
    monkeypatch,
):
    """🔴 CERT-831, VERBATIM AND END TO END.

    Start where the cert starts: `done='drained'` beside one owed retry. The
    retry succeeds. The page behind it is not exhausted. Assert what the cert
    asked to be proved — the done key is CLEARED in Redis, and the next
    invocation scans instead of returning `already_done`.

    RED-FIRST against the blocked subject `3d6e8fd2`: the one-argument reopen
    lambda raises inside `_with_redis`, the marker survives, and the second
    trigger reports `already_done` with the tier's remaining events never asked.
    Both assertions below fail there, and they fail for the defect rather than
    for a signature.

    The second trigger is a real second call, not an inspection of state — the
    short-circuit lives in the runner, so only the runner can prove it is gone.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    first = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )

    done_key = drain.TIER_DONE_KEY.format(tier=TIER)
    assert done_key not in redis.store, (
        "the tier is still marked done after being reopened — the reopen's "
        "write never reached Redis, and the marker now sits beside an EMPTY "
        "retry hash, so nothing will ever detect the contradiction again"
    )
    assert first["tiers"][TIER]["status"] == "in_progress"
    assert pages.filled == [EVENT], "the owed retry was the event actually asked"

    # And the state a fresh reader assembles agrees — the in-memory
    # `state._replace(done=None)` is not what the next trigger reads.
    assert drain._read_checkpoint(TIER).done is None
    assert drain._read_checkpoint(TIER).retry == {}

    second = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )

    assert not second["tiers"][TIER].get("already_done"), (
        "the next trigger short-circuited on a stale terminal marker — the "
        "rest of this tier's charts are now permanently unreachable"
    )
    assert second["tiers"][TIER]["scanned"] == 4, (
        "the second trigger did not scan: it must pick the tier up where the "
        "first one left it, not skip it"
    )
    assert pages.filled == [EVENT, EVENT + 1], (
        "the event behind the retry was never asked — which is the whole cost "
        "of the defect, and is invisible in the tier's own verdict"
    )


async def test_the_reopened_tier_still_settles_terminal_when_it_truly_finishes(
    monkeypatch,
):
    """🔴 THE CONTROL, and it is not optional.

    A reopen that simply never cleared anything would pass nothing above; a
    reopen that left the tier permanently unable to settle would pass everything
    above and disable the drain instead. So: same start, same successful retry,
    but this time the page IS exhausted — the tier must reach a clean terminal
    `drained` under its own steam, freshly written after the reopen.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT])
    pages._queue = [drain.DrainPage([], (BASE, EVENT), True, 3)]
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )

    done_key = drain.TIER_DONE_KEY.format(tier=TIER)
    assert summary["tiers"][TIER]["status"] == drain.DONE_CLEAN
    assert redis.store[done_key] == drain.DONE_CLEAN
    assert summary["tiers"][TIER]["persisted_done_marker"] == drain.DONE_CLEAN


async def test_a_reopen_that_cannot_be_written_does_not_drain_the_tier_anyway(
    monkeypatch,
):
    """🔴 THE REFUSAL IS AN ANSWER. `_fenced` documents that `False` is a real
    result the caller must act on; this call site used to discard it.

    A sibling steals the lease in the instant after the reopen's token read. The
    delete is refused, so the marker is still in Redis and belongs to whoever
    holds the tier now. Draining on regardless would spend a page of venue
    fetches whose every write is refused, and would report progress this pass
    did not make. The tier reports `lock_lost` and touches nothing.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    lock_key = drain.TIER_LOCK_KEY.format(tier=TIER)
    stolen: list = []

    def _steal(fake, key):
        # The instant after our token read answers — the only ordering in which
        # the theft is invisible to a non-atomic fence.
        if key == lock_key and not stolen:
            stolen.append(True)
            fake.store[lock_key] = "a-sibling's-token"
            fake._touch(lock_key)

    redis.on_read = _steal

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )

    assert stolen, "the sibling never got in — this test proved nothing"
    assert summary["tiers"][TIER]["status"] == drain.LOCK_LOST
    assert redis.store[drain.TIER_DONE_KEY.format(tier=TIER)] == drain.DONE_CLEAN, (
        "a pass that no longer holds the tier deleted its marker anyway"
    )
    assert pages.filled == [], (
        "the pass drained events for a tier it does not own"
    )


# ---------------------------------------------------------------------------
# 2. The write itself
# ---------------------------------------------------------------------------


def test_the_reopen_delete_actually_lands_in_redis():
    """The unit under the end-to-end guard: held, and the key is gone.

    Against the blocked subject this returned `held=True` with the key still
    there — which is why `held` alone was never enough to assert.
    """
    drain = _drain()
    redis = _contradicted(drain)
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"

    swallowed: list = []

    def _direct(_tier, apply):
        try:
            apply(redis)
        except Exception as exc:  # noqa: BLE001 — the swallow, made visible
            swallowed.append(repr(exc))

    original, drain._with_redis = drain._with_redis, _direct
    try:
        held = drain._fenced(
            TIER, "tok-1",
            lambda pipe, _observed: pipe.delete(
                drain.TIER_DONE_KEY.format(tier=TIER)
            ),
        )
    finally:
        drain._with_redis = original

    assert held is True
    assert swallowed == [], (
        f"the reopen raised inside the swallow and reported success: {swallowed}"
    )
    assert drain.TIER_DONE_KEY.format(tier=TIER) not in redis.store


# ---------------------------------------------------------------------------
# 3. THE CLASS — a broken callback contract must be loud, not swallowed
# ---------------------------------------------------------------------------


def test_a_one_argument_callback_raises_instead_of_reporting_a_write_it_skipped():
    """🔴 THE GUARD FOR THE CLASS, and the one whose absence is the real story.

    The defect was not that someone forgot to update a lambda — that is an
    ordinary mistake and there were four of them to update. The defect is that
    forgetting was SILENT: the failure landed inside `_with_redis`, which
    swallows by design, and the fence then reported that it still held the tier.
    A wrong callback and a Redis outage produced the same answer.

    So the contract is now checked ABOVE the swallow, and a violation is a loud
    failure at the call that made it. Any future callback written to the old
    shape dies on its first invocation in any environment instead of quietly
    skipping a write for a cert to find.

    🔴 THE REAL `_with_redis` IS IN PLAY HERE, and that is the whole test. An
    earlier version of this guard stubbed `_with_redis` with a non-swallowing
    lambda, and it went red against the blocked tree — but for the wrong
    reason: the raw `TypeError` escaped a swallow that does not exist in the
    stub, so the test was grading its own harness. Routed through the real one,
    the blocked tree does not raise AT ALL; it returns `True`. `DID NOT RAISE`
    is the honest failure, and it is the defect.
    """
    drain = _drain()
    redis = _contradicted(drain)
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )
    try:
        with pytest.raises(TypeError, match="must accept"):
            drain._fenced(TIER, "tok-1", lambda client: client.delete("k"))
    finally:
        monkeypatch.undo()

    assert drain.TIER_DONE_KEY.format(tier=TIER) in redis.store, (
        "the refused callback still wrote something"
    )


def test_the_contract_check_does_not_reject_the_callbacks_the_module_uses():
    """🔴 THE CONTROL FOR THE GUARD ABOVE. A check that refused everything would
    make the previous test pass and break the drain, so every real callback
    shape is asserted to survive it: two positional parameters, `*args`, a bound
    method, and a builtin whose signature cannot be read at all.
    """
    drain = _drain()

    class _Bound:
        def apply(self, pipe, observed):
            return None

    for shape in (
        lambda pipe, observed: None,
        lambda pipe, _observed=None: None,
        lambda *args: None,
        _Bound().apply,
        print,  # not introspectable in every build — accepted, not refused
    ):
        drain._assert_apply_contract(shape)


def test_a_read_phase_without_a_watched_key_is_refused_where_it_can_be_heard():
    """The sibling contract, moved out of the swallow by the same repair.

    A read issued on an unwatched pipeline is QUEUED rather than executed, so it
    answers with the pipeline object — truthy — and `_mark_done` would report
    `awaiting_retries` for every tier forever. That assertion existed, but it
    lived inside `_guarded`, so `_with_redis` ate it and `_fenced` returned
    `True`: a wrong verdict reported as a completed write. It is now raised
    before any Redis work happens.

    🔴 THROUGH THE REAL `_with_redis`, for the reason the test above records.
    An earlier draft stubbed the swallow away and therefore passed in BOTH arms
    — the module's own comment claimed this was "refused loudly here" and it was
    not, and a guard built on a stub could never have said so.
    """
    drain = _drain()
    redis = _contradicted(drain)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )
    try:
        with pytest.raises(AssertionError, match="watched key"):
            drain._fenced(
                TIER, drain._DRY_RUN_LOCK,
                lambda pipe, observed: None,
                read=lambda pipe: pipe.hlen("anything"),
            )
    finally:
        monkeypatch.undo()


def test_every_fenced_callback_in_the_module_takes_the_two_argument_contract():
    """🔴 THE SWEEP, because one missed call site is exactly what happened.

    Four callbacks were meant to be updated and three were. A guard that only
    covered the one the cert found would leave the fifth to the next cert. This
    walks the module's own source for `_fenced(` call sites and asserts each
    one's callback against the contract, so a new caller written to the old
    shape is red here rather than at the far end of a production drain.

    Asserting on `getsource` is a real limitation and is stated rather than
    hidden: it sees call sites, not callables reached at runtime. It is a
    backstop under the contract check, not a replacement for it — the contract
    check is what actually holds, in every environment, for every caller.
    """
    import ast
    import inspect

    drain = _drain()
    tree = ast.parse(inspect.getsource(drain))

    # 🔴 RESOLVED PER ENCLOSING FUNCTION, NOT MODULE-WIDE. Three of the four
    # callbacks are a nested `def _apply`, and `_release_tier_lock` has a nested
    # `_apply` of its OWN that is not a `_fenced` callback and takes one
    # argument by design. A module-wide name map picks whichever it walked last
    # and grades the wrong function — this sweep failed on exactly that before
    # it was scoped, which is worth recording: a name-keyed lookup over nested
    # scopes is a coin flip, not a lookup.
    checked = 0
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local = {
            n.name: n for n in ast.walk(owner)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n is not owner
        }
        for node in ast.walk(owner):
            target = getattr(node, "func", None)
            if not (
                isinstance(node, ast.Call)
                and isinstance(target, ast.Name)
                and target.id == "_fenced"
            ):
                continue
            # `_fenced(tier, token, apply, ...)` — the callback is positional 3.
            assert len(node.args) >= 3, ast.dump(node)
            apply_arg = node.args[2]
            checked += 1

            if isinstance(apply_arg, ast.Lambda):
                params, where = apply_arg.args, f"line {apply_arg.lineno}"
            else:
                assert isinstance(apply_arg, ast.Name), ast.dump(apply_arg)
                resolved = local.get(apply_arg.id)
                assert resolved is not None, (
                    f"`{apply_arg.id}` passed to _fenced at line {node.lineno} "
                    "could not be resolved in its own scope — the sweep cannot "
                    "grade what it cannot find"
                )
                params = resolved.args
                where = f"`{owner.name}`'s `{apply_arg.id}`"

            assert _takes_the_contract(params), (
                f"the `_fenced` callback at {where} takes "
                f"{len(params.args)} positional argument(s); the contract is "
                "`apply(pipe, observed)` (CERT-831)"
            )

    assert checked >= 4, (
        f"only {checked} `_fenced` call sites found — the sweep is looking in "
        "the wrong place, which would make it green on a tree with the defect"
    )


def _takes_the_contract(params) -> bool:
    """Does an `ast.arguments` accept two positional arguments?"""
    return len(params.args) >= 2 or params.vararg is not None


def test_the_sweep_is_red_on_the_exact_callback_the_cert_found():
    """🔴 THE SWEEP'S OWN CONTROL — gotcha: a source scan that finds nothing
    passes for free, and so does one whose predicate is wrong. Feed the sweep
    the blocked line verbatim and prove it bites, then feed it the repaired line
    and prove it does not.
    """
    import ast

    def _grade(line):
        tree = ast.parse(f"def f():\n    {line}\n")
        calls = [
            n.args[2] for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_fenced"
        ]
        assert len(calls) == 1, "the sweep did not find the call at all"
        return _takes_the_contract(calls[0].args)

    assert not _grade(
        "_fenced(tier.name, lock, lambda client: client.delete(k))"
    ), "the sweep's predicate accepts the exact defect it exists to catch"
    assert _grade(
        "_fenced(tier.name, lock, lambda pipe, _observed: pipe.delete(k))"
    ), "the sweep's predicate rejects the repair — it would be red on green"


# ---------------------------------------------------------------------------
# 4. The fence's other guarantees are untouched by all of the above
# ---------------------------------------------------------------------------


def test_the_reopen_does_not_downgrade_a_failure_ending_it_cannot_re_derive():
    """A `drained_with_failures` marker is deleted by the reopen too, and that
    is deliberate rather than an oversight: the give-up COUNTER is untouched and
    monotone, so the tier re-derives the same ending when it settles again. This
    asserts the counter survives the reopen, which is what makes the deletion
    safe — the same argument `_record_attempts` already makes in its own block.
    """
    drain = _drain()
    redis = _contradicted(drain, marker=drain.DONE_WITH_FAILURES)
    redis.store[drain.GAVE_UP_KEY.format(tier=TIER)] = 2
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"

    original, drain._with_redis = drain._with_redis, lambda _t, apply: apply(redis)
    try:
        held = drain._fenced(
            TIER, "tok-1",
            lambda pipe, _observed: pipe.delete(
                drain.TIER_DONE_KEY.format(tier=TIER)
            ),
        )
    finally:
        drain._with_redis = original

    assert held is True
    assert drain.TIER_DONE_KEY.format(tier=TIER) not in redis.store
    assert redis.store[drain.GAVE_UP_KEY.format(tier=TIER)] == 2, (
        "the give-up count is what re-derives `drained_with_failures`; losing "
        "it turns an abandoned event into a clean finish"
    )


def test_a_settle_phase_is_still_run_when_the_callback_returns_one():
    """`callable(settle)` replaced `settle is not None` so that a callback ending
    in a chainable queued write does not have its return value CALLED. The
    settle phase itself must still work — asserted here rather than assumed,
    because the two changes are one line apart.
    """
    drain = _drain()
    redis = _contradicted(drain)
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"
    seen: list = []

    def _apply(pipe, _observed):
        pipe.incrby(drain.GAVE_UP_KEY.format(tier=TIER), 3)

        def _settle(results):
            seen.append(results[-1])

        return _settle

    original, drain._with_redis = drain._with_redis, lambda _t, apply: apply(redis)
    try:
        assert drain._fenced(TIER, "tok-1", _apply) is True
    finally:
        drain._with_redis = original

    assert seen == [3], (
        "the settle phase did not run, or the lease renewal's reply was not "
        "stripped before the caller indexed its own commands"
    )


async def test_the_two_triggers_never_publish_a_done_marker_beside_an_empty_retry(
    monkeypatch,
):
    """🔴 THE INVARIANT, over every state a reader could land on rather than the
    last one — the same standard CERT-773's guard set.

    The damage is not that the marker is wrong at the end; it is that a reader
    arriving at any moment after the successful retry sees a finished tier. The
    seeded starting state is excluded: it is the pre-existing corruption this
    repair exists to clean up, and it is visible by construction.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    await drain.run_thirty_day_chart_drain(limit=5, only_tier=TIER, dry_run=False)
    await drain.run_thirty_day_chart_drain(limit=5, only_tier=TIER, dry_run=False)

    states = redis.visible_states(TIER)[1:]
    assert states, "nothing became visible — the runner did not write"
    for state in states:
        assert not (_is_terminal(state.done) and not state.retry), (
            f"a reader could see {state.done!r} beside an empty retry hash on a "
            "tier that is not finished — the next trigger skips it forever"
        )


async def test_the_recovery_is_idempotent_under_a_repeated_trigger(monkeypatch):
    """Re-running the recovery must be free. The operator's loop re-calls until
    terminal, so the reopen path is entered by whichever trigger reads the
    contradiction — and a second one that finds it already cleared must simply
    drain, not re-report a repair it did not perform.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    results = [
        await drain.run_thirty_day_chart_drain(
            limit=5, only_tier=TIER, dry_run=False,
        )
        for _ in range(3)
    ]

    assert all(r["tiers"][TIER]["status"] == "in_progress" for r in results)
    assert drain.TIER_DONE_KEY.format(tier=TIER) not in redis.store
    assert all(not r["tiers"][TIER].get("already_done") for r in results)


async def test_a_dry_run_never_reopens_the_tier(monkeypatch):
    """A spot check writes nothing, including the repair. It takes no lock, so
    it has no lease to fence with, and deleting a marker it is not authorised to
    touch would let a read-only probe reopen a tier for the real drain.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    await drain.run_thirty_day_chart_drain(limit=5, only_tier=TIER, dry_run=True)

    assert redis.store[drain.TIER_DONE_KEY.format(tier=TIER)] == drain.DONE_CLEAN, (
        "a dry run deleted the tier's terminal marker"
    )


# ---------------------------------------------------------------------------
# 5. CERT-836 — the reopen that was never CONFIRMED, and the write that heals it
# ---------------------------------------------------------------------------
#
# 🔴 THE CASE A CALLBACK REPAIR CANNOT REACH, and the reason this file needed a
# second section. Section 1 fixed the reopen's arguments. CERT-836 then found
# that fixing the callback is not the same as the reopen having HAPPENED.
#
# `_with_redis` fails open by design — a Redis blip must cost a re-scan, not a
# crashed drain — so ANY Redis exception makes `_fenced` answer `True`. That is
# safe only while nothing LATER in the same run persists, and that assumption is
# precisely what breaks here: if Redis dies for the single instant of the reopen
# transaction and recovers immediately, the reopen is silently lost while every
# write after it lands. The successful retry is removed, the cursor advances,
# `drained` survives beside an empty hash, and the next trigger returns
# `already_done` over everything behind it.
#
# Every guard in section 1 is green through this, and cannot be otherwise: their
# Redis is healthy for the whole run, so the split never occurs. That is worth
# stating plainly — a suite can be thorough about the mechanism it was written
# for and blind to the one next to it.
#
# THE REPAIR IS NOT A BETTER REOPEN. It is to stop the invariant depending on a
# separate write having succeeded: `_record_attempts` now deletes the terminal
# marker UNCONDITIONALLY, inside the transaction that records attempts. The
# reopen may be lost; the write that would otherwise have made the loss
# permanent now carries the cure. `_settle_tier` writes the true marker
# afterwards when the tier really has finished.


class _BlipOnce:
    """A Redis that fails exactly ONE transaction, then works perfectly.

    Selected by the commands the block CONTAINS rather than by a call count:
    a counter would move whenever anything upstream added a round trip, and the
    test would silently start failing a different transaction than the one it
    names. This fails the block that deletes the done key and touches no hash —
    which is the reopen, and only the reopen.
    """

    def __init__(self, redis):
        self.redis = redis
        self.armed = True
        self.fired = []
        self._real = redis.pipeline
        redis.pipeline = self._pipeline

    def _pipeline(self, transaction=True):
        pipe = self._real(transaction)
        real_execute = pipe.execute

        def execute():
            names = [n for n, _a, _k in pipe._queued]
            if (
                self.armed
                and "delete" in names
                and "hdel" not in names
                and "hset" not in names
            ):
                self.armed = False
                self.fired.append(tuple(names))
                raise ConnectionError("redis went away for one instant")
            return real_execute()

        pipe.execute = execute
        return pipe


async def test_a_reopen_lost_to_a_redis_blip_does_not_strand_the_tier(monkeypatch):
    """🔴 CERT-836, VERBATIM: `done + retry` → the reopen's EXEC fails once →
    Redis recovers → the retry succeeds → the page is not exhausted.

    Prove the marker/retry pair is left recoverable and the second trigger
    SCANS the next event instead of returning `already_done`.

    RED-FIRST against `1b77900a` (the CERT-831 repair, with the correct
    two-argument callback): second trigger returns
    `{'status': 'drained', 'already_done': True}`, Redis holds `drained` with an
    empty retry hash, and event 7008 is never filled.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)
    blip = _BlipOnce(redis)

    await drain.run_thirty_day_chart_drain(limit=5, only_tier=TIER, dry_run=False)
    second = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )

    assert blip.fired, (
        "the blip never fired — this test proved nothing. The reopen's "
        "transaction shape changed and the selector no longer finds it."
    )
    assert not blip.armed

    assert drain.TIER_DONE_KEY.format(tier=TIER) not in redis.store, (
        "the reopen was lost to the blip AND nothing else cleared the marker — "
        "the tier is now `drained` beside an empty retry hash, which is "
        "self-consistent, so nothing will ever detect it again"
    )
    assert not second["tiers"][TIER].get("already_done"), (
        "the second trigger short-circuited: every event behind the retry is "
        "now permanently unreachable"
    )
    assert pages.filled == [EVENT, EVENT + 1], (
        f"the event behind the retry was never scanned: filled={pages.filled}"
    )


async def test_the_blip_is_survivable_when_it_hits_the_ATTEMPTS_write_instead(
    monkeypatch,
):
    """The other side of the same coin, and it must NOT be papered over.

    If the blip takes the attempts write rather than the reopen, the retry is
    NOT removed — so the tier still owes it, the pair stays contradictory, and
    the next trigger re-opens and re-drains. That is the correct outcome (work
    repeated, nothing lost) and it is the direction this whole module errs in.
    Asserted so a future "fix" that swallows this case cannot call itself an
    improvement.
    """
    drain = _drain()
    redis = _contradicted(drain)
    pages = _Pages(drain, present=[EVENT, EVENT + 1])
    _wire_recovering_runner(monkeypatch, drain, redis, pages)

    real_pipeline = redis.pipeline
    state = {"armed": True, "fired": False}

    def _pipeline(transaction=True):
        pipe = real_pipeline(transaction)
        real_execute = pipe.execute

        def execute():
            names = [n for n, _a, _k in pipe._queued]
            if state["armed"] and "hdel" in names:
                state["armed"] = False
                state["fired"] = True
                raise ConnectionError("redis went away for one instant")
            return real_execute()

        pipe.execute = execute
        return pipe

    redis.pipeline = _pipeline

    await drain.run_thirty_day_chart_drain(limit=5, only_tier=TIER, dry_run=False)
    assert state["fired"], "the blip never fired — this test proved nothing"

    # The retry survives because its removal never landed. The tier therefore
    # still owes work and cannot be terminal, whichever order a reader arrives
    # in — which is the invariant, not the specific keys.
    after = drain._read_checkpoint(TIER)
    assert not (after.done and not after.retry), (
        f"a terminal marker beside an empty retry hash: done={after.done!r}"
    )

    second = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier=TIER, dry_run=False,
    )
    assert not second["tiers"][TIER].get("already_done")


def test_the_attempts_write_clears_the_marker_even_when_it_only_DROPS(monkeypatch):
    """The unit under the two runner guards above.

    The pre-CERT-836 code deleted the marker only when the pass ADDED a retry.
    A pass that only DROPS one — the retry SUCCEEDED — left it, and that is the
    branch the lost reopen falls through. Asserted directly so the reason the
    delete is unconditional is visible without running the whole runner.
    """
    drain = _drain()
    redis = _contradicted(drain)
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"

    original, drain._with_redis = drain._with_redis, lambda _t, apply: apply(redis)
    try:
        outcome = drain._record_attempts(
            TIER, [EVENT], [], {EVENT: 1}, 0, "tok-1",
        )
    finally:
        drain._with_redis = original

    assert outcome.held is True
    assert outcome.owed == {}, "the retry succeeded and was dropped"
    assert drain.TIER_DONE_KEY.format(tier=TIER) not in redis.store, (
        "a pass that DROPS a retry must clear the terminal marker too — "
        "leaving it is the branch CERT-836's lost reopen falls through"
    )


def test_the_give_up_counter_survives_the_unconditional_delete():
    """CONTROL — the delete must not cost the tier its failure ending.

    `drained_with_failures` is re-derived from the monotone give-up counter, so
    deleting the marker is only safe while that counter is untouched. If this
    ever goes red, the unconditional delete has turned an abandoned event into a
    clean finish, which is CERT-773 again.
    """
    drain = _drain()
    redis = _contradicted(drain, marker=drain.DONE_WITH_FAILURES)
    redis.store[drain.GAVE_UP_KEY.format(tier=TIER)] = 4
    redis.store[drain.TIER_LOCK_KEY.format(tier=TIER)] = "tok-1"

    original, drain._with_redis = drain._with_redis, lambda _t, apply: apply(redis)
    try:
        outcome = drain._record_attempts(
            TIER, [EVENT], [], {EVENT: 1}, 4, "tok-1",
        )
    finally:
        drain._with_redis = original

    assert redis.store[drain.GAVE_UP_KEY.format(tier=TIER)] == 4
    assert outcome.gave_up_total == 4, (
        "the count the settlement turns on must survive the marker delete"
    )
