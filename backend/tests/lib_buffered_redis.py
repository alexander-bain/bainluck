"""Issue #1813: an execution-dependent buffered Redis test double.

The fakes this replaces applied every queued write the moment it was queued
(``pipeline()`` returned ``self`` and ``set``/``incr``/``hset``/``expire``
mutated the store inline) while the latency tests used bare ``MagicMock``
pipes whose call ledger exists before anything is published. Both shapes make
an omitted ``pipe.execute()`` unobservable: the owning suites stay green even
though real Redis would publish nothing.

This double queues pipeline writes and applies them only in ``execute()``:

* reads (``get``/``ttl``/``hget``/``hgetall``/``lrange``/``keys``/``smembers``)
  see committed state only — queued ops are invisible until ``execute()``;
* a pipe that is never executed publishes nothing (its queue is dropped with
  it — ``discard()`` makes that explicit);
* an ``execute()`` that fails BEFORE dispatch (``execute_raises`` /
  ``fail_all_executes``) publishes nothing: the queue is dropped without
  applying any op. This models only a failure before dispatch (connection
  down, injected fault). It is NOT a general Redis transaction/rollback
  claim: queued ops apply in order with no rollback, so a mid-queue op error
  can leave earlier ops visible — as with a real non-transactional pipeline.

Write semantics model real Redis where the existing suites already depend on
it (the LAT-P022/LAT-P024 lessons): ``SET NX`` declines when the key exists
in ANY type, ``INCR`` creates a missing key with NO expiry and never
refreshes an existing one, ``EXPIRE`` on a missing key is a no-op, list
``LRANGE``/``LTRIM`` resolve negative ends from the tail, and a plain
``SET`` without ``EX`` clears any existing TTL.

The ``calls`` ledger records what the client *queued* (at queue time), not
what was published — it is a record of the calls, and existing call-shape
assertions (e.g. ``TestWindowCounterDoesNotSlide``) keep reading it unchanged.
Publication is observable only through the stores. That split is deliberate:
a test that wants "was it flushed?" must read state, never the ledger.

Scope: used only by the #1813 tranche files (delivery/metrics writers and the
latency middleware). Not a repo-wide fake.
"""

from __future__ import annotations


def to_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode()


# Back-compat alias used inside this module.
_b = to_bytes


def _list_span(length, start, stop):
    """Inclusive ``[start, stop]`` bounds with Redis negative-index semantics.

    A negative index counts from the tail (``-1`` is the last element).
    Returns ``(lo, hi)`` or ``None`` for an empty selection (``start > stop``
    after normalization, or ``start`` past the end).
    """
    if start < 0:
        start += length
    if stop < 0:
        stop += length
    if start < 0:
        start = 0
    if stop >= length:
        stop = length - 1
    if start > stop or start >= length:
        return None
    return (start, stop)


class BufferedPipeline:
    """One pipeline: queues writes, publishes them only on ``execute()``."""

    def __init__(self, store: "BufferedRedis"):
        self._store = store
        self._queued: list[tuple] = []
        #: When set, ``execute()`` fails BEFORE dispatch: the queue is dropped
        #: and this is raised without applying any op. Pre-dispatch only —
        #: a mid-queue op error below applies in order with no rollback.
        self.execute_raises: BaseException | None = None

    def discard(self):
        """Drop the queued writes without publishing them."""
        self._queued = []
        return True

    def execute(self):
        if self.execute_raises is not None:
            self._queued = []
            raise self.execute_raises
        queued, self._queued = self._queued, []
        out = []
        # Sequential apply, no rollback: a mid-queue op error leaves earlier
        # ops visible (real non-transactional pipeline semantics).
        for op in queued:
            out.append(self._store._apply(op))
        return out

    # --- queued writes --------------------------------------------------
    def _q(self, op):
        self._store.calls.append(op)
        self._queued.append(op)
        return True

    def set(self, key, value, ex=None, nx=False):
        return self._q(("set", key, value, ex, nx))

    def incr(self, key):
        return self._q(("incr", key))

    def expire(self, key, ttl):
        return self._q(("expire", key, ttl))

    def hset(self, key, field=None, value=None, mapping=None):
        return self._q(("hset", key, field, value, dict(mapping or {})))

    def lpush(self, key, value):
        return self._q(("lpush", key, value))

    def ltrim(self, key, start, end):
        return self._q(("ltrim", key, start, end))

    def zadd(self, key, mapping):
        return self._q(("zadd", key, dict(mapping)))

    def zremrangebyscore(self, key, lo, hi):
        return self._q(("zremrangebyscore", key, lo, hi))

    def zremrangebyrank(self, key, start, stop):
        return self._q(("zremrangebyrank", key, start, stop))

    def sadd(self, key, *members):
        return self._q(("sadd", key, members))


class BufferedRedis:
    """Committed stores plus a queueing ``pipeline()``.

    Subclasses override ``keys()`` where a reader needs a narrower answer;
    everything else is shared so the three writer suites grade the same
    publication discipline.
    """

    def __init__(self):
        self.strings: dict = {}
        self.hashes: dict = {}
        self.lists: dict = {}
        self.zsets: dict = {}
        self.sets: dict = {}
        self.ttls: dict = {}
        #: What the client queued, in order (call record, NOT publication).
        self.calls: list[tuple] = []
        self.pipeline_count = 0
        #: When set, every new pipe's ``execute()`` fails BEFORE dispatch
        #: with this: the queue is dropped, nothing is applied.
        self.fail_all_executes: BaseException | None = None

    # --- plumbing ---------------------------------------------------------
    def pipeline(self, *args, **kwargs):
        self.pipeline_count += 1
        pipe = BufferedPipeline(self)
        if self.fail_all_executes is not None:
            pipe.execute_raises = self.fail_all_executes
        return pipe

    def _exists(self, key) -> bool:
        return (
            key in self.strings
            or key in self.hashes
            or key in self.lists
            or key in self.zsets
            or key in self.sets
        )

    def _apply(self, op):
        kind = op[0]
        if kind == "set":
            _, key, value, ex, nx = op
            if nx and self._exists(key):
                return None
            self.strings[key] = _b(value)
            if ex is not None:
                self.ttls[key] = ex
            elif key in self.ttls:
                # Real SET without EX/KEEPTTL clears the TTL.
                del self.ttls[key]
            return True
        if kind == "incr":
            _, key = op
            self.strings[key] = str(int(self.strings.get(key, b"0")) + 1).encode()
            return self.strings[key]
        if kind == "expire":
            _, key, ttl = op
            if self._exists(key):
                self.ttls[key] = ttl
                return True
            return False
        if kind == "hset":
            _, key, field, value, mapping = op
            target = self.hashes.setdefault(key, {})
            for f, v in mapping.items():
                target[_b(f)] = _b(v)
            if field is not None:
                target[_b(field)] = _b(value)
            return True
        if kind == "lpush":
            _, key, value = op
            self.lists.setdefault(key, []).insert(0, _b(value))
            return True
        if kind == "ltrim":
            _, key, start, end = op
            items = list(self.lists.get(key, []))
            span = _list_span(len(items), start, end)
            self.lists[key] = items[span[0]:span[1] + 1] if span is not None else []
            return True
        if kind == "zadd":
            _, key, mapping = op
            target = self.zsets.setdefault(key, {})
            for member, score in mapping.items():
                target[str(member)] = float(score)
            return True
        if kind == "zremrangebyscore":
            _, key, lo, hi = op
            target = self.zsets.get(key, {})
            lo_f = float("-inf") if lo == "-inf" else float(lo)
            hi_f = float("inf") if hi == "+inf" else float(hi)
            for member in [m for m, s in target.items() if lo_f <= s <= hi_f]:
                del target[member]
            return True
        if kind == "zremrangebyrank":
            _, key, start, stop = op
            target = self.zsets.get(key, {})
            ordered = sorted(target.items(), key=lambda kv: (kv[1], kv[0]))
            n = len(ordered)
            stop_i = stop if stop >= 0 else n + stop
            for member, _ in ordered[start:stop_i + 1]:
                del target[member]
            return True
        if kind == "sadd":
            _, key, members = op
            target = self.sets.setdefault(key, set())
            for m in members:
                target.add(str(m))
            return True
        raise AssertionError(f"unknown queued op: {kind}")

    # --- direct (non-pipelined) writes --------------------------------------
    # Real Redis publishes these at call time — only pipeline writes wait for
    # `execute()` — so they commit immediately (e.g. `single_flight.acquire`'s
    # `client.set(..., nx=True)`). They bypass the `calls` ledger, which
    # records pipeline queueing only, matching the doubles this replaces.
    def set(self, key, value, ex=None, nx=False):
        return self._apply(("set", key, value, ex, nx))

    def incr(self, key):
        return self._apply(("incr", key))

    def expire(self, key, ttl):
        return self._apply(("expire", key, ttl))

    def hset(self, key, field=None, value=None, mapping=None):
        return self._apply(("hset", key, field, value, dict(mapping or {})))

    # --- reads: committed state only --------------------------------------
    def get(self, key):
        return self.strings.get(key)

    def ttl(self, key):
        """Redis TTL contract: -2 no such key, -1 exists with no expiry."""
        if not self._exists(key):
            return -2
        return self.ttls.get(key, -1)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(_b(field))

    def lrange(self, key, start, end):
        items = list(self.lists.get(key, []))
        span = _list_span(len(items), start, end)
        if span is None:
            return []
        return items[span[0]:span[1] + 1]

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def keys(self, pattern):
        import fnmatch

        all_keys = (
            set(self.strings)
            | set(self.hashes)
            | set(self.lists)
            | set(self.zsets)
            | set(self.sets)
        )
        return [k.encode() for k in all_keys if fnmatch.fnmatchcase(k, pattern)]
