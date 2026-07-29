"""Shared, freshness-tagged golf listing base for the cold feed path (Queue 278).

The Discover / Sports feed's golf tournaments were rebuilt inline via
``app.routes.golf.get_golf`` on every process cold start (dyno restart) and on
every 300s process-cache expiry — a measured ~8.9s DB + DataGolf rebuild that
risked the Heroku 30s router H12 on ordinary ``GET /api/feed`` requests
(#1475 / #1459).

This module publishes the *user-independent* golf listing base as one
freshness-tagged envelope in Redis and lets the feed consume it through the
bounded, process-shared async client (Queue 271 / 277 primitives in
``app.utils.request_cache``). Design contract:

* **The feed treats the base as fresh only through the same 300s boundary it
  always used.** The category page's 2h storage TTL is retention, not permission
  to label a 301-second payload fresh. An older-but-bounded base is served as a
  truthfully-labeled ``last_good`` fallback.
* **A dyno restart alone never calls DataGolf.** After a restart Redis still
  holds the base published by the hourly category precompute, so the request
  path reads it (fresh or last-good) instead of rebuilding. The ONLY path that
  performs a live rebuild is a genuine Redis outage / empty-cache, and that
  rebuild is bounded and singleflight-owned.
* **One fill per process across feed response keys.** Two concurrent feed
  responses (e.g. ``discover limit=50`` and ``sports limit=200``) that both miss
  the base launch exactly ONE rebuild via the Queue 277 exact-owner lifecycle;
  the second coalesces onto it. Cancellation/failure removes only the exact
  owner and permits one clean replacement.
* **No user/session data in the shared payload.** The base carries only the
  tournament semantic payload (order/keys, golfer probabilities/ranks/movement,
  market IDs/sources, H2H/props, schedule/stale fields). Per-user tour filtering,
  personalization, scoring, headline/reason, marquee pinning, and final ranking
  all stay request-side in ``feed._score_golf_tournaments``.

The frozen offline contract is the C71 pack:
``backend/scripts/evals/cold_feed_equivalence.py`` (golf scenarios) +
``golf_base_cache_fixtures.json``. This module is the live implementation of the
same selection/ownership semantics; ``tests/test_golf_base_cache.py`` guards it.
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
GOLF_BASE_SCHEMA_VERSION = 1
GOLF_BASE_FRESH_KEY = "bainluck:golf_base:v1"
GOLF_BASE_LAST_GOOD_KEY = "bainluck:golf_base:v1:last_good"

# The feed freshness boundary — mirrors the historical ``_GOLF_CACHE_TTL`` so the
# 300s feed-golf freshness contract is preserved exactly. A payload older than
# this is NOT fresh (it is served, if at all, as bounded last-good).
GOLF_BASE_FRESH_SECONDS = _env_int("GOLF_BASE_FRESH_SECONDS", 300)
# The bounded last-good window: how stale a base may be and still be served as a
# truthfully-labeled fallback rather than forcing an inline rebuild. Defaults to
# the category page's 2h storage retention.
GOLF_BASE_LAST_GOOD_MAX_AGE_S = _env_int("GOLF_BASE_LAST_GOOD_MAX_AGE_S", 7200)

# Redis retention (TTL) of each key. The fresh key outlives a single freshness
# window so a restart finds a servable (if stale) base; the last-good key is
# retained longer as the durable floor.
GOLF_BASE_FRESH_TTL_S = _env_int("GOLF_BASE_FRESH_TTL_S", 7200)
GOLF_BASE_LAST_GOOD_TTL_S = _env_int("GOLF_BASE_LAST_GOOD_TTL_S", 86400)

# Singleflight owner key for the base FILL. Deliberately independent of any feed
# response cache key so distinct feed responses coalesce onto ONE rebuild.
GOLF_BASE_BUILD_KEY = "golf_base:fill"

# A rebuild (get_golf) is bounded well under the router cutoff. It only runs on a
# genuine Redis outage / empty cache, never on a plain restart.
GOLF_BASE_FILL_DEADLINE_MS = _env_int("GOLF_BASE_FILL_DEADLINE_MS", 12000)

# Process-local read throttle: how long a fetched envelope may satisfy requests
# before the process re-reads Redis. Freshness is ALWAYS re-derived from the
# envelope's ``generated_at`` on each hit (see ``_l0_lookup``), so this window
# never mislabels a stale base as fresh — it only bounds Redis round-trips.
GOLF_BASE_L0_TTL_S = _env_int("GOLF_BASE_L0_TTL_S", 60)

# Provenance labels reported alongside the tournaments so a miss/fallback is
# diagnosable.
PROV_FRESH = "fresh"
PROV_LAST_GOOD = "last_good"
PROV_INLINE = "inline"
PROV_UNAVAILABLE = "unavailable"

# Contract mirrors ``cold_feed_equivalence.golf_payload_valid``.
_FORBIDDEN_TOP_LEVEL = {"feed_tours", "personalized", "personalization", "final_rank"}
_FORBIDDEN_TOURNAMENT = {
    "score",
    "reason",
    "headline",
    "personalized",
    "final_rank",
    "_marquee_pin",
}
_REQUIRED_TOURNAMENT = {
    "key",
    "golfers",
    "market_ids",
    "market_sources",
    "h2h_matchups",
    "prop_markets",
    "schedule_status",
}


# --- Validation + normalization -----------------------------------------------
def payload_valid(payload: Any) -> bool:
    """Return True iff ``payload`` is a valid user-independent golf base.

    Mirrors the offline C71 oracle ``golf_payload_valid`` so the live selection
    rejects any payload that leaked user/feed state (forbidden top-level or
    per-tournament keys) or is missing a required tournament field.
    """
    if not isinstance(payload, dict):
        return False
    if _FORBIDDEN_TOP_LEVEL.intersection(payload):
        return False
    tournaments = payload.get("tournaments")
    if not isinstance(tournaments, list):
        return False
    for tournament in tournaments:
        if not isinstance(tournament, dict):
            return False
        if _FORBIDDEN_TOURNAMENT.intersection(tournament):
            return False
        if not _REQUIRED_TOURNAMENT.issubset(tournament):
            return False
    return True


def normalize_tournaments(tournaments: list[dict]) -> list[dict]:
    """Return the tournament list guaranteed base-shaped.

    ``get_golf`` only sets ``schedule_status``/``h2h_matchups`` when a schedule
    match / routed matchup exists, so those keys can be absent on some entries.
    The feed reads every one of these via ``.get()`` (absence == ``None``/empty),
    so defaulting them in is byte-for-byte semantic-preserving for the feed AND
    satisfies the required-keys contract. Any leaked forbidden key (defensive —
    ``get_golf`` never sets these) is stripped so the base can never carry
    request-side state.
    """
    normalized: list[dict] = []
    for t in tournaments:
        if not isinstance(t, dict):
            continue
        entry = dict(t)
        for forbidden in _FORBIDDEN_TOURNAMENT:
            entry.pop(forbidden, None)
        entry.setdefault("schedule_status", None)
        entry.setdefault("h2h_matchups", [])
        entry.setdefault("prop_markets", [])
        entry.setdefault("market_ids", entry.get("market_ids", []))
        entry.setdefault("market_sources", entry.get("market_sources", []))
        normalized.append(entry)
    return normalized


def build_envelope(now: datetime, tournaments: list[dict]) -> dict:
    """Wrap the tournament list in a freshness-tagged, versioned envelope."""
    return {
        "schema_version": GOLF_BASE_SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "tournaments": normalize_tournaments(tournaments or []),
    }


def _envelope_age_seconds(envelope: Any, now: datetime) -> Optional[float]:
    """Age of ``envelope`` in seconds, or None if it is unusable/malformed."""
    if not isinstance(envelope, dict):
        return None
    if envelope.get("schema_version") != GOLF_BASE_SCHEMA_VERSION:
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


def _usable(envelope: Any, now: datetime, max_age_s: float) -> bool:
    """True iff ``envelope`` is a valid base within ``[0, max_age_s]``."""
    age = _envelope_age_seconds(envelope, now)
    if age is None or age < 0 or age > max_age_s:
        return False
    return payload_valid(envelope)


# --- Process-local read throttle ----------------------------------------------
# One entry per process (the base is global — not per-user). Holds the last
# fetched envelope; each lookup re-derives freshness from ``generated_at`` so it
# can never outlive the 300s freshness contract.
_l0: dict[str, Any] = {"fetched_wall": 0.0, "envelope": None}


def _l0_lookup(now: datetime) -> Optional[tuple[list[dict], str]]:
    """Return (tournaments, provenance) from the process-local cache, if usable."""
    envelope = _l0.get("envelope")
    if envelope is None:
        return None
    if (time.time() - _l0.get("fetched_wall", 0.0)) >= GOLF_BASE_L0_TTL_S:
        return None  # throttle window elapsed — re-read Redis for a fresher base
    if _usable(envelope, now, GOLF_BASE_FRESH_SECONDS):
        return list(envelope["tournaments"]), PROV_FRESH
    if _usable(envelope, now, GOLF_BASE_LAST_GOOD_MAX_AGE_S):
        return list(envelope["tournaments"]), PROV_LAST_GOOD
    return None


def _l0_store(envelope: dict) -> None:
    _l0["envelope"] = envelope
    _l0["fetched_wall"] = time.time()


def _reset_l0_for_tests() -> None:
    _l0["envelope"] = None
    _l0["fetched_wall"] = 0.0


# --- Redis read/publish (bounded, shared client) ------------------------------
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


async def _read_key(client: Any, key: str, *, stages=None, stage_name: str) -> Optional[dict]:
    """Bounded GET of one base key; returns the decoded envelope or None.

    Never raises past a typed miss/timeout/error — a Redis stall degrades to
    ``None`` (fall through to the next tier) instead of hanging the request.
    """
    t0 = time.perf_counter()
    result = await _rc.bounded_redis_call(lambda: client.get(key))
    _record_stage(stages, stage_name, t0)
    if not result.is_ok:
        return None
    return _decode_envelope(result.value)


async def publish_envelope(envelope: dict, *, stages=None) -> None:
    """Publish the base envelope to both Redis keys via the shared client.

    Best-effort + bounded — a publish failure never propagates (the caller has
    already served/returned its payload). Both keys carry the same versioned
    envelope; they differ only in retention TTL.
    """
    payload = json.dumps(envelope, default=str)
    t0 = time.perf_counter()
    try:
        client = await _rc.get_shared_async_redis()
        await _rc.bounded_redis_call(
            lambda: client.set(GOLF_BASE_FRESH_KEY, payload, ex=GOLF_BASE_FRESH_TTL_S)
        )
        await _rc.bounded_redis_call(
            lambda: client.set(
                GOLF_BASE_LAST_GOOD_KEY, payload, ex=GOLF_BASE_LAST_GOOD_TTL_S
            )
        )
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - publish is best-effort
        logger.debug("golf base publish failed", exc_info=True)
    _record_stage(stages, "golf.base_publish", t0)


def publish_envelope_sync(rc: Any, envelope: dict) -> None:
    """Publish the base to both keys with a SYNC Redis client.

    Used by the category precompute task (``_precompute_golf``), which already
    holds a sync ``get_redis_client()``. Keeps the worker off the shared async
    client while writing the exact same key names + envelope shape the feed reads.
    """
    payload = json.dumps(envelope, default=str)
    rc.set(GOLF_BASE_FRESH_KEY, payload, ex=GOLF_BASE_FRESH_TTL_S)
    rc.set(GOLF_BASE_LAST_GOOD_KEY, payload, ex=GOLF_BASE_LAST_GOOD_TTL_S)


def _record_stage(stages, name: str, t0: float) -> None:
    if stages is None:
        return
    stages.append({"stage": name, "ms": round((time.perf_counter() - t0) * 1000, 2)})


# --- Rebuild (fill) + singleflight ownership ----------------------------------
async def _build_fresh_envelope(db, now: datetime, *, stages=None) -> dict:
    """Rebuild the base from source (the expensive DB + DataGolf path).

    Only reached on a genuine Redis outage / empty cache. Bounded by
    ``GOLF_BASE_FILL_DEADLINE_MS`` so it can never run to the router cutoff.
    """
    from app.routes.golf import get_golf

    t0 = time.perf_counter()
    response = await _rc.run_with_deadline(
        get_golf(db), deadline_ms=GOLF_BASE_FILL_DEADLINE_MS
    )
    _record_stage(stages, "golf.base_fill_build", t0)
    tournaments = response.get("tournaments", []) if isinstance(response, dict) else []
    return build_envelope(now, tournaments)


async def _singleflight_fill(db, now: datetime, *, stages=None) -> tuple[Optional[dict], str]:
    """Rebuild the base under the Queue 277 exact-owner lifecycle.

    Guarantees ONE fill per process across concurrent feed response keys: the
    leader builds and publishes; waiters coalesce onto its envelope. A
    dead/cancelled/failed leader resolves+removes only its own future (so it
    never poisons the slot).

    Single-owner invariant (Queue 280): a live leader is the sole owner. A
    waiter whose bounded wait times out NEVER displaces it or starts a second
    fill (that stampede duplicated the expensive DataGolf/DB pass); it returns a
    truthful ``unavailable`` and the feed simply skips golf this request. The
    slot self-heals for the next request once the leader resolves/clears it.
    """
    is_leader, fut = _rc.begin_build(GOLF_BASE_BUILD_KEY)
    if not is_leader:
        coalesced = None
        try:
            coalesced = await _rc.run_with_deadline(
                asyncio.shield(fut), deadline_ms=GOLF_BASE_FILL_DEADLINE_MS
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            coalesced = None
        if isinstance(coalesced, dict) and payload_valid(coalesced):
            return coalesced, PROV_INLINE
        # Leader still running (or produced nothing usable) within the bound —
        # fall back rather than duplicate its fill. Last-good tiers were already
        # exhausted before this inline tier, so the truthful terminal is empty.
        return None, PROV_UNAVAILABLE

    # --- Leader ownership guard: resolve + clear the slot on EVERY exit. ---
    try:
        envelope = await _build_fresh_envelope(db, now, stages=stages)
    except asyncio.CancelledError:
        _rc.finish_build(GOLF_BASE_BUILD_KEY, fut, exc=asyncio.CancelledError())
        raise
    except BaseException:  # provider/DB error — bounded, truthful fallback
        logger.warning("golf base inline fill failed", exc_info=True)
        _rc.finish_build(GOLF_BASE_BUILD_KEY, fut, result=None)
        return None, PROV_UNAVAILABLE

    _rc.finish_build(GOLF_BASE_BUILD_KEY, fut, result=envelope)
    # Publish for subsequent requests without delaying this response.
    _rc.schedule_background(publish_envelope(envelope))
    return envelope, PROV_INLINE


# --- Public entry point -------------------------------------------------------
async def get_golf_base(db, now: datetime, *, stages=None) -> tuple[list[dict], str]:
    """Return (tournaments, provenance) — the user-independent golf base.

    Selection order (each tier bounded, never blocking on an unbounded client):

    1. Process-local throttle hit (Redis round-trip avoided; freshness re-derived).
    2. Redis fresh key, age <= 300s -> ``fresh``.
    3. Redis fresh key, age <= last-good window -> ``last_good`` (truthfully stale).
    4. Redis last-good key, age <= window -> ``last_good``.
    5. Process-local request-cache last-good (survives a Redis outage) -> ``last_good``.
    6. Singleflight inline rebuild (Redis outage / empty cache ONLY) -> ``inline``.
    7. Nothing usable -> ``unavailable`` (empty golf; the feed simply skips golf).

    A plain dyno restart lands on tier 2/3/4 (Redis still holds the precomputed
    base) and therefore never calls DataGolf.
    """
    hit = _l0_lookup(now)
    if hit is not None:
        return hit

    fresh_env: Optional[dict] = None
    try:
        client = await _rc.get_shared_async_redis()
        fresh_env = await _read_key(
            client, GOLF_BASE_FRESH_KEY, stages=stages, stage_name="golf.base_read"
        )
        if _usable(fresh_env, now, GOLF_BASE_FRESH_SECONDS):
            _l0_store(fresh_env)
            _rc.remember_last_good("golf_base", fresh_env)
            return list(fresh_env["tournaments"]), PROV_FRESH

        last_good_env = None
        if _usable(fresh_env, now, GOLF_BASE_LAST_GOOD_MAX_AGE_S):
            last_good_env = fresh_env
        else:
            candidate = await _read_key(
                client,
                GOLF_BASE_LAST_GOOD_KEY,
                stages=stages,
                stage_name="golf.base_read_last_good",
            )
            if _usable(candidate, now, GOLF_BASE_LAST_GOOD_MAX_AGE_S):
                last_good_env = candidate

        if last_good_env is not None:
            _l0_store(last_good_env)
            _rc.remember_last_good("golf_base", last_good_env)
            return list(last_good_env["tournaments"]), PROV_LAST_GOOD
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("golf base redis read failed", exc_info=True)

    # Redis had nothing usable. Serve a process-local last-good if we have one
    # (covers a Redis outage on a warm process without touching DataGolf).
    recalled = _rc.recall_last_good(
        "golf_base", max_age_s=GOLF_BASE_LAST_GOOD_MAX_AGE_S
    )
    if _usable(recalled, now, GOLF_BASE_LAST_GOOD_MAX_AGE_S):
        return list(recalled["tournaments"]), PROV_LAST_GOOD

    # Genuine cold: bounded, singleflight inline rebuild.
    envelope, prov = await _singleflight_fill(db, now, stages=stages)
    if envelope is not None:
        _l0_store(envelope)
        _rc.remember_last_good("golf_base", envelope)
        return list(envelope["tournaments"]), prov
    return [], PROV_UNAVAILABLE
