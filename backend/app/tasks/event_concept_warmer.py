"""Keep the concept payloads warm (#1107, LAT-P021; #1948).

Two entry points, one build path:

``_warm_event_concepts``
    Scheduled. Warms TWO tiers so the 24h mirror stays content-fresh and the
    very first build of the day is never paid by a reader:

      * **leaders** — every UNSETTLED concept, enumerated by the feed's own
        population function (`app/utils/event_concept_population.py`). Added by
        #1948. This tier is load-bearing: since UX-P089 made
        `_resolve_concept_leader` cache-only, a concept whose envelope is not
        warm has no probability, and both surfaces suppress that card entirely.
        A cold key here is a DELETED CARD, not a slow page.
      * **majors** — the four golf majors in ``WARM_CONCEPT_KEYS`` (#1107's p0).
        NOT load-bearing: a cold major still builds inline in the route, so
        missing one costs latency, never content.

    Leaders run FIRST and the tiers have SEPARATE budgets, both for the same
    reason (gotcha #34): majors cost 11-35s against leaders' 0.24-1.37s, so a
    shared budget would let the majors starve the load-bearing tier on every
    single run — silently, which is the shape of #1948 itself.

``_refresh_event_concept``
    Dispatched by the route when it serves the mirror on a miss. This is the
    "revalidate" half of serve-stale-while-revalidate, and it is what keeps the
    warmer from having to race the 60s primary TTL.

WHY THE CADENCE IS NOT SUB-TTL. LAT-P021 was staged asking for "a schedule
shorter than the TTL". Item 0 measured the TTL at **60s** and the four builds at
10.98 + 15.96 + 20.04 + ~35s = **~82s**, so a sub-60s cadence cannot complete a
>60s job — runs would overlap and the global ``task_time_limit=300`` is a hard
SIGKILL that reads as ``no_data``. The route change dissolves the conflict: with
a miss served from the mirror in ~0.44s, the primary TTL no longer governs
user-visible latency, so the warmer only has to keep the CONTENT fresh. Five
minutes does that comfortably.

The warmer is not load-bearing. A cold miss still builds inline in the route
(``build_and_cache`` at step 4), so turning this task off makes the page slow
again — never broken. ``tests/test_warm_event_concepts.py`` asserts that.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

#: Bound on ONE key's build, not on the loop. The longest measured single
#: uninterrupted operation is The Open at ~35s; this is the op that has to be
#: bounded, because bounding only the loop boundary lets one pathological build
#: consume the whole budget and take the other three keys down with it.
PER_KEY_TIMEOUT_SECONDS = 55

# --- The leader tier (#1948) -------------------------------------------------
# The unsettled concepts `_resolve_concept_leader` runs on. Cheap: measured
# 0.24-1.37s per key on production, against golf's 11-35s.
#
# It gets its OWN budget rather than sharing one deadline with the majors, and
# that is gotcha #34 — "never share a single counter between two kinds of work
# across a loop; the early work exhausts the limit before the later work is
# reached". Majors are 40x more expensive per key and would starve this tier
# every single run, silently, which is precisely the failure mode #1948 IS.
LEADER_PER_KEY_TIMEOUT_SECONDS = 10
LEADER_TIER_BUDGET_SECONDS = 70
#: Wall-clock for the majors tier. Their measured total is ~82s (11+16+20+35);
#: 150 carries that with headroom while still capping a pathological run so it
#: cannot reach the task's soft limit.
MAJORS_TIER_BUDGET_SECONDS = 150


async def _leader_population() -> tuple[str, ...]:
    """The unsettled concepts the feed will ask for a leader on (#1948).

    Best-effort and total: a failure here returns an empty tier, so the majors
    still warm and the run still reports honestly. The empty tier is visible in
    the summary (`leader_population: 0`) rather than being indistinguishable
    from "there are no unsettled concepts today" — gotcha #53, an empty result
    and an absent measurement are different facts.
    """
    from app.tasks.base import get_task_session
    from app.utils.event_concept_population import list_unsettled_concept_keys

    try:
        async with get_task_session() as db:
            return await list_unsettled_concept_keys(db)
    except Exception as exc:
        logger.warning("warm_event_concepts: leader population unavailable: %s", exc)
        return ()


async def _build_one(key: str, *, token: str | None, timeout: float | None = None) -> dict:
    """Rebuild and re-cache one concept key. Never raises.

    `timeout` bounds THIS build; ``None`` means the majors bound
    (``PER_KEY_TIMEOUT_SECONDS``). It is read at call time, not bound as a
    default, so a test patching the module constant still governs.

    `token` is the refresh-lock owner token THIS producer holds, and it is
    keyword-only and mandatory so that no caller acquires one by accident. Only
    that token releases the lock; a producer holding nothing releases nothing.

    Passing `None` is legal and means "I hold no lock" — the build still runs (a
    caller that got here wants content) but the lock is left alone. That is the
    transitional case for a `refresh_event_concept` message enqueued by the
    pre-#1678 route, which is already in the broker at deploy time with no token
    in its args; its old `"1"`-valued lock simply expires on its own TTL.
    """
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import cache_keys, get_client, release_refresh_lock

    rc = get_client()
    keys = cache_keys(key)
    started = time.monotonic()

    try:
        from app.utils.event_concept_cache import build_and_cache

        async def _run():
            async with get_task_session() as db:
                return await build_and_cache(key, db, rc)

        payload = await asyncio.wait_for(
            _run(),
            timeout=PER_KEY_TIMEOUT_SECONDS if timeout is None else timeout,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started
        logger.warning("warm_event_concepts: %s timed out after %.1fs", key, elapsed)
        return {"key": key, "ok": False, "reason": "timeout", "seconds": round(elapsed, 2)}
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning("warm_event_concepts: %s failed: %s", key, exc, exc_info=True)
        return {"key": key, "ok": False, "reason": "error", "seconds": round(elapsed, 2)}
    finally:
        # Release the lock THIS producer holds, whatever happened, so the key can
        # schedule another refresh without waiting out REFRESH_LOCK_TTL.
        #
        # It is a compare-and-delete against our own token, and that is the whole
        # fix for #1678 finding 1. This `finally` used to delete the key
        # unconditionally while `_build_one` never acquired anything — so the
        # 5-minute scheduled warmer reliably deleted the lock of an in-flight
        # route-dispatched refresh, and the next reader past the TTL acquired the
        # now-free lock and dispatched a SECOND rebuild alongside the running one.
        # A single-flight primitive that admits a third builder is not one.
        release_refresh_lock(rc, keys, token)

    elapsed = time.monotonic() - started

    if payload is None:
        # Not an error: the key genuinely resolves to nothing (an unscheduled
        # major, a slug that has not been created yet). Recorded as a distinct
        # reason rather than folded into the error count, because "absent" and
        # "broken" are different facts and gotcha #53 is about exactly that.
        logger.info("warm_event_concepts: %s resolves to nothing", key)
        return {"key": key, "ok": False, "reason": "absent", "seconds": round(elapsed, 2)}

    return {"key": key, "ok": True, "reason": "built", "seconds": round(elapsed, 2)}


async def _warm_event_concepts(keys: tuple[str, ...] | None = None) -> dict:
    """Rebuild every warm-listed concept payload. Returns a contract summary.

    The summary speaks the ``task_verdict`` vocabulary (``terminal`` +
    ``completed``/``total`` + ``errors``) so a run that warms three of four
    majors reads PARTIAL rather than GREEN. A warmer whose whole purpose is that
    all four are warm must not be able to report success while one is cold.
    """
    from app.config.event_concept_warm_keys import WARM_CONCEPT_KEYS
    from app.utils.event_concept_cache import acquire_refresh_lock, cache_keys, get_client

    # An explicit key list means "warm exactly these" — the route's refresh path
    # and the tier-focused tests. Only the SCHEDULED run (keys is None) resolves
    # the leader population.
    if keys is not None:
        tiers = (("majors", tuple(keys), PER_KEY_TIMEOUT_SECONDS, MAJORS_TIER_BUDGET_SECONDS),)
        leader_population = None
    else:
        # LEADERS FIRST, and the order is the fix (#1948). After UX-P089 made
        # `_resolve_concept_leader` cache-only, this cache is the ONLY source of
        # a concept card's probability — whereas the majors' mirror is NOT
        # load-bearing (a cold major still builds inline in the route, so a
        # missed major is a slow page; a missed leader is a DELETED CARD). The
        # load-bearing tier must not be the one that runs on leftovers.
        leader_keys = await _leader_population()
        leader_population = len(leader_keys)
        tiers = (
            ("leaders", leader_keys, LEADER_PER_KEY_TIMEOUT_SECONDS, LEADER_TIER_BUDGET_SECONDS),
            ("majors", WARM_CONCEPT_KEYS, PER_KEY_TIMEOUT_SECONDS, MAJORS_TIER_BUDGET_SECONDS),
        )

    targets = tuple(k for _, tier_keys, _, _ in tiers for k in tier_keys)
    rc = get_client()

    results = []
    for tier_name, tier_keys, per_key_timeout, tier_budget in tiers:
        tier_started = time.monotonic()
        for key in tier_keys:
            remaining = tier_budget - (time.monotonic() - tier_started)
            if remaining <= 0:
                # NO SILENT CAPS. A key the budget never reached is reported as
                # its own reason, not folded into "absent" (which asserts the key
                # resolves to nothing) and not dropped from the summary. A tier
                # that is chronically skipped is a budget that needs raising, and
                # that is only visible if the skip is written down.
                logger.warning(
                    "warm_event_concepts: %s tier budget (%ss) exhausted before %s",
                    tier_name,
                    tier_budget,
                    key,
                )
                results.append(
                    {"key": key, "ok": False, "reason": "budget", "seconds": 0.0,
                     "tier": tier_name}
                )
                continue
            # ACQUIRE FIRST, and skip the key if we cannot. This loop is the producer
            # that used to barge in: it never took the lock and then deleted whatever
            # was there on the way out (#1678 finding 1). A key already being rebuilt
            # by a route-dispatched refresh is a key that is being handled — the right
            # move is to leave it alone, not to build it a second time in parallel.
            token = acquire_refresh_lock(rc, cache_keys(key))
            if token is None:
                logger.info("warm_event_concepts: %s already being rebuilt, skipping", key)
                results.append(
                    {"key": key, "ok": False, "reason": "locked", "seconds": 0.0,
                     "tier": tier_name}
                )
                continue
            result = await _build_one(
                key, token=token, timeout=min(per_key_timeout, remaining)
            )
            result["tier"] = tier_name
            results.append(result)

    built = [r for r in results if r["ok"]]
    absent = [r for r in results if r["reason"] == "absent"]
    locked = [r for r in results if r["reason"] == "locked"]
    budget = [r for r in results if r["reason"] == "budget"]
    errors = [r for r in results if r["reason"] in ("timeout", "error")]

    # `absent` and `locked` are accounted-for, not failures: the run did everything
    # it could for them — one genuinely resolves to nothing, the other is mid-build
    # in another producer. Only real damage lands in `errors`. `locked` is reported
    # as its own list rather than folded into a count, because a key that is locked
    # on run after run is a wedged lock, and that must stay visible.
    #
    # `budget` is NOT accounted-for. The run ran out of time before reaching that
    # key, so its envelope may be stale or missing and a card may be dark because
    # of it. Counting it as completed would let a warmer that skipped half the
    # leader tier report GREEN — the exact false-GREEN shape #1515 was filed for.
    completed = len(built) + len(absent) + len(locked)

    summary = {
        "terminal": "complete" if not errors and not budget else "partial",
        "completed": completed,
        "total": len(targets),
        "built": len(built),
        "absent": [r["key"] for r in absent],
        "locked": [r["key"] for r in locked],
        "budget_skipped": [r["key"] for r in budget],
        "errors": [{"key": r["key"], "reason": r["reason"]} for r in errors],
        "seconds": {r["key"]: r["seconds"] for r in results},
        # How many unsettled concepts the leader tier found. `None` on an
        # explicit-keys run (the tier was not resolved); `0` means the
        # enumeration ran and found nothing, which is a different fact.
        "leader_population": leader_population,
    }
    logger.info(
        "warm_event_concepts: %d/%d accounted (%d built, %d absent, %d locked, "
        "%d budget-skipped, %d errors; leader population %s)",
        completed,
        len(targets),
        len(built),
        len(absent),
        len(locked),
        len(budget),
        len(errors),
        leader_population,
    )
    return summary


async def _refresh_event_concept(key: str, token: str | None = None) -> dict:
    """Revalidate one key after the route served its mirror.

    The route acquired the refresh lock before dispatching us and hands the owner
    token across in the message, because the acquire and the release live in
    different processes here. `token` defaults to None so a message enqueued by
    the pre-#1678 route still runs after deploy — it rebuilds and lets that old
    lock lapse on its TTL rather than deleting a lock it cannot prove it owns.
    """
    result = await _build_one(key, token=token)
    return {
        "terminal": "complete" if result["ok"] or result["reason"] == "absent" else "failed",
        "completed": 1 if result["ok"] or result["reason"] == "absent" else 0,
        "total": 1,
        "key": key,
        "reason": result["reason"],
        "seconds": result["seconds"],
    }
