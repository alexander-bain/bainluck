"""live/052 — CERT-794/795: a clean verdict written beside work still owed.

THE CHAIN, and the fourth instance is the interesting one because it is the
first that the previous three repairs cannot see. CERT-753: `drained` while
pages stayed thin. CERT-764: settlement read the give-up count ENTERING the
trigger. CERT-773: two triggers, and the retry-delete/give-up-increment tear
between them. CERT-793 graded that repair GREEN — and CERT-794/795, grading the
same subject, found the SAME disease in the one order the repair does not
order:

    The `_mark_done` monotonicity is about the two TERMINAL markers. It stops a
    clean `drained` from DOWNGRADING a `drained_with_failures`. It says nothing
    about a clean `drained` landing on an EMPTY done-key while a sibling still
    owes a retry — and the sibling can be an older runner whose fixed 30-minute
    lease expired while it was still working. The graders' reproduction ends:

        done  = 'drained'
        retry = {7007: 1}

    Nothing was downgraded. The two writes simply do not know about each other.
    And the next invocation returns on `state.done` and never retries 7007, so
    the match page stays incomplete behind a verdict that says the drain
    finished cleanly. Permanently: nothing re-scans a finished tier.

WHY A FIXED LEASE WAS THE PRECONDITION. `TIER_LOCK_TTL_SECONDS` is a promise
about how long a pass takes, and a promise about duration is not a lock. Any
pass slower than the promise puts two writers back on one tier — which is
exactly what CERT-773's own note said would happen, and it was answered with
"the marker is independently monotone", which turns out to cover one order of
two.

THE REPAIR, three parts, each of which alone closes the graders' reproduction:

  1. **The lease is RENEWED on every state write** (`_still_holds`). A pass that
     is alive keeps its tier. Losing it now means being stalled for a full TTL
     between two writes.
  2. **A writer that lost the lease writes NOTHING** (`_fenced`). Not the retry,
     not the cursor, not the verdict — and the caller STOPS rather than falling
     through to the next write, because advancing a cursor past a failure it was
     not allowed to record is how the failure gets stepped over for good.
  3. **A newly owed retry RE-OPENS the tier, atomically.** The retry write
     deletes the terminal marker inside the same MULTI that adds the field. The
     pair `done + non-empty retry` therefore has no reachable moment, in either
     order — which is stronger than detecting it afterwards.

And because production can ALREADY be holding that pair (the shipped code could
write it), `_drain_tiers` repairs it on read instead of skipping past it.

Every test resolves the module lazily, for the reason the three sibling files
give: a module-level import of a new symbol collapses the file into one
collection error against the pre-fix tree, which is red for the wrong reason.
"""

from datetime import datetime, timezone

from tests.lib_tier_redis import FakeTierRedis

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
TIER = "us_open"
#: The graders' specimen id, kept verbatim so this file and the cert body name
#: the same event.
EVENT = 7007
#: This pass's fencing token. A hex string like the real `uuid4().hex`.
MINE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#: The sibling's. Different, which is the whole point.
THEIRS = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _drain():
    import app.tasks.chart_backfill_thirty_day as module

    return module


def _redis(drain, *, holder=MINE, done=None, retry=None, gave_up=0):
    """A tier mid-drain: we hold the lease unless a sibling is named."""
    store = {drain.GAVE_UP_KEY.format(tier=TIER): gave_up}
    if holder is not None:
        store[drain.TIER_LOCK_KEY.format(tier=TIER)] = holder
    if done is not None:
        store[drain.TIER_DONE_KEY.format(tier=TIER)] = done
    redis = FakeTierRedis(store)
    if retry:
        redis.hashes[drain.RETRY_KEY.format(tier=TIER)] = {
            str(k): str(v) for k, v in retry.items()
        }
    redis.observations.clear()
    redis._publish()
    return redis


def _on(drain, redis):
    """Point the module's Redis accessor at this fake, for one call."""
    original = drain._with_redis

    def _patched(tier, apply):
        try:
            apply(redis)
        except Exception:  # noqa: BLE001 — mirrors the real swallow
            pass

    drain._with_redis = _patched
    return original


def _takes_token(fn) -> bool:
    """Does this function accept a fencing token yet?

    🔴 THE CONTROLS HAVE TO BE GREEN IN BOTH ARMS, and passing a token
    unconditionally is what stops them being. The pre-fix `_record_attempts`
    takes five parameters, so a sixth positional argument is a `TypeError` and
    EVERY test in this file goes red — including the three that assert
    behaviour the repair must NOT change. A red-first arm in which the controls
    fail for a signature reason proves nothing: it cannot tell "the defect is
    present" from "the file does not compile against this tree".

    So the helpers ask. On the pre-fix tree the controls run the old code path
    and pass; only the cases about the defect and about the new fence fail.
    """
    import inspect

    return "token" in inspect.signature(fn).parameters


def _record(drain, redis, *, attempted, failed, prior, gave_up=0, token=MINE):
    original = _on(drain, redis)
    try:
        if _takes_token(drain._record_attempts):
            return drain._record_attempts(
                TIER, attempted, failed, prior, gave_up, token
            )
        return drain._record_attempts(TIER, attempted, failed, prior, gave_up)
    finally:
        drain._with_redis = original


def _mark(drain, redis, marker, token=MINE):
    original = _on(drain, redis)
    try:
        if _takes_token(drain._mark_done):
            return drain._mark_done(TIER, marker, token)
        return drain._mark_done(TIER, marker)
    finally:
        drain._with_redis = original


def _done_of(drain, redis):
    raw = redis.store.get(drain.TIER_DONE_KEY.format(tier=TIER))
    return raw.decode() if isinstance(raw, bytes) else raw


def _retry_of(drain, redis):
    return {
        int(k): int(v)
        for k, v in redis.hashes.get(drain.RETRY_KEY.format(tier=TIER), {}).items()
    }


# ---------------------------------------------------------------------------
# 1. THE CERT'S EXACT SEQUENCE, both orders
# ---------------------------------------------------------------------------


def test_the_graders_reverse_order_cannot_leave_drained_beside_an_owed_retry():
    """🔴 RED-FIRST, and it is CERT-794/795's reproduction verbatim.

    The sibling gets there first with a clean finish; the older runner, still
    holding a valid lease, then records the venue refusal it owes. Pre-fix this
    ends `done='drained'` beside `retry={7007: 1}` and 7007 is never retried
    again. The retry write now deletes the marker in its own transaction, so the
    tier is re-opened by the act of owing something.
    """
    drain = _drain()
    # The sibling's clean finish has already landed.
    redis = _redis(drain, done=drain.DONE_CLEAN)
    assert _done_of(drain, redis) == drain.DONE_CLEAN, "precondition"

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert _retry_of(drain, redis) == {EVENT: 1}, "the refusal is recorded"
    assert _done_of(drain, redis) is None, (
        "the tier is marked drained while it owes a retry on event 7007 — the "
        "next trigger returns on `state.done` and never retries it, and the "
        "match page stays incomplete behind a clean verdict (CERT-794/795)"
    )
    assert outcome.held is True


def test_the_forward_order_refuses_the_clean_marker_instead_of_writing_it():
    """The other order, which the re-open above cannot cover: the retry lands
    FIRST, and the sibling's settlement arrives after it. There is nothing to
    delete — the done key is empty — so `SET NX` would happily write `drained`
    over a tier that visibly owes work. The clean write now checks the retry
    hash on the same connection and reports `awaiting_retries`, which is not
    terminal, so the re-call loop picks the tier straight back up."""
    drain = _drain()
    redis = _redis(drain, retry={EVENT: 1})

    in_force = _mark(drain, redis, drain.DONE_CLEAN)

    assert in_force == drain.AWAITING_RETRIES
    assert _done_of(drain, redis) is None, "no terminal marker was written"
    assert in_force not in drain.TERMINAL_TIER_STATUSES, (
        "reporting a non-terminal answer is the point — a terminal one stops "
        "the operator's re-call loop"
    )


def test_a_tier_that_owes_nothing_still_settles_clean():
    """CONTROL, green in BOTH arms, and the one that matters most. A repair that
    bought the invariant by never writing `drained` would satisfy both cases
    above and turn the drain into something that can never finish."""
    drain = _drain()
    redis = _redis(drain)

    assert _mark(drain, redis, drain.DONE_CLEAN) == drain.DONE_CLEAN
    assert _done_of(drain, redis) == drain.DONE_CLEAN


def test_the_failure_ending_still_upgrades_a_clean_one():
    """CONTROL for CERT-773's repair, asserted here because this file changes
    `_mark_done`. `drained_with_failures` is a plain SET and must still be able
    to land on top of a clean marker — and it is NOT blocked by the retry hash,
    because giving up is precisely how an owed event leaves that hash."""
    drain = _drain()
    redis = _redis(drain, done=drain.DONE_CLEAN)

    assert _mark(drain, redis, drain.DONE_WITH_FAILURES) == drain.DONE_WITH_FAILURES
    assert _done_of(drain, redis) == drain.DONE_WITH_FAILURES


def test_the_re_open_and_the_retry_are_one_transaction():
    """The mechanism behind the first test, asserted directly. The invariant
    could also hold by luck of ordering, and luck is not a repair: the `hset`
    and the `delete` must go out inside ONE MULTI, so no reader can land between
    them and see the contradictory pair the cert reproduced."""
    drain = _drain()
    redis = _redis(drain, done=drain.DONE_CLEAN)

    _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert len(redis.transactions) == 1, "one block, not a command per round trip"
    transactional, names = redis.transactions[0]
    assert transactional, "a pipeline without MULTI is batching, not atomicity"
    assert names == ["hset", "delete"], names
    contradictory = [
        s for s in redis.visible_states(TIER) if s.done and s.retry
    ]
    assert contradictory == [], (
        "no reader may ever land on a terminal marker beside an owed retry"
    )


def test_giving_up_does_not_re_open_the_tier():
    """CONTROL for the re-open's scope. Deleting the marker is right when the
    pass ADDS an owed retry. A pass that only EMPTIES the hash (the event blew
    its budget and was counted) has not created new work and must leave the
    marker alone — otherwise a tier that legitimately ended with failures would
    be re-opened forever by its own last write."""
    drain = _drain()
    redis = _redis(
        drain, done=drain.DONE_WITH_FAILURES,
        retry={EVENT: drain.MAX_EVENT_RETRIES - 1},
    )

    outcome = _record(
        drain, redis, attempted=[EVENT], failed=[EVENT],
        prior={EVENT: drain.MAX_EVENT_RETRIES - 1},
    )

    assert _retry_of(drain, redis) == {}, "the event was given up on"
    assert outcome.gave_up_total == 1
    assert _done_of(drain, redis) == drain.DONE_WITH_FAILURES, (
        "the failure ending stands — nothing new is owed"
    )


# ---------------------------------------------------------------------------
# 2. THE FENCE — a writer that lost the lease writes nothing
# ---------------------------------------------------------------------------


def test_a_pass_whose_lease_a_sibling_took_records_no_retry():
    """The lease expired and a sibling took it, so the lock key now holds THEIR
    token. Everything this pass was about to persist is stale and must be
    dropped — including the retry, because recording it would put this pass's
    view of the tier back into a tier it no longer owns."""
    drain = _drain()
    redis = _redis(drain, holder=THEIRS)

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert outcome.held is False, "the caller must be able to see the refusal"
    assert _retry_of(drain, redis) == {}, "nothing was written"
    assert redis.commands == [
        ("get", (drain.TIER_LOCK_KEY.format(tier=TIER),), {}),
    ], "the fence read the lock and then issued nothing at all"


def test_a_pass_whose_lease_expired_outright_records_no_retry():
    """The other way to lose it: the key is simply gone (TTL elapsed, nobody has
    taken it yet). `GET` answers `None`, which is not our token, so the same
    refusal applies. A renewal must not be able to resurrect a dead lease."""
    drain = _drain()
    redis = _redis(drain, holder=None)

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert outcome.held is False
    assert _retry_of(drain, redis) == {}


def test_a_fenced_out_settlement_reports_lock_lost_and_writes_no_marker():
    """The verdict is the write with the worst consequence, so it is fenced too.
    A pass that lost the tier must not settle it — and must say so by name, not
    by reporting a terminal marker it never persisted."""
    drain = _drain()
    redis = _redis(drain, holder=THEIRS)

    assert _mark(drain, redis, drain.DONE_CLEAN) == drain.LOCK_LOST
    assert _done_of(drain, redis) is None
    assert drain.LOCK_LOST not in drain.TERMINAL_TIER_STATUSES


def test_a_fenced_out_cursor_write_does_not_move_the_cursor():
    """The cursor may advance past a FAILED event only because the retry hash
    remembers it. A writer that cannot record the retry must not record the
    advance either, or the failure is stepped over and never seen again."""
    drain = _drain()
    redis = _redis(drain, holder=THEIRS)
    original = _on(drain, redis)
    try:
        if _takes_token(drain._write_cursor):
            held = drain._write_cursor(TIER, (BASE, EVENT), MINE)
        else:
            held = drain._write_cursor(TIER, (BASE, EVENT))
    finally:
        drain._with_redis = original

    assert held is False
    assert drain.CHECKPOINT_KEY.format(tier=TIER) not in redis.store


def test_holding_the_lease_writes_AND_renews_it():
    """CONTROL, and the half that removes the race's precondition rather than
    its consequence. A pass that still holds the tier writes normally — and the
    same check refreshes the TTL, so a pass that keeps working keeps its tier.
    Without the renewal the fence would only make the failure quieter: the older
    runner would still lose the lease, just silently."""
    drain = _drain()
    redis = _redis(drain)

    outcome = _record(drain, redis, attempted=[EVENT], failed=[EVENT], prior={})

    assert outcome.held is True
    assert _retry_of(drain, redis) == {EVENT: 1}
    assert ("expire", (drain.TIER_LOCK_KEY.format(tier=TIER),
                       drain.TIER_LOCK_TTL_SECONDS), {}) in redis.commands, (
        "a fixed lease is a promise about how long a pass takes, and a promise "
        "about duration is not a lock — the write must renew it"
    )


def test_an_unreachable_redis_is_not_a_lost_lease():
    """FAIL OPEN, matching what `_acquire_tier_lock` already documents. If the
    server cannot be reached there is no lock, no sibling and no persisted
    verdict to corrupt, and reporting that as a lost lease would abort the drain
    over a blip. `held` is about ownership, not about whether Redis answered."""
    drain = _drain()

    class _Dead:
        def get(self, *a, **k):
            raise RuntimeError("connection refused")

        def expire(self, *a, **k):
            raise RuntimeError("connection refused")

        def pipeline(self, transaction=True):
            raise RuntimeError("connection refused")

    outcome = _record(
        drain, _Dead(), attempted=[EVENT], failed=[EVENT], prior={},
    )
    assert outcome.held is True, "a blip is not a sibling"
    assert outcome.owed == {EVENT: 1}, "the arithmetic answer still stands"


def test_a_dry_run_holds_without_touching_redis():
    """The sentinel's two answers, asserted on the new fence directly. A dry run
    took no lock because it persists nothing, and `_DRY_RUN_LOCK` keeps `None`
    meaning exactly one thing (locked out) at every call site. It must not issue
    a lock read to discover that. Red pre-fix because `_still_holds` does not
    exist there — this is a property OF the repair, not a control for it."""
    drain = _drain()
    redis = _redis(drain)

    original = _on(drain, redis)
    try:
        assert drain._still_holds(redis, TIER, drain._DRY_RUN_LOCK) is True
    finally:
        drain._with_redis = original
    assert redis.commands == [], "a dry run asked Redis nothing"
    assert drain._still_holds(redis, TIER, None) is False, (
        "`None` is LOCKED OUT and must never read as ownership"
    )
