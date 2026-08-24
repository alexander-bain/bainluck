"""Process-local sharing for the principal-INDEPENDENT half of a feed build.

#2143 / LAT-P084 (Fable addendum, 2026-08-24, pasted and reviewed by Alex).

## The measurement

Two distinct principals, back to back against production slug v3886 on
2026-08-24, both cache misses, both paying a full cold build:

    A  4447.89ms   futures=2732.76 concepts=1249.04 canonical_counts=702.33
                   market_load=566.86 scoring_loop=321.80 events=279.98
                   personalization=105.60 golf=52.45
    B  4033.75ms   futures=2774.62 concepts=865.02  canonical_counts=683.04
                   market_load=616.50 scoring_loop=304.76 events=280.84
                   personalization=35.09  golf=52.06

Bit-identical output: `returned=20,total=103,type_bundle=5,type_concept=1,
type_event=2,type_futures=12` for both. `personalization` — 35ms and 106ms —
is the only substantially principal-dependent stage. Better than a third (the
decontaminated 2026-08-24 headline says 53.8%) of feed requests are misses, so
this duplicated work is what half of real users wait on.

## What this module is

A bounded, TTL'd, process-local cache for build artifacts that are a pure
function of principal-INDEPENDENT inputs. It is deliberately NOT Redis: the
artifacts are per-worker-cheap and the point is to remove work from the request
path, not to add a network hop to it (a Redis round trip inside the miss path is
how #1459 was made worse once already).

Three properties make it safe to put on the hot path:

1. **Only plain data may be shared.** `assert_plain_data` walks the value and
   refuses anything that is not None/bool/int/float/str/datetime/date/Decimal or
   a list/tuple/dict of those. A hydrated ORM row therefore CANNOT enter this
   cache. That is not a stylistic preference — #2107 (`DetachedInstanceError` on
   a cross-request cached ORM row) is a live P0 whose seven-day watch opened at
   T0 = 2026-08-24T17:23:50Z with zero days banked. This is the mechanical form
   of "we are not doing that again", and it is why `futures.market_load`
   (567-617ms of hydrated rows) is left on the table by this change.

2. **Copies in, copies out.** The stored artifact is deep-copied on store and on
   every read. The feed's display chain mutates items in place (`_rank_score`,
   bundling, pin flags), so handing out a reference would let one principal
   scribble on the next principal's cards. This is the same mutable-by-reference
   class as the C-2107-R1 `season_stats` P3 fixed earlier in this queue; that
   one was found by review, this one is closed by construction.

3. **Fail-open on the response, fail-closed on the sharing.** Every failure mode
   here — a non-plain value, a bad key, a lock timeout — degrades to "build it
   the way we build it today" and returns the caller's value. A cache that can
   500 the endpoint it was added to speed up is a net loss at any hit rate.

Singleflight is included because the production miss pattern is a BURST (one
burst supplied 13 of the 28 misses in the decontaminated headline window).
Without it, concurrent cold principals each pay the full build and the shared
cache saves nothing for exactly the requests that hurt most. The lock wait is
bounded, so a coalesced caller is never worse off than a caller that just built.

Kill switch: `FEED_SHARED_BUILD_TTL_S=0` turns sharing off process-wide without
a code change; every call then builds, exactly as before this module existed.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
import os
import time
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)


class NotPlainData(TypeError):
    """A value (or a cache key) is not safe to share across requests."""


# The ONLY namespaces whose reuse may be named on the public `X-Feed-Shared`
# response header. A fixed allowlist of fixed strings — never a key, never a
# principal, never a query parameter. Anything else shares silently.
SHARED_ARTIFACT_NAMES: frozenset[str] = frozenset({"concepts", "canonical_counts"})

#: Per-namespace entry cap. Concepts key on (sport_filter, minute-bucket) and
#: canonical counts on a digest of the candidate key set, so the live cardinality
#: is small; the cap exists so an unexpected key explosion cannot grow a
#: process-global dict without bound.
MAX_ENTRIES_PER_NAMESPACE = 64

#: Default staleness bound. The concept build embeds `now`-derived text and pin
#: state, so the TTL is what bounds how wrong that can be. 60s is far below the
#: coarsest boundary those values move on (marquee pin windows are hours).
DEFAULT_TTL_S = 60.0

#: How long a coalesced caller waits for the in-flight build before giving up
#: and building for itself. A waiter must never end up SLOWER than a solo
#: builder, and a shared build that wedges must not wedge the endpoint.
LOCK_WAIT_S = 8.0

_PLAIN_SCALARS = (bool, int, float, str, datetime, date, Decimal)
_MAX_DEPTH = 16
_MAX_NODES = 200_000

_KEY_SCALARS = (bool, int, float, str)


# --------------------------------------------------------------------------
# guards
# --------------------------------------------------------------------------


def assert_plain_data(value: Any) -> None:
    """Raise `NotPlainData` unless `value` is safe to hold across requests.

    "Safe" means: no ORM instances, no live sessions, no objects with identity
    or lazy-loading behaviour — only inert data a JSON encoder would accept
    (plus datetime/date/Decimal, which the feed's own card dicts carry).
    """
    nodes = 0

    def _walk(node: Any, depth: int, path: str) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_NODES:
            raise NotPlainData(f"value too large to validate at {path}")
        if depth > _MAX_DEPTH:
            raise NotPlainData(f"value nested deeper than {_MAX_DEPTH} at {path}")
        if node is None or isinstance(node, _PLAIN_SCALARS):
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k is not None and not isinstance(k, _KEY_SCALARS):
                    raise NotPlainData(
                        f"dict key of type {type(k).__name__} at {path}"
                    )
                _walk(v, depth + 1, f"{path}[{k!r}]")
            return
        if isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                _walk(v, depth + 1, f"{path}[{i}]")
            return
        raise NotPlainData(
            f"{type(node).__name__} at {path} is not shareable across requests"
        )

    _walk(value, 0, "value")


def assert_shared_key(key: Any) -> None:
    """Raise `NotPlainData` unless `key` is a tuple of hashable scalars.

    The cache cannot know what a principal IS — but a user object, a session
    dict, or a `PersonalizationContext` would all have to be smuggled in as a
    non-scalar, and this refuses all of them. It is a structural bound on the
    only way principal identity could reach a key by accident.
    """
    if not isinstance(key, tuple):
        raise NotPlainData(f"shared key must be a tuple, got {type(key).__name__}")

    def _walk(node: Any, depth: int) -> None:
        if depth > 4:
            raise NotPlainData("shared key nested too deeply")
        if node is None or isinstance(node, _KEY_SCALARS):
            return
        if isinstance(node, tuple):
            for v in node:
                _walk(v, depth + 1)
            return
        raise NotPlainData(
            f"{type(node).__name__} is not allowed in a shared cache key"
        )

    _walk(key, 0)


def shared_build_ttl_s() -> float:
    """The process-wide TTL, from `FEED_SHARED_BUILD_TTL_S`. 0 disables sharing."""
    raw = os.environ.get("FEED_SHARED_BUILD_TTL_S")
    if raw is None:
        return DEFAULT_TTL_S
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_TTL_S


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------

# namespace -> {key: (stored_at, value)}
_store: dict[str, dict[tuple, tuple[float, Any]]] = {}
# namespace -> {key: asyncio.Lock}
_locks: dict[str, dict[tuple, asyncio.Lock]] = {}
_stats: dict[str, int] = {"hits": 0, "builds": 0, "refused": 0, "coalesced": 0}


def clear_shared_builds(namespace: Optional[str] = None) -> None:
    """Drop shared artifacts. Test hygiene and an operational escape hatch."""
    if namespace is None:
        _store.clear()
        _locks.clear()
        for k in _stats:
            _stats[k] = 0
        return
    _store.pop(namespace, None)
    _locks.pop(namespace, None)


def peek_shared_build(namespace: str) -> Any:
    """Return the most recently stored value in `namespace`, BY REFERENCE.

    Introspection for tests and diagnostics only — production readers must go
    through `get_or_build`, which copies. Returning the reference here is what
    lets a test prove that scribbling on the stored artifact cannot reach the
    next reader.
    """
    entries = _store.get(namespace)
    if not entries:
        return None
    newest = max(entries.values(), key=lambda kv: kv[0])
    return newest[1]


def shared_build_stats() -> dict[str, int]:
    """Counters for the admin/latency panel. Identity-free integers only."""
    out = dict(_stats)
    out["entries"] = sum(len(v) for v in _store.values())
    out["namespaces"] = len(_store)
    return out


def _evict_if_needed(entries: dict[tuple, tuple[float, Any]]) -> None:
    while len(entries) > MAX_ENTRIES_PER_NAMESPACE:
        oldest = min(entries.items(), key=lambda kv: kv[1][0])[0]
        entries.pop(oldest, None)


def _lock_for(namespace: str, key: tuple) -> asyncio.Lock:
    ns = _locks.setdefault(namespace, {})
    lock = ns.get(key)
    if lock is None:
        lock = asyncio.Lock()
        ns[key] = lock
        # Prune idle locks so a key explosion cannot grow this dict forever.
        if len(ns) > MAX_ENTRIES_PER_NAMESPACE * 2:
            for k, lk in list(ns.items()):
                if k != key and not lk.locked():
                    ns.pop(k, None)
    return lock


def _read_fresh(
    namespace: str, key: tuple, ttl_s: float, now: float
) -> tuple[bool, Any]:
    entries = _store.get(namespace)
    if not entries:
        return False, None
    hit = entries.get(key)
    if hit is None:
        return False, None
    stored_at, value = hit
    if (now - stored_at) > ttl_s:
        entries.pop(key, None)
        return False, None
    return True, value


# The ambient reuse sink for one request. A contextvar rather than a threaded
# parameter because the second shared artifact (`canonical_counts`) is resolved
# three call frames below the route, inside `_score_futures`, and threading a
# diagnostic through a scoring signature is how a diagnostic ends up omitted on
# one of the paths (which is exactly what Queue 275 had to go back and fix for
# the stage headers).
_reuse_sink_var: ContextVar[Optional[list]] = ContextVar(
    "feed_shared_reuse_sink", default=None
)


def bind_reuse_sink(sink: list) -> None:
    """Bind `sink` as the ambient reuse sink for the current context."""
    _reuse_sink_var.set(sink)


@contextlib.contextmanager
def reuse_scope(sink: list) -> Iterator[None]:
    """Collect shared-artifact reuse into `sink` for the duration of this scope."""
    token = _reuse_sink_var.set(sink)
    try:
        yield
    finally:
        _reuse_sink_var.reset(token)


def _note_reuse(namespace: str, reuse_sink: Optional[list]) -> None:
    _stats["hits"] += 1
    sink = reuse_sink if reuse_sink is not None else _reuse_sink_var.get()
    if sink is None:
        return
    # Only allowlisted names may reach the public header.
    if namespace in SHARED_ARTIFACT_NAMES and namespace not in sink:
        sink.append(namespace)


async def get_or_build(
    namespace: str,
    key: tuple,
    builder: Callable[[], Awaitable[Any]],
    *,
    ttl_s: Optional[float] = None,
    reuse_sink: Optional[list] = None,
    clock: Optional[Callable[[], float]] = None,
) -> Any:
    """Return the shared artifact for `(namespace, key)`, building it if needed.

    `key` must contain ONLY principal-independent inputs; `builder` must be a
    pure function of them. Every guard failure degrades to calling `builder`.
    """
    _clock = clock or time.monotonic
    _ttl = shared_build_ttl_s() if ttl_s is None else ttl_s

    if _ttl <= 0:
        _stats["builds"] += 1
        return await builder()

    try:
        assert_shared_key(key)
    except NotPlainData:
        logger.warning(
            "shared build key refused for namespace=%s — building unshared", namespace
        )
        _stats["refused"] += 1
        _stats["builds"] += 1
        return await builder()

    ok, value = _read_fresh(namespace, key, _ttl, _clock())
    if ok:
        _note_reuse(namespace, reuse_sink)
        return copy.deepcopy(value)

    lock = _lock_for(namespace, key)
    acquired = False
    if lock.locked():
        _stats["coalesced"] += 1
    try:
        await asyncio.wait_for(lock.acquire(), timeout=LOCK_WAIT_S)
        acquired = True
    except (asyncio.TimeoutError, RuntimeError):
        # A wedged or cross-loop lock must never wedge the endpoint. Build
        # unshared — exactly today's behaviour.
        logger.warning(
            "shared build lock unavailable for namespace=%s — building unshared",
            namespace,
        )
        _stats["builds"] += 1
        return await builder()

    try:
        # Re-read under the lock: the caller we queued behind may have just
        # stored it, which is the whole point of coalescing.
        ok, value = _read_fresh(namespace, key, _ttl, _clock())
        if ok:
            _note_reuse(namespace, reuse_sink)
            return copy.deepcopy(value)

        _stats["builds"] += 1
        built = await builder()

        try:
            assert_plain_data(built)
        except NotPlainData as exc:
            # Fail-closed on sharing, fail-open on the response.
            logger.warning(
                "shared build for namespace=%s refused (%s) — returning unshared",
                namespace,
                exc,
            )
            _stats["refused"] += 1
            return built

        entries = _store.setdefault(namespace, {})
        entries[key] = (_clock(), copy.deepcopy(built))
        _evict_if_needed(entries)
        return built
    finally:
        if acquired:
            lock.release()


# --------------------------------------------------------------------------
# key helpers
# --------------------------------------------------------------------------


def time_bucket(now: datetime, seconds: int) -> int:
    """A coarse, principal-independent time component for a shared key.

    Bucketing on the clock — NOT on an offset from a per-request `now` — is what
    makes two principals arriving 200ms apart land on the SAME key. It is also
    the second bound on staleness alongside the TTL.
    """
    return int(now.timestamp()) // max(1, int(seconds))


def digest_of(values: Iterable[str]) -> str:
    """A short, order-independent digest of a string set, for use in a key.

    The candidate canonical-key set can hold thousands of entries; hashing it
    keeps the cache key a single scalar instead of a multi-thousand-element
    tuple that would be re-hashed on every lookup.
    """
    import hashlib

    h = hashlib.md5()
    for v in sorted(values):
        h.update(v.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()
