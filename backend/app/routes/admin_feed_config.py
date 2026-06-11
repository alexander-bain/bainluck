"""Admin endpoint for feed experiment/config state.

Returns current Redis-backed feed flags so experiment conditions
are provable in audit reports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.routes.admin_utils import _check_admin_secret

router = APIRouter()


@router.get("/feed-config")
async def get_feed_config(request: Request, secret: str = Query(None)):
    """Return current feed experiment state from Redis."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()

    def _get(key: str, default: str = "") -> str:
        val = r.get(key)
        if val is None:
            return default
        return val.decode() if isinstance(val, bytes) else str(val)

    return {
        "interestingness_blend_weight": _get("interestingness:blend_weight", "0.2"),
        "snippet_v2_enabled": _get("snippet_v2:enabled", "false"),
        "cold_start_boost": _get("cold_start:boost_factor", "2.0"),
    }


@router.post("/feed-config")
async def set_feed_config(
    request: Request,
    secret: str = Query(None),
    key: str = Query(..., description="Redis key suffix"),
    value: str = Query(..., description="Value to set"),
):
    """Set a feed config Redis key. Admin-only."""
    _check_admin_secret(secret, request=request)

    ALLOWED_KEYS = {
        "interestingness:blend_weight",
        "snippet_v2:enabled",
        "cold_start:boost_factor",
    }
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Key not in allowed set: {ALLOWED_KEYS}")

    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    r.set(key, value)

    return {"key": key, "value": value, "status": "set"}
