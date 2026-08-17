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

def _load_debug():
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        raw = rc.get(_CACHE_KEY + ":debug")
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
    debug = _load_debug()
    return JSONResponse(
        status_code=202,
        content={
            "status": "no cached table yet",
            "message": "POST to /api/admin/cohort-market-type/build to trigger a background build (runs in worker, ~90s), then GET again. If still empty after 3m, check debug or try /light",
            "cache_key": _CACHE_KEY,
            "debug": debug,
        },
    )

@router.get("/admin/cohort-market-type/light")
async def cohort_market_type_light(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Lightweight approximation: source×market_type×league ECE without full dedup.
    Runs in <10s on web, so it can be served synchronously. Useful to test
    your hypothesis immediately while the canonical build completes."""
    _check_admin_secret(secret, request=request)
    from sqlalchemy import text
    # Direct scan of resolved outcomes with usable prob, no virtual-market/field logic
    rows = (await db.execute(text("""
        SELECT fm.source, COALESCE(fm.llm_sport_category,'uncategorized') as league,
               COALESCE(fm.market_type,'unknown') as market_type,
               COALESCE(fo.calibration_probability, fo.opening_probability) as prob,
               fo.is_winner
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id=fo.market_id
        WHERE fm.status='resolved'
          AND COALESCE(fo.calibration_probability, fo.opening_probability) >0
          AND COALESCE(fo.calibration_probability, fo.opening_probability) <1
          AND fo.opening_probability IS NOT NULL
          AND fo.is_winner IS NOT NULL
        LIMIT 200000
    """))).all()
    # Compute ECE per cohort in Python (10 bins, n-weighted)
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r.source, r.league, r.market_type)].append((float(r.prob), int(r.is_winner)))
    out=[]
    for (src,league,mt), lst in grouped.items():
        n=len(lst)
        if n<30:
            continue
        # 10 bins
        bins=[[] for _ in range(10)]
        for p,a in lst:
            bins[min(int(p*10),9)].append((p,a))
        total_ece=0.0
        for b in bins:
            if not b: continue
            avg_p=sum(p for p,_ in b)/len(b)
            avg_a=sum(a for _,a in b)/len(b)
            total_ece+= len(b)/n * abs(avg_p-avg_a)
        ece= round(total_ece*100,2)
        avg_p=sum(p for p,_ in lst)/n
        avg_a=sum(a for _,a in lst)/n
        out.append({"source":src,"league_category":league,"market_type":mt,"n":n,"ece":ece,"pred":round(avg_p,3),"actual":round(avg_a,3),"gap_pp":round((avg_p-avg_a)*100,2)})
    out=sorted(out, key=lambda x: x["ece"], reverse=True)
    return {"rows_scanned": len(rows), "cohorts": len(grouped), "sufficient": len(out), "by_ece": out[:100], "note": "light approximation without dedup/field-normalization; canonical heavy build is more accurate"}

@router.get("/admin/cohort-market-type/debug")
async def cohort_market_type_debug(
    request: Request,
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    return {"cached": _load_cached() is not None, "debug": _load_debug()}

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
        celery_app.send_task("app.tasks.build_cohort_market_type", queue="heavy")
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
