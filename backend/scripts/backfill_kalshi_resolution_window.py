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


#: A row is a candidate while the date we hold for it is still PROVISIONAL, i.e.
#: while the venue has not yet told us when trading actually stopped.
#:
#: `expiration_time IS NULL` alone — the original marker — is "have I ever touched
#: this row", and CAL-P992 measured what that costs. Kalshi sets `close_time` equal
#: to the backstop while a market is ACTIVE and rewrites it to the settlement
#: instant on finalize. So a row swept while its market was still trading is written
#: with `resolution_date == expiration_time`, which stamps the backstop column and
#: makes the row permanently unselectable — and then the market finalizes and the
#: open-market poll can never re-enumerate it (gotcha #33). The row keeps a future
#: date forever and no run of this script can reach it. Measured on production
#: 2026-09-02: 5,143 `status='open'` rows already sealed this way, five of them
#: (US Open `KXWTASETWINNER` / `KXATPEXACTMATCH` legs) finalized at the venue within
#: an hour of the sweep that sealed them.
#:
#: `resolution_date >= expiration_time` is the provisional test and it is a
#: PROVENANCE read, not a proxy: it is true exactly while `resolution_date` is still
#: a backstop. Once the venue rewrites `close_time`, `resolution_date` moves strictly
#: earlier, the row converges out, and it stays out — the same convergence the old
#: marker gave, keyed on the fact that makes the row done rather than on the fact
#: that we looked at it.
#:
#: `LIKE 'KX%'` rather than `~ '^KX'`: identical semantics for a left-anchored
#: literal prefix, sargable, and executable by the guard in
#: `tests/test_kalshi_resolution_backfill_script_989.py`, which runs this exact
#: string against a seeded table. A regex operator would have made the starvation
#: guard un-runnable, and an un-runnable guard is how the post-LIMIT floor shipped
#: in the first place. (It also excludes 211 legacy non-`KX` rows — all measured as
#: genuinely-future 2027-2032 political/macro markets, so not a dead-card source
#: today; named in #2773 rather than widened here.)
#:
#: ORDERING — `updated_at ASC`, NOT `market_tier ASC`. Tier-first is what the
#: original backlog wanted, but on the provisional population it starves: measured
#: 2026-09-02, tier 1+2 hold 2,951 provisional rows and tier 5 holds 2,038, so a
#: `--limit 500` run ordered by tier never reaches tier 5 at all — and tier 5 is
#: where the settled prop legs live. `updated_at ASC` is not a tie-break dressed up:
#: on a `status='open'` Kalshi row the 2h poller bumps `updated_at` only while the
#: venue still enumerates the market as open, so the moment Kalshi finalizes it the
#: stamp FREEZES (gotcha #33 read forwards). Least-recently-enumerated first is
#: therefore a direct observation of "most likely already settled", and it rotates,
#: so no row can be starved behind a prefix. `commence_time` cannot do this job:
#: 4,954 of the 5,143 sealed rows carry `commence_time = expiration_time`, the same
#: poisoned backstop, so a "has it commenced" gate would have missed all five of the
#: rows that motivated this change.
SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY updated_at ASC NULLS FIRST,
             market_tier ASC NULLS LAST,
             commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

#: What the batch does NOT cover. Reported every run so a bounded sweep can never
#: read as a complete one. `never_swept` / `provisional_recheck` split the eligible
#: population by which of the two selection reasons put the row there, because they
#: behave differently: the never-swept tail can only shrink (the poller writes
#: `expiration_time` on every upsert), while the provisional set refills every time
#: a market is swept before it settles.
COUNT_SQL = """
    SELECT
        count(*) AS eligible_total,
        count(*) FILTER (
            WHERE commence_time IS NOT NULL AND commence_time < :purge_floor
        ) AS excluded_purged,
        count(*) FILTER (WHERE expiration_time IS NULL) AS never_swept,
        count(*) FILTER (
            WHERE expiration_time IS NOT NULL
              AND (resolution_date IS NULL OR resolution_date >= expiration_time)
        ) AS provisional_recheck
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
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
    never_swept = int(totals[2]) if totals else -1
    provisional_recheck = int(totals[3]) if totals else -1

    stats = {
        "eligible_total": eligible_total,
        "excluded_purged": excluded_purged,
        # The two selection reasons, reported apart. `never_swept` is the original
        # backlog and can only shrink; `provisional_recheck` is the population that
        # refills whenever a market is swept before the venue settles it, and is the
        # reason this sweep is not a one-off (CAL-P992).
        "never_swept": never_swept,
        "provisional_recheck": provisional_recheck,
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
                f"eligible ({never_swept} never swept, {provisional_recheck} holding "
                f"a provisional date), {excluded_purged} of them past the purge "
                "floor. If eligible_total is 0 the migration may not have run; if it "
                "equals excluded_purged the recoverable population is exhausted."
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
