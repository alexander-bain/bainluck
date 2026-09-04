"""A Redis fake for the 30-day chart drain's per-tier state — one, not three.

🔴 WHY THIS IS SHARED, and it is the CERT-773 lesson rather than tidiness. The
whole repair is about what a CONCURRENT READER can see, so the guards are only
as good as the fake's model of visibility. Three per-file fakes drift, and the
first one that publishes a transaction's commands individually turns every
interleaving test in that file green against a tree that has no transaction at
all. There is one fake, it models MULTI/EXEC, and every drain test uses it.

WHAT IT MODELS, and why each part is load-bearing:

* **Bytes on the wire.** A real client hashes fields as bytes, so `b"7007"` and
  `"7007"` are ONE field to a server and two to a dict, and hands values back as
  bytes — which is what `_decode` exists for. A fake that skips this lets a
  production `hdel(key, str(event_id))` look like it deleted a field it missed.
* **`SET NX` returns `True` or `None`.** The monotone done-marker turns on that
  answer: `None` means a terminal marker is already there and is not ours to
  replace. A fake that returned `True` unconditionally would make the downgrade
  guard look present while it did nothing.
* **`INCRBY` returns the value it stored.** CERT-764's repair reads that reply.
* **MULTI/EXEC publishes ONCE.** Commands queued on a transactional pipeline
  mutate the store only at `execute()`, and the whole block becomes visible as a
  single transition. :attr:`observations` records every state a reader could
  land on, which is what lets a test assert that the torn state CERT-773
  reproduced — retry hash emptied, give-up counter not yet incremented — is not
  among them.
* **WATCH aborts EXEC when a watched key moved** (live/055, #2766 — CERT-798's
  named follow-up `CHART-LEASE-ATOMIC-COMPARE-RENEW`). Every mutation bumps a
  per-key version; `watch()` snapshots the versions it saw, and `execute()`
  raises :class:`redis.exceptions.WatchError` — the real class, not a stand-in —
  if any of them changed. Without this the fake would run the optimistic fence
  and never once refuse, which is the same failure mode this module's header
  warns about twice already: a guard that looks present while it does nothing.

  🔴 `EXPIRE` BUMPS THE VERSION, because real Redis signals a watch on it. That
  is not a detail — it is why the lease RENEWAL has to be queued inside the
  MULTI rather than issued next to the token read. A renewal sent while watching
  would invalidate the pass's own WATCH and abort every single write.
"""

from typing import NamedTuple, Optional

try:  # The production fence catches this exact class; the fake must raise it.
    from redis.exceptions import WatchError
except Exception:  # pragma: no cover — redis is a hard dependency of the app
    class WatchError(Exception):  # type: ignore[no-redef]
        pass


class Observed(NamedTuple):
    """One state of a tier that a concurrent reader could actually see."""

    retry: dict
    gave_up: int
    done: Optional[str]
    cursor: Optional[str]


class FakeTierRedis:
    """Enough Redis to hold the drain's per-tier keys, with MULTI semantics."""

    def __init__(self, initial=None, hashes=None, on_publish=None, on_read=None):
        self.store = dict(initial or {})
        self.hashes = {k: dict(v) for k, v in (hashes or {}).items()}
        #: 🔴 A SECOND WORKER PROCESS. Called with this fake every time a state
        #: becomes visible, which is exactly the set of moments another process
        #: could read at. This is the only honest way to reproduce CERT-773 in a
        #: test: the real concurrency is across Celery workers, and a
        #: single-threaded event loop can never land a coroutine between two
        #: Redis round trips of another coroutine. Reentrancy is suppressed, so
        #: what the sibling itself writes does not recursively invoke it.
        self.on_publish = on_publish
        self._publishing = False
        #: 🔴 A SIBLING ACTING BETWEEN OUR TOKEN READ AND OUR WRITE (live/055,
        #: #2766). Called with `(self, key)` after every `GET` answers.
        #:
        #: WHY THE READ AND NOT `watch()`. This is the interposition point that
        #: exists in BOTH trees, which is what makes a guard built on it able to
        #: tell the two apart. Every version of this fence reads the lock token
        #: and then writes; only the fixed one holds a watch across the gap. A
        #: hook on `watch()` would simply never fire against unfenced code, so a
        #: test using it would go red for "nobody called watch" rather than for
        #: "the stolen lease's write landed anyway" — the second is the defect,
        #: the first is a proxy for it.
        #:
        #: Reentrancy is suppressed, so a sibling that reads does not recurse.
        self.on_read = on_read
        self._reading = False
        #: Every visible state, in order. Index 0 is the state before anything
        #: this test did, so a reader arriving at any moment saw one of these.
        self.observations: list = []
        #: Every command applied, `(name, args, kwargs)`, pipelined or not — so
        #: a test can assert on what was ISSUED as well as on what is visible.
        self.commands: list = []
        #: One entry per `execute()`: `(transaction_flag, [command names])`. A
        #: guard that only checked `commands` could not tell four round trips
        #: from one MULTI, which is the entire distinction CERT-773 turns on.
        self.transactions: list = []
        #: Per-key modification counter, the whole of WATCH's machinery. A key
        #: that has never been touched is absent, which reads as version 0, so
        #: watching a key that does not exist YET and having it appear is
        #: correctly seen as a change.
        self.versions: dict = {}
        #: One entry per `execute()` that WATCH refused, `(keys, )` — so a test
        #: can assert the abort happened rather than infer it from a side effect
        #: that did not occur.
        self.watch_aborts: list = []
        self._publish()

    # -- the wire ----------------------------------------------------------

    @staticmethod
    def _field(value):
        return value.decode() if isinstance(value, bytes) else str(value)

    def _touch(self, key) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def _fire_read(self, key) -> None:
        if self.on_read is None or self._reading:
            return
        self._reading = True
        try:
            self.on_read(self, key)
        finally:
            self._reading = False

    def _publish(self) -> None:
        """Record a state a concurrent reader could land on.

        Consecutive duplicates are collapsed, so `observations` is the list of
        visible TRANSITIONS rather than of commands: a read changes nothing and
        therefore cannot create a new state for anyone to see. That is what lets
        a guard count transitions and have the number mean something.
        """
        state = (dict(self.store), {k: dict(v) for k, v in self.hashes.items()})
        if self.observations and self.observations[-1] == state:
            return
        self.observations.append(state)
        if self.on_publish is None or self._publishing:
            return
        self._publishing = True
        try:
            self.on_publish(self)
        finally:
            self._publishing = False

    # -- primitives: they MUTATE, they do not publish ----------------------

    def _get(self, key):
        value = self.store.get(key)
        self._fire_read(key)
        return value

    def _set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None  # exactly what redis-py answers for a refused NX
        self.store[key] = value
        self._touch(key)
        return True

    def _delete(self, key):
        existed = self.store.pop(key, None) is not None
        if existed:
            self._touch(key)
        return 1 if existed else 0

    def _incrby(self, key, n):
        new = int(self.store.get(key, 0)) + n
        self.store[key] = new
        self._touch(key)
        return new

    def _hgetall(self, key):
        return {
            k.encode(): str(v).encode()
            for k, v in self.hashes.get(key, {}).items()
        }

    def _hset(self, key, mapping=None):
        target = self.hashes.setdefault(key, {})
        for field, value in (mapping or {}).items():
            target[self._field(field)] = self._field(value)
        if mapping:
            self._touch(key)
        return len(mapping or {})

    def _hdel(self, key, *ids):
        removed = 0
        for i in ids:
            if self.hashes.get(key, {}).pop(self._field(i), None) is not None:
                removed += 1
        if removed:
            self._touch(key)
        return removed

    def _hlen(self, key):
        """🔴 CERT-794/795. The clean done-marker refuses while this is non-zero,
        so a fake that always answered 0 would make the refusal look present
        while it did nothing — the same failure the `SET NX` note above warns
        about.

        Fires :attr:`on_read` for the same reason `_get` does (live/055, #2766):
        the settlement BRANCHES on this answer, so the instant right after it is
        where a sibling can invalidate the decision, and a test needs to be able
        to stand there."""
        length = len(self.hashes.get(key, {}))
        self._fire_read(key)
        return length

    def _expire(self, key, seconds):
        """Lease renewal. The fake holds no clock, so TTLs are not simulated: a
        test makes a lease expire by DELETING or overwriting the lock key, which
        is what expiry looks like to every reader anyway. What is modelled is
        that `expire` on a MISSING key is a no-op answering 0 — a renewal cannot
        resurrect a lease a sibling has already taken and released.

        🔴 A SUCCESSFUL EXPIRE BUMPS THE VERSION (live/055, #2766). Real Redis
        calls `signalModifiedKey` from the EXPIRE path, so a renewal issued while
        watching the lock invalidates the watcher's own WATCH. Modelling it is
        what forces the renewal to be queued INSIDE the MULTI; a fake that
        treated EXPIRE as invisible would let the production code renew in the
        watch phase and pass here while aborting every write in production."""
        if key not in self.store:
            return 0
        self._touch(key)
        return 1

    def _apply(self, name, args, kwargs):
        self.commands.append((name, args, dict(kwargs)))
        return getattr(self, f"_{name}")(*args, **kwargs)

    # -- direct commands: mutate, then publish -----------------------------

    def _run(self, name, *args, **kwargs):
        result = self._apply(name, args, kwargs)
        self._publish()
        return result

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

    def hlen(self, key):
        return self._run("hlen", key)

    def expire(self, key, seconds):
        return self._run("expire", key, seconds)

    def pipeline(self, transaction=True):
        return FakePipeline(self, transaction=transaction)

    # -- what a reader could have seen -------------------------------------

    def visible_states(self, tier: str) -> list:
        """Every :class:`Observed` state of one tier, in order."""
        from app.tasks import chart_backfill_thirty_day as drain

        retry_key = drain.RETRY_KEY.format(tier=tier)
        gave_up_key = drain.GAVE_UP_KEY.format(tier=tier)
        done_key = drain.TIER_DONE_KEY.format(tier=tier)
        cursor_key = drain.CHECKPOINT_KEY.format(tier=tier)
        seen = []
        for store, hashes in self.observations:
            seen.append(
                Observed(
                    retry={
                        int(k): int(v) for k, v in hashes.get(retry_key, {}).items()
                    },
                    gave_up=int(store.get(gave_up_key, 0) or 0),
                    done=store.get(done_key),
                    cursor=store.get(cursor_key),
                )
            )
        return seen


class FakePipeline:
    """MULTI/EXEC. Nothing queued here is visible until :meth:`execute`.

    `transaction=False` is honoured rather than ignored — a non-transactional
    pipeline publishes each command as it lands, which is the behaviour that
    re-opens CERT-773. Modelling it is how a test can prove the drain asked for
    a transaction instead of merely asking for a pipeline.
    """

    def __init__(self, redis: FakeTierRedis, transaction: bool = True):
        self._redis = redis
        self._transaction = transaction
        self._queued: list = []
        #: For assertions about what the block actually contained.
        self.executed: list = []
        #: `{key: version}` as of `watch()`, or `None` when not watching.
        #: redis-py's real pipeline goes into IMMEDIATE mode on `watch()` and
        #: back into buffered mode on `multi()`; both are modelled, because the
        #: read-branch-write the fence performs is only correct in that order.
        self._watched: Optional[dict] = None
        self._immediate = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.reset()
        return False

    # -- WATCH / MULTI (live/055, #2766) -----------------------------------

    def watch(self, *keys):
        self._watched = {k: self._redis.versions.get(k, 0) for k in keys}
        self._immediate = True
        return True

    def unwatch(self):
        self._watched = None
        self._immediate = False
        return True

    def multi(self):
        """Leave immediate mode; everything after this is queued until EXEC.

        redis-py raises if you call this without watching or twice; the fake
        does not need to police that, and pretending to would only add a way for
        a test to fail for a reason production cannot have.
        """
        self._immediate = False
        return None

    def reset(self):
        self._queued = []
        self.unwatch()

    def _queue(self, name, *args, **kwargs):
        if self._immediate:
            # Watching, pre-MULTI: redis-py runs the command straight away and
            # hands back the real answer. This is the only mode in which the
            # fence can READ and then BRANCH.
            return self._redis._run(name, *args, **kwargs)
        self._queued.append((name, args, kwargs))
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

    def hlen(self, key):
        return self._queue("hlen", key)

    def expire(self, key, seconds):
        return self._queue("expire", key, seconds)

    def execute(self):
        # 🔴 THE ABORT. Checked BEFORE anything is applied, which is the whole
        # point: a transaction whose watched key moved must leave the store
        # exactly as it found it, so the caller's refusal is a refusal and not a
        # half-write it then has to reason about.
        if self._watched is not None:
            moved = [
                k for k, v in self._watched.items()
                if self._redis.versions.get(k, 0) != v
            ]
            if moved:
                self._redis.watch_aborts.append(tuple(moved))
                self.reset()
                raise WatchError(
                    "Watched variable changed: " + ", ".join(sorted(moved))
                )

        queued, self._queued = self._queued, []
        self.executed = list(queued)
        self._redis.transactions.append(
            (self._transaction, [name for name, _a, _k in queued])
        )
        results = []
        for name, args, kwargs in queued:
            results.append(self._redis._apply(name, args, kwargs))
            if not self._transaction:
                # Pipelining without MULTI is just batching: every command is
                # separately visible, which is the shape CERT-773 blocked.
                self._redis._publish()
        if self._transaction:
            self._redis._publish()
        self.unwatch()
        return results
