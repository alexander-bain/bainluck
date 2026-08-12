"""Admin endpoints for Celery worker health, inspection, and task metrics."""


from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.routes.admin_utils import _check_admin_destructive, _check_admin_secret


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

    # #995 attempt-4: poll_kalshi SIGKILLs before recording any metric (no_data),
    # so this phase marker is the only way to see WHERE it died — it holds the
    # stage that was live when the worker was killed. Surface it here.
    poll_kalshi_phase = None
    kalshi_settled_phase = None
    creation_watchdog = None
    try:
        _r2 = get_redis_client()
        _pk = _r2.get("bainluck:poll_kalshi:phase")
        if _pk:
            poll_kalshi_phase = _pk.decode() if isinstance(_pk, bytes) else _pk
        # #969: same instrument-first marker for the CRITICAL kalshi_settled bust.
        _ks = _r2.get("bainluck:kalshi_settled:phase")
        if _ks:
            kalshi_settled_phase = _ks.decode() if isinstance(_ks, bytes) else _ks
        # #969 NEVER-AGAIN: surface the creates-freshness watchdog summary
        # (per-source last_created ages + any stuck poll phase). This is the
        # creates-specific signal the 28-day freeze needed — coarse "updated in
        # 24h" health stayed green throughout it.
        import json as _json
        _wd = _r2.get("bainluck:watchdog:summary")
        if _wd:
            creation_watchdog = _json.loads(
                _wd.decode() if isinstance(_wd, bytes) else _wd
            )
    except Exception:
        poll_kalshi_phase = None

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
        "poll_kalshi_phase": poll_kalshi_phase,
        "kalshi_settled_phase": kalshi_settled_phase,
        "creation_watchdog": creation_watchdog,
    }


def build_schedule_adherence(beat_schedule, metrics, label_map, deliveries=None):
    """Grade every beat entry's schedule adherence. Pure — no Redis, no celery.

    Split out from the route so the join logic is unit-testable against fixed
    inputs. The arguments are exactly the facts the question needs: what is
    SCHEDULED (the live beat schedule), what was RECORDED (the metrics), which
    recorded label belongs to which scheduled task (the map), and how many times
    each task was actually DELIVERED (LAT-P039).

    Deliveries are keyed by the celery name directly, so they need no label
    join — and that is the point, not a convenience. The label map is written
    from inside ``_tracked_run``, so the 30 beat tasks that never call it were
    unjoinable and therefore ungradeable forever: they made up 30 of the 34
    ``unmapped`` entries (#1716). A task with deliveries is now graded on them
    even when the label join finds nothing, so being invisible to the join no
    longer means being invisible to the surface.
    """
    from app.utils.schedule_adherence import adherence, beat_intervals, find_lapping

    intervals = beat_intervals(beat_schedule)
    by_label = {m.get("task"): m for m in metrics if m.get("task")}
    deliveries = deliveries or {}

    graded = {}
    unmapped = []
    for full_name, interval_s in sorted(intervals.items()):
        label = label_map.get(full_name)
        m = by_label.get(label) if label else None
        d = deliveries.get(full_name) or {}
        if not m and not d:
            # Honest third state. "No label recorded yet" is NOT "behind" and
            # NOT "healthy" — it is a beat entry the health surface cannot see,
            # which is a finding in its own right and is reported as one rather
            # than being dropped from the denominator.
            unmapped.append({
                "task": full_name,
                "interval_s": round(interval_s, 1),
                "reason": "no_metric_label_recorded" if not label
                          else "label_recorded_but_no_metrics",
            })
            continue
        # No metrics row at all means completions are UNKNOWN, not zero. Passing
        # 0 would be gotcha #53 committed by the fix for gotcha #53: an absent
        # observation rendered as an observed absence, and here it would make
        # every delivery-only task look like one that never finishes.
        terminals = None
        if m:
            terminals = (m.get("successes_24h", 0) + m.get("failures_24h", 0)
                         + m.get("incompletes_24h", 0))
        graded[full_name] = adherence(
            starts=(m or {}).get("starts_24h", 0),
            starts_window_s=(m or {}).get("starts_window_s"),
            interval_s=interval_s,
            terminals=terminals,
            durations_ms=(m or {}).get("recent_durations_ms") or [],
            deliveries=d.get("fires"),
            deliveries_window_s=d.get("window_s"),
            # LAT-P040 (#835): the duration sample's own span, so the p95 is not
            # read against `window_s` (which ages the starts counter and is up
            # to ~23x longer — measured on `poll_odds`, 2026-08-11).
            durations_window_s=(m or {}).get("recent_durations_window_s"),
            durations_saturated=(m or {}).get("recent_durations_saturated"),
        )

    lapping = find_lapping(graded)
    counts = {}
    for g in graded.values():
        counts[g["verdict"]] = counts.get(g["verdict"], 0) + 1
    return {
        "scheduled_tasks": len(intervals),
        "graded": len(graded),
        "verdict_counts": counts,
        "lapping": lapping,
        "unmapped": unmapped,
        "all": graded,
    }


@router.get("/celery/schedule-adherence")
async def celery_schedule_adherence(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Which scheduled tasks are NOT running as often as they are scheduled to.

    LAT-P022 (#1609). The queue-depth number that filed #1609 was a human
    noticing a symptom; by the time this lane measured it the depth had fallen
    from ~490 to ~35 while the underlying condition had not changed at all —
    `precompute_discover_candidate_base` completed ZERO runs in a measured
    6-minute window against ~3 scheduled, and read `health: healthy` throughout,
    because health here means "the last run that finished, finished" and says
    nothing about how many never got a slot.

    This endpoint answers the other question. It divides each task's recorded
    fire count by its own counter window to get a RATE, compares that against
    the interval derived from the live beat schedule, and separately checks
    whether p95 runtime has crossed the interval (the textbook lapping shape).
    Nothing here is transcribed: the intervals come from
    `celery_app.conf.beat_schedule` itself and the label join comes from what
    actually ran, so neither can drift from the system it grades.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app
    from app.tasks.redis_state import (
        get_all_task_deliveries,
        get_all_task_metrics,
        get_task_label_map,
    )

    return build_schedule_adherence(
        celery_app.conf.beat_schedule,
        get_all_task_metrics(),
        get_task_label_map(),
        get_all_task_deliveries(),
    )


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
    _check_admin_destructive(secret, request=request)
    from app.tasks import celery_app
    purged = celery_app.control.purge()
    return {"purged": purged}


@router.get("/celery-debug")
async def celery_debug(request: Request, secret: str = Query(None)):
    """Inspect Celery worker status and queue lengths."""
    _check_admin_secret(secret, request=request)
    from app.tasks import celery_app

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
        # #1197: bounded, retry-wrapped helper (broker_url == REDIS_URL on Heroku)
        # instead of a raw from_url with no timeout/keepalive/TLS-EOF retry.
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
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



#: Key families whose per-key suffix is an opaque id. Without folding these the
#: census reports one "class" per key, the top-N cut keeps only the biggest
#: individual keys, and a family that dominates memory in aggregate — celery's
#: result backend does exactly this — disappears from the ranking.
_REDIS_ID_SUFFIX_PREFIXES = (
    "celery-task-meta-",
    "_kombu.binding.",
    "unacked",
)


def _redis_key_class(key: str) -> str:
    """Fold a key into the family it belongs to, id suffixes and all."""
    for prefix in _REDIS_ID_SUFFIX_PREFIXES:
        if key.startswith(prefix):
            return f"{prefix}*"
    # Otherwise: first two colon segments, so `bainluck:calibration:x` and
    # `bainluck:calibration:y` roll up together.
    return ":".join(key.split(":")[:2]) or "(root)"


@router.get("/redis-census")
async def redis_census(
    request: Request,
    secret: str = Query(None),
    scan_limit: int = Query(20000, ge=100, le=200000),
    sample_per_class: int = Query(12, ge=1, le=50),
):
    """Bounded, read-only census of what is actually occupying Redis.

    Queue 300 Item 2 needs an evidence-backed answer to "would code-only
    controls reclaim enough, or does the plan have to grow?", and that question
    is unanswerable from ``used_memory`` alone — you need to know WHICH key
    classes hold the bytes. No rail existed for that, so this is it.

    Every part of it is deliberately bounded, because a diagnostic that can
    wedge the instance it is diagnosing is worse than no diagnostic:

    * ``SCAN`` with a cursor and a hard ``scan_limit`` ceiling — never
      ``KEYS``, which is O(N) and blocks the single-threaded server.
    * ``MEMORY USAGE`` is sampled (``sample_per_class`` keys per class), not
      called per key, and its own ``SAMPLES 0`` estimate is used for
      collections.
    * The client comes from ``get_redis_client()``, which carries the mandatory
      socket/connect timeouts (gotcha #39).

    Strictly read-only: no write, no delete, no ``FLUSH``, no config change.
    Sizing decisions belong to Alex; this endpoint only supplies the numbers.
    """
    _check_admin_secret(secret, request=request)

    from collections import defaultdict

    from app.tasks.redis_state import get_redis_client

    out: dict = {"scan_limit": scan_limit, "truncated": False}
    try:
        r = get_redis_client()
        info_mem = r.info("memory")
        info_stats = r.info("stats")
        info_clients = r.info("clients")
        out["memory"] = {
            "used_memory": info_mem.get("used_memory"),
            "used_memory_human": info_mem.get("used_memory_human"),
            "used_memory_peak_human": info_mem.get("used_memory_peak_human"),
            "maxmemory": info_mem.get("maxmemory"),
            "maxmemory_human": info_mem.get("maxmemory_human"),
            "maxmemory_policy": info_mem.get("maxmemory_policy"),
            "mem_fragmentation_ratio": info_mem.get("mem_fragmentation_ratio"),
        }
        maxmem = info_mem.get("maxmemory") or 0
        used = info_mem.get("used_memory") or 0
        out["memory"]["pct_of_maxmemory"] = (
            round(100.0 * used / maxmem, 2) if maxmem else None
        )
        # Eviction is the number that decides the argument: a high used_memory
        # on an LRU instance is normal; keys actually being EVICTED is data loss.
        out["eviction"] = {
            "evicted_keys": info_stats.get("evicted_keys"),
            "expired_keys": info_stats.get("expired_keys"),
            "keyspace_hits": info_stats.get("keyspace_hits"),
            "keyspace_misses": info_stats.get("keyspace_misses"),
        }
        out["clients"] = {
            "connected_clients": info_clients.get("connected_clients"),
            "blocked_clients": info_clients.get("blocked_clients"),
            "rejected_connections": info_stats.get("rejected_connections"),
        }
        out["dbsize"] = r.dbsize()

        # Queue 300R: a raw TTL is uninterpretable on its own — 3,000s remaining
        # means "20 minutes old" under a 1h `result_expires` and "23 hours old"
        # under Celery's 24h default. Report the configuration next to the
        # observation so the census stays self-describing across the retention
        # change, and so "Celery-result key count/age" is answerable from one
        # read instead of two.
        try:
            from app.tasks import celery_app as _celery_app
            from app.tasks.result_retention import (
                RESULT_CONSUMER_TASKS,
                beat_only_tasks,
            )

            out["celery_results"] = {
                "result_expires_s": _celery_app.conf.result_expires,
                "result_consumer_tasks": len(RESULT_CONSUMER_TASKS),
                "suppressed_beat_tasks": len(
                    beat_only_tasks(_celery_app.conf.beat_schedule)
                ),
            }
        except Exception as exc:  # noqa: BLE001 — the census must survive it
            out["celery_results"] = {"error": str(exc)[:200]}

        classes: dict = defaultdict(
            lambda: {"keys": 0, "sampled": 0, "sampled_bytes": 0, "no_ttl": 0, "ttls": []}
        )
        scanned = 0
        cursor = 0
        while True:
            cursor, batch = r.scan(cursor=cursor, count=500)
            for raw in batch:
                key = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                cls = _redis_key_class(key)
                cell = classes[cls]
                cell["keys"] += 1
                if cell["sampled"] < sample_per_class:
                    try:
                        size = r.memory_usage(key, samples=0)
                        if size:
                            cell["sampled_bytes"] += int(size)
                            cell["sampled"] += 1
                    except Exception:  # noqa: BLE001 — a sample is optional
                        pass
                    ttl = r.ttl(key)
                    if ttl is None or ttl < 0:
                        cell["no_ttl"] += 1
                    else:
                        cell["ttls"].append(int(ttl))
                scanned += 1
            if cursor == 0:
                break
            if scanned >= scan_limit:
                out["truncated"] = True
                break

        out["scanned"] = scanned
        expires_s = (out.get("celery_results") or {}).get("result_expires_s")
        summary = []
        for cls, cell in classes.items():
            avg = cell["sampled_bytes"] / cell["sampled"] if cell["sampled"] else 0
            row = {
                "class": cls,
                "keys": cell["keys"],
                "avg_sampled_bytes": int(avg),
                # Estimate, clearly labelled: avg of a small sample times the
                # key count. Good enough to rank classes, never precise.
                "est_total_bytes": int(avg * cell["keys"]),
                "sampled": cell["sampled"],
                "sampled_without_ttl": cell["no_ttl"],
                "min_ttl_s": min(cell["ttls"]) if cell["ttls"] else None,
                "max_ttl_s": max(cell["ttls"]) if cell["ttls"] else None,
            }
            # Age, for the one class whose TTL is set from a config we control.
            # A TTL LONGER than the configured expiry cannot have been written
            # under the current config — it is residue from a previous
            # `result_expires`, and subtracting it yields a negative "age".
            # So those keys are counted rather than aged, which also makes this
            # the read that shows the old 24h residue draining away.
            if cls == "celery-task-meta-*" and cell["ttls"] and expires_s:
                expires_s = int(expires_s)
                current = [t for t in cell["ttls"] if t <= expires_s]
                legacy = len(cell["ttls"]) - len(current)
                row["sampled_ttl_over_configured_expiry"] = legacy
                row["configured_expiry_s"] = expires_s
                if current:
                    # Oldest sampled key = the one with the least time left.
                    row["max_sampled_age_s"] = expires_s - min(current)
                    row["min_sampled_age_s"] = expires_s - max(current)
            summary.append(row)
        summary.sort(key=lambda c: -c["est_total_bytes"])
        out["classes"] = summary[:60]
        out["note"] = (
            "est_total_bytes is avg_sampled_bytes * keys — a ranking estimate, "
            "not a measurement. Read-only; no keys were written or removed."
        )
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:300]
    return out
