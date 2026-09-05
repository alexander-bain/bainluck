"""Reproduce `market_backfill_unmatched` at the venue, one series at a time.

#3149's batched backfill asks Kalshi once per SERIES and then matches the
returned markets back to the candidate events by `event_ticker`. The beat of
2026-09-05 10:45Z reported `filled=3816`, `unmatched=7722`, `candidates=11538`
— the two halves sum exactly, so every candidate was attempted and 7722 of them
found no market carrying their own ticker.

`unmatched` cannot say WHY on its own, and the aggregate has two very different
explanations that must not be conflated (notice 26 — measure the venue, not our
mirror):

* **ours** — a case/format mismatch, a series whose markets sit past
  `_BACKFILL_SERIES_MAX_PAGES`, or `event_series_ticker` mis-splitting. Fixable.
* **the venue's** — the event exists but has no markets at all, which is the
  documented Kalshi retention shape (gotcha #35: EVENT data is permanent,
  MARKET data purges at >=74/<86 days). Not fixable by us at any page budget.

So this asks the venue both questions for one series and reports the split:

    python3 scripts/probe_backfill_unmatched.py KXMLBGAME KXNFLGAME

For every series it prints how many of the venue's own events carry zero
markets under the exact fetch the backfill runs, and the age distribution of
those events, so the retention explanation can be confirmed or refused rather
than assumed.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from urllib.request import Request, urlopen
import json

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Mirrors app/services/kalshi_api.py's backfill loop exactly. A probe that
# fetches more pages than the code does would report a bug the code cannot see.
MAX_PAGES = 10
PAGE_LIMIT = 1000

#: `KXMLBGAME-26SEP072205TORATH` -> 2026-09-07. Kalshi's game tickers carry the
#: date in the suffix; this is the only per-event date available without a
#: second request per event, and it is what the retention question needs.
_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def _get(path: str) -> dict:
    req = Request(f"{BASE}{path}", headers={"User-Agent": "bainluck-probe/1"})
    with urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())


def ticker_date(event_ticker: str) -> Optional[datetime]:
    m = _DATE_RE.search(event_ticker or "")
    if not m:
        return None
    yy, mon, dd = m.groups()
    if mon not in _MONTHS:
        return None
    try:
        return datetime(2000 + int(yy), _MONTHS[mon], int(dd), tzinfo=timezone.utc)
    except ValueError:
        return None


def probe(series: str) -> None:
    now = datetime.now(timezone.utc)

    events: list[str] = []
    cursor = ""
    while True:
        q = f"/events?series_ticker={series}&limit=200"
        if cursor:
            q += f"&cursor={cursor}"
        page = _get(q)
        events.extend((e.get("event_ticker") or "").upper()
                      for e in page.get("events") or [])
        cursor = page.get("cursor") or ""
        if not cursor:
            break
        time.sleep(0.3)

    with_markets: set[str] = set()
    requests = 0
    cursor = ""
    for _ in range(MAX_PAGES):
        q = f"/markets?series_ticker={series}&limit={PAGE_LIMIT}"
        if cursor:
            q += f"&cursor={cursor}"
        page = _get(q)
        requests += 1
        markets = page.get("markets") or []
        for m in markets:
            with_markets.add((m.get("event_ticker") or "").upper())
        cursor = page.get("cursor") or ""
        if not cursor or not markets:
            break
        time.sleep(0.3)

    unmatched = [e for e in events if e not in with_markets]
    ages = Counter()
    undated = 0
    for e in unmatched:
        d = ticker_date(e)
        if d is None:
            undated += 1
            continue
        age = (now - d).days
        if age < 0:
            ages["future"] += 1
        elif age < 74:
            ages["0-73d"] += 1
        elif age < 86:
            ages["74-85d (purge window)"] += 1
        else:
            ages[">=86d (purged)"] += 1

    print(f"\n=== {series} ===")
    print(f"  venue events          : {len(events)}")
    print(f"  market pages fetched  : {requests} (cap {MAX_PAGES})")
    print(f"  events with >=1 market: {len(with_markets & set(events))}")
    print(f"  events with 0 markets : {len(unmatched)}")
    if unmatched:
        for k in ["future", "0-73d", "74-85d (purge window)", ">=86d (purged)"]:
            if ages[k]:
                print(f"      {k:<24}: {ages[k]}")
        if undated:
            print(f"      {'undated ticker':<24}: {undated}")
        print(f"  sample: {unmatched[:5]}")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["KXMLBGAME"]:
        try:
            probe(s)
        except Exception as exc:  # noqa: BLE001 — a probe reports, never raises
            print(f"\n=== {s} ===\n  FAILED: {exc}")
