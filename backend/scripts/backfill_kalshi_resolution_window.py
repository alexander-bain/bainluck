"""Re-derive `resolution_date` from Kalshi `close_time` for existing open rows.

CAL-P989 (#2660, #1818). The poller fix only reaches rows the poller re-upserts,
and `kalshi_api.py:895` enumerates the venue with `status="open"` — so an event
Kalshi has already FINALIZED is never enumerated again and never receives its
close_time (gotcha #33, the same shape that made #1818 a standing population).
That is what this one-off catch-up is for.

    Dry run (default — reads the venue, writes NOTHING):
        python3 scripts/backfill_kalshi_resolution_window.py --limit 500

    Apply:
        python3 scripts/backfill_kalshi_resolution_window.py --limit 500 --apply

WHAT IT WRITES. For each `source='kalshi'`, `status='open'` row it fetches the
event, derives the window with the same pure function the poller now uses, and
sets `resolution_date = max(close_time)` and `expiration_time = max(expiration_time)`.
It never touches `status`, `is_winner`, prices, or any other column: a wrong date
and a wrong grade are different defects with different blast radii, and moving both
at once is how #1852 happened (CAL-P061's design constraint, inherited here).

NOT A ONE-OFF — CAL-P992, and this is the correction that matters. The first sweep
(2026-09-02, 8,986 rows) drained the backlog and then quietly re-created it, because
its progress marker was "have I written this row" rather than "is this row's date
final". Kalshi sets `close_time` equal to the backstop while a market is ACTIVE and
rewrites it to the settlement instant on finalize, so every row swept mid-life was
written with the backstop, had `expiration_time` stamped, and became unselectable —
and the open-market poll can never re-enumerate it once it finalizes (gotcha #33).
Five US Open prop legs finalized within the hour after the sweep that sealed them,
and 5,143 `status='open'` rows are sitting in that trap now. So the candidate test is
`resolution_date >= expiration_time` — the date is provisional until the venue moves
it earlier — and this script is a REPEATABLE sweep whose population refills daily,
not a catch-up that can be run once and retired.

ORDERING — BOTH BOUNDS, AND BOTH IN THE PREDICATE (gotcha #41). This population
expires: Kalshi purges market data at >=74/<86 days, and 21 of 200 sampled tickers
already answer with an empty market list or an HTTP error. Oldest-first would
therefore spend the budget on rows that are already dead. Newest-first alone would
starve the tail. So the sweep runs *within* a retention floor, ordered by
`updated_at ASC` — least-recently-enumerated first. On a `status='open'` Kalshi row
that stamp is bumped by the 2h poller only while the venue still lists the market, so
it freezes the moment Kalshi finalizes: the ordering reads "most likely already
settled" straight off the venue's own behaviour, and because every write refreshes
the stamp it rotates, which is what bounds the sweep's reach to ceil(N/limit) runs.
`market_tier ASC, commence_time DESC` — the original key — is kept only as a
tie-break: measured 2026-09-02, tier-first strands all 2,038 tier-5 provisional rows
behind 2,951 tier-1/2 rows, and tier 5 is where the settled prop legs live.

    THE FLOOR IS IN THE `WHERE` CLAUSE, NOT IN PYTHON AFTER THE `LIMIT`.
    CERT-766 reproduced why: with the floor applied post-LIMIT, a batch of 500
    provably-purged tier-1 rows filled the whole limit, prepared zero writes, and
    left a recoverable tier-2 row unselected. Nothing in that run wrote
    `expiration_time`, so the next run selected the same 500 dead rows, and the
    recoverable row was stranded FOREVER. A skip that does not free its slot is
    not a skip, it is a permanent starvation. Excluded rows are still COUNTED and
    reported (`excluded_purged`) so the truncation is loud rather than silent.

ZERO-YIELD IS LOUD. An empty result is reported as its own outcome with the reason
attached, never as success: a 200 with no markets is the retention cliff wearing the
same shape as "no such event" (gotcha #53), and "it returned" is not "it worked".

THE ONE STARVATION THIS DOES NOT CLOSE, NAMED RATHER THAN HIDDEN. A row *inside*
the retention floor whose ticker the venue cannot resolve (404, or 200-with-no-
markets) yields no date, so there is nothing this script is allowed to write for it
— `status` and `is_winner` belong to a different repair. Such rows keep their slot
across runs. The report calls that out by name (`unresolvable_at_venue`, and a loud
BATCH FULLY UNRESOLVABLE banner when they consume the entire batch), and `--offset`
exists so an operator can advance past a stuck prefix rather than re-running into it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(0, ".")

# CAL-P998 / D47: the repair itself now lives in the APP, at
# `app/tasks/kalshi_resolution_sweep.py`, and this file is the attended CLI over
# it. The direction is load-bearing and it is the whole reason for the move: a
# Celery task cannot import from `scripts/` (not on the dyno's path), so while
# the predicate lived here the sweep could only ever be run by a human — and
# nobody did. The sealed population went 5,143 (2026-09-03 05:00Z) to 5,137
# (same day 22:0xZ). Everything below is IMPORTED, never restated, so the
# attended run and the daily beat cannot drift into scoring different rows.
#
# The module-level docstring above is kept verbatim: it is the derivation of the
# predicate, the ordering and the retention floor, and it is cited by
# `tests/test_kalshi_resolution_backfill_script_989.py`, CERT-766 and #2771.
from app.tasks.kalshi_resolution_sweep import (  # noqa: E402
    COUNT_SQL,
    SELECT_SQL,
    UPDATE_SQL,
    SWEEP_BATCH_LIMIT,
    SWEEP_CONCURRENCY,
    KalshiAPIService,
    run_backfill,
    run_sweep,
)

__all__ = [
    "COUNT_SQL", "SELECT_SQL", "UPDATE_SQL", "SWEEP_BATCH_LIMIT",
    "SWEEP_CONCURRENCY", "KalshiAPIService", "run_backfill", "run_sweep", "main",
]

async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--apply", action="store_true", help="write; default is dry run")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--out", default=None, help="write the JSON report here")
    args = ap.parse_args()

    from app.services.database import async_session_maker

    report = await run_backfill(
        session_maker=async_session_maker,
        client_factory=KalshiAPIService,
        limit=args.limit,
        offset=args.offset,
        apply=args.apply,
        concurrency=args.concurrency,
    )

    print(json.dumps(report, indent=2, default=str))
    if report.get("zero_yield"):
        print(
            "ZERO YIELD — this run prepared no writes. That is a reportable "
            "outcome, not a success.",
            flush=True,
        )
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(report, handle, indent=2, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
