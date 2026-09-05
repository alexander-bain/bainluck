"""Cross-worker sharing for the principal-INDEPENDENT half of a feed build.

#2143 / LAT-P084 (Fable addendum, 2026-08-24, pasted and reviewed by Alex).
Cross-worker tier added by LAT-P103 (2026-08-27) — see "The second tier" below.

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
   (567-617ms of hydrated rows) was left on the table by this change.

   **LAT-P174 took `market_load` WITHOUT relaxing this rule** (#2143 residual,
   2026-08-31). An ORM row still cannot enter here; what enters is a plain
   table of the loaded COLUMN VALUES, and the hydrated objects are rebuilt per
   request as inert snapshots (`app/utils/futures_market_snapshot.py`). The
   refusal above is the reason that module exists, not an obstacle it went
   around: the guard is what forced the carrier to change.

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

## The second tier (LAT-P103, #2143 residual, 2026-08-27)

#2203 fixed the *inert* principal — a fresh install now reads the anonymous
entry instead of building. It could not fix Alex: user 364 has 139 rows in the
30-day affinity window and 13 in the 14-day dismiss window, so his
`PersonalizationContext` is NOT structurally equal to a default one, the
short-circuit does not apply, and every open pays a build. #2203's own closing
paragraph names the remedy: *"That residual needs the principal-independent
stage artifacts to survive a cold worker — #2143's module is process-local by
design."* This is that change.

Process-local was never enough on its own. Production runs several web dynos at
`WEB_CONCURRENCY=2`, so an artifact built by one worker is invisible to every
other worker and to every worker that restarts. With a 60s TTL, a single
principal's request has a small chance of landing on the one worker that
happens to hold a warm copy; the other workers rebuild it from scratch. The
artifact is a pure function of principal-independent inputs — which means it
was always shareable *across processes*; the module simply had nowhere to put
it.

The paragraph above says this cache is "deliberately NOT Redis", and that
sentence is still right about the thing it was arguing against: a Redis round
trip on the HIT path. Nothing about that path changed. The tiering is:

    L1  process-local dict     read first, unchanged, zero added latency
    L2  Redis                  read ONLY when L1 misses and the alternative is
                               a 683-1249ms rebuild, bounded at 250ms
    L3  build

An L1 hit never touches Redis. An L1 miss trades a bounded ~1ms `GET` against
work measured at 683-1249ms per artifact. That is the same tiering
`candidate_base.py` already runs on this exact route, on this exact request.

Four properties keep the second tier from being able to serve a wrong answer:

4. **The wire format is exactly invertible.** `assert_plain_data` admits
   `datetime`, `date`, `Decimal` and `tuple`, and dict keys that are not
   strings — none of which survive a naive JSON round trip. So the codec tags
   them, and a payload the codec cannot represent is REFUSED for publication
   rather than published lossily. L1 (deepcopy) and L2 (encode/decode) must
   hand out the same object, or a request would silently get a different feed
   depending on which worker it landed on.

5. **The envelope carries its own key and is verified on read.** The Redis key
   is a digest, and a digest is a hash: two different cache keys COULD map to
   one Redis key. The envelope stores the original key's `repr` and a reader
   that does not match it treats the entry as a miss. A collision therefore
   costs a rebuild, never a wrong artifact.

6. **Age is bounded by the reader's wall clock, not only by Redis `EX`.** L1
   ages on `time.monotonic`, which is meaningless in another process, so the
   envelope carries `stored_wall` and the reader applies the same TTL it would
   apply locally. `EX` is the backstop, not the bound.

7. **Every L2 failure degrades to L1's behaviour.** A stall, a connection
   error, a malformed envelope, an over-cap payload, a codec refusal: each one
   returns the caller to "build it the way we build it today". A cache that can
   500 the endpoint it was added to speed up is a net loss at any hit rate —
   the second tier inherits that rule verbatim from the first.

Kill switches: `FEED_SHARED_BUILD_TTL_S=0` turns ALL sharing off process-wide
without a code change; every call then builds, exactly as before this module
existed. `FEED_SHARED_BUILD_CROSS_WORKER=0` turns off the Redis tier ALONE,
leaving the process-local tier exactly as it shipped in LAT-P084 — so a
rollback of this change needs no deploy and does not give back #2143's original
win.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
import os
import time
import zlib
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
SHARED_ARTIFACT_NAMES: frozenset[str] = frozenset(
    {"concepts", "canonical_counts", "market_load"}
)

#: Per-namespace entry cap. Concepts key on (sport_filter, hour-bucket) and
#: canonical counts on a digest of the candidate key set, so the live cardinality
#: is small; the cap exists so an unexpected key explosion cannot grow a
#: process-global dict without bound.
MAX_ENTRIES_PER_NAMESPACE = 64

#: Namespaces whose entries are big enough that the count cap has to be a MEMORY
#: bound rather than a key-explosion backstop (LAT-P174).
#:
#: The default 64 is sized for artifacts of a few kilobytes. `market_load` holds
#: the loaded column values of the whole candidate base — measured at ~1.2 MB
#: encoded for 700 markets / 2,223 outcomes, and several times that as live
#: Python lists. Sixty-four of those is hundreds of megabytes on a dyno, so the
#: cap that is a formality for a small artifact is the whole safety property for
#: a large one.
#:
#: Six, because the live key cardinality is the number of distinct candidate
#: bases in flight within one TTL — one per `(sport_filter, static_tag_filter)`
#: shape the surfaces actually request — and an entry rotates when the base's ID
#: set changes. Undershooting costs a rebuild, which is exactly today's
#: behaviour; overshooting costs resident memory on the flagship route, which is
#: not recoverable by failing open.
MAX_ENTRIES_BY_NAMESPACE: dict[str, int] = {"market_load": 6}

#: Default staleness bound. The concept build embeds `now`-derived text and pin
#: state, so the TTL is what bounds how wrong that can be. 60s is far below the
#: coarsest boundary those values move on (marquee pin windows are hours).
DEFAULT_TTL_S = 60.0

# --- LAT-P230 (#3144): the cadences a shared artifact's TTL is DERIVED from ---
#
# `market_load` died at 60s while its own KEY lived for ~120s, so the second half
# of every key generation was thrown away. Measured 2026-09-05 by the LAT-P229 gap
# sweep: the artifact shares at a 45s gap (4/4, zero pairs dropped) and not at 75s,
# and the cost tracks it directly — 2,632ms median elapsed shared against 5,140ms
# unshared.
#
# Both cadences are declared HERE, beside the TTL they bound, on the #2236
# precedent: that incident was a 120 in the beat file and a 60 in `feed_cache.py`
# with nothing comparing them, and a literal in one file would rebuild that
# arrangement exactly. `test_shared_artifact_total_age_lat_p230.py` reads the REAL
# beat schedule and fails if either drifts.
#: `precompute-discover-candidate-base`, `crontab(minute="*/2")`.
CANDIDATE_BASE_REPUBLISH_PERIOD_S = 120.0
#: `poll_live_prediction_markets`, `schedule: 120.0`.
LIVE_MARKET_POLL_PERIOD_S = 120.0


def market_load_ttl_ceiling_s() -> float:
    """The longest TTL `market_load` may be given before it buys nothing.

    Two independent bounds, and the TTL must respect the tighter of them:

    * `CANDIDATE_BASE_REPUBLISH_PERIOD_S` — the artifact's key is a membership
      digest of the candidate base. Past one republish period the key rotates,
      so a longer TTL holds entries nobody will ask for again. Against a
      six-entry cap that is not merely wasteful, it EVICTS live ones.
    * `LIVE_MARKET_POLL_PERIOD_S` — past it the artifact would be staler than
      the source's own update cadence, which is the point where a cache stops
      being a copy of the data and starts being a different answer.

    The two agreeing on 120s is the reason to trust the number; neither was
    chosen for being round.

    A function and not a bare `assert` at import time for the reason
    `live_republish_headroom_s()` gives: a guard should FAIL loudly and by name
    rather than take the web dyno down.
    """
    return min(CANDIDATE_BASE_REPUBLISH_PERIOD_S, LIVE_MARKET_POLL_PERIOD_S)


#: Per-namespace TTL default, for artifacts whose key outlives `DEFAULT_TTL_S`.
#: `market_load`'s value is DERIVED — see `market_load_ttl_ceiling_s()`.
TTL_S_BY_NAMESPACE: dict[str, float] = {"market_load": 120.0}


def market_load_ttl_headroom_s() -> float:
    """Slack in the LAT-P230 invariant. Negative means it is violated.

        TTL_S_BY_NAMESPACE["market_load"] <= market_load_ttl_ceiling_s()

    Whoever next shortens either cadence will be editing this function's
    neighbours, and the guard test fails if they do not also lower the TTL.
    """
    return market_load_ttl_ceiling_s() - TTL_S_BY_NAMESPACE["market_load"]


#: The clock-bucket width for a shared key that carries one (LAT-P104).
#:
#: **A key that rotates faster than the TTL discards entries that are still
#: fresh.** The concept key bucketed on 30s against this 60s TTL, so the fleet
#: rebuilt a 865-1249ms stage TWICE per TTL when once is the floor. The natural
#: experiment is already in LAT-P103's production read: across the same ten cold
#: requests, `canonical_counts` — which carries no clock component at all —
#: was reused 10/10, and `concepts` — which carried the 30s bucket — 6/10.
#:
#: **Why a bucket at all, rather than letting the TTL be the only bound.** Its
#: remaining job is BOUNDARY ALIGNMENT, not staleness: an entry is served only
#: while `age < TTL` *and* the bucket has not turned, so staleness is already
#: `min(TTL, bucket)` and the TTL binds at any width >= 60s. What the bucket
#: still buys is that the key turns AT a content boundary instead of up to a
#: TTL after it.
#:
#: **Why an hour.** Every `now`-derived branch in the concept build sits on a
#: grid no finer than 12 hours, and all three are enumerated rather than
#: assumed — `_score_event_concept` and `_concept_headline` read `now.date()`,
#: and `marquee_pin_state`'s windows open at UTC midnight and expire at UTC
#: 12:00 (`list_all_concepts`, the fourth input, takes no clock at all). An
#: hourly bucket lands exactly on all of them. `test_feed_concept_stage_key_
#: bucket_p104.py` executes that enumeration, so an hour-granularity branch
#: added later goes red here rather than shipping stale text.
#:
#: **Why not 12 hours, which those same boundaries would permit.** The rebuild
#: rate is `1/TTL + 1/bucket`, so once the bucket clears the TTL the TTL
#: dominates and 12h saves under 2% over 1h. Against that: `datetime.timestamp()`
#: reads a NAIVE datetime as local time, and every zone this product runs in is
#: a whole number of hours from UTC — so an hourly grid stays aligned under that
#: mistake and a 12-hour grid silently would not.
CLOCK_BUCKET_S = 3600

#: How long a coalesced caller waits for the in-flight build before giving up
#: and building for itself. A waiter must never end up SLOWER than a solo
#: builder, and a shared build that wedges must not wedge the endpoint.
LOCK_WAIT_S = 8.0

# --------------------------------------------------------------------------
# cross-worker tier (LAT-P103)
# --------------------------------------------------------------------------

#: Which tier served a reused artifact. A CLOSED vocabulary, because these
#: strings reach a public response header — the point of naming the tier at all
#: is that "the share still works" and "the share still works ACROSS WORKERS"
#: are different claims and only the second one closes #2143's residual.
SHARED_TIER_LOCAL = "local"
SHARED_TIER_CROSS_WORKER = "cross_worker"
SHARED_TIER_NAMES: frozenset[str] = frozenset(
    {SHARED_TIER_LOCAL, SHARED_TIER_CROSS_WORKER}
)

#: Redis key prefix. The version segment is bumped whenever the envelope or the
#: wire codec changes shape, so a deploy that changes either cannot read a
#: predecessor's entries — the old keys simply expire under their own `EX`.
REDIS_KEY_PREFIX = "feed:pic:v2"

#: Bounds on the Redis hop. Deliberately tighter than the shared 600ms
#: `REQUEST_REDIS_OP_DEADLINE_MS`: this hop is speculative (it is trying to
#: AVOID work, and losing it only costs the work we were going to do anyway),
#: so it must fail fast rather than add a visible tax to the miss path.
REDIS_READ_DEADLINE_MS = 250
REDIS_PUBLISH_DEADLINE_MS = 250

# --- LAT-P221 (#2971): ONE CAP WAS SERVING TWO UNRELATED BOUNDS -------------
#
# A single `MAX_ENVELOPE_BYTES = 2 MB` was checked against the JSON envelope and
# used as both "how long may the decode hold the GIL" and "how much of Redis may
# one artifact occupy". Those are different quantities with different units, and
# conflating them is what silently un-shared the feed's most expensive artifact.
#
# MEASURED IN PRODUCTION, 2026-09-04. The `market_load` snapshot — the hydrated
# Discover candidate base — encodes to a **2.79 MB envelope** (700 markets /
# 6,904 outcomes, sized with this module's own codec on real sampled rows). So
# `_publish_cross_worker` refused it on EVERY build, and the artifact never left
# the worker that made it. Production agreed: `x-feed-shared` listed
# `canonical_counts,concepts` and never `market_load`, and the only reuse ever
# observed for it was `x-feed-shared-tier: local`.
#
# The cost of that refusal is the whole cold feed. `futures.market_load` is
# 692-775 ms of a 1,537-1,982 ms cache-miss request; on the requests that did
# reuse it from L1 the same stage cost 68-71 ms and the whole request cost
# 735-774 ms. 47% of production feed requests miss.
#
# It rotted rather than broke: LAT-P174 sized this artifact at ~1.2 MB for 2,223
# outcomes. The outcome population is now 6,904 — 3.1x — and nothing compared
# the artifact against its own cap. `test_market_load_publishes_at_production_scale`
# is that comparison, and it is why this cannot rot again in silence.
#
#: The DECODE bound: how much JSON one reader may parse in one go. The parse
#: holds the GIL for its whole C-level run (gotcha #38), so this is an
#: event-loop-stall budget, not a memory budget. Measured on the real artifact:
#: decompress + `json.loads` + `_decode` costs ~10.4 ms/MB, so 6 MB is ~62 ms
#: locally and ~150 ms on a Standard-2X dyno — weighed, as LAT-P103 requires,
#: not against a hit but against the 692-775 ms rebuild it replaces, which holds
#: the GIL longer than the parse does. Enforced on BOTH sides: the publisher
#: refuses to write more than this, and `wire_decode` refuses to inflate past it
#: so a foreign or corrupt entry cannot stall a worker either.
MAX_ENVELOPE_BYTES = 6 * 1024 * 1024

#: The STORAGE bound: how much of Redis one artifact may occupy. Redis is a
#: shared 100 MB LRU — Celery's state lives in the same instance — so an
#: artifact that fits the decode budget can still be antisocial. This keeps the
#: old 2 MB number, because 2 MB was always the defensible answer to THIS
#: question; it was only ever the wrong answer to the other one.
MAX_STORED_BYTES = 2 * 1024 * 1024

#: The stored wire form is a zlib stream, not the raw JSON. Level 1, because the
#: ratio is what matters and the last 20% of it is not worth 2x the CPU:
#: measured on the real `market_load` envelope, L1 gives 4.2x (2.79 MB -> 0.59 MB)
#: for 9.3 ms compress / 1.9 ms decompress, against L6's 5.0x for 20.6 ms.
#: Compression is what lets the storage bound stay at 2 MB while the decode bound
#: rises — the artifact's Redis footprint goes DOWN, not up.
WIRE_COMPRESS_LEVEL = 1

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
                    raise NotPlainData(f"dict key of type {type(k).__name__} at {path}")
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


def _parse_ttl(raw: Optional[str]) -> Optional[float]:
    """`raw` as a non-negative TTL, or `None` if it is absent or unparseable.

    `None` rather than a fallback value so the caller can tell "not set" from
    "set to something", which is the whole of the precedence order below. An
    unparseable value reads as absent so a typo falls through to the next rule
    rather than to zero, which would silently disable the cache.
    """
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _namespace_ttl_env(namespace: str) -> str:
    """The per-namespace TTL env var name, e.g. `FEED_SHARED_BUILD_TTL_S_MARKET_LOAD`."""
    return f"FEED_SHARED_BUILD_TTL_S_{namespace.upper()}"


def shared_build_ttl_s(namespace: Optional[str] = None) -> float:
    """The staleness bound for `namespace`, in seconds. 0 disables sharing.

    Was one number for every namespace until LAT-P230. `market_load`'s key
    outlives `DEFAULT_TTL_S` by 2x, so one process-wide number meant the flagship
    artifact was thrown away halfway through its own key's life.

    Precedence, in order, and the order is the whole contract:

    1. ``FEED_SHARED_BUILD_TTL_S=0`` — the operator kill switch, and it stays
       ABSOLUTE. A per-namespace default that could outlive it would mean the one
       lever that turns sharing off no longer turns sharing off.
    2. ``FEED_SHARED_BUILD_TTL_S_<NAMESPACE>`` — a per-namespace operator override.
    3. ``FEED_SHARED_BUILD_TTL_S`` — an explicit process-wide operator choice binds
       every namespace, including ones carrying a built-in default. An operator who
       sets the global expects it to bind, and a built-in that quietly outranked it
       would be a lever that lies.
    4. ``TTL_S_BY_NAMESPACE[namespace]`` — the built-in per-namespace default.
    5. ``DEFAULT_TTL_S``.

    Called with no `namespace` it is the process-wide value, byte-identical to the
    pre-LAT-P230 behaviour — which is what `clock_bucket_s()` still wants, since
    the bucket it clamps belongs to `concepts`.
    """
    global_raw = os.environ.get("FEED_SHARED_BUILD_TTL_S")
    global_ttl = _parse_ttl(global_raw)

    # (1) The kill switch, before anything else can outrank it.
    if global_ttl == 0.0:
        return 0.0

    if namespace is not None:
        # (2)
        namespace_ttl = _parse_ttl(os.environ.get(_namespace_ttl_env(namespace)))
        if namespace_ttl is not None:
            return namespace_ttl

    # (3)
    if global_ttl is not None:
        return global_ttl

    # (4)
    if namespace is not None and namespace in TTL_S_BY_NAMESPACE:
        return TTL_S_BY_NAMESPACE[namespace]

    # (5)
    return DEFAULT_TTL_S


def clock_bucket_s() -> float:
    """The clock-bucket width to key on, never finer than the live TTL.

    `CLOCK_BUCKET_S` is the chosen width; this clamp is what makes "the key
    never discards a fresh entry" hold BY CONSTRUCTION rather than by an
    assertion a reviewer has to notice. `FEED_SHARED_BUILD_TTL_S` can be raised
    at runtime with no deploy, and the one thing that must not happen when it is
    is the defect LAT-P104 removed coming back one env var later.

    Widening the bucket past the TTL is free: staleness is `min(TTL, bucket)`,
    so the TTL keeps binding and only the wasted rotation goes away.
    """
    return max(float(CLOCK_BUCKET_S), shared_build_ttl_s())


def cross_worker_enabled() -> bool:
    """Whether the Redis tier is live, from `FEED_SHARED_BUILD_CROSS_WORKER`.

    Default ON — this IS the ship, so it must not need a config var set at
    deploy to take effect. Only an explicit "0"/"false"/"off" disables it, and
    doing so leaves the process-local tier exactly as LAT-P084 shipped it.
    """
    raw = os.environ.get("FEED_SHARED_BUILD_CROSS_WORKER")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "off", "no"}


# --------------------------------------------------------------------------
# wire codec — exactly invertible over the plain-data type space
# --------------------------------------------------------------------------
#
# `assert_plain_data` admits four things JSON cannot represent: `datetime`,
# `date`, `Decimal`, and `tuple` — plus dicts whose keys are not strings. The
# process-local tier round-trips all of them for free (it deepcopies). If the
# Redis tier lost them, one principal would get `datetime` and the next would
# get `str` for the same artifact, depending on which worker answered. That is
# a WORSE failure than not sharing at all, because it is invisible.
#
# So: tag them, and refuse to publish anything the codec cannot represent. The
# codec is the inverse of itself by construction and `test_..._cold_worker.py`
# proves it over the whole admitted type space, including the sentinel-key
# escape hatch below.

_TAG = "__pic__"


class _CodecRefused(TypeError):
    """A value cannot be represented on the wire without loss."""


def _encode_key(key: Any) -> Any:
    """Encode one dict key. Keys are scalars (`assert_plain_data` enforces it)."""
    if key is None or isinstance(key, (bool, int, float, str)):
        return key
    raise _CodecRefused(f"dict key of type {type(key).__name__}")


def _decode_key(key: Any) -> Any:
    return key


def _encode(node: Any) -> Any:
    if node is None or isinstance(node, (bool, int, float, str)):
        return node
    # `datetime` is a subclass of `date`, so it MUST be tested first or every
    # timestamp comes back with its time-of-day silently truncated.
    if isinstance(node, datetime):
        return {_TAG: "dt", "v": node.isoformat()}
    if isinstance(node, date):
        return {_TAG: "d", "v": node.isoformat()}
    if isinstance(node, Decimal):
        return {_TAG: "dec", "v": str(node)}
    if isinstance(node, tuple):
        return {_TAG: "tup", "v": [_encode(v) for v in node]}
    if isinstance(node, list):
        return [_encode(v) for v in node]
    if isinstance(node, dict):
        # Fast path: a plain string-keyed dict is itself on the wire — which is
        # every dict the feed's cards actually contain. The escaped form exists
        # so the RARE case cannot corrupt anything, not because it is expected.
        if all(isinstance(k, str) for k in node) and _TAG not in node:
            return {k: _encode(v) for k, v in node.items()}
        return {
            _TAG: "map",
            "v": [[_encode_key(k), _encode(v)] for k, v in node.items()],
        }
    raise _CodecRefused(f"{type(node).__name__} is not representable on the wire")


def _decode(node: Any) -> Any:
    if isinstance(node, list):
        return [_decode(v) for v in node]
    if not isinstance(node, dict):
        return node
    tag = node.get(_TAG)
    if tag is None:
        return {k: _decode(v) for k, v in node.items()}
    raw = node.get("v")
    if tag == "dt":
        return datetime.fromisoformat(raw)
    if tag == "d":
        return date.fromisoformat(raw)
    if tag == "dec":
        return Decimal(raw)
    if tag == "tup":
        return tuple(_decode(v) for v in raw)
    if tag == "map":
        return {_decode_key(k): _decode(v) for k, v in raw}
    raise _CodecRefused(f"unknown wire tag {tag!r}")


def encode_shared_payload(value: Any) -> str:
    """Serialize `value` losslessly, or raise `_CodecRefused`.

    `allow_nan` is left at its default so a non-finite float round-trips as
    itself rather than becoming `null`. Non-finite scores are a bug elsewhere,
    but this codec's job is to be a mirror, not a filter.
    """
    return json.dumps(_encode(value), separators=(",", ":"), ensure_ascii=False)


def decode_shared_payload(raw: str) -> Any:
    """Inverse of `encode_shared_payload`."""
    return _decode(json.loads(raw))


def wire_encode(envelope_json: str) -> bytes:
    """The bytes that go into Redis for one envelope."""
    return zlib.compress(envelope_json.encode("utf-8", "replace"), WIRE_COMPRESS_LEVEL)


def wire_decode(raw: Any) -> Optional[str]:
    """Inverse of `wire_encode`, or `None` for anything that is not our wire form.

    `None` covers every way a Redis value can fail to be one of ours — a
    predecessor's uncompressed JSON, another lane's typo, a truncated write, a
    stream that inflates past the decode budget. The caller treats all of them
    as a miss and builds, which is what it would have done anyway.

    The inflation is BOUNDED, not just checked afterwards: `decompressobj`
    stops at `MAX_ENVELOPE_BYTES + 1` bytes, so a foreign entry cannot spend a
    worker's event loop expanding before we get the chance to reject it.
    """
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        return None
    try:
        inflated = zlib.decompressobj().decompress(bytes(raw), MAX_ENVELOPE_BYTES + 1)
    except zlib.error:
        return None
    if len(inflated) > MAX_ENVELOPE_BYTES:
        return None
    try:
        return inflated.decode("utf-8")
    except UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------

# namespace -> {key: (stored_at, value)}
_store: dict[str, dict[tuple, tuple[float, Any]]] = {}
# namespace -> {key: asyncio.Lock}
_locks: dict[str, dict[tuple, asyncio.Lock]] = {}
_stats: dict[str, int] = {
    "hits": 0,
    "builds": 0,
    "refused": 0,
    "coalesced": 0,
    # CERT-1864: entries evicted for being too old to feed a LIVE page, which is
    # a different (and stricter) bound than the namespace TTL they died inside.
    "dropped_over_age": 0,
    # CERT-1885: the Redis half of that eviction. Split from `dropped_over_age`
    # because a local drop with no matching invalidation is the defect CERT-1885
    # found, and two counters are what make that visible from outside.
    "cross_worker_invalidated": 0,
    # LAT-P103 cross-worker tier. Split from `hits` on purpose: `hits` answers
    # "did sharing work", these answer "did sharing survive a cold worker",
    # which is the whole claim #2143's residual turns on.
    "cross_worker_hits": 0,
    "cross_worker_misses": 0,
    "cross_worker_failures": 0,
    "cross_worker_publishes": 0,
    "cross_worker_publish_refused": 0,
}


def clear_shared_builds(namespace: Optional[str] = None) -> None:
    """Drop shared artifacts. Test hygiene and an operational escape hatch.

    Process-local ONLY. It deliberately does not (and cannot cheaply) delete the
    Redis tier: a test that clears this is simulating a COLD WORKER, and a cold
    worker is exactly the process that still sees Redis.
    """
    if namespace is None:
        _store.clear()
        _locks.clear()
        for k in _stats:
            _stats[k] = 0
        return
    _store.pop(namespace, None)
    _locks.pop(namespace, None)


def drop_entries_older_than(
    max_age_s: float, *, clock=None
) -> list[tuple[str, tuple]]:
    """Evict every process-local artifact already older than `max_age_s`.

    Returns the `(namespace, key)` of each entry dropped — the IDENTITIES, not a
    count, because the caller's next move is `forget_stale_cross_worker` on
    exactly these (CERT-1885). A count cannot say WHICH artifact to invalidate,
    and re-deriving the list would mean scanning a store the drop just emptied.

    CERT-1864. A shared artifact may legitimately live longer than a live feed
    payload may (`market_load`'s TTL is 120s against a 60s live ceiling), so an
    artifact can reach an age at which it is still a valid CACHE ENTRY and no
    longer a valid INPUT to a live page. The route refuses to serve a payload
    built from one — and if the entry stays, the next request consumes exactly
    the same too-old artifact and is refused in turn, every request until the
    TTL expires. One refused response is the ceiling working; a minute of them
    is an outage. Dropping the entry is what makes the next build a rebuild
    WITHOUT the shared artifact, which is the first of the three outcomes #2216
    allows past the ceiling.

    Deliberately generic — an age bound, not a feed concept. This module knows
    nothing about liveness and must not learn: the caller owns the policy and
    passes the number, exactly as `get_or_build` takes its TTL rather than
    deriving one.

    Process-local ONLY. **On its own this does not stop the repeat**
    (CERT-1885): the cross-worker tier is default-ON, its bound is the namespace
    TTL, and the next request re-promotes the identical artifact from Redis at
    the identical age. The local drop is half a repair; `forget_stale_cross_worker`
    over the returned identities is the other half.
    """
    _clock = clock or time.monotonic
    now = _clock()
    dropped: list[tuple[str, tuple]] = []
    for namespace, entries in list(_store.items()):
        for key, stored in list(entries.items()):
            stored_at = stored[0]
            if (now - stored_at) > max_age_s:
                entries.pop(key, None)
                dropped.append((namespace, key))
        if not entries:
            _store.pop(namespace, None)
    _stats["dropped_over_age"] += len(dropped)
    return dropped


async def forget_stale_cross_worker(
    entries: Iterable[tuple[str, tuple]], max_age_s: float
) -> int:
    """Delete the Redis copy of each `(namespace, key)` that is ALSO over `max_age_s`.

    Returns how many keys were deleted. Never raises — an invalidation that
    cannot reach Redis must not turn a degraded response into a 500.

    CERT-1885 is why this exists, and the finding was exact: evicting the
    process-local copy of an over-ceiling artifact leaves the Redis copy
    readable at its namespace TTL, so the very next request promotes the same
    70-second-old artifact back into the same worker, is refused in turn, and
    the empty `unavailable` repeats. Half a repair reads exactly like a whole
    one in a single-request test.

    **It reads before it deletes**, and deletes only what is genuinely over the
    bound. A sibling worker may have republished a FRESH artifact under this key
    since this worker read its own copy; deleting that would cost every worker a
    rebuild to fix a staleness that no longer exists. The read is the envelope's
    own `stored_wall`, which is the same number `_read_cross_worker` bounds on,
    so the two cannot disagree about what "too old" means.

    Deliberately generic, like `drop_entries_older_than`: an age bound, not a
    feed concept. The caller owns the policy and passes the number.
    """
    identities = [e for e in (entries or ())]
    if not identities or not cross_worker_enabled():
        return 0
    from app.utils import request_cache as _rc

    try:
        client = await _shared_redis_client()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("shared build: no redis client for invalidation", exc_info=True)
        return 0

    deleted = 0
    for namespace, key in identities:
        redis_key = redis_key_for(namespace, key)
        result = await _rc.bounded_redis_call(
            lambda k=redis_key: client.get(k), deadline_ms=REDIS_READ_DEADLINE_MS
        )
        if result.is_failure or not result.is_ok:
            continue
        raw = wire_decode(result.value)
        if raw is None:
            continue
        try:
            envelope = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(envelope, dict) or envelope.get("ns") != namespace:
            continue
        stored_wall = envelope.get("stored_wall")
        if not isinstance(stored_wall, (int, float)) or isinstance(stored_wall, bool):
            continue
        if max(0.0, time.time() - float(stored_wall)) <= max_age_s:
            # A sibling republished it since we read ours. Leave it alone.
            continue
        drop = await _rc.bounded_redis_call(
            lambda k=redis_key: client.delete(k), deadline_ms=REDIS_READ_DEADLINE_MS
        )
        if not drop.is_failure:
            deleted += 1
    if deleted:
        _stats["cross_worker_invalidated"] += deleted
    return deleted


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
    out["cross_worker_enabled"] = int(cross_worker_enabled())
    return out


def max_entries_for(namespace: str) -> int:
    """The entry cap for `namespace` — the per-namespace override, else default."""
    return MAX_ENTRIES_BY_NAMESPACE.get(namespace, MAX_ENTRIES_PER_NAMESPACE)


def _evict_if_needed(
    entries: dict[tuple, tuple[float, Any]], namespace: Optional[str] = None
) -> None:
    cap = MAX_ENTRIES_PER_NAMESPACE
    if namespace is not None:
        cap = max_entries_for(namespace)
    while len(entries) > cap:
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
) -> tuple[bool, Any, float]:
    """`(hit, value, age_s)` from the process-local tier.

    `age_s` (LAT-P230) is how old the entry already was — the first term of the
    total-age sum in `feed_cache.live_total_age_headroom_s()`. A miss reports
    `0.0`, which is never read: the caller only consults the age on a hit.
    """
    entries = _store.get(namespace)
    if not entries:
        return False, None, 0.0
    hit = entries.get(key)
    if hit is None:
        return False, None, 0.0
    stored_at, value = hit
    age_s = now - stored_at
    if age_s > ttl_s:
        entries.pop(key, None)
        return False, None, 0.0
    return True, value, max(0.0, age_s)


# The ambient reuse sink for one request. A contextvar rather than a threaded
# parameter because the second shared artifact (`canonical_counts`) is resolved
# three call frames below the route, inside `_score_futures`, and threading a
# diagnostic through a scoring signature is how a diagnostic ends up omitted on
# one of the paths (which is exactly what Queue 275 had to go back and fix for
# the stage headers).
_reuse_sink_var: ContextVar[Optional[list]] = ContextVar(
    "feed_shared_reuse_sink", default=None
)

# The tier sink is separate from the name sink rather than folded into it: the
# name sink's contents are filtered against `SHARED_ARTIFACT_NAMES` on the way
# to `X-Feed-Shared`, so smuggling a tier through it as a decorated string would
# mean loosening that filter. Two closed vocabularies, two sinks, two headers.
_tier_sink_var: ContextVar[Optional[list]] = ContextVar(
    "feed_shared_tier_sink", default=None
)

# LAT-P230: how old the shared artifacts this request CONSUMED already were.
#
# Artifact age and response age ADD. `feed_response_cache_ttls()` could see the
# second term and not the first, so a payload could pass a 60s response TTL while
# carrying 60s-old inputs — the exact shape of #2236, two individually-correct
# numbers whose PRODUCT nobody computed. This is the missing term.
#
# A third sink rather than a field on the tier sink, for the reason written above
# it: the tier sink's contents are a closed vocabulary filtered on the way to a
# header, and smuggling a float through it would mean loosening that filter.
# Three closed vocabularies, three sinks.
_age_sink_var: ContextVar[Optional[list]] = ContextVar(
    "feed_shared_age_sink", default=None
)


def bind_reuse_sink(
    sink: list,
    tier_sink: Optional[list] = None,
    age_sink: Optional[list] = None,
) -> None:
    """Bind `sink` (and optionally `tier_sink` / `age_sink`) for this context."""
    _reuse_sink_var.set(sink)
    if tier_sink is not None:
        _tier_sink_var.set(tier_sink)
    if age_sink is not None:
        _age_sink_var.set(age_sink)


@contextlib.contextmanager
def reuse_scope(
    sink: list,
    tier_sink: Optional[list] = None,
    age_sink: Optional[list] = None,
) -> Iterator[None]:
    """Collect shared-artifact reuse into `sink` for the duration of this scope."""
    token = _reuse_sink_var.set(sink)
    tier_token = _tier_sink_var.set(tier_sink) if tier_sink is not None else None
    age_token = _age_sink_var.set(age_sink) if age_sink is not None else None
    try:
        yield
    finally:
        _reuse_sink_var.reset(token)
        if tier_token is not None:
            _tier_sink_var.reset(tier_token)
        if age_token is not None:
            _age_sink_var.reset(age_token)


#: Namespaces whose artifacts CANNOT carry live state — measured, then guarded.
#:
#: LAT-P231 / CERT-1886 follow-up, and the number that forced it is a production
#: one. Within an hour of the ceiling shipping, 5 of 40 anonymous `/api/feed`
#: polls came back EMPTY (`X-Feed-Cache: unavailable`, `input_age_ceiling`), and
#: every single refusal had `X-Feed-Shared: …,market_load` while the builds that
#: reused only `canonical_counts,concepts` were served normally. So the artifact
#: emptying Discover was the one that provably cannot make a page live.
#:
#: `market_load` carries `FuturesMarket` rows. `FuturesMarket.status` takes
#: `open`/`closed`/`resolved`/`active`; every `status="live"` write in the tree
#: targets `Event.status`; a futures card's `data["status"]` is `market.status`,
#: and `payload_contains_live_event` reads exactly that key. Its prices are also
#: not the thing the 60s ceiling bounds: the live-market poll is 2 minutes, and a
#: page with no live card is already cacheable for 60s fresh + 300s stale.
#:
#: 🔴 The exemption is per-NAMESPACE and it is a GUARD, not an argument.
#: CERT-1856's lesson stands verbatim — "an exemption argued about ONE input is
#: not an exemption for the mechanism that input travels through" — which is why
#: the clamp itself is unchanged and still counts every namespace NOT named here.
#: `concepts` is not named here and must never be: `_score_event_concepts` copies
#: a concept's `status`, `live` included. The day a futures card can render
#: `status == "live"`,
#: `test_shared_artifact_total_age_lat_p230.py::TestMarketLoadCannotItselfAgeALivePrice`
#: goes red and this set has to shrink before that card can ship.
LIVENESS_INERT_NAMESPACES = frozenset({"market_load"})


def _note_age(namespace: str, age_s: float) -> None:
    """Record ONE shared artifact this request consumed, as an ORIGIN.

    A `LIVENESS_INERT_NAMESPACES` artifact is NOT recorded: its age is real but
    it is not an age the LIVE ceiling is about, and counting it refused live
    pages that were carrying perfectly current scores (see that set's note).
    The reuse sink still names it, so `X-Feed-Shared` is unchanged and nobody
    loses the ability to see that it was consumed.

    A freshly-built artifact records its origin rather than nothing,
    deliberately: it makes "this request touched a shared artifact and it was
    new" distinguishable from "this request touched none at all". An empty sink
    then means the latter, and a reader cannot mistake a silent instrument for a
    fresh payload.

    CERT-1862: what is stored is the monotonic instant the artifact was BORN
    (`monotonic() - age`), not the age it happened to have when we looked at it.
    An age is a measurement frozen at the moment of consumption; an origin keeps
    aging by itself. The distinction is the whole defect: consumption happens
    early in a request and the ceiling is applied late, so a stored age is
    already wrong by however long the build took. Measured against the shipping
    arithmetic: an artifact consumed at 50s with a 20s build still read 50s, and
    a live payload was served at 79s true age against a 60s ceiling.

    Monotonic, not wall-clock, because this is an elapsed-time question and must
    not be moved by an NTP step mid-request.
    """
    if namespace in LIVENESS_INERT_NAMESPACES:
        return
    sink = _age_sink_var.get()
    if sink is not None:
        sink.append(time.monotonic() - max(0.0, float(age_s)))


def oldest_consumed_artifact_age_s(origin_sink: Optional[Iterable[float]]) -> float:
    """Age NOW of the OLDEST shared artifact a request consumed. `0.0` if none.

    The oldest artifact is the one with the EARLIEST origin, hence `min` here
    against the `max` this function used when the sink held ages — a payload is
    only as fresh as its stalest input, and averaging would let one fresh
    artifact pay for an ancient one.

    Re-derived from `time.monotonic()` on every call (CERT-1862), so the answer
    grows as the request does. Callers may therefore ask at any point — at TTL
    selection, at publication, anywhere later — and get the age as of the asking
    rather than as of the consumption.
    """
    if not origin_sink:
        return 0.0
    origins = [float(o) for o in origin_sink]
    if not origins:
        return 0.0
    return max(0.0, time.monotonic() - min(origins))


def _note_reuse(
    namespace: str,
    reuse_sink: Optional[list],
    tier: str = SHARED_TIER_LOCAL,
) -> None:
    _stats["hits"] += 1
    sink = reuse_sink if reuse_sink is not None else _reuse_sink_var.get()
    tier_sink = _tier_sink_var.get()
    if tier_sink is not None and tier in SHARED_TIER_NAMES and tier not in tier_sink:
        tier_sink.append(tier)
    if sink is None:
        return
    # Only allowlisted names may reach the public header.
    if namespace in SHARED_ARTIFACT_NAMES and namespace not in sink:
        sink.append(namespace)


# --------------------------------------------------------------------------
# cross-worker read / publish
# --------------------------------------------------------------------------


def redis_key_for(namespace: str, key: tuple) -> str:
    """The Redis key for one `(namespace, key)` pair.

    A digest, because a candidate-set key carries a 32-char hash and a concept
    key carries a tag tuple; neither belongs verbatim in a Redis key name. The
    digest is not trusted for identity — `_read_cross_worker` re-checks the
    envelope's stored key repr, so a collision costs a rebuild, never a wrong
    artifact.
    """
    digest = hashlib.md5(repr(key).encode("utf-8", "replace")).hexdigest()
    return f"{REDIS_KEY_PREFIX}:{namespace}:{digest}"


async def _shared_redis_client() -> Any:
    from app.utils import request_cache as _rc

    return await _rc.get_shared_async_redis()


async def _read_cross_worker(
    namespace: str, key: tuple, ttl_s: float
) -> tuple[bool, Any, float]:
    """Return `(hit, value, age_s)` from the Redis tier. Never raises.

    Bounded, and every failure mode — disabled, no client, stall, malformed
    envelope, wrong namespace/key, too old — returns `(False, None, 0.0)`, i.e.
    the caller builds exactly as it does today.

    `age_s` is how old the artifact ALREADY was when this worker read it, and it
    is returned rather than discarded because the caller promotes the value into
    the local tier. A promotion that forgets the age restarts the TTL (LAT-P229)
    — see the promotion site.
    """
    if not cross_worker_enabled():
        return False, None, 0.0
    from app.utils import request_cache as _rc

    try:
        client = await _shared_redis_client()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("shared build: no redis client", exc_info=True)
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0

    redis_key = redis_key_for(namespace, key)
    result = await _rc.bounded_redis_call(
        lambda: client.get(redis_key), deadline_ms=REDIS_READ_DEADLINE_MS
    )
    if result.is_failure:
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0
    if not result.is_ok:
        _stats["cross_worker_misses"] += 1
        return False, None, 0.0

    raw = wire_decode(result.value)
    if raw is None:
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0

    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError):
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0
    if not isinstance(envelope, dict) or envelope.get("v") != 1:
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0

    # A digest is a hash. Identity is the stored key repr, checked here, so a
    # collision between two distinct cache keys can only cost a rebuild.
    if envelope.get("ns") != namespace or envelope.get("k") != repr(key):
        _stats["cross_worker_misses"] += 1
        return False, None, 0.0

    stored_wall = envelope.get("stored_wall")
    if not isinstance(stored_wall, (int, float)) or isinstance(stored_wall, bool):
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0
    # Wall clock, because L1's monotonic clock means nothing in the process that
    # wrote this. A negative age is a writer whose clock runs ahead: the entry is
    # YOUNGER than it looks, so clamping to 0 is the conservative reading.
    age_s = max(0.0, time.time() - float(stored_wall))
    if age_s > ttl_s:
        _stats["cross_worker_misses"] += 1
        return False, None, 0.0

    try:
        value = decode_shared_payload(envelope["payload"])
    except Exception:
        logger.warning(
            "shared build: undecodable payload for namespace=%s — building", namespace
        )
        _stats["cross_worker_failures"] += 1
        return False, None, 0.0

    _stats["cross_worker_hits"] += 1
    return True, value, age_s


async def _publish_cross_worker(
    namespace: str, key: tuple, value: Any, ttl_s: float
) -> None:
    """Publish `value` to the Redis tier. Best-effort, bounded, never raises.

    Called AFTER the singleflight lock is released, so a slow publish delays
    nobody: the value is already in L1 and already returned to its builder.
    """
    if not cross_worker_enabled() or ttl_s <= 0:
        return
    from app.utils import request_cache as _rc

    try:
        payload = encode_shared_payload(value)
    except Exception as exc:
        # Fail-closed on sharing. A payload we cannot represent losslessly is
        # never published half-right — the next worker rebuilds instead.
        logger.warning(
            "shared build: namespace=%s not publishable (%s) — local tier only",
            namespace,
            exc,
        )
        _stats["cross_worker_publish_refused"] += 1
        return

    envelope = json.dumps(
        {
            "v": 1,
            "ns": namespace,
            "k": repr(key),
            "stored_wall": time.time(),
            "payload": payload,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )
    # Two bounds, two reasons (LAT-P221). The decode budget is checked on the
    # JSON, because that is what a reader has to parse; the storage budget is
    # checked on the compressed blob, because that is what Redis has to hold.
    size = len(envelope.encode("utf-8", "replace"))
    if size > MAX_ENVELOPE_BYTES:
        logger.warning(
            "shared build: namespace=%s envelope %s bytes over decode cap %s "
            "— local tier only",
            namespace,
            size,
            MAX_ENVELOPE_BYTES,
        )
        _stats["cross_worker_publish_refused"] += 1
        return

    blob = wire_encode(envelope)
    if len(blob) > MAX_STORED_BYTES:
        logger.warning(
            "shared build: namespace=%s stored %s bytes over storage cap %s "
            "(envelope %s) — local tier only",
            namespace,
            len(blob),
            MAX_STORED_BYTES,
            size,
        )
        _stats["cross_worker_publish_refused"] += 1
        return

    try:
        client = await _shared_redis_client()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("shared build: no redis client for publish", exc_info=True)
        _stats["cross_worker_failures"] += 1
        return

    redis_key = redis_key_for(namespace, key)
    # `EX` is the backstop; the reader's own age check against `stored_wall` is
    # the bound. Ceil so a sub-second TTL still produces a legal expiry.
    expire_s = max(1, int(ttl_s) + 1)
    result = await _rc.bounded_redis_call(
        lambda: client.set(redis_key, blob, ex=expire_s),
        deadline_ms=REDIS_PUBLISH_DEADLINE_MS,
        treat_none_as_miss=False,
    )
    if result.is_failure:
        _stats["cross_worker_failures"] += 1
        return
    _stats["cross_worker_publishes"] += 1


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

    Tiers, in order (LAT-P103): process-local dict → Redis → `builder`. The
    Redis hop happens only after the local tier has already missed, so a warm
    worker pays nothing for it and a cold one trades ~1ms against the rebuild.
    """
    _clock = clock or time.monotonic
    _ttl = shared_build_ttl_s(namespace) if ttl_s is None else ttl_s

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

    ok, value, age_s = _read_fresh(namespace, key, _ttl, _clock())
    if ok:
        # L1 hit — the Redis tier is never consulted here. This is the path the
        # module docstring's "deliberately NOT Redis" sentence is about, and it
        # is byte-for-byte the path LAT-P084 shipped.
        _note_reuse(namespace, reuse_sink, SHARED_TIER_LOCAL)
        _note_age(namespace, age_s)
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
        ok, value, age_s = _read_fresh(namespace, key, _ttl, _clock())
        if ok:
            _note_reuse(namespace, reuse_sink, SHARED_TIER_LOCAL)
            _note_age(namespace, age_s)
            return copy.deepcopy(value)

        # LAT-P103: L1 missed, so the alternative is a 683-1249ms rebuild.
        # THAT is what the bounded Redis hop is being weighed against — not
        # against a hit. A cold worker (fresh dyno, restarted worker, or simply
        # one of the other `WEB_CONCURRENCY` processes) reaches the artifact
        # here instead of rebuilding it.
        ok, value, age_s = await _read_cross_worker(namespace, key, _ttl)
        if ok:
            # Promote into L1 so this worker's NEXT request skips the hop too.
            #
            # BACKDATED BY THE AGE IT ARRIVED WITH (LAT-P229). Storing `_clock()`
            # here — which is what this line did — reset the artifact's age to
            # zero, so an entry read from Redis at 59s under a 60s TTL got a
            # second full TTL locally and the real staleness bound was 2 x TTL.
            # The promotion is still right; only the timestamp was.
            #
            # `age_s` is a DURATION measured on the wall clock, and `_clock()` is
            # monotonic. Subtracting one from the other is sound because only the
            # difference is ever read (`_read_fresh` compares `now - stored_at`),
            # and durations are the same quantity on both clocks.
            entries = _store.setdefault(namespace, {})
            entries[key] = (_clock() - age_s, copy.deepcopy(value))
            _evict_if_needed(entries, namespace)
            _note_reuse(namespace, reuse_sink, SHARED_TIER_CROSS_WORKER)
            _note_age(namespace, age_s)
            return value

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
        _evict_if_needed(entries, namespace)
        # Age zero — this request BUILT it. Recorded rather than skipped so an
        # empty age sink means "no shared artifact was consumed at all" and not
        # "the instrument was silent" (LAT-P230).
        _note_age(namespace, 0.0)
        # Snapshot for the publisher too: the caller mutates its cards in place
        # (`_rank_score`, bundling, pin flags), and the publish runs after this
        # function has handed `built` back.
        snapshot = copy.deepcopy(built)
    finally:
        if acquired:
            lock.release()

    # Reached ONLY by the build-and-store path — every other path above returns
    # inside the `try`. Publishing HERE, outside the lock, is what keeps a slow
    # or stalled Redis write from holding a coalescing waiter: the value is
    # already in L1 and already owed to its builder.
    try:
        await _publish_cross_worker(namespace, key, snapshot, _ttl)
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - publish is best-effort by contract
        logger.debug("shared build publish failed", exc_info=True)
    return built


# --------------------------------------------------------------------------
# key helpers
# --------------------------------------------------------------------------


def time_bucket(now: datetime, seconds: float) -> int:
    """A coarse, principal-independent time component for a shared key.

    Bucketing on the clock — NOT on an offset from a per-request `now` — is what
    makes two principals arriving 200ms apart land on the SAME key.

    It is NOT a staleness bound (LAT-P104 corrects the sentence that used to
    stand here). An entry is served only while `age < TTL` *and* the bucket has
    not turned, so staleness is `min(TTL, bucket)` and a bucket wider than the
    TTL changes nothing about how stale a reader can get. What the width does
    govern is how much still-fresh work the key throws away: pass
    `clock_bucket_s()` rather than a literal unless you have enumerated the
    boundaries your build actually moves on.
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
