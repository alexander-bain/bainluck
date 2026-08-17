"""Admin cohort-market-type ECE table — league×source×market_type sorted descending by ECE."""
import json
import time
from fastapi import APIRouter, Query, Request, BackgroundTasks
from fastapi import Depends
from fastapi.responses import JSONResponse
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_CACHE_KEY = "bainluck:cohort_market_type"
_CACHE_TTL = 86400

def _load_cached():
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        raw = rc.get(_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

@router.get("/admin/cohort-market-type")
async def cohort_market_type(
    request: Request,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    cached = _load_cached()
    if cached:
        return cached
    return JSONResponse(
        status_code=202,
        content={
            "status": "no cached table yet",
            "message": "POST to /api/admin/cohort-market-type/build to trigger a background build (runs in worker, ~90s), then GET again",
            "cache_key": _CACHE_KEY,
        },
    )

@router.post("/admin/cohort-market-type/build")
async def cohort_market_type_build(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    # Enqueue background build via Celery if available, else run in background task
    try:
        from app.tasks import celery_app
        celery_app.send_task("app.tasks.build_cohort_market_type")
        return {"status": "enqueued", "task": "app.tasks.build_cohort_market_type", "cache_key": _CACHE_KEY}
    except Exception as e:
        # Fallback: run in FastAPI background task (still hits 30s limit, but try)
        background_tasks.add_task(_build_and_cache)
        return {"status": "enqueued_background", "error": str(e)[:200]}

async def _build_and_cache():
    try:
        from scripts.evals.cohort_sweep import load_from_session, sweep
        from app.services.database import async_session_maker
        async with async_session_maker() as s:
            rows = await load_from_session(s)
        report = sweep(rows)
        by_ece = sorted([c for c in report["drill_down"] if c["sufficient"]], key=lambda c: c["ece"], reverse=True)
        payload = {
            "rows": report["rows"],
            "cohorts": report["cohorts"],
            "sufficient": len(by_ece),
            "minimum_cohort_n": report["minimum_cohort_n"],
            "by_ece": by_ece,
            "generated_at": time.time(),
        }
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        rc.set(_CACHE_KEY, json.dumps(payload, default=str), ex=_CACHE_TTL)
    except Exception as e:
        import traceback
        traceback.print_exc()

@router.get("/admin/cohort-market-type/full")
async def cohort_market_type_full(
    request: Request,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    cached = _load_cached()
    if cached:
        return cached
    return JSONResponse(status_code=202, content={"status": "no cached table yet"})
