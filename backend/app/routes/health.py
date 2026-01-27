"""Health check endpoints."""

from fastapi import APIRouter

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
