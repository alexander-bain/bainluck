#!/usr/bin/env python3
"""CERT-773's race, driven end to end — runnable against ANY head of the drain.

    python3 scripts/repro_cert773_race.py

The cert's reproduction, verbatim:

    Independent race reproduction starts with retry `{7007: 2}`, give-up count
    `0`, and the cursor at the tier end. Trigger A's third failure removes
    `7007`; Trigger B reads before A's `INCRBY` and gets `retry={}`,
    `gave_up=0`, `done=None`; A then persists `drained_with_failures`, B
    persists `drained`, and the final Redis state is `gave_up=1` beside
    `done=drained`.

🔴 WHY THIS IS A SCRIPT AND NOT ONLY A TEST. Trigger B is a SECOND CELERY WORKER
PROCESS, and no arrangement of coroutines inside one event loop can land B
between two Redis round trips of A — the loop only yields at an `await`, and
there is none between `hdel` and `incrby`. So B is modelled where the tearing
actually happens: at the Redis boundary. The fake below calls B at every moment
a state becomes VISIBLE, which is exactly the set of moments another process
could read at, and it is the complete set rather than a hand-picked one.

The script imports nothing that the pre-fix tree lacks, so it runs unchanged on
both heads and the two outputs are directly comparable. It writes nothing
outside its own memory and touches no network, no database and no real Redis.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TIER = "us_open"
EVENT = 7007
#: The keyset position the tier ended on. Both halves, because half a keyset
#: is not a position (the module refuses one).
END_CURSOR = (datetime(2026, 9, 1, tzinfo=timezone.utc), EVENT)


class Redis:
    """Enough Redis to hold one tier's four keys, with MULTI/EXEC semantics.

    Deliberately standalone rather than importing the test library: this has to
    run against a checkout of the blocked subject, where that library does not
    exist. `on_publish` is trigger B.
    """

    def __init__(self):
        self.store = {}
        self.hashes = {}
        self.on_publish = None
        self._busy = False
        self.log = []

    @staticmethod
    def _f(v):
        return v.decode() if isinstance(v, bytes) else str(v)

    # -- mutation, without publishing -------------------------------------
    def _get(self, key):
        return self.store.get(key)

    def _set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def _delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def _incrby(self, key, n):
        self.store[key] = int(self.store.get(key, 0)) + n
        return self.store[key]

    def _hgetall(self, key):
        return {
            k.encode(): str(v).encode()
            for k, v in self.hashes.get(key, {}).items()
        }

    def _hset(self, key, mapping=None):
        t = self.hashes.setdefault(key, {})
        for f, v in (mapping or {}).items():
            t[self._f(f)] = self._f(v)
        return len(mapping or {})

    def _hdel(self, key, *ids):
        return sum(
            1 for i in ids
            if self.hashes.get(key, {}).pop(self._f(i), None) is not None
        )

    def _apply(self, name, args, kwargs):
        self.log.append(name)
        return getattr(self, f"_{name}")(*args, **kwargs)

    # -- a state becomes visible -------------------------------------------
    def _publish(self):
        if self.on_publish is None or self._busy:
            return
        self._busy = True
        try:
            self.on_publish()
        finally:
            self._busy = False

    def _run(self, name, *args, **kwargs):
        out = self._apply(name, args, kwargs)
        self._publish()
        return out

    def get(self, key):
        return self._run("get", key)

    def set(self, key, value, nx=False, ex=None):
        return self._run("set", key, value, nx=nx, ex=ex)

    def delete(self, key):
        return self._run("delete", key)

    def incrby(self, key, n):
        return self._run("incrby", key, n)

    def hgetall(self, key):
        return self._run("hgetall", key)

    def hset(self, key, mapping=None):
        return self._run("hset", key, mapping=mapping)

    def hdel(self, key, *ids):
        return self._run("hdel", key, *ids)

    def pipeline(self, transaction=True):
        return Pipeline(self, transaction)


class Pipeline:
    def __init__(self, redis, transaction=True):
        self.r = redis
        self.tx = transaction
        self.q = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _queue(self, name, *a, **k):
        self.q.append((name, a, k))
        return self

    def get(self, key):
        return self._queue("get", key)

    def set(self, key, value, nx=False, ex=None):
        return self._queue("set", key, value, nx=nx, ex=ex)

    def delete(self, key):
        return self._queue("delete", key)

    def incrby(self, key, n):
        return self._queue("incrby", key, n)

    def hgetall(self, key):
        return self._queue("hgetall", key)

    def hset(self, key, mapping=None):
        return self._queue("hset", key, mapping=mapping)

    def hdel(self, key, *ids):
        return self._queue("hdel", key, *ids)

    def execute(self):
        q, self.q = self.q, []
        out = []
        for name, a, k in q:
            out.append(self.r._apply(name, a, k))
            if not self.tx:
                self.r._publish()
        if self.tx:
            self.r._publish()
        return out


def main() -> int:
    import app.tasks.chart_backfill_thirty_day as drain
    import app.tasks.redis_state as redis_state

    redis = Redis()
    redis_state.get_redis_client = lambda *a, **k: redis
    drain.INTER_EVENT_SLEEP_SECONDS = 0

    retry_key = drain.RETRY_KEY.format(tier=TIER)
    gave_up_key = drain.GAVE_UP_KEY.format(tier=TIER)
    done_key = drain.TIER_DONE_KEY.format(tier=TIER)
    cursor_key = drain.CHECKPOINT_KEY.format(tier=TIER)

    # ---- the cert's starting state ------------------------------------
    redis.hashes[retry_key] = {str(EVENT): str(drain.MAX_EVENT_RETRIES - 1)}
    redis.store[gave_up_key] = 0
    redis.store[cursor_key] = "%s|%d" % (END_CURSOR[0].isoformat(), EVENT)

    print("CERT-773 race reproduction")
    print("=" * 72)
    head = os.popen("git rev-parse HEAD").read().strip()
    dirty = os.popen("git status --porcelain").read().strip()
    print("head under test : %s%s" % (head, "  (+ uncommitted changes)" if dirty else ""))
    print("start state     : retry=%r gave_up=%r done=%r (cursor at tier end)" % (
        {EVENT: drain.MAX_EVENT_RETRIES - 1}, 0, None,
    ))
    print()

    # ---- trigger B: a second worker, reading at every visible moment ----
    #
    # B READS at every moment, and its LAST read is kept so phase 2 can settle
    # from it. The cert's ordering has B persisting after A, which is what makes
    # the damage permanent, and that ordering is arbitrary between two OS
    # processes — so both are shown rather than picking the flattering one.
    b_reads = []
    b_settled = []
    exhausted = drain.DrainPage([], END_CURSOR, True, 0)

    def settle_as(state, who):
        report = {}
        marker = drain._settle_tier(
            TIER, drain.DrainPage([], END_CURSOR, True, 0), report,
            owed=state.retry, gave_up=state.gave_up, dry_run=False,
        )
        print("  %s reads  retry=%-12r gave_up=%d done=%-22r -> settles %r"
              % (who, dict(state.retry), state.gave_up, state.done,
                 marker or report.get("status")))
        return marker

    def trigger_b():
        state = drain._read_checkpoint(TIER)
        b_reads.append(state)
        if state.done:
            return  # terminal already: a real sibling moves to the next tier
        marker = settle_as(state, "B")
        if marker is not None:
            b_settled.append(marker)

    redis.on_publish = trigger_b

    # ---- phase 1: B settles the moment it reads --------------------------
    print("PHASE 1 — B settles as soon as it reads (A's write still in flight)")
    print("A: third failed fetch of event %d (retry budget exhausted)" % EVENT)
    outcome = drain._record_attempts(
        TIER, [EVENT], [EVENT], {EVENT: drain.MAX_EVENT_RETRIES - 1}, 0,
    )
    owed = outcome.owed if hasattr(outcome, "owed") else outcome
    total = getattr(outcome, "gave_up_total", None)
    print("A: _record_attempts -> owed=%r gave_up_total=%r" % (owed, total))

    redis.on_publish = None  # A settles alone; B has had every look it gets
    a_report = {}
    a_marker = drain._settle_tier(
        TIER, exhausted, a_report,
        owed=owed, gave_up=total if total is not None else 0, dry_run=False,
    )
    print("A: _settle_tier     -> %r" % a_marker)

    torn = [r for r in b_reads if not r.retry and r.gave_up == 0 and not r.done]
    print("B's reads           : %d, of which TORN "
          "(retry={} gave_up=0 done=None): %d" % (len(b_reads), len(torn)))
    print("B settled           : %r" % (b_settled or "nothing terminal",))
    print("Redis command log   : %s" % " ".join(redis.log))
    print("final Redis state   : gave_up=%d  done=%r" % (
        int(redis.store.get(gave_up_key, 0) or 0), redis.store.get(done_key),
    ))
    print()

    # ---- phase 2: the cert's literal ordering — B persists LAST ----------
    #
    # Same interleaving, on a FRESH tier, with B's settlement deferred until
    # after A's. B settles from the state it READ mid-write, which is the whole
    # point: B is not re-reading, it is acting on a snapshot it took earlier.
    # This is the ordering the cert names, and the one whose damage is
    # permanent — B's marker is the last word.
    print("PHASE 2 — the cert's ordering: B reads mid-write, A persists, B "
          "persists LAST")
    redis.store.clear()
    redis.hashes.clear()
    redis.log.clear()
    redis.hashes[retry_key] = {str(EVENT): str(drain.MAX_EVENT_RETRIES - 1)}
    redis.store[gave_up_key] = 0
    redis.store[cursor_key] = "%s|%d" % (END_CURSOR[0].isoformat(), EVENT)

    p2_reads = []

    def b_only_reads():
        p2_reads.append(drain._read_checkpoint(TIER))

    redis.on_publish = b_only_reads
    outcome2 = drain._record_attempts(
        TIER, [EVENT], [EVENT], {EVENT: drain.MAX_EVENT_RETRIES - 1}, 0,
    )
    redis.on_publish = None
    owed2 = outcome2.owed if hasattr(outcome2, "owed") else outcome2
    total2 = getattr(outcome2, "gave_up_total", None)
    drain._settle_tier(
        TIER, exhausted, {},
        owed=owed2, gave_up=total2 if total2 is not None else 0, dry_run=False,
    )
    print("A: settled first    -> done=%r" % redis.store.get(done_key))

    # The snapshot B is holding: the torn one if the tree let it exist, else
    # the only one it could have taken.
    p2_torn = [r for r in p2_reads if not r.retry and r.gave_up == 0 and not r.done]
    held = (p2_torn or p2_reads or [None])[0]
    if held is None:
        print("  B never got a look in; nothing to replay.")
        b2_marker = None
    else:
        b2_marker = settle_as(held, "B")
    final_done = redis.store.get(done_key)
    final_gave_up = int(redis.store.get(gave_up_key, 0) or 0)
    print("final Redis state   : gave_up=%d  done=%r" % (final_gave_up, final_done))
    print()

    # ---- the verdict ----------------------------------------------------
    reproduced = (
        final_done == drain.DONE_CLEAN
        or drain.DONE_CLEAN in b_settled
        or b2_marker == drain.DONE_CLEAN
    )
    if reproduced:
        print("VERDICT: REPRODUCED — a clean %r was settled over an abandoned "
              "event." % drain.DONE_CLEAN)
        print("         This is CERT-773's finding. The tier is permanently, "
              "cleanly finished")
        print("         and event %d stays thin behind it." % EVENT)
        return 1
    print("VERDICT: NOT REPRODUCED — no reader, at any moment and in either "
          "order,")
    print("         could settle a clean %r. gave_up=%d stands beside done=%r,"
          % (drain.DONE_CLEAN, final_gave_up, final_done))
    print("         which is the honest ending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
