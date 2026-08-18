import json, time, logging
from app.tasks import celery_app
from app.tasks.base import run_async

logger = logging.getLogger(__name__)
_CACHE_KEY = "bainluck:cohort_market_type"
_CACHE_TTL = 86400

@celery_app.task(bind=True, name="app.tasks.build_cohort_market_type", soft_time_limit=600, time_limit=660, queue="heavy")
def build_cohort_market_type(self):
    return run_async(_build())

async def _build():
    from app.tasks.redis_state import get_redis_client
    rc = get_redis_client()
    try:
        from scripts.evals.cohort_sweep import load_from_session, sweep, sweep_with_bands, sweep_weekly
        from app.services.database import async_session_maker
        async with async_session_maker() as s:
            rows = await load_from_session(s)
        report = sweep(rows)
        by_ece = sorted([c for c in report["drill_down"] if c["sufficient"]], key=lambda c: c["ece"], reverse=True)
        # 4th axis: probability-band
        band_report = sweep_with_bands(rows)
        # Time dimension: weekly for last 6 weeks (uses resolution_week on rows)
        weekly_report = sweep_weekly(rows, weeks=6)
        # Monday scoreboard: per-cohort weekly ECE trend (last 6 weeks)
        payload = {
            "rows": report["rows"],
            "cohorts": report["cohorts"],
            "sufficient": len(by_ece),
            "minimum_cohort_n": report["minimum_cohort_n"],
            "by_ece": by_ece,
            "by_band": band_report["drill_down"],
            "by_band_worst": band_report["worst_50"],
            "weekly": weekly_report["weekly"],
            "weekly_by_cohort": weekly_report["by_cohort"],
            "generated_at": time.time(),
        }
        rc.set(_CACHE_KEY, json.dumps(payload, default=str), ex=_CACHE_TTL)
        logger.info("cohort_market_type built: %d rows %d cohorts %d sufficient, bands %d weekly %d", report["rows"], report["cohorts"], len(by_ece), len(band_report["drill_down"]), len(weekly_report["weekly"]))
        return {"rows": report["rows"], "sufficient": len(by_ece), "bands": len(band_report["drill_down"]), "weekly": len(weekly_report["weekly"])}
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        rc.set(_CACHE_KEY+":debug", json.dumps({"error": str(e)[:500], "trace": err[-4000:], "at": time.time()}), ex=3600)
        logger.exception("cohort_market_type build failed")
        raise
