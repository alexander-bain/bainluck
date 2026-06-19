"""Admin endpoints for Celery worker health, inspection, and task metrics."""


from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.routes.admin_utils import _check_admin_secret


router = APIRouter()


@router.get("/celery/health")
async def celery_health(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check Celery worker health via heartbeat timestamp in Redis."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_redis_client

    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if not heartbeat:
            return {"status": "unknown", "message": "No heartbeat found — worker may not have started yet"}

        heartbeat_time = datetime.fromisoformat(heartbeat.decode())
        age_seconds = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()

        if age_seconds > 180:  # 3 minutes
            return {
                "status": "unhealthy",
                "last_heartbeat": heartbeat_time.isoformat(),
                "age_seconds": round(age_seconds),
                "message": "Heartbeat is stale — Celery worker may be down",
            }

        return {
            "status": "healthy",
            "last_heartbeat": heartbeat_time.isoformat(),
            "age_seconds": round(age_seconds),
        }
    except Exception as e:
        return {"status": "error", "message": f"Redis error: {str(e)}"}


@router.get("/celery/dashboard")
async def celery_dashboard(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Task-level success metrics dashboard.

    Shows success/failure rates, last run times, durations, and key output
    metrics for all tracked tasks. Detects degraded performance (not just
    crashes) — e.g., ESPN sync matching 0 events, odds polling returning
    empty results.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_all_task_metrics, get_redis_client

    # Get per-task metrics
    tasks = get_all_task_metrics()

    # Get Odds API quota (passive, from Redis cache)
    from app.tasks.redis_state import get_odds_api_quota
    odds_api_quota = get_odds_api_quota()

    # Get heartbeat status for overall worker health
    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if heartbeat:
            heartbeat_time = datetime.fromisoformat(heartbeat.decode())
            heartbeat_age = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
            worker_status = "healthy" if heartbeat_age < 180 else "unhealthy"
        else:
            heartbeat_age = None
            worker_status = "unknown"
    except Exception:
        heartbeat_age = None
        worker_status = "error"

    # #898: surface the backfill_winners per-phase timing so the
    # SoftTimeLimitExceeded culprit phase is observable here (the task dies
    # mid-phase before its end-of-run summary emits, and Heroku logs are not
    # readable from the executor sandbox). `running_phase` is the phase that was
    # in flight at the last write — i.e. the budget consumer when it timed out.
    backfill_phase_timing = None
    try:
        import json as _json
        _r = get_redis_client()
        _raw = _r.get("bainluck:backfill_phase_timing")
        if _raw:
            backfill_phase_timing = _json.loads(_raw)
    except Exception:
        backfill_phase_timing = None

    # Compute overall health
    critical_tasks = [t for t in tasks if t.get("health") == "critical"]
    degraded_tasks = [t for t in tasks if t.get("health") == "degraded"]

    if worker_status != "healthy":
        overall = "worker_down"
    elif critical_tasks:
        overall = "critical"
    elif degraded_tasks:
        overall = "degraded"
    elif not tasks:
        overall = "no_data"
    else:
        overall = "healthy"

    return {
        "overall_health": overall,
        "worker_status": worker_status,
        "worker_heartbeat_age_seconds": round(heartbeat_age) if heartbeat_age else None,
        "tracked_tasks": len(tasks),
        "critical_tasks": [t["task"] for t in critical_tasks],
        "degraded_tasks": [t["task"] for t in degraded_tasks],
        "tasks": tasks,
        "odds_api_quota": odds_api_quota,
        "backfill_phase_timing": backfill_phase_timing,
    }


@router.get("/celery/task-metrics/{task_name}")
async def get_task_metrics_endpoint(
    request: Request,
    task_name: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Get detailed metrics for a specific task."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_task_metrics
    return get_task_metrics(task_name)


@router.get("/celery/inspect")
async def celery_inspect(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Inspect Celery worker: registered tasks, active tasks, reserved queue."""
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app
    i = celery_app.control.inspect(timeout=5)
    registered = i.registered() or {}
    active = i.active() or {}
    reserved = i.reserved() or {}

    result = {}
    for worker_name in set(list(registered) + list(active) + list(reserved)):
        worker_tasks = registered.get(worker_name, [])
        taxonomy = [t for t in worker_tasks if "taxonomy" in t or "event_tag" in t]
        result[worker_name] = {
            "total_registered": len(worker_tasks),
            "taxonomy_tasks": taxonomy,
            "active": [
                {"name": t.get("name"), "id": t.get("id")}
                for t in active.get(worker_name, [])
            ],
            "reserved_count": len(reserved.get(worker_name, [])),
            "reserved_sample": [
                {"name": t.get("name"), "id": t.get("id")}
                for t in reserved.get(worker_name, [])[:10]
            ],
        }
    return result


@router.post("/celery-purge-background")
async def celery_purge_background(request: Request, secret: str = Query(None)):
    """Purge stale tasks from the background queue."""
    _check_admin_secret(secret, request=request)
    from app.tasks import celery_app
    purged = celery_app.control.purge()
    return {"purged": purged}


@router.get("/celery-debug")
async def celery_debug(request: Request, secret: str = Query(None)):
    """Inspect Celery worker status and queue lengths."""
    _check_admin_secret(secret, request=request)
    from app.tasks import celery_app
    import redis as redis_lib

    result = {}

    # Worker ping
    try:
        inspector = celery_app.control.inspect(timeout=5)
        result["ping"] = inspector.ping() or "no response"
        result["active"] = inspector.active() or "no response"
        result["registered"] = {
            k: len(v) for k, v in (inspector.registered() or {}).items()
        }
        result["stats"] = {
            k: {"total": v.get("total", {}), "pool": v.get("pool", {}).get("max-concurrency")}
            for k, v in (inspector.stats() or {}).items()
        }
    except Exception as e:
        result["inspect_error"] = str(e)

    # Queue lengths and task name distribution from Redis
    try:
        redis_url = celery_app.conf.broker_url
        import ssl as _ssl
        r = redis_lib.from_url(
            redis_url,
            ssl_cert_reqs=_ssl.CERT_NONE if redis_url.startswith("rediss") else None,
        )
        bg_len = r.llen("background")
        result["queue_lengths"] = {
            "background": bg_len,
            "realtime": r.llen("realtime"),
            "celery": r.llen("celery"),
        }
        # Sample first 20 tasks from background queue to see what's piled up
        if bg_len > 0:
            import json as _json
            sample = []
            for raw in r.lrange("background", 0, min(19, bg_len - 1)):
                try:
                    body = _json.loads(raw)
                    headers = body.get("headers", {})
                    sample.append(headers.get("task", "unknown"))
                except Exception:
                    sample.append("parse_error")
            # Count by task name
            from collections import Counter
            result["queue_sample"] = dict(Counter(sample).most_common(10))

        result["redis_info"] = {
            "used_memory_human": r.info("memory").get("used_memory_human"),
            "connected_clients": r.info("clients").get("connected_clients"),
        }
    except Exception as e:
        result["redis_error"] = str(e)

    return result

