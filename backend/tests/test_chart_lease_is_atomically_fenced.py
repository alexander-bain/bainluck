"""live/055 — #2766: the chart drain's lease fence is a compare-and-swap, not a
read-then-hope.

THE FINDING, AND IT IS MY OWN FIX BEING GRADED. CERT-798 repaired CERT-794/795
by fencing and renewing the per-tier lease on every state write. Its grader
banked it GREEN and named one surviving follow-up,
`CHART-LEASE-ATOMIC-COMPARE-RENEW`: the fence was

    GET lock -> compare -> EXPIRE lock -> write

which is three round trips and therefore three instants. Between the compare and
the write the lease can expire and be taken by a sibling, and the write lands
anyway. `_still_holds`'s own docstring conceded it — "as close to the write as it
can be without a server-side script" — and `_release_tier_lock`'s conceded the
matching one on the way out: "a vanishingly narrow window remains where the lock
is re-taken between the two".

WHY "NARROW" WAS NOT GOOD ENOUGH. CERT-794's window was thirty minutes and
CERT-798 cut it to microseconds, which is a real improvement and not a fix.
Microseconds is a statement about how OFTEN you meet the bug, not about whether
it is there, and the thing on the other side of it is the drain's terminal
verdict — the one write whose consequence is permanent, because nothing re-scans
a tier marked done. A correctness argument that rests on a race being unlikely is
the argument CERT-773 already lost once on this file.

THE REPAIR. WATCH the lock (and any key the write's decision reads), compare the
token in the watch phase, then queue the renewal AND the writes in one MULTI. If
the lock moves at any point after the WATCH, `EXEC` aborts and nothing lands.

    WATCH lock [, retry]
    GET lock, compare                <- immediate
    HLEN retry                       <- immediate, when the decision needs it
    MULTI
      EXPIRE lock                    <- the renewal, inside the block it protects
      <the writes>
    EXEC                             <- aborts if anything watched moved

🔴 THE RENEWAL HAD TO MOVE INSIDE. Real Redis signals a watch from the `EXPIRE`
path, so renewing in the watch phase would abort the pass's own transaction every
time. `tests/lib_tier_redis.py` models that (`_expire` bumps the version), which
is why a fake that ignored it would have let a self-aborting implementation pass.

HOW THESE TESTS INTERPOSE, and why on the READ. The sibling steals the lease from
`FakeTierRedis(on_read=...)`, fired the moment the lock's `GET` answers. That
instant exists in BOTH trees, which is what lets one assertion separate them:
against the pre-fix fence the theft is simply not noticed and the write lands
(the defect, reproduced); against this one `EXEC` refuses. A hook on `watch()`
would never fire against unfenced code, so it could only ever prove "somebody
called watch" — a proxy for the fix, not the fix.

CONTROLS CARRY THE WEIGHT HERE. A fence that refused everything would pass every
theft test in this file and destroy the drain, so every theft case has an
undisturbed twin asserting the write still lands and `watch_aborts` is empty.
"""

from datetime import datetime, timezone

from tests.lib_tier_redis import FakeTierRedis

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
TIER = "us_open"
#: CERT-794/795's specimen id, kept so this file and the chain name one event.
EVENT = 7007
MINE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
THEIRS = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _drain():
    import app.tasks.chart_backfill_thirty_day as module

    return module


def _keys(drain):
    return (
        drain.TIER_LOCK_KEY.format(tier=TIER),
        drain.TIER_DONE_KEY.format(tier=TIER),
        drain.RETRY_KEY.format(tier=TIER),
        drain.CHECKPOINT_KEY.format(tier=TIER),
    )


def _redis(drain, *, holder=MINE, done=None, retry=None, gave_up=0, on_read=None):
    lock_key, done_key, retry_key, _cursor = _keys(drain)
    store = {drain.GAVE_UP_KEY.format(tier=TIER): gave_up}
    if holder is not None:
        store[lock_key] = holder
    if done is not None:
        store[done_key] = done
    redis = FakeTierRedis(store, on_read=on_read)
    if retry:
        redis.hashes[retry_key] = {str(k): str(v) for k, v in retry.items()}
    redis.observations.clear()
    redis.versions.clear()
    redis._publish()
    return redis


def _steal_the_lease_once(drain):
    """A sibling that takes the tier the instant our token read answers.

    ONE SHOT. The fence reads the lock once, but `_mark_done` also queues a
    read-back inside its MULTI and `_release_tier_lock` reads on the way out; a
    hook that fired every time would be describing a different, sillier world
    (a sibling stealing the lease three times in one call) and would make the
    controls unreadable.
    """
    lock_key = drain.TIER_LOCK_KEY.format(tier=TIER)
    fired: list = []

    def _on_read(fake, key):
        if key != lock_key or fired:
            return
        fired.append(True)
        fake.set(lock_key, THEIRS)

    return _on_read, fired


def _add_a_retry_once(drain, event_id=8008):
    """A sibling that OWES A RETRY the instant the settlement's `HLEN` answers.

    🔴 THE INSTANT MATTERS, and it is `HLEN` rather than the lock's `GET`. Fired
    on the lock read, the sibling's retry would land BEFORE `_mark_done` counts
    the hash, so even the unfixed code would see it and refuse — the test would
    pass in both arms and discriminate nothing. Fired here, the settlement has
    already read zero and already decided to write a clean marker, which is the
    only ordering in which the defect exists.

    This is the "one key over" hazard, and it is the reason `_mark_done` watches
    the retry key and not only the lock. A read a write branches on is part of
    the write: if only the lock were watched, a clean `drained` would land on a
    tier that owes work — CERT-794/795's end state, re-created by its own repair
    one key to the left.
    """
    retry_key = drain.RETRY_KEY.format(tier=TIER)
    fired: list = []

    def _on_read(fake, key):
        if key != retry_key or fired:
            return
        fired.append(True)
        fake.hset(retry_key, mapping={str(event_id): "1"})

    return _on_read, fired


def _on(drain, redis):
    original = drain._with_redis

    def _patched(tier, apply):
        try:
            apply(redis)
        except Exception:  # noqa: BLE001 — mirrors the real swallow
            pass

    drain._with_redis = _patched
    return original


def _record(drain, redis, *, attempted, failed, prior, gave_up=0, token=MINE):
    original = _on(drain, redis)
    try:
        return drain._record_attempts(TIER, attempted, failed, prior, gave_up, token)
    finally:
        drain._with_redis = original


def _mark(drain, redis, marker, token=MINE):
    original = _on(drain, redis)
    try:
        return drain._mark_done(TIER, marker, token)
    finally:
        drain._with_redis = original


def _cursor(drain, redis, token=MINE):
    original = _on(drain, redis)
    try:
        return drain._write_cursor(TIER, (BASE, EVENT), token)
    finally:
        drain._with_redis = original


def _retry_of(drain, redis):
    return {
        int(k): int(v)
        for k, v in redis.hashes.get(drain.RETRY_KEY.format(tier=TIER), {}).items()
    }


def _done_of(drain, redis):
    raw = redis.store.get(drain.TIER_DONE_KEY.format(tier=TIER))
    return raw.decode() if isinstance(raw, bytes) else raw


# ---------------------------------------------------------------------------
# 1. THE SEAM ITSELF — a lease stolen after the check
# ---------------------------------------------------------------------------


def test_a_retry_write_whose_lease_is_stolen_after_the_check_lands_nothing():
    """🔴 THE FINDING, reproduced. The token read says the tier is ours; a
    sibling takes it in the next instant; the write must not land."""
    drain = _drain()
    on_read, fired = _steal_the_lease_once(drain)
    redis = _redis(drain, on_read=on_read)

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert fired, "the sibling never got to act — this test proved nothing"
    assert outcome.held is False, (
        "the lease moved between the check and the write; the write must be "
        "refused, not merely improbable"
    )
    assert _retry_of(drain, redis) == {}, "nothing may persist behind a lost lease"
    assert redis.watch_aborts, "the refusal must come from the watch, not luck"


def test_a_settlement_whose_lease_is_stolen_after_the_check_writes_no_marker():
    """The same theft against the write with the permanent consequence. A tier
    marked done is never re-scanned, so a verdict landing behind a lost lease is
    the worst version of this bug rather than another instance of it."""
    drain = _drain()
    on_read, fired = _steal_the_lease_once(drain)
    redis = _redis(drain, on_read=on_read)

    verdict = _mark(drain, redis, drain.DONE_CLEAN)

    assert fired
    assert verdict == drain.LOCK_LOST
    assert _done_of(drain, redis) is None
    assert drain.LOCK_LOST not in drain.TERMINAL_TIER_STATUSES


def test_a_cursor_write_whose_lease_is_stolen_after_the_check_does_not_advance():
    """The cursor may step past a FAILED event only because the retry hash
    remembers it, so a writer that cannot record the retry must not record the
    advance either. Same fence, same instant, same answer."""
    drain = _drain()
    on_read, fired = _steal_the_lease_once(drain)
    redis = _redis(drain, on_read=on_read)

    held = _cursor(drain, redis)

    assert fired
    assert held is False
    assert drain.CHECKPOINT_KEY.format(tier=TIER) not in redis.store


# ---------------------------------------------------------------------------
# 2. THE KEY THE DECISION READS IS PART OF THE DECISION
# ---------------------------------------------------------------------------


def test_a_retry_owed_after_the_hlen_blocks_the_clean_marker():
    """🔴 CERT-794/795's end state, re-created one key to the left, and closed.

    `_mark_done` refuses a clean `drained` while the retry hash is non-empty.
    That check is a READ, and a read the write branches on is part of the write:
    if only the lock were watched, a sibling could owe a retry between the `HLEN`
    and the `SET NX` and the clean marker would land on a tier that owes work —
    exactly `done='drained'` beside a populated retry hash. Watching the retry
    key is what makes that unrepresentable rather than unlikely.
    """
    drain = _drain()
    on_read, fired = _add_a_retry_once(drain)
    redis = _redis(drain, on_read=on_read)

    verdict = _mark(drain, redis, drain.DONE_CLEAN)

    assert fired, "the sibling never owed anything — this test proved nothing"
    assert _done_of(drain, redis) is None, (
        "a clean terminal marker landed on a tier that owes a retry — this is "
        "the CERT-794/795 pair with a narrower window, not a different bug"
    )
    assert verdict != drain.DONE_CLEAN
    assert verdict not in drain.TERMINAL_TIER_STATUSES


def test_the_settlement_watches_the_retry_key_and_not_only_the_lock():
    """The mechanism behind the test above, asserted directly, because the
    invariant could hold by ordering luck on a fake and luck is not a repair."""
    drain = _drain()
    watched: list = []
    redis = _redis(drain)

    real_pipeline = redis.pipeline

    def _spy(transaction=True):
        pipe = real_pipeline(transaction=transaction)
        real_watch = pipe.watch

        def _watch(*keys):
            watched.append(tuple(keys))
            return real_watch(*keys)

        pipe.watch = _watch
        return pipe

    redis.pipeline = _spy
    _mark(drain, redis, drain.DONE_CLEAN)

    assert watched, "the settlement opened no watch at all"
    keys = set(watched[0])
    assert drain.TIER_LOCK_KEY.format(tier=TIER) in keys
    assert drain.RETRY_KEY.format(tier=TIER) in keys, (
        "the settlement reads the retry hash and branches on it, so it must "
        "watch it — otherwise the fence is atomic about the wrong key"
    )


# ---------------------------------------------------------------------------
# 3. THE RELEASE — the compare/delete half of the finding
# ---------------------------------------------------------------------------


def test_the_release_does_not_delete_a_lock_re_taken_after_its_check():
    """`_release_tier_lock`'s own docstring named this window. An overrunning
    pass reads its own token, a sibling takes the lease in that instant, and the
    read-then-delete then removes the SIBLING's lock — manufacturing exactly the
    two-writers-one-tier state this whole chain exists to prevent."""
    drain = _drain()
    lock_key = drain.TIER_LOCK_KEY.format(tier=TIER)
    on_read, fired = _steal_the_lease_once(drain)
    redis = _redis(drain, on_read=on_read)

    original = _on(drain, redis)
    try:
        drain._release_tier_lock(TIER, MINE)
    finally:
        drain._with_redis = original

    assert fired
    assert redis.store.get(lock_key) == THEIRS, (
        "the lock was re-taken between our read and our delete; deleting it "
        "hands a live tier to a third pass"
    )


def test_the_release_still_hands_back_our_own_lock():
    """CONTROL. The fix must not turn the release into a no-op — a lock that is
    never released holds its tier for a full TTL after a clean finish."""
    drain = _drain()
    lock_key = drain.TIER_LOCK_KEY.format(tier=TIER)
    redis = _redis(drain)

    original = _on(drain, redis)
    try:
        drain._release_tier_lock(TIER, MINE)
    finally:
        drain._with_redis = original

    assert lock_key not in redis.store
    assert redis.watch_aborts == []


def test_the_release_still_leaves_a_lock_that_was_never_ours():
    """CONTROL, the pre-existing behaviour. A pass holding a stale token must
    not delete the current holder's lock, and that was already true — asserted
    here so the rewrite is shown not to have dropped it."""
    drain = _drain()
    lock_key = drain.TIER_LOCK_KEY.format(tier=TIER)
    redis = _redis(drain, holder=THEIRS)

    original = _on(drain, redis)
    try:
        drain._release_tier_lock(TIER, MINE)
    finally:
        drain._with_redis = original

    assert redis.store.get(lock_key) == THEIRS


# ---------------------------------------------------------------------------
# 4. CONTROLS — the fence must still let the ordinary pass through
# ---------------------------------------------------------------------------


def test_an_undisturbed_retry_write_lands_and_aborts_nothing():
    """CONTROL, and the one that matters most: a fence that refused everything
    would pass every theft test above while disabling the drain."""
    drain = _drain()
    redis = _redis(drain)

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert outcome.held is True
    assert _retry_of(drain, redis) == {EVENT: 1}
    assert redis.watch_aborts == [], "nothing moved, so nothing may abort"


def test_an_undisturbed_settlement_lands_and_aborts_nothing():
    """CONTROL for the settlement path, including its read phase."""
    drain = _drain()
    redis = _redis(drain)

    assert _mark(drain, redis, drain.DONE_CLEAN) == drain.DONE_CLEAN
    assert _done_of(drain, redis) == drain.DONE_CLEAN
    assert redis.watch_aborts == []


def test_an_undisturbed_cursor_write_lands():
    """CONTROL for the simplest write, which has no read phase at all."""
    drain = _drain()
    redis = _redis(drain)

    assert _cursor(drain, redis) is True
    assert redis.store.get(drain.CHECKPOINT_KEY.format(tier=TIER)) is not None
    assert redis.watch_aborts == []


def test_the_refused_nx_read_back_is_inside_the_same_transaction():
    """CERT-764's clause, tightened. When `SET NX` refuses, the caller reports
    the marker actually IN FORCE rather than the one it proposed — and that
    read-back used to be a separate round trip after the refusal, so a third
    writer could change the answer in between. Queued in the same MULTI, the
    `GET` observes the state the `SET NX` just declined to change."""
    drain = _drain()
    redis = _redis(drain, done=drain.DONE_WITH_FAILURES)

    assert _mark(drain, redis, drain.DONE_CLEAN) == drain.DONE_WITH_FAILURES
    assert _done_of(drain, redis) == drain.DONE_WITH_FAILURES, "not downgraded"

    transactional, names = redis.transactions[-1]
    assert transactional
    assert names == ["expire", "set", "get"], (
        "the renewal, the refused NX and its read-back are one block: %s" % (names,)
    )


def test_a_dry_run_still_writes_without_watching_or_renewing_a_lease():
    """CONTROL for the sentinel. A dry run holds no lock, so there is nothing to
    watch and nothing to renew — but its writes still go out as one transaction,
    because the atomicity BETWEEN them is CERT-773's guarantee and does not come
    from the lease."""
    drain = _drain()
    redis = _redis(drain, holder=None)

    outcome = _record(
        drain, redis, attempted=[EVENT], failed=[EVENT], prior={},
        token=drain._DRY_RUN_LOCK,
    )

    assert outcome.held is True
    assert _retry_of(drain, redis) == {EVENT: 1}
    transactional, names = redis.transactions[-1]
    assert transactional
    assert "expire" not in names, "a dry run has no lease to renew"


def test_an_unreachable_redis_is_still_not_a_lost_lease():
    """CONTROL, FAIL OPEN. Reworking the fence must not turn a connection blip
    into an aborted drain — `held` is about ownership, not about whether Redis
    answered. The pipeline is now the first thing the fence touches, so this
    fake refuses there."""
    drain = _drain()

    class _Dead:
        def get(self, *a, **k):
            raise RuntimeError("connection refused")

        def pipeline(self, transaction=True):
            raise RuntimeError("connection refused")

    outcome = _record(drain, _Dead(), attempted=[EVENT], failed=[EVENT], prior={})

    assert outcome.held is True, "a blip is not a sibling"
    assert outcome.owed == {EVENT: 1}, "the arithmetic answer still stands"


# ---------------------------------------------------------------------------
# 5. THE FAKE ITSELF — a guard is worth nothing if its model cannot say no
# ---------------------------------------------------------------------------


def test_the_fake_aborts_a_transaction_whose_watched_key_moved():
    """🔴 ANTI-VACUITY. Every test above rests on the fake refusing an `EXEC`
    after a watched key moves. A fake that never refused would make all of them
    pass against a tree with no fence at all — which is the failure this
    module's own header warns about twice, in the `SET NX` and `HLEN` notes."""
    from redis.exceptions import WatchError

    redis = FakeTierRedis({"k": "v"})
    with redis.pipeline(transaction=True) as pipe:
        pipe.watch("k")
        assert pipe.get("k") == "v", "reads answer immediately while watching"
        redis.set("k", "moved")  # the sibling
        pipe.multi()
        pipe.set("k", "ours")
        try:
            pipe.execute()
        except WatchError:
            pass
        else:  # pragma: no cover — the assertion below reports it properly
            raise AssertionError("EXEC did not abort after the watched key moved")

    assert redis.store["k"] == "moved", "the aborted block must leave no trace"
    assert redis.watch_aborts == [("k",)]


def test_the_fake_lets_an_undisturbed_watched_transaction_through():
    """CONTROL for the anti-vacuity test — a fake that aborted unconditionally
    would also make every theft test above pass."""
    redis = FakeTierRedis({"k": "v"})
    with redis.pipeline(transaction=True) as pipe:
        pipe.watch("k")
        pipe.get("k")
        pipe.multi()
        pipe.set("k", "ours")
        pipe.execute()

    assert redis.store["k"] == "ours"
    assert redis.watch_aborts == []


def test_the_fake_treats_expire_as_a_modification_like_real_redis():
    """🔴 THE MODELLING DETAIL THE FIX TURNS ON. Real Redis signals a watch from
    the `EXPIRE` path, so a lease renewal issued while watching aborts the
    watcher's own transaction. That is why the renewal is queued inside the
    MULTI. A fake that treated `EXPIRE` as invisible would let an implementation
    that renews in the watch phase pass here and abort every write in
    production."""
    from redis.exceptions import WatchError

    redis = FakeTierRedis({"lock": "tok"})
    with redis.pipeline(transaction=True) as pipe:
        pipe.watch("lock")
        redis.expire("lock", 1800)  # the renewal, in the WRONG place
        pipe.multi()
        pipe.set("other", "x")
        try:
            pipe.execute()
        except WatchError:
            pass
        else:  # pragma: no cover
            raise AssertionError("EXPIRE must invalidate a watch on that key")

    assert "other" not in redis.store


def test_the_fake_does_not_bump_a_version_for_a_no_op_expire():
    """CONTROL for the rule above. `EXPIRE` on a MISSING key changes nothing and
    answers 0, and a renewal cannot resurrect a lease a sibling already released
    — so it must not count as a modification either."""
    redis = FakeTierRedis({})
    assert redis.expire("gone", 1800) == 0
    assert redis.versions.get("gone", 0) == 0
