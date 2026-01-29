"""
OddsTracker API
Main FastAPI application entry point.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import events, sports, health
from app.services.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="OddsTracker API",
    description="Convert sports betting odds into win probabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
allowed_origins = [
    "http://localhost:3000",  # Next.js dev
    "http://127.0.0.1:3000",
    "https://odds.alexbain.com",
    "https://www.odds.alexbain.com",
    # Vercel preview/production URLs
    "https://odds-tracker.vercel.app",
    "https://odds-tracker-git-master-alexander-bains-projects.vercel.app",
]

# Add production frontend URL from environment
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

# Allow all Vercel preview deployments
allowed_origin_regex = r"https://odds-tracker.*\.vercel\.app"

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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "OddsTracker API",
        "version": "0.1.0",
        "docs": "/docs",
    }
