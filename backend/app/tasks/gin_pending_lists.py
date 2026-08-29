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
sibling entry records for budget guards. A pass over seven indexes at a 2-minute
beat merges roughly one minute of accumulation each time, which is work an
inserting backend would otherwise do anyway; this moves it off the read path and
off whichever poll happened to cross the line, it does not create it.

ONE BAD INDEX MUST NOT WIPE THE PASS (gotcha #42): every index is attempted
inside its own try/except and its own savepoint, and damage lands in ``errors``.
The summary speaks `task_verdict`'s vocabulary, and the three terminals are
distinct on purpose — `complete` (all seven visited), `partial` (some visited),
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


async def _flush_one(session, index_name: str) -> int:
    """Flush one index's pending list; return the pages it reclaimed.

    ``gin_clean_pending_list`` is restricted to the index's owner. Every
    trigram index above is owned by the application role (verified against
    `pg_class.relowner` on production, 2026-08-28), so this is a permitted call
    and not a superuser one.

    The index name is validated against the frozen literal by the caller and
    then interpolated, because ``regclass`` will not take a bind parameter in
    this position on every driver path. The value can therefore only ever be
    one of seven constants defined in this module.
    """
    if index_name not in SEARCH_TRIGRAM_INDEXES:
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
    """One pass over the declared pool. Never raises; always returns a summary."""
    started = time.perf_counter()
    if not gin_flush_enabled():
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
    pages_total = 0

    async with get_task_session() as session:
        for index_name in SEARCH_TRIGRAM_INDEXES:
            try:
                # A savepoint per index: a flush that fails (lock timeout, a
                # dropped index) must not poison the transaction the next six
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
    total = len(SEARCH_TRIGRAM_INDEXES)
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
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    logger.info(
        "gin_pending_list_flush terminal=%s completed=%s/%s pages=%s elapsed_ms=%s",
        terminal,
        completed,
        total,
        pages_total,
        summary["elapsed_ms"],
    )
    return summary
