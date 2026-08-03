"""
Bain Luck API
Main FastAPI application entry point.
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk

# ---------------------------------------------------------------------------
# Structured JSON logging for production (Heroku)
# ---------------------------------------------------------------------------
if os.getenv("DYNO"):
    from pythonjsonlogger import jsonlogger

    _json_handler = logging.StreamHandler()
    _json_handler.setFormatter(jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    logging.root.handlers = [_json_handler]
    logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

from app.routes import events, sports, health, futures, admin, admin_analytics, admin_backfill_linkage, admin_backfill_odds, admin_judgments, admin_llm_diagnosis, admin_source_health, admin_feed_config, admin_label_pass, admin_team_clusters, admin_cockpit, admin_file_issue, auth, user, feed, market_moves, oscars, oscars_pool, golf, event, hub, march_madness, playoffs, weather, economics, politics, entertainment, league_futures, predictions, og_image, teams, prop_families, feedback, calibration, source_intelligence, notifications, challenges, unsubscribe
from app.services.database import init_db

# Initialize Sentry error tracking
# Set SENTRY_DSN env var in Heroku to enable
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    def _before_send(event, hint):
        exc_info = hint.get("exc_info")
        if exc_info:
            exc_type = exc_info[0]
            exc_name = exc_type.__name__ if exc_type else ""
            if exc_name in (
                "WorkerLost", "Terminated", "TimeLimitExceeded",
                "PendingRollbackError", "InvalidRequestError",
            ):
                return None
            if exc_name == "ConnectionError" and "redis" in str(exc_info[1]).lower():
                return None
        return event

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("HEROKU_SLUG_COMMIT"),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
        before_send=_before_send,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    await init_db()
    # Queue 271 / #1197: warm the process-shared async Redis client so the feed +
    # calibration request paths reuse ONE pool instead of constructing/closing a
    # pool per request (the churn that amplifies the Heroku Redis TLS flakiness).
    try:
        from app.utils.request_cache import get_shared_async_redis

        await get_shared_async_redis()
    except Exception:  # pragma: no cover - never block startup on Redis
        logger.debug("shared async redis warm-up skipped", exc_info=True)
    yield
    # Shutdown
    try:
        from app.utils.request_cache import close_shared_async_redis

        await close_shared_async_redis()
    except Exception:  # pragma: no cover - shutdown best-effort
        logger.debug("shared async redis close skipped", exc_info=True)


app = FastAPI(
    title="Bain Luck API",
    description="Convert sports betting odds into win probabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
#
# Queue 302 (#1525 Shape C): CORSMiddleware MUST be the OUTERMOST middleware so
# that EVERY response — including short-circuit responses produced by inner
# middleware that never reach the route (a RateLimitMiddleware 429, an auth 401,
# an unhandled 500) — passes back out through the CORS send-wrapper and receives
# the `Access-Control-Allow-Origin` / `Access-Control-Expose-Headers` a browser
# needs. When CORS was added FIRST (innermost) a rate-limit 429 emitted OUTSIDE
# it carried no CORS headers, so the browser reported an opaque `ERR_FAILED`
# ("Failed to load feed") and JavaScript could not read the status or
# `Retry-After` (#1525 Shape C — distinct from Shape A client abort / Shape B
# RSC prefetch abort, which are client-owned). Outermost placement also means
# preflight OPTIONS are answered by CORS before RateLimitMiddleware runs, so a
# preflight no longer consumes the request's rate budget.
#
# Starlette applies middleware from LAST-added (outermost) to first-added
# (innermost), so the actual `add_middleware(CORSMiddleware, ...)` call lives
# below, AFTER every other middleware registration — see the CORS block near the
# end of this middleware section. The origin allowlist / regex / expose-headers
# used there are defined here.
allowed_origins = [
    "http://localhost:3000",  # Next.js dev
    "http://127.0.0.1:3000",
    "https://bainluck.com",
    "https://www.bainluck.com",
    # Vercel preview/production URLs
    "https://bainluck.vercel.app",
]

# Add production frontend URL from environment
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

# Allow all Vercel preview deployments
allowed_origin_regex = r"https://bainluck.*\.vercel\.app"


# ---------------------------------------------------------------------------
# Rate limiting (limits library + Redis)
# ---------------------------------------------------------------------------
from app.utils.rate_limit import RateLimitMiddleware
from app.middleware.latency import LatencyMiddleware

app.add_middleware(RateLimitMiddleware)
app.add_middleware(LatencyMiddleware)


# C30 / Queue #264: cache-isolation policy (CACHE_RULES + the identity-aware
# rewrite) lives in app.utils.http_cache_policy so the middleware and the
# two-principal contract tests share one decision. Re-exported here for any
# caller/test that imports it from app.main.
from app.utils.http_cache_policy import CACHE_RULES, apply_cache_policy  # noqa: E402,F401


@app.middleware("http")
async def request_timing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"
    if duration_ms > 1000 and "/admin" not in request.url.path:
        logger.warning("SLOW %s %s [%s] %dms", request.method, request.url.path, request_id, duration_ms)
    elif duration_ms > 500 and "/admin" not in request.url.path:
        logger.info("MODERATE %s %s [%s] %dms", request.method, request.url.path, request_id, duration_ms)

    # Authentication and identity ALWAYS win over latency caching. Protected /
    # personalized / identity-bearing responses become private+no-store; route
    # directives are preserved; anonymous public routes keep their TTLs.
    apply_cache_policy(request, response)
    return response


# ---------------------------------------------------------------------------
# CORS (registered LAST so it is the OUTERMOST middleware) — see the CORS
# configuration comment near the top of this section for why. This wraps
# RateLimitMiddleware, LatencyMiddleware, and request_timing so that every
# response, including an inner-middleware short-circuit like a 429, is CORS-valid
# for allowed origins (#1525 Shape C / Queue 302). Disallowed / missing /
# malformed origins are still NOT reflected — CORSMiddleware's own allowlist +
# regex are unchanged; credentials/origin-reflection rules are unchanged.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # L2-189: expose feed timing/cache headers so the browser can read them
    # cross-origin (bainluck.com → api.bainluck.com). CORS hides any
    # non-safelisted response header unless it is listed here; these are set
    # per-request by routes/feed.py (_set_feed_timing_header /
    # _set_feed_cache_status / _finalize_feed_response) and power browser-visible
    # latency telemetry.
    # Queue 275/277 (#1475): X-Feed-Stages / X-Feed-Counts / X-Feed-Count-Scope /
    # X-Feed-Singleflight are the identity-free stage/coverage/scope/singleflight
    # diagnostics emitted on EVERY feed return path; expose them so a browser
    # field debugger can read all feed/request headers cross-origin.
    # Queue 281 (#1475): X-Feed-Golf-Provenance is the one bounded, allowlisted
    # golf-base publisher signal (fresh/last_good/inline/unavailable) — identity-
    # free, so Ops can positively verify the shared golf base cross-origin.
    expose_headers=[
        "X-Response-Time",
        "X-Request-ID",
        "X-Feed-Elapsed-Ms",
        "X-Feed-Cache",
        "X-Feed-Stages",
        "X-Feed-Counts",
        "X-Feed-Count-Scope",
        "X-Feed-Singleflight",
        "X-Feed-Golf-Provenance",
    ],
)


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(sports.router, prefix="/api/sports", tags=["Sports"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(futures.router, prefix="/api/futures", tags=["Futures"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(admin_analytics.router, prefix="/api/admin", tags=["Admin Analytics"])
app.include_router(admin_backfill_linkage.router, prefix="/api", tags=["Admin Linkage"])
app.include_router(admin_backfill_odds.router, prefix="/api", tags=["Admin Sparsity"])
app.include_router(admin_judgments.router, prefix="/api", tags=["Admin Judgments"])
app.include_router(admin_llm_diagnosis.router, prefix="/api", tags=["Admin LLM"])
app.include_router(admin_source_health.router, prefix="/api", tags=["Admin Source Health"])
app.include_router(admin_feed_config.router, prefix="/api/admin", tags=["Admin Feed Config"])
app.include_router(admin_label_pass.router, prefix="/api/admin", tags=["Admin Label Pass"])
app.include_router(admin_team_clusters.router, prefix="/api/admin", tags=["Admin Team Clusters"])
app.include_router(admin_cockpit.router, prefix="/api", tags=["Admin Cockpit"])
app.include_router(admin_file_issue.router, prefix="/api", tags=["Admin File Issue"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/me", tags=["User"])
app.include_router(user.shared_router, prefix="/api/shared", tags=["Shared"])
app.include_router(feed.router, prefix="/api/feed", tags=["Feed"])
app.include_router(market_moves.router, prefix="/api/market-moves", tags=["Market Moves"])
app.include_router(oscars.router, prefix="/api/oscars", tags=["Oscars"])
app.include_router(oscars_pool.router, prefix="/api/oscars", tags=["Oscars Pool"])
app.include_router(golf.router, prefix="/api/golf", tags=["Golf"])
app.include_router(event.router, prefix="/api/event", tags=["Event Concept"])
app.include_router(hub.router, prefix="/api/hub", tags=["Competition Hub"])
app.include_router(march_madness.router, prefix="/api/march-madness", tags=["March Madness"])
app.include_router(playoffs.router, prefix="/api/playoffs", tags=["Playoffs"])
app.include_router(weather.router, prefix="/api/weather", tags=["Weather"])
app.include_router(economics.router, prefix="/api/economics", tags=["Economics"])
app.include_router(politics.router, prefix="/api/politics", tags=["Politics"])
app.include_router(entertainment.router, prefix="/api/entertainment", tags=["Entertainment"])
app.include_router(league_futures.router, prefix="/api/leagues", tags=["Leagues"])
app.include_router(teams.router, prefix="/api/teams", tags=["Teams"])
app.include_router(prop_families.router, prefix="/api/teams", tags=["Prop Families"])
app.include_router(calibration.router, prefix="/api", tags=["Calibration"])
app.include_router(source_intelligence.router, prefix="/api", tags=["Source Intelligence"])
app.include_router(predictions.router)
app.include_router(feedback.router)
app.include_router(notifications.router)
app.include_router(challenges.router, prefix="/api/challenges", tags=["Challenges"])
app.include_router(unsubscribe.router)
app.include_router(og_image.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Bain Luck API",
        "version": "0.1.0",
        "docs": "/docs",
    }
