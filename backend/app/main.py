"""
Bain Luck API
Main FastAPI application entry point.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk

from app.routes import events, sports, health, futures, admin, auth, user, feed, market_moves, oscars, oscars_pool, golf, march_madness, playoffs, wrestlemania, weather
from app.services.database import init_db

# Initialize Sentry error tracking
# Set SENTRY_DSN env var in Heroku to enable
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=0.1,  # 10% of requests for performance monitoring
        profiles_sample_rate=0.1,
        send_default_pii=False,
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
)

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
app.include_router(wrestlemania.router, prefix="/api/wrestlemania", tags=["WrestleMania"])
app.include_router(weather.router, prefix="/api/weather", tags=["Weather"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Bain Luck API",
        "version": "0.1.0",
        "docs": "/docs",
    }
