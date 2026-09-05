"""What the discovered-series fetch actually COSTS, per series, at the venue.

The tag census (`census_sports_tag_coverage.py`) says which tag is dark. This
says whether a second tag fits, and it is the question the widening turns on:
`_DISCOVERY_RESERVE_S` is 25.0s out of a 240s fetch budget already carved
60s guaranteed floor / 45s market backfill / 110s main scan, and today's
tennis-only selection is ~27 series.

Method: replay the shipped loop's exact per-series work — `sleep(0.2)` then
`get_events(status=open, series_ticker=…, with_nested_markets=True, limit=50)`
per page, then `_parse_events_offloaded` — against the live venue, and time it.
Nothing is written and no cache is touched. The parse is included deliberately:
#995 was a parse that held the GIL, so a cost model that times only the HTTP
call measures the wrong half.

The output that matters is `seconds/series` for tennis versus football. Football
tickers hold more nested markets per event (a KXNFLRACE event is a many-outcome
market, a KXATPDOUBLES event is one two-outcome market), so cost does NOT scale
with series count alone — assuming it does is how a reserve gets sized on the
cheap tag and spent by the expensive one.

Usage:

    cd backend && python3 scripts/probe_discovery_fetch_cost.py --tag Tennis
    cd backend && python3 scripts/probe_discovery_fetch_cost.py --tag Football --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Optional

sys.path.insert(0, ".")

from app.services.kalshi_api import (  # noqa: E402
    KalshiAPIService,
    _DISCOVERY_MAX_OPEN_EVENTS,
    _DISCOVERY_MAX_PAGES,
    _DISCOVERY_MAX_SERIES,
    _DISCOVERY_PAGE_LIMIT,
    _HEAVY_TOKENS,
    _SPORTS_SERIES_TICKERS,
)
from app.utils.kalshi_series_selection import select_discovered_series  # noqa: E402

sys.path.insert(0, "scripts")
from census_sports_tag_coverage import catalog_for_tag  # noqa: E402


async def time_series(svc: KalshiAPIService, ticker: str, pages: int) -> dict:
    """One series, fetched exactly as the shipped loop fetches it."""
    t0 = time.monotonic()
    returned = 0
    markets = 0
    cursor: Optional[str] = None
    err = None
    fetched_pages = 0
    try:
        for _ in range(pages):
            await asyncio.sleep(0.2)
            page, cursor = await asyncio.wait_for(
                svc.get_events(
                    status="open",
                    series_ticker=ticker,
                    with_nested_markets=True,
                    limit=_DISCOVERY_PAGE_LIMIT,
                    cursor=cursor,
                ),
                timeout=45.0,
            )
            for ed in page:
                markets += len(ed.get("markets") or [])
            parsed = await asyncio.wait_for(
                svc._parse_events_offloaded(page), timeout=60.0
            )
            returned += sum(1 for p in parsed if p)
            fetched_pages += 1
            if not cursor:
                break
    except Exception as e:  # noqa: BLE001 — a probe reports its own failures
        err = f"{type(e).__name__}: {e}"
    return {
        "ticker": ticker,
        "pages": fetched_pages,
        "returned": returned,
        "markets": markets,
        "elapsed_s": round(time.monotonic() - t0, 2),
        "error": err,
    }


async def main(tag: str, limit: Optional[int]) -> int:
    svc = KalshiAPIService()
    print(f"METHOD: venue catalog for tag={tag}, one open-listing census, then the "
          f"shipped per-series nested fetch, timed.\n")

    counts, census = await svc.census_open_series()
    tickers, cat = await catalog_for_tag(svc, tag)
    print(f"census: {census}\ncatalog[{tag}]: {cat}\n")

    selected, receipt = select_discovered_series(
        discovered=tickers,
        open_counts=counts,
        guaranteed=_SPORTS_SERIES_TICKERS,
        heavy_tokens=_HEAVY_TOKENS,
        max_series=_DISCOVERY_MAX_SERIES,
        max_open_events=_DISCOVERY_MAX_OPEN_EVENTS,
        page_limit=_DISCOVERY_PAGE_LIMIT,
        max_pages=_DISCOVERY_MAX_PAGES,
    )
    total_pages = sum(p for _, p in selected)
    print(f"selected {len(selected)} series, {total_pages} pages planned, "
          f"{receipt['selected_open_events']} open events expected")

    sample = selected if limit is None else selected[:limit]
    print(f"timing {len(sample)} of them\n")

    t0 = time.monotonic()
    rows = []
    for ticker, pages in sample:
        row = await time_series(svc, ticker, pages)
        rows.append(row)
        print(f"  {row['ticker']:<28} {row['elapsed_s']:>6.2f}s  "
              f"{row['pages']}p  ev={row['returned']:>3}  mkts={row['markets']:>5}"
              f"{'  ERR ' + str(row['error']) if row['error'] else ''}")
    wall = time.monotonic() - t0

    ok = [r for r in rows if not r["error"]]
    per_series = wall / max(1, len(ok))
    ev = sum(r["returned"] for r in ok)
    mk = sum(r["markets"] for r in ok)
    print(f"\n  sampled  {len(ok)} series in {wall:.1f}s  "
          f"-> {per_series:.2f}s/series, {ev} events, {mk} markets")
    print(f"  EXTRAPOLATED full {tag} selection ({len(selected)} series): "
          f"{per_series * len(selected):.0f}s")
    print("  discovery fetch reserve is 25.0s")
    await svc.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="Tennis")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.tag, args.limit)))
