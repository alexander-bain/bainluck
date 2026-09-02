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

ORDERING — BOTH BOUNDS, AND BOTH IN THE PREDICATE (gotcha #41). This population
expires: Kalshi purges market data at >=74/<86 days, and 21 of 200 sampled tickers
already answer with an empty market list or an HTTP error. Oldest-first would
therefore spend the budget on rows that are already dead. Newest-first alone would
starve the tail. So the sweep is ordered by `market_tier ASC, commence_time DESC`
*within* a retention floor — the highest-visibility, most-recently-concluded markets
first, which is also the order that retires Discover page-one dead cards fastest.

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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

# `KalshiAPIService` — NOT `KalshiAPIClient`, which has never existed in
# `app.services.kalshi_api`. CERT-766 caught the wrong name as an ImportError
# raised before argparse ran, so the script could not select a row, let alone
# write one, and the catch-up this whole ship depends on was a no-op.
from app.services.kalshi_api import KalshiAPIService  # noqa: E402
from app.utils.kalshi_resolution_window import (  # noqa: E402
    derive_resolution_window,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS  # noqa: E402


@dataclass
class _Leg:
    close_time: Optional[datetime]
    expiration_time: Optional[datetime]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


#: The candidate population. `LIKE 'KX%'` rather than `~ '^KX'`: identical
#: semantics for a left-anchored literal prefix, sargable, and executable by the
#: guard in `tests/test_kalshi_resolution_backfill_script_989.py`, which runs this
#: exact string against a seeded table. A regex operator would have made the
#: starvation guard un-runnable, and an un-runnable guard is how the post-LIMIT
#: floor shipped in the first place.
SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND expiration_time IS NULL
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY market_tier ASC NULLS LAST, commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

#: What the batch does NOT cover. Reported every run so a bounded sweep can never
#: read as a complete one.
COUNT_SQL = """
    SELECT
        count(*) AS eligible_total,
        count(*) FILTER (
            WHERE commence_time IS NOT NULL AND commence_time < :purge_floor
        ) AS excluded_purged
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND expiration_time IS NULL
"""

#: `updated_at` is BOUND, not `now()`: the two date columns and the stamp then come
#: from one instant the caller controls, so the guard can assert on the exact
#: parameters that reach the driver instead of on a value the database invents.
UPDATE_SQL = """
    UPDATE futures_markets
    SET resolution_date = :resolution_date,
        expiration_time = :expiration_time,
        updated_at = :updated_at
    WHERE id = :id
"""


async def run_backfill(
    *,
    session_maker: Callable,
    client_factory: Callable[[], object],
    limit: int = 200,
    offset: int = 0,
    apply: bool = False,
    concurrency: int = 6,
    now: Optional[datetime] = None,
) -> dict:
    """Select, derive and (optionally) write. Every dependency is a parameter.

    `session_maker` and `client_factory` are injected rather than imported at the
    call site so the composed guard can drive this whole path — selection,
    derivation, and the two-column UPDATE — against a seeded table and a faked
    venue. `now` is a parameter for the same reason the derivation takes no clock
    (gotcha #44): the retention floor must not move under a test.
    """
    now = now or datetime.now(timezone.utc)
    purge_floor = now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

    async with session_maker() as session:
        rows = (
            await session.execute(
                text(SELECT_SQL),
                {"purge_floor": purge_floor, "limit": limit, "offset": offset},
            )
        ).all()
        totals = (
            await session.execute(text(COUNT_SQL), {"purge_floor": purge_floor})
        ).first()

    eligible_total = int(totals[0]) if totals else -1
    excluded_purged = int(totals[1]) if totals else -1

    stats = {
        "eligible_total": eligible_total,
        "excluded_purged": excluded_purged,
        "candidates": len(rows),
        "moved_earlier": 0,
        "unchanged": 0,
        "newly_past": 0,
        "fallback_no_close_time": 0,
        "unresolvable_at_venue": 0,
        "errors": 0,
    }
    samples: list[dict] = []

    if not rows:
        # Not a success. Either the migration has not run, or the floor has
        # excluded everything left — two very different facts, so print both
        # numbers rather than one word.
        stats["writes_prepared"] = 0
        stats["writes_applied"] = 0
        return {
            "mode": "APPLY" if apply else "DRY_RUN",
            "measured_at": now.isoformat(),
            "purge_floor": purge_floor.isoformat(),
            "zero_yield": True,
            "zero_yield_reason": (
                f"no candidates at offset {offset}: {eligible_total} rows still "
                f"eligible, {excluded_purged} of them past the purge floor. If "
                "eligible_total is 0 the migration may not have run; if it equals "
                "excluded_purged the recoverable population is exhausted."
            ),
            "stats": stats,
            "newly_past_samples": [],
        }

    sem = asyncio.Semaphore(concurrency)
    client = client_factory()

    async def handle(row) -> Optional[dict]:
        market_id, ticker, stored_rd, commence, tier = row

        async with sem:
            try:
                event = await client.get_event(ticker, with_nested_markets=True)
            except Exception:
                stats["errors"] += 1
                return None

        markets = (event or {}).get("markets") or []
        if not markets:
            # 200-with-no-markets and 404 are NOT the same fact, but neither
            # yields a date. Counted apart from errors so a zero-yield run
            # cannot read as a clean one.
            stats["unresolvable_at_venue"] += 1
            return None

        window = derive_resolution_window(
            [
                _Leg(_parse(m.get("close_time")), _parse(m.get("expiration_time")))
                for m in markets
            ]
        )
        if window.resolution_date is None:
            stats["unresolvable_at_venue"] += 1
            return None
        if window.used_expiration_fallback:
            stats["fallback_no_close_time"] += 1

        if stored_rd is not None and window.resolution_date < stored_rd:
            stats["moved_earlier"] += 1
            if stored_rd > now >= window.resolution_date:
                stats["newly_past"] += 1
                if len(samples) < 15:
                    samples.append(
                        {
                            "id": market_id,
                            "ticker": ticker,
                            "tier": tier,
                            "was": stored_rd.isoformat(),
                            "now": window.resolution_date.isoformat(),
                        }
                    )
        else:
            stats["unchanged"] += 1

        return {
            "id": market_id,
            "resolution_date": window.resolution_date,
            "expiration_time": window.expiration_time,
            "updated_at": now,
        }

    try:
        results = await asyncio.gather(*(handle(r) for r in rows))
    finally:
        # `BaseAPIClient` exposes `close()` and no `__aenter__`, so `async with`
        # on the service raises AttributeError. Explicit try/finally instead.
        close = getattr(client, "close", None)
        if close is not None:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe

    writes = [r for r in results if r]
    stats["writes_prepared"] = len(writes)

    if apply and writes:
        async with session_maker() as session:
            for chunk_start in range(0, len(writes), 500):
                chunk = writes[chunk_start : chunk_start + 500]
                for w in chunk:
                    await session.execute(text(UPDATE_SQL), w)
                await session.commit()
        stats["writes_applied"] = len(writes)
    else:
        stats["writes_applied"] = 0

    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "purge_floor": purge_floor.isoformat(),
        "offset": offset,
        "zero_yield": len(writes) == 0,
        "stats": stats,
        "newly_past_samples": samples,
    }
    if stats["unresolvable_at_venue"] == len(rows):
        # Every slot in the batch went to a row this script may not write. Those
        # rows keep their slot, so an unattended re-run selects them again.
        report["batch_fully_unresolvable"] = (
            f"all {len(rows)} selected rows were unresolvable at the venue and "
            "none can be written (a missing date is not a status change). "
            f"Re-running at --offset {offset} selects the same rows; advance the "
            "offset to reach the recoverable tail."
        )
    return report


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
