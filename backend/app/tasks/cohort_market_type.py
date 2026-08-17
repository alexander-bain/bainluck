import json, time, logging
from app.tasks import celery_app
from app.tasks.base import run_async

logger = logging.getLogger(__name__)
_CACHE_KEY = "bainluck:cohort_market_type"
_CACHE_TTL = 86400

@celery_app.task(bind=True, name="app.tasks.build_cohort_market_type", soft_time_limit=600, time_limit=660)
def build_cohort_market_type(self):
    return run_async(_build())

async def _build():
    from scripts.evals.cohort_sweep import load_from_session, sweep
    from app.services.database import async_session_maker
    from app.tasks.redis_state import get_redis_client
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
    rc = get_redis_client()
    rc.set(_CACHE_KEY, json.dumps(payload, default=str), ex=_CACHE_TTL)
    logger.info("cohort_market_type built: %d rows %d cohorts %d sufficient", report["rows"], report["cohorts"], len(by_ece))
    return {"rows": report["rows"], "sufficient": len(by_ece)}
