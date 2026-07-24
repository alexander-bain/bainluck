"""Precompute heavy admin health endpoints into Redis (L2-90 async-cache).

Two admin reads — ``/api/admin/audit/all`` and
``/api/admin/prediction-markets/link-rate`` — computed ~25s synchronously and
were intermittently 503ing at the 30s router limit under load (the same disease
``/api/calibration`` had). These tasks compute the payloads on the background
worker and cache them in Redis so the GET handlers serve instantly. The routes
still fall back to computing inline on a cold cache or ``?bust=1``, so nothing
depends on the task having run — the beat just keeps the cache warm.

Redis keys / TTL are shared with the routes:
- ``bainluck:admin:audit_all``        (ex=3600)
- ``bainluck:admin:link_rate``        (ex=3600)
- ``bainluck:admin:matured_linkage``  (ex=3600)  # Queue #220/221 Item 2
"""

import json
import logging

logger = logging.getLogger(__name__)

_ADMIN_HEALTH_CACHE_TTL = 3600  # 1h — generous so a few skipped beats never empty it


async def _precompute_admin_audit_all():
    """Compute the all-grids matching audit and cache it in Redis."""
    from app.routes.admin_data_quality import _compute_audit_all_grids
    from app.tasks.redis_state import get_redis_client

    payload = await _compute_audit_all_grids()
    rc = get_redis_client()
    rc.set(
        "bainluck:admin:audit_all",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    logger.info(
        "Cached admin audit/all in Redis (avg_score=%s)",
        payload.get("avg_score"),
    )
    return {"status": "ok", "avg_score": payload.get("avg_score")}


async def _precompute_admin_link_rate():
    """Compute the prediction-market link-rate and cache it in Redis."""
    from app.routes.admin_matching import _compute_link_rate
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        # Runs off the request path (soft_time_limit=120s), so give the compute
        # a generous per-query statement_timeout rather than the route's tight
        # 20s router-limit budget (Queue #250 Item 3c).
        payload = await _compute_link_rate(db, stmt_timeout_s=90)

    rc = get_redis_client()
    rc.set(
        "bainluck:admin:link_rate",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    overall = payload.get("overall", {})
    logger.info(
        "Cached admin link-rate in Redis (link_rate_pct=%s, total=%s)",
        overall.get("link_rate_pct"),
        overall.get("total_game_markets"),
    )
    return {"status": "ok", "link_rate_pct": overall.get("link_rate_pct")}


async def _precompute_admin_matured_linkage():
    """Compute the matured-linkage metric and cache it in Redis (Item 2)."""
    from app.routes.admin_matching import _compute_matured_linkage
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        payload = await _compute_matured_linkage(db)

    rc = get_redis_client()
    rc.set(
        "bainluck:admin:matured_linkage",
        json.dumps(payload),
        ex=_ADMIN_HEALTH_CACHE_TTL,
    )
    logger.info(
        "Cached admin matured-linkage in Redis (headline_pct=%s, phantom=%s, checkable=%s)",
        payload.get("headline_pct"),
        payload.get("phantom"),
        payload.get("checkable_pairs"),
    )
    return {"status": "ok", "headline_pct": payload.get("headline_pct")}
