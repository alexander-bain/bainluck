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

logger = logging.getLogger(__name__)

from app.routes import events, sports, health, futures, admin, auth, user, feed, market_moves, oscars, oscars_pool, golf, march_madness, playoffs, weather, economics, politics, entertainment, league_futures, predictions, og_image, teams, feedback, calibration, source_intelligence, notifications
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
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Bain Luck API",
    description="Convert sports betting odds into win probabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Response-Time", "X-Request-ID"],
)


CACHE_RULES: list[tuple[str, int]] = [
    ("/api/feed", 10),
    ("/api/playoffs/", 300),
    ("/api/sports", 120),
    ("/api/golf", 300),
    ("/api/weather", 300),
    ("/api/economics", 120),
    ("/api/politics", 120),
    ("/api/entertainment", 120),
    ("/api/categories", 120),
]


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

    if request.method == "GET" and response.status_code == 200:
        path = request.url.path
        if "/admin" not in path:
            for prefix, max_age in CACHE_RULES:
                if path.startswith(prefix):
                    response.headers["Cache-Control"] = f"public, max-age={max_age}, stale-while-revalidate=60"
                    break
            # Event detail: longer cache for completed events
            if path.startswith("/api/events/") and "/history" in path:
                response.headers["Cache-Control"] = "public, max-age=30"
    return response


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(sports.router, prefix="/api/sports", tags=["Sports"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(futures.router, prefix="/api/futures", tags=["Futures"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/me", tags=["User"])
app.include_router(user.shared_router, prefix="/api/shared", tags=["Shared"])
app.include_router(feed.router, prefix="/api/feed", tags=["Feed"])
app.include_router(market_moves.router, prefix="/api/market-moves", tags=["Market Moves"])
app.include_router(oscars.router, prefix="/api/oscars", tags=["Oscars"])
app.include_router(oscars_pool.router, prefix="/api/oscars", tags=["Oscars Pool"])
app.include_router(golf.router, prefix="/api/golf", tags=["Golf"])
app.include_router(march_madness.router, prefix="/api/march-madness", tags=["March Madness"])
app.include_router(playoffs.router, prefix="/api/playoffs", tags=["Playoffs"])
app.include_router(weather.router, prefix="/api/weather", tags=["Weather"])
app.include_router(economics.router, prefix="/api/economics", tags=["Economics"])
app.include_router(politics.router, prefix="/api/politics", tags=["Politics"])
app.include_router(entertainment.router, prefix="/api/entertainment", tags=["Entertainment"])
app.include_router(league_futures.router, prefix="/api/leagues", tags=["Leagues"])
app.include_router(teams.router, prefix="/api/teams", tags=["Teams"])
app.include_router(calibration.router, prefix="/api", tags=["Calibration"])
app.include_router(source_intelligence.router, prefix="/api", tags=["Source Intelligence"])
app.include_router(predictions.router)
app.include_router(feedback.router)
app.include_router(notifications.router)
app.include_router(og_image.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Bain Luck API",
        "version": "0.1.0",
        "docs": "/docs",
    }
