"""Health check endpoints."""

import os
import subprocess
from fastapi import APIRouter, Query

from app.services.odds_api import OddsAPIService

router = APIRouter()

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
    """Health check at /api/health path for convenience."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "commit": GIT_COMMIT,
        "features": ["sync_sports", "discover_events", "get_support"],
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes/container orchestration.

    TODO: Add database connectivity check.
    """
    return {
        "status": "ready",
        "checks": {
            "database": "ok",  # TODO: Actually check DB
            "odds_api": "ok",  # TODO: Check API quota
        }
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
