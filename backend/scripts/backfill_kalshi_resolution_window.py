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

ORDERING — BOTH BOUNDS, DELIBERATELY (gotcha #41). This population expires: Kalshi
purges market data at >=74/<86 days, and 21 of 200 sampled tickers already answer
with an empty market list or an HTTP error. Oldest-first would therefore spend the
budget on rows that are already dead. Newest-first alone would starve the tail. So
the sweep is ordered by `market_tier ASC, commence_time DESC` within a retention
floor: the highest-visibility, most-recently-concluded markets first — which is
also the order that retires Discover page-one dead cards fastest — and rows past
the provable purge horizon are reported as SKIPPED_PURGED rather than silently
dropped.

ZERO-YIELD IS LOUD. An empty result is reported as its own outcome with the reason
attached, never as success: a 200 with no markets is the retention cliff wearing the
same shape as "no such event" (gotcha #53), and "it returned" is not "it worked".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.services.kalshi_api import KalshiAPIClient  # noqa: E402
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


SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id ~ '^KX'
      AND expiration_time IS NULL
    ORDER BY market_tier ASC NULLS LAST, commence_time DESC NULLS LAST
    LIMIT :limit
"""

UPDATE_SQL = """
    UPDATE futures_markets
    SET resolution_date = :resolution_date,
        expiration_time = :expiration_time,
        updated_at = now()
    WHERE id = :id
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--apply", action="store_true", help="write; default is dry run")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--out", default=None, help="write the JSON report here")
    args = ap.parse_args()

    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        rows = (await session.execute(text(SELECT_SQL), {"limit": args.limit})).all()

    print(f"candidates: {len(rows)}", flush=True)
    if not rows:
        print(
            "ZERO CANDIDATES — nothing selected. This is a reportable outcome, "
            "not a success: check that the migration ran and that "
            "expiration_time is still NULL for open Kalshi rows."
        )
        return 0

    now = datetime.now(timezone.utc)
    purge_floor = now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

    stats = {
        "candidates": len(rows),
        "moved_earlier": 0,
        "unchanged": 0,
        "newly_past": 0,
        "fallback_no_close_time": 0,
        "skipped_purged": 0,
        "unresolvable_at_venue": 0,
        "errors": 0,
    }
    samples: list[dict] = []
    sem = asyncio.Semaphore(args.concurrency)

    async with KalshiAPIClient() as client:

        async def handle(row) -> Optional[dict]:
            market_id, ticker, stored_rd, commence, tier = row

            # Provably purged: fetching can only waste budget (gotcha #35, and the
            # UPPER bound because skipping work must fail-open).
            if commence is not None and commence < purge_floor:
                stats["skipped_purged"] += 1
                return None

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
            }

        results = await asyncio.gather(*(handle(r) for r in rows))

    writes = [r for r in results if r]
    stats["writes_prepared"] = len(writes)

    if args.apply and writes:
        from app.services.database import async_session_maker as maker

        async with maker() as session:
            for chunk_start in range(0, len(writes), 500):
                chunk = writes[chunk_start : chunk_start + 500]
                for w in chunk:
                    await session.execute(text(UPDATE_SQL), w)
                await session.commit()
        stats["writes_applied"] = len(writes)
    else:
        stats["writes_applied"] = 0

    report = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "stats": stats,
        "newly_past_samples": samples,
    }
    print(json.dumps(report, indent=2))
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(report, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
