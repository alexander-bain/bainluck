"""Health check endpoints."""

import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.services.odds_api import OddsAPIService

router = APIRouter()

_PROCESS_START = time.time()

# Which PROCESS answered — #2107.
#
# The bug that made this necessary was a poisoned module-global cache: a
# per-PROCESS fault, invisible to any check that only knows which release is
# deployed. Two things could not be measured while it was live:
#
#   1. **Coverage.** "Zero 500s" over a sampling window means nothing unless
#      you can show the samples reached every process. With one web dyno
#      today that is trivially true; the moment web scales, it stops being.
#   2. **Restarts.** A restart clears any process-global state, so a probe
#      that spans one silently resets its own horizon — the failure this
#      program has already been defeated by five times on the worker side.
#      `process_id` changes on restart even when `dyno` does not.
#
# `DYNO` is set by Heroku (`web.1`); absent locally, which is honest rather
# than fabricated. `process_id` is minted at import, so it is per-process even
# where several processes share one dyno name.
DYNO = os.getenv("DYNO") or None
PROCESS_ID = uuid.uuid4().hex[:12]

# Get git commit at startup (cached)
def _get_git_commit():
    """Get current git commit hash."""
    # First try environment variable (set during build)
    commit = os.getenv("GIT_COMMIT") or os.getenv("HEROKU_SLUG_COMMIT")
    if commit:
        return commit[:8]

    # Fallback: try git command (only works in dev)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "unknown"

GIT_COMMIT = _get_git_commit()


def _error_label(exc: Exception) -> str:
    """THE CLASS NAME, NEVER THE MESSAGE — on an endpoint that needs no auth.

    #6404 ruled this for `/api/health` and wrote the reason into this file:
    an exception string can carry the connection URL, and on Heroku that URL
    embeds the password. The rule was built on ONE of the two unauthenticated
    probes here. `/health/ready` — same file, same router, same open door —
    went on interpolating `f"error: {e}"` on three branches, and one of them
    is strictly worse than the Redis case #6404 was written about:

        `OddsAPIService.check_quota()` sends the key as a QUERY PARAMETER
        (`params={"apiKey": self.api_key}`) and calls `raise_for_status()`.
        httpx puts the full request URL in that exception's message, so
        `str(exc)` reads:

            Client error '401 Unauthorized' for url
            'https://api.the-odds-api.com/v4/sports/?apiKey=<the live key>'

        Verified by constructing the error, not recalled: the planted key is
        in `str(exc)`, and `TestTheMessageIsNeverPublished` asserts both that
        it is (so the guard is not vacuous) and that it never reaches the body.

    That is our most quota-constrained credential (5M/month) published on an
    open endpoint, on the failure path — the one nobody reads until it fires.
    The class name plus the branch it came from is the whole diagnostic and
    carries nothing.
    """
    return f"error: {type(exc).__name__}"


@router.get("/health")
async def health_check():
    """Basic health check with version info."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "commit": GIT_COMMIT,
        "features": ["sync_sports", "discover_events", "get_support"],
    }


@router.get("/api/health")
async def api_health_check():
    """Lightweight liveness check for uptime monitors. No auth required."""
    db_ok = True
    redis_ok = True

    try:
        from app.services.database import engine
        from sqlalchemy import text as _text
        async with engine.connect() as conn:
            await conn.execute(_text("SELECT 1"))
    except Exception:
        db_ok = False

    # 🔴 #6404 — A FALSE HERE USED TO NAME NOTHING, AND THE FLAP IS INTERMITTENT.
    #
    # Measured by integrator/int375 17:06–17:09Z on `355ca6dc`: 4 of 19 samples
    # `redis: false`, `db: true` throughout, and — the detail that makes it a
    # question rather than a sick dyno — a true→false flip on the SAME
    # `process_id` 21 s apart. A bare `except Exception` cannot tell any of these
    # apart, and they want opposite responses:
    #
    #   * `ConnectionError`  — a TLS handshake EOF on a fresh connection. This is
    #     #1197's documented churn, and `get_redis_client` mints a NEW client and
    #     a NEW pool on every call (275 call sites, no cache anywhere), so every
    #     probe is an independent handshake. Independent trials is exactly the
    #     shape one process flipping produces.
    #   * `TimeoutError`     — Redis answered too slowly, bounded at
    #     `_DEFAULT_REDIS_SOCKET_TIMEOUT`. `elapsed_ms` near the bound is the
    #     tell, and this one is a real degradation.
    #   * anything else      — a probe bug, and a `degraded` that does not mean
    #     degraded trains every lane to ignore the field.
    #
    # ⚠️ THE CLASS NAME, NEVER THE MESSAGE. `/api/health` is UNAUTHENTICATED, and
    # a redis-py exception string can carry the connection URL — which on Heroku
    # embeds the password. `str(exc)` here would publish a live credential to an
    # open endpoint on the one code path nobody reads until it fires. The class
    # name plus the elapsed time is the whole diagnostic and carries no secret.
    redis_error = None
    _redis_t0 = time.monotonic()
    try:
        from app.tasks.redis_state import get_redis_client
        get_redis_client().ping()
    except Exception as exc:
        redis_ok = False
        redis_error = type(exc).__name__
    redis_elapsed_ms = int((time.monotonic() - _redis_t0) * 1000)

    status = "ok" if (db_ok and redis_ok) else "degraded"
    code = 200 if (db_ok or redis_ok) else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "db": db_ok,
            "redis": redis_ok,
            # Additive. `redis` stays the bool every monitor already reads; this
            # says WHY it is what it is. Present on success too, so a healthy
            # probe's latency is a baseline the next flap can be read against
            # rather than a number with nothing to compare to.
            "redis_check": {
                "error": redis_error,
                "elapsed_ms": redis_elapsed_ms,
            },
            "commit": GIT_COMMIT,
            "uptime_seconds": int(time.time() - _PROCESS_START),
            "dyno": DYNO,
            "process_id": PROCESS_ID,
        },
    )


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check for Kubernetes/container orchestration.

    🔴 THIS ENDPOINT IS UNAUTHENTICATED — measured, not assumed: an
    `Authorization`-free GET answers 200 on production. So nothing in this body
    may carry a secret, and nothing in it may state a fact it cannot support.
    Both halves of that were being broken; see the two blocks below (#4196).
    """
    checks = {}
    all_ok = True

    # Check database connectivity
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = _error_label(e)
        all_ok = False

    # Check Redis connectivity
    try:
        from app.tasks.redis_state import get_redis_client
        _redis = get_redis_client()
        _redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = _error_label(e)
        all_ok = False

    # Last poll recency — #4196.
    #
    # THE FIVE KEYS THIS USED TO READ ARE WRITTEN BY NOTHING IN THIS TREE.
    # `last_poll:odds`, `last_poll:espn`, `last_poll:kalshi`, `last_poll:polymarket`
    # and `last_poll:statpal` have no writer at any call site; the only stamp
    # anything sets is odds polling's `bainluck:last_poll:{sport_key}` —
    # PREFIXED, and per SPORT rather than per source. So the block could only
    # ever return five nulls, and it did, on production, in the same response
    # whose `odds_api.updated_at` was eleven seconds old.
    #
    # A null here reads as "this source has never polled". Five of them, under
    # the word `ready`, is the #4196 failure exactly: a probe whose reading is
    # wrong in the reassuring direction is worse than no probe, because the one
    # that means it gets ignored too.
    #
    # So report the key space that IS written, and report only it. The four
    # sources nobody stamps are ABSENT, not null — absent is "we do not measure
    # this", null is "measured, never seen", and a readiness probe that cannot
    # tell those apart is how this bug was born. One MGET, not one GET per
    # sport: this is a liveness path, not a dashboard (`/api/admin/providers`
    # already serves the per-sport breakdown for anyone who wants it).
    #
    # The writer sets `ex=3600`, which is what makes a null here MEANINGFUL
    # rather than unknowable: it means no sport has been polled in an hour.
    try:
        from app.tasks.redis_state import get_redis_client
        from app.utils.sport_keys import SPORT_LEAGUE_MAP
        _redis = get_redis_client()
        _stamps = _redis.mget(
            [f"bainluck:last_poll:{sport_key}" for sport_key in sorted(SPORT_LEAGUE_MAP)]
        )
        _newest = None
        for _raw in _stamps or []:
            if not _raw:
                continue
            try:
                _ts = float(_raw.decode() if isinstance(_raw, bytes) else _raw)
            except (AttributeError, TypeError, ValueError):
                continue
            if _newest is None or _ts > _newest:
                _newest = _ts
        checks["last_polls"] = {
            "odds_api": (
                datetime.fromtimestamp(_newest, tz=timezone.utc).isoformat()
                if _newest is not None
                else None
            ),
        }
    except Exception:
        checks["last_polls"] = "unavailable"

    # Check Odds API quota (from Redis cache — avoids burning an API request)
    try:
        from app.tasks.redis_state import get_odds_api_quota
        quota = get_odds_api_quota()
        if quota.get("status") in ("unknown", "no_data", "error"):
            # Fallback to live check if Redis has no data
            service = OddsAPIService()
            quota_live = await service.check_quota()
            await service.close()
            checks["odds_api"] = {
                "status": "ok",
                "requests_remaining": quota_live.get("requests_remaining", "unknown"),
                "requests_used": quota_live.get("requests_used", "unknown"),
                "source": "live",
            }
        else:
            checks["odds_api"] = {
                "status": "ok" if quota["health"] != "critical" else "degraded",
                "requests_remaining": str(quota["remaining"]),
                "requests_used": str(quota["used"]),
                "health": quota["health"],
                "updated_at": quota["updated_at"],
                "source": "cached",
            }
    except Exception as e:
        # The branch the helper's docstring is about: this one can hold the key.
        checks["odds_api"] = _error_label(e)
        all_ok = False

    # Check queue lengths
    try:
        from app.tasks.redis_state import get_redis_client
        _r = get_redis_client()
        checks["queue_lengths"] = {
            "background": _r.llen("background") or 0,
            "realtime": _r.llen("realtime") or 0,
        }
    except Exception:
        checks["queue_lengths"] = "unavailable"

    return {
        "status": "ready" if all_ok else "degraded",
        "uptime_seconds": int(time.time() - _PROCESS_START),
        "checks": checks,
    }


@router.get("/health/api-test")
async def test_odds_api(
    sport: str = Query("basketball_nba", description="Sport key to test"),
):
    """
    Test endpoint to check raw Odds API response.

    Shows what markets are actually being returned from the API.
    Useful for diagnosing why spread/totals data might be missing.
    """
    try:
        service = OddsAPIService()
        events = await service.get_odds(sport)
        await service.close()

        # Analyze what markets are present
        market_summary = {}
        sample_event = None

        for event in events[:5]:  # Check first 5 events
            if sample_event is None:
                sample_event = {
                    "id": event["id"],
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                }

            for bookmaker in event.get("bookmakers", []):
                bk_name = bookmaker["key"]
                if bk_name not in market_summary:
                    market_summary[bk_name] = set()

                for market in bookmaker.get("markets", []):
                    market_summary[bk_name].add(market["key"])

        # Convert sets to lists for JSON serialization
        market_summary = {k: sorted(list(v)) for k, v in market_summary.items()}

        # Check if any bookmaker has spread/totals
        has_spreads = any("spreads" in markets for markets in market_summary.values())
        has_totals = any("totals" in markets for markets in market_summary.values())

        return {
            "status": "ok",
            "sport": sport,
            "events_count": len(events),
            "sample_event": sample_event,
            "markets_by_bookmaker": market_summary,
            "diagnosis": {
                "has_h2h": any("h2h" in markets for markets in market_summary.values()),
                "has_spreads": has_spreads,
                "has_totals": has_totals,
                "issue": None if (has_spreads and has_totals) else
                    "API is NOT returning spread/totals markets. Check API tier or subscription.",
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
