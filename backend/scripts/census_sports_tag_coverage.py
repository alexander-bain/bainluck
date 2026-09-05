"""Which SPORTS TAG is dark next — measured at the venue, not at our mirror.

Notice 26's method, stated up front: the catalog half is Kalshi's own
``/series?category=Sports&tags=<tag>`` walked to exhaustion for each of the nine
tags in ``KalshiAPIService.SPORTS_TAGS``; the live half is ONE
``status=open&with_nested_markets=false`` walk of the whole open listing, which
already counts open events for every series on the exchange regardless of tag.
Nothing here reads ``futures_markets`` or guesses a ticker.

Why this is worth a beat's worth of paging (QUEUE LAW). ``_DISCOVERY_TAGS`` is
``("Tennis",)``. For the other eight tags the hand list
``_SPORTS_SERIES_TICKERS`` IS the coverage rule, and for tennis that rule named 4
of 39 live series and left the US Open doubles draw unfetchable for five days.
This census says which tag currently holds the biggest live-but-uncarried
population, i.e. whose matches are missing from the site right now — and that
tag's matches are the next ship.

It also runs the real ``select_discovered_series`` per tag, so the answer is not
"how many series exist" but "how many this beat could actually take", with the
refusals broken out. ``heavy_payload_shape`` is expected to dominate the
ball-sport tags: their tickers are full of GAME/SPREAD/TOTAL/WINNER, which is
precisely the population #995 taught us to decline. A tag whose entire live
population is heavy is a real finding, reported as one.

Usage (no DB, no admin token, ~60-90s):

    cd backend && python3 scripts/census_sports_tag_coverage.py
    cd backend && python3 scripts/census_sports_tag_coverage.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
    _DISCOVERY_TAGS,
    _HEAVY_TOKENS,
    _SPORTS_SERIES_TICKERS,
)
from app.utils.kalshi_series_selection import select_discovered_series  # noqa: E402

#: Page ceiling for a per-tag catalog walk. `discover_series_for_tags` caps at 5
#: pages of 200 because it runs inside a 240s beat; a measurement is not on that
#: budget and a tag truncated at 1,000 series would understate exactly the thing
#: being measured. Truncation is reported either way.
CATALOG_MAX_PAGES = 40


async def catalog_for_tag(svc: KalshiAPIService, tag: str) -> tuple[list[str], dict]:
    """Every series ticker the venue lists for one tag, walked to exhaustion."""
    tickers: list[str] = []
    seen: set[str] = set()
    cursor: Optional[str] = None
    pages = 0
    exhausted = False
    error: Optional[str] = None

    try:
        while pages < CATALOG_MAX_PAGES:
            if pages:
                await asyncio.sleep(0.15)
            series_list, cursor = await asyncio.wait_for(
                svc.get_series(category="Sports", tags=tag, limit=200, cursor=cursor),
                timeout=30.0,
            )
            for s in series_list:
                t = (s.get("ticker") or "").strip().upper()
                if t and t not in seen:
                    seen.add(t)
                    tickers.append(t)
            pages += 1
            if not cursor or not series_list:
                exhausted = True
                break
    except Exception as e:  # noqa: BLE001 — a measurement reports its own gaps
        error = f"{type(e).__name__}: {e}"

    receipt = {"pages": pages, "series": len(tickers), "exhausted": exhausted}
    if error:
        receipt["error"] = error
    return tickers, receipt


def score_tag(tag: str, tickers: list[str], counts: dict[str, int]) -> dict:
    """What one beat could take from this tag, and what it would refuse and why."""
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
    live = {t: counts[t] for t in tickers if counts.get(t)}
    guaranteed = {g.upper() for g in _SPORTS_SERIES_TICKERS}
    # The ship-sized number: open events in series the venue lists, that carry
    # live events, and that the hand list does NOT name. Everything the hand
    # list already names is by definition not missing from the site.
    uncarried = {t: n for t, n in live.items() if t not in guaranteed}
    heavy = {
        t: n for t, n in uncarried.items()
        if any(tok in t for tok in _HEAVY_TOKENS)
    }
    return {
        "tag": tag,
        "series_listed": len(tickers),
        "series_live": len(live),
        "open_events_live": sum(live.values()),
        "series_uncarried": len(uncarried),
        "open_events_uncarried": sum(uncarried.values()),
        "uncarried_heavy_series": len(heavy),
        "uncarried_heavy_events": sum(heavy.values()),
        "selected_count": len(selected),
        "selected_open_events": receipt["selected_open_events"],
        "skipped": receipt["skipped"],
        "top_selected": [
            {"ticker": t, "open": receipt["selected_expected"][t], "pages": p}
            for t, p in selected[:10]
        ],
        "top_declined_heavy": [
            {"ticker": t, "open": n}
            for t, n in sorted(heavy.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ],
    }


async def main(out_path: Optional[str]) -> int:
    t0 = time.monotonic()
    svc = KalshiAPIService()
    tags = list(KalshiAPIService.SPORTS_TAGS)

    print(f"METHOD: venue catalog /series?category=Sports&tags=<tag> for {len(tags)} "
          f"tags, then ONE status=open census walk. No mirror reads.\n")

    # One census for every tag: the open walk is series-agnostic.
    counts, census = await svc.census_open_series()
    print(f"census: {census}\n")
    if not census.get("exhausted"):
        print("!! census did NOT exhaust — every number below is a LOWER BOUND\n")

    rows = []
    for tag in tags:
        tickers, cat = await catalog_for_tag(svc, tag)
        row = score_tag(tag, tickers, counts)
        row["catalog"] = cat
        row["discovery_enabled"] = tag in _DISCOVERY_TAGS
        rows.append(row)
        flag = "*" if row["discovery_enabled"] else " "
        print(
            f"{flag} {tag:<17} listed={row['series_listed']:>5} "
            f"live={row['series_live']:>4} openEv={row['open_events_live']:>5} "
            f"| UNCARRIED series={row['series_uncarried']:>4} "
            f"events={row['open_events_uncarried']:>5} "
            f"(heavy {row['uncarried_heavy_events']:>5}) "
            f"| selectable={row['selected_count']:>3} "
            f"ev={row['selected_open_events']:>5}"
        )

    print("\nRANKED by what one beat could actually take (selected_open_events):")
    for r in sorted(rows, key=lambda r: -r["selected_open_events"]):
        if r["discovery_enabled"]:
            continue
        print(f"  {r['tag']:<17} selectable={r['selected_count']:>3} series / "
              f"{r['selected_open_events']:>5} open events   skipped={r['skipped']}")
        for s in r["top_selected"][:5]:
            print(f"      + {s['ticker']:<28} {s['open']:>4} open  ({s['pages']}p)")
        for s in r["top_declined_heavy"][:3]:
            print(f"      - {s['ticker']:<28} {s['open']:>4} open  HEAVY, declined")

    payload = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "venue catalog per tag + one open-listing census",
        "census": census,
        "discovery_tags": list(_DISCOVERY_TAGS),
        "max_series": _DISCOVERY_MAX_SERIES,
        "tags": rows,
        "elapsed_s": round(time.monotonic() - t0, 1),
    }
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"\nwrote {out_path}")
    print(f"elapsed {payload['elapsed_s']}s")
    await svc.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="out", default=None)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.out)))
