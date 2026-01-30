"""Health check endpoints."""

from fastapi import APIRouter, Query

from app.services.odds_api import OddsAPIService

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


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
