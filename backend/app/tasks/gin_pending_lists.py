"""Keep the search path's trigram GIN pending lists flushed (LAT-P109, #2255).

THE SHIP: cold search stops randomly costing an extra second.

WHAT WAS MEASURED, ON PRODUCTION, 2026-08-28, SLUG ``0e2414cd``.

The needle's cold-search member returned a p50 of **787.5 ms over six obscure
terms, spread 433 → 1,945 ms**. The spread is not term difficulty. Two probes of
the SAME term minutes apart returned 727 ms and then 179 ms, and the per-stage
breakdown (`/api/events/search?debug_timing=true`) put the move in one place:
the `futures` stage, 54–68 % of the whole request on every one of 32 fresh
terms sampled.

Inside that stage, `EXPLAIN (ANALYZE, BUFFERS)` of the exact query the route
compiles (`term = cremonese`, taken twice, eleven minutes apart):

    node                                        pass A      pass B
    Append (the UNION of the recall arms)       148.9 ms    27.8 ms
      Bitmap Index Scan ix_futures_name_trgm     50.2 ms    19.5 ms
      Bitmap Index Scan ix_futures_outcomes…     87.6 ms     4.0 ms

Same query, same rows out (29 candidates, 20 returned), **5.4x**. Nothing about
the data changed between the two passes. What changed is the GIN **pending
list**.

🔴 THE PROOF IS A PATTERN THAT MATCHES NOTHING. A `%zzqqxxvv%` probe returns
zero rows and can do no useful work, so whatever it costs is pure overhead —
and it cost **49.9 ms over 507 shared blocks** on `futures_outcomes.name`, then
**0.3 ms over 31 blocks** ninety seconds later. A GIN entry-tree descent for an
absent key is a handful of pages. 507 pages is the pending list being read
start to finish, which is what `gin_pending_list_limit = 4MB` (= 512 × 8 kB
pages, confirmed by `current_setting`) buys every single reader.

🔴 AND IT IS A SAWTOOTH, NOT A ONE-OFF. Zero-match probes every 46 s:

    index                     t+0    t+46   t+92   t+138  t+184
    futures_markets.name      530    530    531    →24    25     (flush observed)
    futures_outcomes.name      93    100    141    170    208    (~50 pages/min)
    events.home_team_name     118    118    132    148    161    (~20 pages/min)
    teams.name                 14     14     15     15     15    (write-quiet)

Every index on the search read path climbs to 512 pages, is flushed by whichever
unlucky INSERT crosses the limit, and starts climbing again. `futures_outcomes`
refills in about ten minutes. A search that lands near the top of the sawtooth
pays the whole 4 MB on each of the four trigram indexes it touches; a search
that lands just after a flush pays nothing. **That is the 433 → 1,945 ms spread,
and it is a coin flip the user loses about half the time.**

Autovacuum also flushes pending lists, and it is not the answer here: it fires
on the table's own dead-tuple threshold (hundreds of thousands of rows on a
3.2 M-row table), which is orders of magnitude slower than the 4 MB limit. The
sawtooth above IS the steady state.

WHY A TASK AND NOT THE ONE-LINE DDL. `ALTER INDEX … SET (gin_pending_list_limit
= '256kB')` is the smaller, permanent form of this fix and it is the right end
state. It is DDL, and ruling 080 makes a migration slot an integrator-owned
artifact that a lane requests and never takes. So the slot is REQUESTED on #2255
and this task is the shippable form today: same effect on the read
path, no schema change, no writer behaviour change, and reversible by a config
var without a deploy.

WHAT THIS DOES NOT DO. It does not make any query cheaper than a clean index
already makes it — the floor is `pass B` above, not zero. It does not touch
recall, ordering, or any predicate: `gin_clean_pending_list` moves entries that
are already in the index from the pending list into the tree, so every reader
sees exactly the same rows before and after. And it is not a cache: there is
nothing to warm and nothing to invalidate.

BUDGET, AND WHY IT IS BOUNDED WHERE IT IS. The longest uninterrupted operation
is one `gin_clean_pending_list` call, so THAT is what carries the timeout
(`PER_INDEX_TIMEOUT_MS`), not the loop boundary — the shape gotcha #124's
sibling entry records for budget guards. A pass over eight indexes at a 2-minute
beat merges roughly one minute of accumulation each time, which is work an
inserting backend would otherwise do anyway; this moves it off the read path and
off whichever poll happened to cross the line, it does not create it.

ONE BAD INDEX MUST NOT WIPE THE PASS (gotcha #42): every index is attempted
inside its own try/except and its own savepoint, and damage lands in ``errors``.
The summary speaks `task_verdict`'s vocabulary, and the three terminals are
distinct on purpose — `complete` (every index visited), `partial` (some visited),
`failed` (none). **The unit is indexes VISITED, never pages reclaimed**: a pass
that finds every list already empty has done exactly its job, and the steady
state this task is trying to reach is `pages_cleaned = 0`. What must never read
GREEN is a pass that visited nothing, which is gotcha #53's shape — "it
returned" is not "it worked".
"""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy import text

logger = logging.getLogger(__name__)


#: The trigram GIN indexes ON THE SEARCH READ PATH, declared as a frozen literal
#: rather than discovered by a `pg_index` predicate. A predicate would silently
#: adopt every GIN index anyone adds later, including ones on tables this task
#: has never measured — and the whole claim above is a measurement of these
#: seven. A new index joins by an explicit edit, which is a visible commit.
#:
#: `ix_events_{home,away}_trgm` and `ix_events_{home,away}_team_name_trgm` are
#: DUPLICATE PAIRS — same table, same column, same opclass (verified in
#: `pg_indexes` on 2026-08-28). Both are listed because both exist and both
#: carry a pending list today. Dropping the duplicates is a separate, DDL-shaped
#: ship; it is parked, not assumed.
SEARCH_TRIGRAM_INDEXES: tuple[str, ...] = (
    "ix_futures_outcomes_name_trgm",
    "ix_futures_name_trgm",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_home_team_name_trgm",
    "ix_events_away_team_name_trgm",
    "ix_teams_name_trgm",
)

#: #10090 Holder A — GIN indexes flushed for their WRITERS, not for search.
#:
#: An `events` writer whose insert pushes a GIN pending list past
#: `gin_pending_list_limit` merges the whole list inside its own statement, with
#: the row it is updating still locked. Mapped on production 2026-10-29 04:39Z:
#: a single-row `UPDATE events` was active ≥ 9.9 s, the price stamps for the same
#: row queued behind it on `transactionid`, and autovacuum's ANALYZE queued
#: behind it on the GIN metapage lock — the shape of an in-statement merge
#: (reproduced locally on PG14, magnitude not). The four `events` trigram lists
#: are flushed above; `ix_events_event_tags` (`jsonb_path_ops`, created with the
#: GIN default `fastupdate = on`) was in no list, so only a writer or a rare
#: autovacuum ever emptied it. Which index that statement merged is not known;
#: this closes the one that nothing was keeping down.
#:
#: Listed FIRST in whichever pass visits it, so a slow trigram flush cannot
#: starve it under the task's soft limit. Same frozen-literal rule as the
#: search pool.
WRITE_PATH_GIN_INDEXES: tuple[str, ...] = ("ix_events_event_tags",)

#: The whole declared pool — and the only names `_flush_one` takes.
FLUSHED_GIN_INDEXES: tuple[str, ...] = WRITE_PATH_GIN_INDEXES + SEARCH_TRIGRAM_INDEXES

#: #10090 — every GIN index on `events`, flushed by their OWN beat on `realtime`
#: (`flush-events-gin-pending-lists`), `ix_events_event_tags` first.
#:
#: WHY A SECOND BEAT. The 2-minute beat on `background` started 37 times in the
#: 24 h before 15:44Z 10/29 against 720 fires, with gaps of 43 min and 5 h
#: (task-metrics, read by speed). `background` is `--concurrency=2` against ~140
#: beats and its measured lag is p50 152 s / max 2,511 s on a 120 s beat
#: (LAT-P112, recorded at the `warm-container-hubs` entry); this beat's
#: `expires: 110` therefore discards most fires before a worker takes them, by
#: design, and no `expires` value fixes a queue that is late by more than a
#: period. `realtime` delivered 40 s against a declared 40 s (max 54 s) in the
#: same measurement. `warm-container-hubs` moved for the same reason (#9982).
#:
#: WHY IT CANNOT ITSELF BECOME A STALL. (1) A writer never waits on a flush: an
#: inserting backend over the limit takes the GIN metapage lock CONDITIONALLY and,
#: finding a cleanup in progress, appends and returns (lane1's PG14 review of
#: #11732, 10/29 14:05Z: max 3.1 ms at ~650 pages). (2) Each list holds about
#: one period of growth when the beat delivers, and is capped near
#: `gin_pending_list_limit` by the writers themselves when it does not, so one
#: flush is at most one full-limit merge (~10 s, the in-statement merge mapped at
#: 04:39Z) — under `PER_INDEX_TIMEOUT_MS`. A flush cut by its timeout reclaims 0
#: pages, so that bound must stay above a full-limit merge. (3) The pass starts no
#: flush after `EVENTS_PASS_BUDGET_S`, so one fire holds a realtime slot for at
#: most budget + one flush. (4) These five leave the `background` pass, so no
#: flush ever waits on another flush's metapage lock.
EVENTS_GIN_INDEXES: tuple[str, ...] = (
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_home_team_name_trgm",
    "ix_events_away_team_name_trgm",
)

#: What the `background` pass visits while the events beat is on: the rest of the
#: pool, in pool order.
BACKGROUND_GIN_INDEXES: tuple[str, ...] = tuple(
    name for name in FLUSHED_GIN_INDEXES if name not in EVENTS_GIN_INDEXES
)

#: The events pass starts no new flush once this much of it has elapsed. With
#: `PER_INDEX_TIMEOUT_MS` the longest a fire can hold its realtime slot is
#: 20 + 15 s, under the task's 45 s soft limit.
EVENTS_PASS_BUDGET_S = 20.0

#: The bound on the longest uninterrupted operation — one flush of one index.
#: Well under the task's own `soft_time_limit`, which is itself well under the
#: 300 s global hard `task_time_limit` (a SIGKILL, which would be recorded as
#: `no_data` rather than as a failure).
PER_INDEX_TIMEOUT_MS = 15_000


def gin_flush_enabled() -> bool:
    """Rollback without a deploy. Defaults ON; set to 0/false to disable.

    The switch exists so the rollback of this queue is a config change rather
    than a revert — it is not a rollout gate and it is not meant to be set.
    """
    raw = os.environ.get("SEARCH_GIN_FLUSH_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def events_gin_flush_enabled() -> bool:
    """Rollback of the `realtime` events beat without a deploy. Defaults ON.

    Off, the events pass skips and the `background` pass takes its five
    indexes back — exactly the state before the events beat existed.
    """
    raw = os.environ.get("EVENTS_GIN_FLUSH_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def background_pass_indexes() -> tuple[str, ...]:
    """The `background` pass: the whole pool if the events beat is off."""
    return BACKGROUND_GIN_INDEXES if events_gin_flush_enabled() else FLUSHED_GIN_INDEXES


async def _flush_one(session, index_name: str) -> int:
    """Flush one index's pending list; return the pages it reclaimed.

    ``gin_clean_pending_list`` is restricted to the index's owner. Every
    trigram index above is owned by the application role (verified against
    `pg_class.relowner` on production, 2026-08-28), so this is a permitted call
    and not a superuser one.

    The index name is validated against the frozen literal by the caller and
    then interpolated, because ``regclass`` will not take a bind parameter in
    this position on every driver path. The value can therefore only ever be
    one of the constants in `FLUSHED_GIN_INDEXES`. `ix_events_event_tags` was
    created by the same migration role as the trigram indexes (`add_event_tags`).
    """
    if index_name not in FLUSHED_GIN_INDEXES:
        raise ValueError(f"index not in the declared pool: {index_name!r}")
    await session.execute(
        text(f"SET LOCAL statement_timeout = {int(PER_INDEX_TIMEOUT_MS)}")
    )
    row = (
        await session.execute(
            text(f"SELECT gin_clean_pending_list('{index_name}'::regclass) AS pages")
        )
    ).first()
    pages = int(row.pages) if row is not None and row.pages is not None else 0
    return pages


async def _flush_gin_pending_lists() -> dict:
    """The `background` pass. Never raises; always returns a summary."""
    return await _flush_pass(
        background_pass_indexes(), enabled=gin_flush_enabled(), label="background"
    )


async def _flush_events_gin_pending_lists() -> dict:
    """The `realtime` events pass (#10090). Never raises; always returns a summary."""
    return await _flush_pass(
        EVENTS_GIN_INDEXES,
        enabled=gin_flush_enabled() and events_gin_flush_enabled(),
        label="events",
        pass_budget_s=EVENTS_PASS_BUDGET_S,
    )


async def _flush_pass(
    indexes: tuple[str, ...],
    *,
    enabled: bool,
    label: str,
    pass_budget_s: float | None = None,
) -> dict:
    """One pass over ``indexes``, in order. Never raises; always returns a summary."""
    started = time.perf_counter()
    if not enabled:
        return {
            "terminal": "skipped",
            "skip_reason": "disabled",
            "completed": 0,
            "total": 0,
            "pages_cleaned": 0,
            "per_index": {},
            "errors": [],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    from app.tasks.base import get_task_session

    per_index: dict[str, int] = {}
    errors: list[dict] = []
    budget_skipped: list[str] = []
    pages_total = 0

    async with get_task_session() as session:
        for index_name in indexes:
            if (
                pass_budget_s is not None
                and time.perf_counter() - started >= pass_budget_s
            ):
                budget_skipped.append(index_name)
                continue
            try:
                # A savepoint per index: a flush that fails (lock timeout, a
                # dropped index) must not poison the transaction the rest
                # still have to run in.
                async with session.begin_nested():
                    pages = await _flush_one(session, index_name)
                per_index[index_name] = pages
                pages_total += pages
            except Exception as exc:  # noqa: BLE001 — one index, not the pass
                logger.warning(
                    "gin pending-list flush failed for %s: %s", index_name, exc
                )
                errors.append({"index": index_name, "error": str(exc)[:300]})

    completed = len(per_index)
    total = len(indexes)
    if completed == 0:
        terminal = "failed"
    elif completed < total:
        terminal = "partial"
    else:
        terminal = "complete"

    summary = {
        "terminal": terminal,
        "completed": completed,
        "total": total,
        "pages_cleaned": pages_total,
        "per_index": per_index,
        "errors": errors,
        "budget_skipped": budget_skipped,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    logger.info(
        "gin_pending_list_flush pass=%s terminal=%s completed=%s/%s pages=%s "
        "elapsed_ms=%s",
        label,
        terminal,
        completed,
        total,
        pages_total,
        summary["elapsed_ms"],
    )
    return summary
