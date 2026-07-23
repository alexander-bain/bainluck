"""Admin repair rail — REPAIRS AS ENDPOINTS, never incantations (Queue #247 Item 5).

Three days of failed detached one-offs (#1220/#1229/#1230) proved the gotcha-#48
class is a pattern, not bad luck: a heroku one-off dyno silently no-ops in the
sandbox, `cd backend` no-ops under PROJECT_PATH=backend, ANY(:ids)/UPDATE…FROM roll
back with no readable stdout, and the only way to know if a repair ran is a
follow-up db-query. This rail replaces the incantation with a single call that is
**executable AND self-verifying**: every repair runs inside the web dyno on a
transactional session and RETURNS its own before/after census in the response body.

    POST /api/admin/repairs/{name}?apply=false   # dry-run: census + plan, no writes
    POST /api/admin/repairs/{name}?apply=true    # commit + return after-census

    name ∈ { season-series | inverted-events | tt-retag | team-identity-merge }

Auth: Bearer $ADMIN_TOKEN (or ?secret=). Dry-run is the default — you must pass
apply=true to write. Each repair's core is a session-taking ``repair()``/
``run_*`` shared with its committed CLI script, so the endpoint and the script can
never drift.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db_rw
from app.routes.admin_utils import _check_admin_secret

router = APIRouter()

# name → (module path, callable name). Each callable is ``async fn(session, apply)``.
_REPAIRS = {
    "season-series": ("scripts.repair_season_series_mislinks", "repair"),
    "inverted-events": ("scripts.repair_inverted_completed_at", "repair"),
    "tt-retag": ("scripts.retag_table_tennis", "repair"),
    "team-identity-merge": ("app.utils.team_merge", "run_team_identity_merge"),
}


@router.post("/repairs/{name}")
async def run_repair(
    name: str,
    request: Request,
    secret: str = Query(None),
    apply: bool = Query(False, description="False (default) = dry-run census only; True = commit"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Run a committed data repair and return its before/after census.

    Dry-run by default. See module docstring for the repair catalog.
    """
    _check_admin_secret(secret, request=request)

    if name not in _REPAIRS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown repair '{name}'. Available: {sorted(_REPAIRS)}",
        )

    module_path, fn_name = _REPAIRS[name]
    import importlib

    module = importlib.import_module(module_path)
    fn = getattr(module, fn_name)

    try:
        result = await fn(db, apply)
    except Exception as e:
        # Never leave a half-applied repair committed on an error path.
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Repair '{name}' failed: {e}")

    return {"repair": name, "apply": apply, "result": result}


@router.get("/repairs")
async def list_repairs(request: Request, secret: str = Query(None)):
    """List the available repairs (discovery)."""
    _check_admin_secret(secret, request=request)
    return {"repairs": sorted(_REPAIRS)}


@router.post("/repairs/ensure-indexes")
async def ensure_indexes(
    request: Request,
    secret: str = Query(None),
    wait: bool = Query(False, description="True runs inline (may hit the 30s HTTP wall); default queues a Celery task"),
):
    """#1197: build the missing team-route event indexes (home/away team_id + name)
    CONCURRENTLY. Queues a Celery worker task by default (CONCURRENTLY on events can
    exceed the 30s HTTP timeout); pass wait=true to run inline and get the per-index
    result. Idempotent (IF NOT EXISTS)."""
    _check_admin_secret(secret, request=request)

    if wait:
        from app.utils.ensure_indexes import ensure_perf_indexes
        return {"indexes": await ensure_perf_indexes()}

    from app.tasks import ensure_perf_indexes as task
    from app.utils.ensure_indexes import PERF_INDEXES

    r = task.delay()
    return {
        "status": "queued",
        "task_id": r.id,
        "building": [n for n, _ in PERF_INDEXES],
        "note": "CONCURRENTLY in the worker; re-measure warm team-route latency in ~1-2 min",
    }
