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
  ``discover-candidates:v1:{sport|all}:{static-tags|no-static-tags}`` — it
  deliberately excludes ``limit``, ``offset``, user, and session, so page one and
  page two (and native's 50/200 shapes) reuse the SAME base. The anonymous
  default (``sport=None``, ``static_tag_filter=None``) is the hot key the beat
  keeps warm.

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
CANDIDATE_BASE_SCHEMA_VERSION = 1
_KEY_PREFIX = "discover-candidates"
_KEY_VERSION = "v1"
# Redis key namespace (distinct from the offline oracle's ``candidate_base_key``
# which returns the *identity* string below without the redis namespace).
_REDIS_NS = "bainluck:candidate_base:v1"

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
def _static_tags_token(static_tag_filter: Optional[list[str]]) -> str:
    if not static_tag_filter:
        return "no-static-tags"
    # Order-independent, stable token so ["a","b"] and ["b","a"] share a base.
    return ",".join(sorted(str(t) for t in static_tag_filter))


def base_identity(
    sport_filter: Optional[str], static_tag_filter: Optional[list[str]]
) -> str:
    """Return the user-independent identity string for this candidate base.

    Excludes limit, offset, user, and session by construction; includes only the
    pool inputs (sport + static tags). Mirrors the C85 offline oracle
    ``candidate_base_key`` (which returns ``discover-candidates:v1:all:no-static-tags``
    for the anonymous default).
    """
    sport_token = sport_filter or "all"
    return f"{_KEY_PREFIX}:{_KEY_VERSION}:{sport_token}:{_static_tags_token(static_tag_filter)}"


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
    return {
        "schema_version": CANDIDATE_BASE_SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
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


def _l0_store(identity: str, envelope: dict) -> None:
    _l0[identity] = {"envelope": envelope, "fetched_wall": time.time()}


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
    identity = base_identity(sport_filter, static_tag_filter)

    hit = _l0_lookup(identity, now)
    if hit is not None:
        _record_stage(stages, "candidate_base_read", time.perf_counter())
        return hit

    fresh_key, last_good_key = _redis_keys(identity)
    t0 = time.perf_counter()
    try:
        client = await _rc.get_shared_async_redis()
        if await _kill_switch_disabled(client):
            _record_stage(stages, "candidate_base_read", t0)
            return None, PROV_DISABLED, None

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
    t0 = time.perf_counter()
    try:
        client = await _rc.get_shared_async_redis()
        if await _kill_switch_disabled(client):
            return
        await _rc.bounded_redis_call(
            lambda: client.set(fresh_key, payload, ex=CANDIDATE_BASE_FRESH_TTL_S)
        )
        await _rc.bounded_redis_call(
            lambda: client.set(
                last_good_key, payload, ex=CANDIDATE_BASE_LAST_GOOD_TTL_S
            )
        )
        _l0_store(identity, envelope)
        _rc.remember_last_good(f"candidate_base:{identity}", envelope)
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - publish is best-effort
        logger.debug("candidate base publish failed", exc_info=True)
    _record_stage(stages, "candidate_base_publish", t0)


def publish_candidate_base_sync(rc: Any, envelope: dict) -> None:
    """Publish a base to both keys with a SYNC Redis client.

    Used by the precompute beat task, which already holds a sync
    ``get_redis_client()``. Writes the exact key names + envelope shape the feed
    reads. A failed/partial build must never reach here (the task only publishes a
    fully-built, valid envelope), so the prior last-good key is never clobbered by
    a bad build.
    """
    if not payload_valid(envelope):
        return
    identity = envelope["identity"]
    fresh_key, last_good_key = _redis_keys(identity)
    payload = json.dumps(envelope, default=str)
    rc.set(fresh_key, payload, ex=CANDIDATE_BASE_FRESH_TTL_S)
    rc.set(last_good_key, payload, ex=CANDIDATE_BASE_LAST_GOOD_TTL_S)
