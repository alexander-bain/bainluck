"""Shared, user-independent Discover candidate-ID base for the cold feed path (Queue 285).

``GET /api/feed`` rebuilds its Discover futures candidate pool on every *cold*
response-cache key — nine ordered ID queries (external-curator recall + eight
``select(FuturesMarket.id)`` pools) that took a measured ~3–6s cold. Because the
response cache fragments on ``limit``/``offset``/user/session, page one and page
two of the same anonymous scroll are *different* response keys, so each cold page
re-ran the entire candidate discovery even though the ordered candidate ID list
is identical for both (the pools depend ONLY on ``now``, ``sport_filter`` and
``static_tag_filter`` — never on the user, session, limit, offset, or
personalization).

This module publishes that *user-independent ordered candidate-ID list* as one
freshness-tagged, versioned envelope in Redis and lets the feed consume it
through the bounded, process-shared async client (Queue 271/277 primitives in
``app.utils.request_cache``). It is the candidate-ID analogue of
``app.utils.golf_base`` and follows the same selection/freshness/last-good
contract. Design contract:

* **The base carries only user-independent candidate IDs + identity metadata.**
  No market questions, probabilities, personalization, seen/dismiss state, or
  final rank ever enter the payload. The feed loads the current market/outcome
  ORM rows and runs every existing runtime filter, interestingness,
  personalization, scoring, diversity, bundle, and page operation request-side,
  exactly as before. The base is only the *input ID set*, not the answer.

* **Keyed by the pool inputs, not the request shape.** The base key is
  ``discover-candidates:v2:{sport|all}:{static-tags|no-static-tags}`` — it
  deliberately excludes ``limit``, ``offset``, user, and session, so page one and
  page two (and native's 50/200 shapes) reuse the SAME base. The anonymous
  default (``sport=None``, ``static_tag_filter=None``) is the hot key the beat
  keeps warm. The v2 encoding is *injective*: structural characters are escaped,
  tags are deduped + sorted, and an over-long tag set collapses to a digest, so
  two different filters can never share a key and two equivalent ones always do.

* **Fresh only through the anonymous feed freshness boundary.** A base older than
  ``CANDIDATE_BASE_FRESH_SECONDS`` (defaults to the 60s anon feed response TTL) is
  not labelled ``fresh``. An older-but-bounded base is served as a truthfully
  labelled ``last_good`` fallback; beyond the last-good bound the feed falls back
  to its current direct-query path. The downstream per-market re-filters
  (resolution date, staleness, settlement) run on FRESH ORM rows every request,
  so a slightly-stale candidate set can never surface a resolved/dead card.

* **Fallback is always the current path.** On a missing / stale / invalid base,
  or when the Redis kill switch is set, the feed runs its existing inline
  candidate queries under the existing absolute request deadline — no new blind
  parallelism and no query ``gather()`` on the one request ``AsyncSession``.

* **Arbitrary sport/static-tag requests are safe.** They read the correctly-keyed
  base if one exists (published by the beat or by an earlier request), otherwise
  fall back to direct queries. Only the anonymous default key is beat-warmed.

The frozen offline contract is the C85 pack
(``backend/scripts/evals/cold_feed_latency_authority.py``) and the
``futures_pool_equivalence`` rows in ``cold_feed_equivalence.py``;
``tests/test_candidate_base.py`` and
``tests/test_feed_candidate_base_equivalence.py`` guard the live boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils import request_cache as _rc

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- Keys, versions, and freshness policy -------------------------------------
# v2 (Queue 288/C91): collision-free canonical identity encoding + a monotonic
# ``generated_epoch_ms``. The version bump is deliberate — a v1 envelope must
# never be read under a v2 identity, and vice versa, so the two namespaces are
# disjoint and the cutover needs no migration (the beat republishes within one
# interval; until then the feed simply falls back to its direct-query path).
CANDIDATE_BASE_SCHEMA_VERSION = 2
_KEY_PREFIX = "discover-candidates"
_KEY_VERSION = "v2"
# Redis key namespace (distinct from the offline oracle's ``candidate_base_key``
# which returns the *identity* string below without the redis namespace).
_REDIS_NS = "bainluck:candidate_base:v2"

# The feed freshness boundary — defaults to the 60s anonymous feed response cache
# TTL so the base is never labelled ``fresh`` looser than the anon feed's own
# freshness contract. A payload older than this is served (if at all) as bounded
# ``last_good``.
CANDIDATE_BASE_FRESH_SECONDS = _env_int("CANDIDATE_BASE_FRESH_SECONDS", 60)
# The bounded last-good window: how stale a base may be and still be served as a
# truthfully labelled fallback rather than forcing the inline direct queries.
CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S = _env_int(
    "CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S", 3600
)

# Redis retention (TTL) of each key. The fresh key outlives one freshness window
# so a restart finds a servable (if stale) base; the last-good key is retained
# longer as the durable floor.
CANDIDATE_BASE_FRESH_TTL_S = _env_int("CANDIDATE_BASE_FRESH_TTL_S", 3600)
CANDIDATE_BASE_LAST_GOOD_TTL_S = _env_int("CANDIDATE_BASE_LAST_GOOD_TTL_S", 86400)

# Process-local read throttle: how long a fetched envelope may satisfy requests
# before the process re-reads Redis. Freshness is ALWAYS re-derived from the
# envelope's ``generated_at`` on each hit, so this never mislabels a stale base
# as fresh — it only bounds Redis round-trips within a hot process.
CANDIDATE_BASE_L0_TTL_S = _env_int("CANDIDATE_BASE_L0_TTL_S", 30)

# Hard ceiling on the process-local L0 map. Arbitrary sport/static-tag requests
# each mint their own identity, so an unbounded map is a memory-growth vector
# under filter churn (a crawler varying ``sport=`` is enough). Eviction is
# expiry-first, then oldest-fetch-first.
CANDIDATE_BASE_L0_MAX_ENTRIES = _env_int("CANDIDATE_BASE_L0_MAX_ENTRIES", 256)

# Admission bounds for the user-supplied pool inputs. These bound the Redis key
# and the L0 map; they are NOT a product filter policy (every tag that reaches
# the pools today is far below them).
MAX_TAG_LENGTH = _env_int("CANDIDATE_BASE_MAX_TAG_LENGTH", 256)
MAX_STATIC_TAGS = _env_int("CANDIDATE_BASE_MAX_STATIC_TAGS", 32)
MAX_IDENTITY_LENGTH = _env_int("CANDIDATE_BASE_MAX_IDENTITY_LENGTH", 256)


class CandidateBaseTagError(ValueError):
    """A malformed / non-string / oversized pool input was rejected at admission.

    Subclasses ``ValueError`` so existing broad ``except (ValueError, TypeError)``
    callers keep working; the route layer maps it to a 400, never a 500.
    """

# Redis kill switch. When this key equals "0" the feed ignores the base entirely
# (reads and publishes) and runs its current direct-query path — one key,
# immediate rollback.
CANDIDATE_BASE_ENABLED_KEY = "discover_candidate_base:enabled"

# Provenance labels reported alongside the candidate IDs so a miss/fallback is
# diagnosable in stage evidence (no IDs / content are ever recorded).
PROV_FRESH = "fresh"
PROV_LAST_GOOD = "last_good"
PROV_DIRECT = "direct"
PROV_DISABLED = "disabled"
PROV_UNAVAILABLE = "unavailable"

# Keys a valid base envelope must carry; forbidden keys would mean request-side
# state leaked into the shared payload.
_REQUIRED_ENVELOPE_KEYS = {
    "schema_version",
    "generated_at",
    "generated_epoch_ms",
    "identity",
    "candidate_ids",
    "external_curator_recall_ids",
    "pool_counts",
    "source_watermark",
}
_FORBIDDEN_ENVELOPE_KEYS = {
    "user",
    "user_id",
    "session",
    "session_id",
    "limit",
    "offset",
    "personalization",
    "final_rank",
    "scores",
}


# --- Identity keying ----------------------------------------------------------
# Reserved sentinels that a *literal* value must never be able to impersonate.
_SENTINEL_ALL = "all"
_SENTINEL_NO_TAGS = "no-static-tags"
# Characters that carry structure in the identity string. Escaping them makes the
# encoding injective: two different (sport, tags) inputs can never render to the
# same identity. ``%`` must be escaped first (it is the escape character), and
# ``~`` is reserved as the digest marker so a literal token can never start with it.
_ESCAPES = (("%", "%25"), (":", "%3A"), (",", "%2C"), ("~", "%7E"))


def _escape(token: str) -> str:
    for raw, encoded in _ESCAPES:
        token = token.replace(raw, encoded)
    return token


def _disambiguate(token: str) -> str:
    """Percent-encode the first character of a token that equals a sentinel.

    ``sport="all"`` must not render the same identity as ``sport=None``, and a
    literal tag ``"no-static-tags"`` must not render the same as *no tags*.
    """
    if token in (_SENTINEL_ALL, _SENTINEL_NO_TAGS):
        return f"%{ord(token[0]):02X}{token[1:]}"
    return token


def _validate_tag(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CandidateBaseTagError(
            f"{field} must be a string, got {type(value).__name__}"
        )
    if len(value) > MAX_TAG_LENGTH:
        raise CandidateBaseTagError(
            f"{field} exceeds {MAX_TAG_LENGTH} characters ({len(value)})"
        )
    return value


def _static_tags_token(static_tag_filter: Optional[list[str]]) -> str:
    """Return a collision-free, order- and duplicate-independent tags token.

    Canonicalization is limited to transforms that are provably SQL-identical:
    **dedupe** and **sort**. Case folding and Unicode normalization are
    deliberately NOT applied — Postgres JSONB containment (``event_tags @> ...``)
    is byte-exact, so folding them would merge two genuinely different candidate
    sets and serve the wrong markets.
    """
    if not static_tag_filter:
        return _SENTINEL_NO_TAGS
    if len(static_tag_filter) > MAX_STATIC_TAGS:
        raise CandidateBaseTagError(
            f"static tag filter exceeds {MAX_STATIC_TAGS} tags "
            f"({len(static_tag_filter)})"
        )
    validated = [
        _validate_tag(t, field="static tag") for t in static_tag_filter
    ]
    # Dedupe + sort: both are no-ops for the resulting SQL, so the deduped and
    # reordered forms of one filter must share exactly one base.
    token = ",".join(_escape(t) for t in sorted(set(validated)))
    return _disambiguate(token)


def base_identity(
    sport_filter: Optional[str], static_tag_filter: Optional[list[str]]
) -> str:
    """Return the user-independent identity string for this candidate base.

    Excludes limit, offset, user, and session by construction; includes only the
    pool inputs (sport + static tags). The anonymous default stays the readable
    ``discover-candidates:v2:all:no-static-tags`` (the C85 offline oracle key,
    version-bumped); any input containing a structural character is escaped, and
    an over-long tag set collapses to a ``~<sha256>`` digest so the Redis key is
    length-bounded without ever becoming ambiguous.

    Raises ``CandidateBaseTagError`` on a non-string / oversized pool input.
    """
    if sport_filter is None:
        sport_token = _SENTINEL_ALL
    else:
        sport_token = _disambiguate(
            _escape(_validate_tag(sport_filter, field="sport filter"))
        )
    tags_token = _static_tags_token(static_tag_filter)

    identity = f"{_KEY_PREFIX}:{_KEY_VERSION}:{sport_token}:{tags_token}"
    if len(identity) <= MAX_IDENTITY_LENGTH:
        return identity
    # Digest the (already canonical) tags token. ``~`` cannot begin an escaped
    # literal token, so the digest form can never collide with a literal one.
    digest = hashlib.sha256(tags_token.encode("utf-8")).hexdigest()[:40]
    return f"{_KEY_PREFIX}:{_KEY_VERSION}:{sport_token}:~{digest}"


def _redis_keys(identity: str) -> tuple[str, str]:
    """Return (fresh_key, last_good_key) for a base identity."""
    fresh = f"{_REDIS_NS}:{identity}"
    return fresh, f"{fresh}:last_good"


# --- Validation + envelope ----------------------------------------------------
def payload_valid(envelope: Any, expected_identity: Optional[str] = None) -> bool:
    """Return True iff ``envelope`` is a well-formed, user-independent base.

    Rejects any envelope with a wrong schema version, missing required keys, a
    leaked request-side (forbidden) key, a non-int candidate ID, or — when
    ``expected_identity`` is given — a base built for a different identity (so a
    key mix-up can never serve the wrong sport/tag's candidates).
    """
    if not isinstance(envelope, dict):
        return False
    if envelope.get("schema_version") != CANDIDATE_BASE_SCHEMA_VERSION:
        return False
    if _FORBIDDEN_ENVELOPE_KEYS.intersection(envelope):
        return False
    if not _REQUIRED_ENVELOPE_KEYS.issubset(envelope):
        return False
    identity = envelope.get("identity")
    if not isinstance(identity, str) or not identity:
        return False
    if expected_identity is not None and identity != expected_identity:
        return False
    for id_field in ("candidate_ids", "external_curator_recall_ids"):
        ids = envelope.get(id_field)
        if not isinstance(ids, list):
            return False
        for market_id in ids:
            if not isinstance(market_id, int) or isinstance(market_id, bool):
                return False
    return True


def build_envelope(
    now: datetime,
    identity: str,
    candidate_ids: list[int],
    *,
    pool_counts: Optional[dict[str, int]] = None,
    external_curator_recall_ids: Optional[list[int]] = None,
) -> dict:
    """Wrap an ordered candidate-ID list in a freshness-tagged, versioned envelope.

    ``candidate_ids`` MUST already be the order-preserving deduped union the feed
    consumes (see ``feed._compute_ordered_candidate_ids``).
    ``external_curator_recall_ids`` is the (user-independent) set of IDs the
    external-curator recall lane returned — the feed applies a recall score/rank
    bonus to these, so it must ride in the base for a base-served build to score
    identically to a direct build. ``source_watermark`` is a cheap, query-free
    provenance signal (max candidate id + count) so a consumer can tell two bases
    apart without carrying any market content.
    """
    ids = [int(mid) for mid in candidate_ids]
    curator_ids = [int(mid) for mid in (external_curator_recall_ids or [])]
    generated = now.astimezone(timezone.utc)
    return {
        "schema_version": CANDIDATE_BASE_SCHEMA_VERSION,
        "generated_at": generated.isoformat(),
        # Integer build clock for the monotonic publish guard. Comparing ints in
        # the Redis compare-and-set script is exact, unlike lexicographic
        # comparison of ISO strings with optional microseconds.
        "generated_epoch_ms": int(generated.timestamp() * 1000),
        "identity": identity,
        "candidate_ids": ids,
        "external_curator_recall_ids": curator_ids,
        "pool_counts": dict(pool_counts or {}),
        "source_watermark": {
            "count": len(ids),
            "max_market_id": max(ids) if ids else 0,
        },
    }


def _envelope_age_seconds(envelope: Any, now: datetime) -> Optional[float]:
    if not isinstance(envelope, dict):
        return None
    if envelope.get("schema_version") != CANDIDATE_BASE_SCHEMA_VERSION:
        return None
    generated_at = envelope.get("generated_at")
    if not isinstance(generated_at, str):
        return None
    try:
        ts = datetime.fromisoformat(generated_at)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now.astimezone(timezone.utc) - ts).total_seconds()


def _usable(envelope: Any, now: datetime, max_age_s: float, identity: str) -> bool:
    age = _envelope_age_seconds(envelope, now)
    if age is None or age < 0 or age > max_age_s:
        return False
    return payload_valid(envelope, expected_identity=identity)


# --- Process-local read throttle (per identity) -------------------------------
_l0: dict[str, dict[str, Any]] = {}


def _served(envelope: dict, provenance: str) -> tuple[list[int], str, list[int]]:
    """Return the (candidate_ids, provenance, curator_ids) served tuple."""
    return (
        list(envelope["candidate_ids"]),
        provenance,
        list(envelope.get("external_curator_recall_ids") or []),
    )


def _l0_lookup(
    identity: str, now: datetime
) -> Optional[tuple[list[int], str, list[int]]]:
    entry = _l0.get(identity)
    if not entry:
        return None
    envelope = entry.get("envelope")
    if envelope is None:
        return None
    if (time.time() - entry.get("fetched_wall", 0.0)) >= CANDIDATE_BASE_L0_TTL_S:
        return None
    if _usable(envelope, now, CANDIDATE_BASE_FRESH_SECONDS, identity):
        return _served(envelope, PROV_FRESH)
    if _usable(envelope, now, CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S, identity):
        return _served(envelope, PROV_LAST_GOOD)
    return None


def _l0_evict(now_wall: float) -> None:
    """Expiry-first, then oldest-first eviction to the configured bound.

    Arbitrary sport/static-tag requests each mint an identity, so without this
    the map grows for as long as the dyno lives.
    """
    for identity, entry in list(_l0.items()):
        if (now_wall - entry.get("fetched_wall", 0.0)) >= CANDIDATE_BASE_L0_TTL_S:
            _l0.pop(identity, None)
    overflow = len(_l0) - CANDIDATE_BASE_L0_MAX_ENTRIES
    if overflow <= 0:
        return
    for identity, _ in sorted(
        _l0.items(), key=lambda kv: kv[1].get("fetched_wall", 0.0)
    )[:overflow]:
        _l0.pop(identity, None)


def _l0_store(identity: str, envelope: dict) -> None:
    now_wall = time.time()
    _l0[identity] = {"envelope": envelope, "fetched_wall": now_wall}
    # Bounded by construction: the map can never be observed above the cap, and
    # expired entries never linger (the map is <=256 entries, so this is cheap).
    _l0_evict(now_wall)


def _l0_drop(identity: str) -> None:
    """Forget any process-local base for ``identity`` (kill-switch rollback)."""
    _l0.pop(identity, None)


def _reset_l0_for_tests() -> None:
    _l0.clear()


# --- Redis read / publish (bounded, shared client) ----------------------------
def _decode_envelope(raw: Any) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    if isinstance(raw, dict):
        return raw
    return None


def _record_stage(stages, name: str, t0: float) -> None:
    if stages is None:
        return
    stages.append({"stage": name, "ms": round((time.perf_counter() - t0) * 1000, 2)})


async def _read_key(client: Any, key: str) -> Optional[dict]:
    result = await _rc.bounded_redis_call(lambda: client.get(key))
    if not result.is_ok:
        return None
    return _decode_envelope(result.value)


async def _kill_switch_disabled(client: Any) -> bool:
    """True iff the Redis kill switch is explicitly set to "0" (base disabled)."""
    result = await _rc.bounded_redis_call(
        lambda: client.get(CANDIDATE_BASE_ENABLED_KEY)
    )
    if not result.is_ok:
        return False  # missing key / stall -> base stays enabled (default on)
    value = result.value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return False
    return str(value).strip() == "0"


async def get_candidate_base(
    now: datetime,
    sport_filter: Optional[str],
    static_tag_filter: Optional[list[str]],
    *,
    stages=None,
) -> tuple[Optional[list[int]], str, Optional[list[int]]]:
    """Return (ordered_candidate_ids, provenance, external_curator_recall_ids).

    Read-only: this NEVER runs the candidate SQL and never touches the request
    ``AsyncSession``. Selection order (each tier bounded):

    1. Process-local throttle hit (Redis round-trip avoided; freshness re-derived).
    2. Redis fresh key, age <= freshness window -> ``fresh``.
    3. Redis fresh key, age <= last-good window -> ``last_good``.
    4. Redis last-good key, age <= last-good window -> ``last_good``.
    5. Process-local request-cache last-good (survives a Redis outage) -> ``last_good``.

    On a kill switch, missing/stale/invalid base, or Redis outage returns
    ``(None, provenance, None)`` where provenance is ``disabled`` (kill switch) or
    ``direct`` (everything else). The caller then runs its existing direct-query
    path and (unless disabled) publishes the freshly-computed base. When a base is
    served, the third element is the external-curator recall ID list carried in
    the envelope, so the feed's recall score/rank bonus scores identically.
    """
    # Defense in depth: the route bounds these at admission, but a bad pool input
    # from ANY caller must degrade to the direct-query path, never raise into a
    # request handler as a 500.
    try:
        identity = base_identity(sport_filter, static_tag_filter)
    except CandidateBaseTagError:
        logger.debug("candidate base identity rejected at read", exc_info=True)
        return None, PROV_DIRECT, None

    fresh_key, last_good_key = _redis_keys(identity)
    t0 = time.perf_counter()

    # The kill switch is checked BEFORE any local (L0 / process last-good)
    # service, so rollback is immediate rather than lagging one L0 window. A
    # switch-read failure leaves the base ENABLED (default on) so a Redis outage
    # degrades to last-good instead of a direct-query stampede.
    client = None
    try:
        client = await _rc.get_shared_async_redis()
        if await _kill_switch_disabled(client):
            _l0_drop(identity)  # no warm local base may outlive the switch
            _record_stage(stages, "candidate_base_read", t0)
            return None, PROV_DISABLED, None
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("candidate base kill-switch read failed", exc_info=True)

    hit = _l0_lookup(identity, now)
    if hit is not None:
        _record_stage(stages, "candidate_base_read", t0)
        return hit

    try:
        if client is None:
            client = await _rc.get_shared_async_redis()
        fresh_env = await _read_key(client, fresh_key)
        if _usable(fresh_env, now, CANDIDATE_BASE_FRESH_SECONDS, identity):
            _l0_store(identity, fresh_env)
            _rc.remember_last_good(f"candidate_base:{identity}", fresh_env)
            _record_stage(stages, "candidate_base_read", t0)
            return _served(fresh_env, PROV_FRESH)

        last_good_env = None
        if _usable(fresh_env, now, CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S, identity):
            last_good_env = fresh_env
        else:
            candidate = await _read_key(client, last_good_key)
            if _usable(candidate, now, CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S, identity):
                last_good_env = candidate

        if last_good_env is not None:
            _l0_store(identity, last_good_env)
            _rc.remember_last_good(f"candidate_base:{identity}", last_good_env)
            _record_stage(stages, "candidate_base_read", t0)
            return _served(last_good_env, PROV_LAST_GOOD)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("candidate base redis read failed", exc_info=True)

    # Redis had nothing usable — serve a process-local last-good if we have one
    # (covers a Redis outage on a warm process without running the candidate SQL).
    recalled = _rc.recall_last_good(
        f"candidate_base:{identity}", max_age_s=CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S
    )
    if _usable(recalled, now, CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S, identity):
        _record_stage(stages, "candidate_base_read", t0)
        return _served(recalled, PROV_LAST_GOOD)

    _record_stage(stages, "candidate_base_read", t0)
    return None, PROV_DIRECT, None


# --- Monotonic publication ----------------------------------------------------
# Compare-and-set: write only when the incoming build is not OLDER than what is
# already stored. Two builds can overlap (a slow request-path build and the beat,
# or two cold pages), and without this the one that finishes LAST wins even when
# it started first — republishing a stale candidate set over a fresh one.
_MONOTONIC_SET_LUA = """
local incoming = tonumber(ARGV[2])
local current = redis.call('GET', KEYS[1])
if current then
  local ok, decoded = pcall(cjson.decode, current)
  if ok and type(decoded) == 'table' and type(decoded['generated_epoch_ms']) == 'number' then
    if decoded['generated_epoch_ms'] > incoming then
      return 0
    end
  end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[3]))
return 1
"""


def _is_older_than_stored(raw: Any, epoch_ms: int) -> bool:
    """True iff ``raw`` decodes to an envelope strictly NEWER than ``epoch_ms``."""
    existing = _decode_envelope(raw)
    if not isinstance(existing, dict):
        return False
    stored = existing.get("generated_epoch_ms")
    return isinstance(stored, int) and stored > epoch_ms


async def _monotonic_set(client: Any, key: str, payload: str, epoch_ms: int, ttl: int) -> None:
    """Atomically set ``key`` unless a strictly newer envelope is already there.

    Falls back to a bounded read-compare-set when the Redis deployment rejects
    ``EVAL`` — narrower (the compare and the set are not one operation) but still
    rejects the common older-completes-last case, and never blocks publication.
    """
    result = await _rc.bounded_redis_call(
        lambda: client.eval(_MONOTONIC_SET_LUA, 1, key, payload, epoch_ms, ttl),
        treat_none_as_miss=False,
    )
    if result.is_ok or result.status == _rc.TIMEOUT:
        return
    current = await _rc.bounded_redis_call(lambda: client.get(key))
    if current.is_ok and _is_older_than_stored(current.value, epoch_ms):
        return
    await _rc.bounded_redis_call(lambda: client.set(key, payload, ex=ttl))


def _monotonic_set_sync(rc_client: Any, key: str, payload: str, epoch_ms: int, ttl: int) -> None:
    """Sync twin of ``_monotonic_set`` for the precompute beat."""
    try:
        rc_client.eval(_MONOTONIC_SET_LUA, 1, key, payload, epoch_ms, ttl)
        return
    except Exception:
        logger.debug("candidate base monotonic EVAL unavailable", exc_info=True)
    try:
        if _is_older_than_stored(rc_client.get(key), epoch_ms):
            return
    except Exception:
        logger.debug("candidate base monotonic read failed", exc_info=True)
    rc_client.set(key, payload, ex=ttl)


async def publish_candidate_base(envelope: dict, *, stages=None) -> None:
    """Publish a base envelope to both Redis keys via the shared async client.

    Best-effort + bounded — a publish failure never propagates (the caller has
    already served its response). ``payload_valid`` is enforced so a malformed /
    request-tainted envelope can never be published. The kill switch is honoured:
    a disabled base is never (re)published.
    """
    if not payload_valid(envelope):
        return
    identity = envelope["identity"]
    fresh_key, last_good_key = _redis_keys(identity)
    payload = json.dumps(envelope, default=str)
    epoch_ms = int(envelope["generated_epoch_ms"])
    t0 = time.perf_counter()
    try:
        client = await _rc.get_shared_async_redis()
        # Checked immediately before the writes: a disable that lands while this
        # build was running must not be undone by the build's own publish.
        if await _kill_switch_disabled(client):
            _l0_drop(identity)
            return
        await _monotonic_set(
            client, fresh_key, payload, epoch_ms, CANDIDATE_BASE_FRESH_TTL_S
        )
        await _monotonic_set(
            client, last_good_key, payload, epoch_ms, CANDIDATE_BASE_LAST_GOOD_TTL_S
        )
        _l0_store(identity, envelope)
        _rc.remember_last_good(f"candidate_base:{identity}", envelope)
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - publish is best-effort
        logger.debug("candidate base publish failed", exc_info=True)
    _record_stage(stages, "candidate_base_publish", t0)


def _kill_switch_disabled_sync(rc_client: Any) -> bool:
    """Sync twin of ``_kill_switch_disabled`` (missing key / error -> enabled)."""
    try:
        value = rc_client.get(CANDIDATE_BASE_ENABLED_KEY)
    except Exception:
        logger.debug("candidate base sync kill-switch read failed", exc_info=True)
        return False
    if value is None:
        return False
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return False
    return str(value).strip() == "0"


def publish_candidate_base_sync(rc: Any, envelope: dict) -> None:
    """Publish a base to both keys with a SYNC Redis client.

    Used by the precompute beat task, which already holds a sync
    ``get_redis_client()``. Writes the exact key names + envelope shape the feed
    reads. A failed/partial build must never reach here (the task only publishes a
    fully-built, valid envelope), so the prior last-good key is never clobbered by
    a bad build.

    The kill switch is re-checked HERE, not just at the top of the build: the beat
    build takes up to ~20s, so a disable landing mid-build would otherwise be
    silently undone by the build's own publish. Writes are monotonic — an older
    build finishing after a newer one cannot replace it.
    """
    if not payload_valid(envelope):
        return
    if _kill_switch_disabled_sync(rc):
        logger.info("Discover candidate base publish skipped — kill switch off")
        return
    identity = envelope["identity"]
    fresh_key, last_good_key = _redis_keys(identity)
    payload = json.dumps(envelope, default=str)
    epoch_ms = int(envelope["generated_epoch_ms"])
    _monotonic_set_sync(rc, fresh_key, payload, epoch_ms, CANDIDATE_BASE_FRESH_TTL_S)
    _monotonic_set_sync(
        rc, last_good_key, payload, epoch_ms, CANDIDATE_BASE_LAST_GOOD_TTL_S
    )
