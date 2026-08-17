"""Admin cohort-market-type ECE table — league×source×market_type sorted descending by ECE."""
from fastapi import APIRouter, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db

router = APIRouter()

@router.get("/admin/cohort-market-type")
async def cohort_market_type(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    from scripts.evals.cohort_sweep import load_from_session, sweep
    rows = await load_from_session(db)
    report = sweep(rows)
    by_ece = sorted([c for c in report["drill_down"] if c["sufficient"]], key=lambda c: c["ece"], reverse=True)
    # Keep payload small: top 100 + summary
    return {
        "rows": report["rows"],
        "cohorts": report["cohorts"],
        "sufficient": len(by_ece),
        "minimum_cohort_n": report["minimum_cohort_n"],
        "by_ece": by_ece[:100],
        "by_ece_full_url": "use ?full=1 for all",
    }

@router.get("/admin/cohort-market-type/full")
async def cohort_market_type_full(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    _check_admin_secret(secret, request=request)
    from scripts.evals.cohort_sweep import load_from_session, sweep
    rows = await load_from_session(db)
    report = sweep(rows)
    by_ece = sorted([c for c in report["drill_down"] if c["sufficient"]], key=lambda c: c["ece"], reverse=True)
    return {"rows": report["rows"], "cohorts": report["cohorts"], "by_ece": by_ece}
