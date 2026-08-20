"""Admin endpoints for Celery worker health, inspection, and task metrics."""


import time
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


def _stamp_ages_s(metric, now_epoch):
    """``(newest_terminal_age_s, newest_start_age_s)`` from one metrics row.

    LAT-P071. The stamp arm needs AGES, and only a caller with a clock can turn
    the hash's ISO strings into them — which is why this lives here and not in
    the pure grader.

    A stamp in the FUTURE returns ``None`` rather than a negative age. Ahead-drift
    is a real failure mode in this tree (ruling 008 names two lane-lock incidents
    caused by it), and a negative age would sail through every ``age <= limit``
    comparison below as the freshest possible reading — a clock-skewed stamp
    would certify a dead beat as healthy. Unknown is the safe answer; it grades
    ``unmeasurable``, which is visible, instead of ``on_schedule``, which is not.
    """
    from app.tasks.redis_state import _parse_iso, _TERMINAL_STAMP_FIELDS

    def _age(value):
        epoch = _parse_iso(value)
        if epoch is None:
            return None
        age = now_epoch - epoch
        return age if age >= 0 else None

    terminals = [a for a in (_age(metric.get(f)) for f in _TERMINAL_STAMP_FIELDS)
                 if a is not None]
    return (min(terminals) if terminals else None,
            _age(metric.get("last_started_at")))


def build_schedule_adherence(
    beat_schedule, metrics, label_map, deliveries=None, now_epoch=None
):
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
    import time as _time

    from app.tasks.redis_state import WINDOW_COUNTER_TTL
    from app.utils.schedule_adherence import adherence, beat_intervals, find_lapping

    now_epoch = _time.time() if now_epoch is None else now_epoch
    intervals = beat_intervals(beat_schedule)
    by_label = {m.get("task"): m for m in metrics if m.get("task")}
    deliveries = deliveries or {}

    graded = {}
    unmapped = []
    for full_name, interval_s in sorted(intervals.items()):
        label = label_map.get(full_name)
        m = by_label.get(label) if label else None
        d = deliveries.get(full_name) or {}
        terminal_age, start_age = _stamp_ages_s(m, now_epoch) if m else (None, None)
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
            # LAT-P071: the stamp arm's inputs. `counter_ttl_s` is read from the
            # writer's own constant rather than transcribed, so the ceiling the
            # grader computes can never drift from the TTL that creates it.
            newest_terminal_age_s=terminal_age,
            newest_start_age_s=start_age,
            counter_ttl_s=float(WINDOW_COUNTER_TTL),
        )

    lapping = find_lapping(graded)
    counts = {}
    for g in graded.values():
        counts[g["verdict"]] = counts.get(g["verdict"], 0) + 1
    return {
        "scheduled_tasks": len(intervals),
        "graded": len(graded),
        "verdict_counts": counts,
        # LAT-P071: how many entries each ARM answered. Without this the reader
        # cannot tell a rate-arm PASS from a stamp-arm PASS, and the two support
        # very different claims — the rate arm says "it fired N times in a
        # measured window", the stamp arm says only "something happened
        # recently". Reporting one number for both would launder the weaker
        # evidence into the stronger one's confidence.
        "arm_counts": _arm_counts(graded),
        "lapping": lapping,
        "unmapped": unmapped,
        "all": graded,
    }


def _arm_counts(graded):
    """Per-arm verdict tallies, plus the standing blind-spot census.

    ``rate_arm_blind_total`` is a property of the SCHEDULE and the counter TTL,
    not of today's traffic, so it does not move when the system is healthy. That
    is the point: it is the number that says how much of the beat schedule this
    endpoint could never grade before the stamp arm existed (measured 33 of 123
    on 2026-08-19), and it should be watched for growth every time a slow beat
    is added.
    """
    out = {}
    for g in graded.values():
        arm = g.get("arm", "rate")
        bucket = out.setdefault(arm, {})
        bucket[g["verdict"]] = bucket.get(g["verdict"], 0) + 1
    out["rate_arm_blind_total"] = sum(
        1 for g in graded.values() if g.get("rate_arm_blind")
    )
    return out


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


#: How long an inspect snapshot may be reused. celery's `inspect` is a BROADCAST:
#: every call publishes to a control exchange and blocks until every worker
#: replies or the timeout expires. Four of them in one handler is up to 20s of
#: blocking work.
#:
#: 🔴 THIS CONSTANT EXISTS BECAUSE THE ENDPOINT TOOK PRODUCTION DOWN.
#: LAT-P071, 2026-08-19 05:00–05:03Z: two read-only samplers polling
#: `/api/admin/celery-debug` (one at 20s, one at 8s) drove the whole API to HTTP
#: 503 at the 30s H12 ceiling — `/api/health` included — for ~10 minutes, while
#: `heroku ps` reported the web dyno `up` the entire time with uptime unbroken.
#: Killing the two pollers restored p50 to 0.23s within 25 seconds, four
#: consecutive calls, with no restart. The dyno was never unhealthy: the single
#: uvicorn event loop was simply never free.
#:
#: Nothing about the endpoint looked dangerous — it is a read-only debug route,
#: and that is exactly why it is one auto-refreshing dashboard tab away from an
#: outage. 5s is chosen to be shorter than any plausible human refresh and longer
#: than the tightest sane poll.
_INSPECT_TTL_S = 5.0
_INSPECT_CACHE: dict = {"at": 0.0, "data": None}
_INSPECT_LOCK = None


async def _inspect_snapshot(timeout=5, fresh=False):
    """One celery `inspect` broadcast set, OFF the event loop, memoised and
    single-flighted.

    Three protections, and each one is load-bearing for a different failure:

    * **off-loop** (`run_in_threadpool`) — a broadcast is socket I/O plus
      pure-Python message assembly, both of which release the GIL, so a thread
      genuinely helps here. (Contrast gotcha #38: `to_thread` does NOT help a
      C-level `json.loads`, which holds the GIL for the whole parse. The
      distinction is why this is worth stating rather than assuming.)
    * **single-flight** — concurrent callers share ONE broadcast instead of each
      starting four. Without it, off-loop only moves the pile-up into the
      threadpool, where exhausting the 40 default threads stalls every other
      route that needs one.
    * **memoised** — a poller faster than `_INSPECT_TTL_S` gets the cached
      snapshot. This is the protection that would actually have prevented the
      LAT-P071 outage, because the load there was cadence, not concurrency.

    The cache state is DISCLOSED in the payload. A debug endpoint that silently
    serves a stale snapshot is worse than a slow one — it invites conclusions
    about a moment that has passed.

    🔴 `fresh=True` BYPASSES THE MEMO, AND IS NOT A TEST ACCOMMODATION. Caught by
    the full suite, not by review: a warm cache **masked a live broker failure**.
    `test_response_shape_on_inspect_error` asserts that when `inspect` raises the
    payload says `inspect_error` rather than 200-ing silently — a gotcha #53
    contract — and a 5 s-old success satisfied the request without ever making the
    call that would have failed.

    A 5 s window of that is an acceptable cost for the availability the memo buys,
    and `_cache` discloses it. What is NOT acceptable is having no way out: an
    operator asking "are my workers alive" must be able to get an UNCACHED answer.
    So the bypass exists, it still runs off-loop and single-flighted (it skips the
    memo READ, never the protections), and a raising call writes nothing to the
    cache — an error is not a snapshot.
    """
    import asyncio
    import time as _time

    from starlette.concurrency import run_in_threadpool

    global _INSPECT_LOCK
    if _INSPECT_LOCK is None:
        _INSPECT_LOCK = asyncio.Lock()

    now = _time.time()
    cached = _INSPECT_CACHE.get("data")
    if not fresh and cached is not None and (now - _INSPECT_CACHE["at"]) < _INSPECT_TTL_S:
        return cached, {"cached": True, "age_s": round(now - _INSPECT_CACHE["at"], 2)}

    async with _INSPECT_LOCK:
        # Re-check inside the lock: whoever we queued behind has just refreshed it.
        now = _time.time()
        cached = _INSPECT_CACHE.get("data")
        if not fresh and cached is not None and (now - _INSPECT_CACHE["at"]) < _INSPECT_TTL_S:
            return cached, {"cached": True,
                            "age_s": round(now - _INSPECT_CACHE["at"], 2)}

        def _blocking():
            from app.tasks import celery_app
            i = celery_app.control.inspect(timeout=timeout)
            return {
                "ping": i.ping() or {},
                "active": i.active() or {},
                "reserved": i.reserved() or {},
                "registered": i.registered() or {},
                "stats": i.stats() or {},
            }

        data = await run_in_threadpool(_blocking)
        _INSPECT_CACHE["data"] = data
        _INSPECT_CACHE["at"] = _time.time()
        return data, {"cached": False, "age_s": 0.0}


@router.get("/celery/inspect")
async def celery_inspect(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    fresh: bool = Query(False, description="Bypass the 5s inspect memo"),
):
    """Inspect Celery worker: registered tasks, active tasks, reserved queue."""
    _check_admin_secret(secret, request=request)

    snap, cache_state = await _inspect_snapshot(fresh=fresh)
    registered = snap["registered"]
    active = snap["active"]
    reserved = snap["reserved"]

    result = {"_cache": cache_state}
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


#: Kombu's redis transport publishes with ``lpush`` and consumes with ``rpop``
#: (verified against the installed kombu, not assumed). So index 0 is the NEWEST
#: message and index -1 is the OLDEST — the one about to be served. Both ends are
#: censused because they answer different questions and the existing
#: ``celery-debug`` sample only ever saw one of them.
_QUEUE_CENSUS_MAX_CAP = 4000

#: Celery splits one logical queue across per-priority Redis keys. With no
#: priorities in use everything lands on the base key, but a census that read
#: only the base key would silently under-report the moment that changed — and
#: an under-count here reads as "the backlog cleared".
_PRIORITY_SUFFIXES = ("", "\x06\x163", "\x06\x166", "\x06\x169")


def _census_slice(raw_entries):
    """Task-name histogram for a list of raw celery message bodies.

    A body that will not parse is counted as ``parse_error`` rather than
    skipped. Dropping it would shrink the denominator silently, and a census
    whose denominator moves is not a census.
    """
    import json as _json
    from collections import Counter

    names = []
    for raw in raw_entries:
        try:
            names.append(
                (_json.loads(raw).get("headers") or {}).get("task") or "unknown"
            )
        except Exception:
            names.append("parse_error")
    return dict(Counter(names).most_common()), names


@router.get("/celery/queue-census")
async def celery_queue_census(
    request: Request,
    queue: str = Query("background"),
    cap: int = Query(1000, ge=20, le=_QUEUE_CENSUS_MAX_CAP),
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """What is ACTUALLY in a queue, from both ends, with its coverage stated.

    LAT-P071. ``celery-debug`` samples ``lrange(queue, 0, 19)`` under the comment
    "see what's piled up". Two things are wrong with reading it that way, and the
    program has now been misled by both:

    1. **It is the wrong end.** ``lpush``/``rpop`` means index 0 is the newest
       ARRIVAL. The messages that are piled up — the ones a starved beat is stuck
       behind — are at the far end, and no instrument in this tree has ever
       looked at them.
    2. **20 of 2,842 is not a sample of anything.** It is a window at one end of
       an ordered list, and LAT-P066 was careful to say so; but a bare
       ``{"warm_typeahead": 18}`` in a payload gets read as a proportion anyway.

    So this returns both ends, both histograms, and — the field that makes the
    other two safe to read — ``coverage``: what fraction of the depth was
    actually examined, and whether the read was ``truncated``. A census that
    cannot say how much it saw is an anecdote with a total attached.

    Read-only: ``lrange`` and ``llen`` only. Nothing here consumes, acks, moves
    or purges a message.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    per_key, depth = {}, 0
    for suffix in _PRIORITY_SUFFIXES:
        key = f"{queue}{suffix}"
        n = r.llen(key)
        if n:
            per_key[repr(key)] = n
            depth += n

    half = max(1, cap // 2)
    # Both slices come off the BASE key. A per-priority queue deep enough to need
    # its own census is a different situation and gets reported as a depth, not
    # guessed at from the base key's composition.
    base = queue
    base_len = r.llen(base)
    newest_raw = r.lrange(base, 0, min(half, base_len) - 1) if base_len else []
    oldest_raw = r.lrange(base, -min(half, base_len), -1) if base_len else []
    newest_hist, _ = _census_slice(newest_raw)
    oldest_hist, oldest_names = _census_slice(oldest_raw)

    examined = len(newest_raw) + len(oldest_raw)
    # The two slices overlap once the cap exceeds the depth; past that point the
    # census is COMPLETE and `examined` would double-count. Say complete.
    complete = base_len > 0 and cap >= base_len
    seen = base_len if complete else examined

    return {
        "queue": queue,
        "depth": depth,
        "depth_by_key": per_key,
        "cap": cap,
        "coverage": {
            "examined": seen,
            "of_depth": depth,
            "pct": round(100.0 * seen / depth, 1) if depth else None,
            "complete": complete,
            "truncated": bool(depth) and not complete,
        },
        # `oldest_first` is the SERVICE order. The first name in it is the next
        # message this queue will hand to a worker.
        "next_to_be_served": oldest_names[-1] if oldest_names else None,
        "oldest_end": oldest_hist,
        "newest_end": newest_hist,
        "note": (
            "lpush/rpop: index 0 is the newest arrival, index -1 is served next. "
            "oldest_end is the backlog a starved beat waits behind; newest_end is "
            "the current arrival mix."
        ),
    }


@router.post("/celery-purge-background")
async def celery_purge_background(request: Request, secret: str = Query(None)):
    """Purge stale tasks from the background queue."""
    _check_admin_destructive(secret, request=request)
    from app.tasks import celery_app
    purged = celery_app.control.purge()
    return {"purged": purged}


@router.get("/celery-debug")
async def celery_debug(
    request: Request,
    secret: str = Query(None),
    fresh: bool = Query(False, description="Bypass the 5s inspect memo"),
):
    """Inspect Celery worker status and queue lengths."""
    _check_admin_secret(secret, request=request)

    result = {}

    # Worker ping. Off-loop, single-flighted and memoised — see `_inspect_snapshot`.
    # This handler used to make FOUR blocking 5s broadcasts inline in an `async
    # def`, which is what took the API down on 2026-08-19 (LAT-P071).
    try:
        snap, result["_cache"] = await _inspect_snapshot(fresh=fresh)
        result["ping"] = snap["ping"] or "no response"
        result["active"] = snap["active"] or "no response"
        result["registered"] = {k: len(v) for k, v in snap["registered"].items()}
        result["stats"] = {
            k: {"total": v.get("total", {}), "pool": v.get("pool", {}).get("max-concurrency")}
            for k, v in snap["stats"].items()
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

#: A colon segment at least this long, made only of hex digits and dashes, is an
#: id (uuid, sha) rather than a family name.
_OPAQUE_HEX_MIN_LEN = 16


def _looks_like_opaque_id(segment: str) -> bool:
    """True when a segment names ONE row/job rather than a family of them.

    #1807: the prefix table above only folds families somebody thought to list.
    ``interestingness:{market_id}`` was not on it, so 41,152 cache keys became
    41,152 distinct "classes" — and since each class was under its own sampling
    quota, the census issued a ``MEMORY USAGE`` **and** a ``TTL`` round trip for
    every single key. That is what pushed it past the 30 s router timeout. The
    fix has to be structural rather than another table entry, because the next
    ``<family>:{id}`` cache to land would reintroduce it silently.
    """
    if not segment:
        return False
    if segment.isdigit():
        return True
    stripped = segment.replace("-", "")
    return len(stripped) >= _OPAQUE_HEX_MIN_LEN and all(
        c in "0123456789abcdefABCDEF" for c in stripped
    )


def _redis_key_class(key: str) -> str:
    """Fold a key into the family it belongs to, id suffixes and all."""
    for prefix in _REDIS_ID_SUFFIX_PREFIXES:
        if key.startswith(prefix):
            return f"{prefix}*"
    # Otherwise: first two colon segments, so `bainluck:calibration:x` and
    # `bainluck:calibration:y` roll up together — with any segment that is an
    # opaque id collapsed to `*`, so `interestingness:41152` folds to
    # `interestingness:*` instead of naming itself.
    segments = [
        "*" if _looks_like_opaque_id(s) else s for s in key.split(":")[:2]
    ]
    return ":".join(segments) or "(root)"


#: Indirection so a test can drive the census deadline off a deterministic
#: counter. A test that measured real elapsed time would be a test that branches
#: on the clock (gotcha #44), and this one has to assert the deadline fires.
_census_clock = time.monotonic


@router.get("/redis-census")
async def redis_census(
    request: Request,
    secret: str = Query(None),
    scan_limit: int = Query(200000, ge=100, le=2000000),
    sample_per_class: int = Query(12, ge=1, le=50),
    deadline_s: float = Query(12.0, ge=1.0, le=25.0),
    sample_budget: int = Query(4000, ge=0, le=100000),
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
    * ``MEMORY USAGE`` is sampled (``sample_per_class`` keys per class, and no
      more than ``sample_budget`` in total), not called per key, and its own
      ``SAMPLES 0`` estimate is used for collections.
    * A wall-clock ``deadline_s`` well inside Heroku's 30 s router timeout.
    * The client comes from ``get_redis_client()``, which carries the mandatory
      socket/connect timeouts (gotcha #39).

    #1807 is why the last two of those exist. The per-class sampling quota is
    only a bound if the number of classes is bounded, and it was not: an
    unfolded ``<family>:{id}`` keyspace made every key its own class, so the
    "sampled" path ran per key and the endpoint 503'd at the router timeout —
    on the DEFAULT call, at the keyspace the endpoint was built to measure.
    A 503 is indistinguishable from the app being down, so the endpoint now
    answers with a partial census and says which bound stopped it. **An empty
    200, a partial 200 and a dead Redis must never read the same** (gotcha #53),
    hence the explicit ``verdict``.

    Strictly read-only: no write, no delete, no ``FLUSH``, no config change.
    Sizing decisions belong to Alex; this endpoint only supplies the numbers.
    """
    _check_admin_secret(secret, request=request)

    from collections import defaultdict

    from app.tasks.redis_state import get_redis_client

    started = _census_clock()
    out: dict = {
        "scan_limit": scan_limit,
        "deadline_s": deadline_s,
        "sample_budget": sample_budget,
        "truncated": False,
        "truncated_reason": None,
        # `partial` = full coverage, incomplete sampling. Always present so a
        # consumer can read it without a key check (gotcha #53).
        "partial_reason": None,
        "verdict": "complete",
    }
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
        scan_calls = 0
        sample_ops = 0
        budget_exhausted = False
        stop_reason: str | None = None
        while True:
            cursor, batch = r.scan(cursor=cursor, count=500)
            scan_calls += 1
            for raw in batch:
                # BOTH bounds are checked per KEY, before the expensive work —
                # not at the page boundary, where they used to sit.
                #
                # The loop broke on `cursor == 0` ABOVE these two checks, so the
                # terminal page never consulted either. For any keyspace smaller
                # than one SCAN count that is the ONLY page, and its full cost —
                # up to 500 x (MEMORY USAGE + TTL) synchronous round trips — had
                # already been paid by the time the break ran. Measured on the
                # unfixed endpoint: 50 s of sampling against `deadline_s=12`,
                # returned as `verdict="complete"`, and 300 keys scanned against
                # a `scan_limit` of 100 reported as 100% coverage.
                #
                # Per-key also makes the overshoot one key's work instead of one
                # page's, which is what this endpoint's docstring always claimed.
                if scanned >= scan_limit:
                    stop_reason = "scan_limit"
                    break
                if _census_clock() - started >= deadline_s:
                    stop_reason = "deadline"
                    break
                key = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                cls = _redis_key_class(key)
                cell = classes[cls]
                cell["keys"] += 1
                # Two bounds, because the per-class quota alone is not one: it
                # only limits work if the class count is limited too (#1807).
                if cell["sampled"] < sample_per_class and sample_ops < sample_budget:
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
                    sample_ops += 1
                elif cell["sampled"] < sample_per_class:
                    budget_exhausted = True
                scanned += 1
            if stop_reason:
                out["truncated"] = True
                out["truncated_reason"] = stop_reason
                break
            if cursor == 0:
                break

        out["scanned"] = scanned
        dbsize = out.get("dbsize") or 0
        out["coverage_pct"] = round(100.0 * scanned / dbsize, 1) if dbsize else None
        # The numbers that make a slow census diagnosable instead of mysterious.
        # `sample_ops` is the one that regressed in #1807: it tracked `scanned`
        # one-for-one when it should have tracked `classes_seen`.
        out["cost"] = {
            "scan_calls": scan_calls,
            "sample_ops": sample_ops,
            "classes_seen": len(classes),
            "sample_budget_exhausted": budget_exhausted,
        }
        if out["truncated"]:
            # Incomplete COVERAGE subsumes incomplete sampling: if the scan
            # stopped early, "partial" would understate what was missed.
            out["verdict"] = "truncated"
        elif budget_exhausted:
            # Coverage is genuinely complete — every key was scanned and
            # counted — but the BYTE RANKING stopped early, and ranking classes
            # by bytes is the only reason this endpoint exists. An unsampled
            # class estimates as zero bytes, so a run that sampled 10 of 1,000
            # classes was reporting `complete` while its headline numbers were
            # mostly zeros. `sample_budget_exhausted` recorded the debt in
            # `cost`, but nothing propagated it to the field the #1807 live
            # proof actually reads.
            #
            # A third value rather than reusing `truncated`, because coverage
            # IS complete and saying otherwise is its own false statement —
            # gotcha #53 applied to our own verdict vocabulary: three different
            # facts, three different bodies.
            out["verdict"] = "partial"
            out["partial_reason"] = "sample_budget"
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
            # An unsampled class estimates at zero bytes, which would sort it
            # last — i.e. exactly like a class known to be tiny. Say which it is
            # rather than letting the ranking imply a measurement never taken.
            row["est_basis"] = "sampled" if cell["sampled"] else "unsampled"
            summary.append(row)
        # Key count breaks the tie so unsampled classes still rank among
        # themselves instead of landing in arbitrary dict order.
        summary.sort(key=lambda c: (-c["est_total_bytes"], -c["keys"]))
        out["classes"] = summary[:60]
        out["classes_omitted"] = max(0, len(summary) - 60)
        out["note"] = (
            "est_total_bytes is avg_sampled_bytes * keys — a ranking estimate, "
            "not a measurement. Read-only; no keys were written or removed. "
            "Read `verdict` before any count: `complete` covered the keyspace "
            "AND sampled it, `partial` covered it all but stopped sampling "
            "early (see `partial_reason` — unsampled classes estimate as zero "
            "bytes and must not be read as small), `truncated` covered only "
            "`coverage_pct` of it, `error` counted nothing."
        )
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:300]
        # Without this an unreachable Redis returns a 200 whose class list is
        # empty — the same body as a genuinely empty keyspace (gotcha #53).
        out["verdict"] = "error"
    return out


@router.get("/typeahead-warmer/last")
async def typeahead_warmer_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """The typeahead warmer's recent PASS results, as a distribution.

    LAT-P074 (#1866, #1609, #1996). Read-only, two bounded Redis reads, no
    celery broadcast — this is deliberately NOT `/celery-debug`'s shape, and the
    difference is the reason that endpoint has a 🔴 block above it.

    **What this adds that production did not already have, stated exactly.**
    The last pass summary has always been readable: `_tracked_run` writes it to
    `task_metrics:warm_typeahead.last_result_summary` and
    `GET /api/admin/celery/task-metrics/warm_typeahead` returns it. LAT-P073
    believed otherwise and planned around the gap; the correction is recorded in
    `app/utils/typeahead_pass_ring.py` so the next reader does not repeat it.

    What that slot cannot do is hold a DISTRIBUTION. It is one value, overwritten
    by every run, and two thirds of runs are no-ops (measured 2026-08-20T00:15Z:
    33 of 50 executions <= 71 ms, 17 >= 32.9 s). Three pieces of work need the
    distribution rather than the last value:

    * `typeahead_beat_budget.MEASURED_WALL_MAX_S` needs a **pass-only** maximum;
    * the publish gate's registered halt is `expired` **per pass**;
    * #1996 needs no-ops **counted**, which the skip counters here do.

    **Three states, never two** (gotcha #53, ruling 075 clause 2): `unreadable`
    means Redis raised and we learned nothing; `no_data` means Redis answered and
    the warmer has written nothing; `ok` means read the numbers. And inside
    `ok`, `passes.n == 0` with `skips.total > 0` is a warmer that is firing and
    skipping every single time — a diagnosis a bare empty ring cannot make.

    Off-loop via `run_in_threadpool` for the same reason `_inspect_snapshot` is:
    `get_redis_client()` is bounded at 5 s (gotcha #39), and 5 s of a blocked
    single uvicorn event loop under an auto-refreshing dashboard tab is exactly
    how #1994 happened at a larger scale. Two Redis ops are microseconds when
    Redis is healthy; the threadpool is insurance for when it is not.
    """
    _check_admin_secret(secret, request=request)

    from starlette.concurrency import run_in_threadpool

    from app.tasks.typeahead_warmer import (
        _PASS_RING_KEY,
        _PASS_RING_MAX,
        _PASS_RING_TTL_SECONDS,
        _WARMER_STATE_KEY,
    )
    from app.utils.typeahead_beat_budget import RESPONSE_CACHE_TTL_S
    from app.utils.typeahead_pass_ring import (
        decode_records,
        decode_state,
        summarise,
        unreadable,
    )

    now = time.time()

    def _read():
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        pipe = rc.pipeline()
        # LRANGE is bounded by the ring's own cap, not by a caller-supplied
        # number: an endpoint whose cost a caller can raise is an endpoint a
        # caller can use to hurt the instance (#1807's lesson, one size down).
        pipe.lrange(_PASS_RING_KEY, 0, _PASS_RING_MAX - 1)
        pipe.hgetall(_WARMER_STATE_KEY)
        return pipe.execute()

    try:
        raw_ring, raw_state = await run_in_threadpool(_read)
    except Exception as exc:  # noqa: BLE001
        return unreadable(
            str(exc)[:300],
            now=now,
            ring_max=_PASS_RING_MAX,
            ttl_s=RESPONSE_CACHE_TTL_S,
        )

    payload = summarise(
        decode_records(raw_ring),
        decode_state(raw_state),
        now=now,
        ring_max=_PASS_RING_MAX,
        ttl_s=RESPONSE_CACHE_TTL_S,
    )
    payload["ring_ttl_s"] = _PASS_RING_TTL_SECONDS
    payload["note"] = (
        "passes.seconds_wall is the PASS-ONLY wall distribution — the number "
        "typeahead_beat_budget.MEASURED_WALL_MAX_S must be derived from. "
        "passes.expired is cache-entry loss: entries whose key was already gone "
        "when the pass reached them. status=unreadable means the read failed "
        "and nothing here is a measurement; status=no_data means the warmer has "
        "written nothing; passes.n=0 with skips.total>0 means it is firing and "
        "skipping every time."
    )
    return payload
