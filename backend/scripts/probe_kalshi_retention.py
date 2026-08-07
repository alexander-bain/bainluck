#!/usr/bin/env python3
"""Measure how long Kalshi actually keeps a settled market's price history.

CAL-P008 (#683). ``app/utils/kalshi_retention.py`` carries a horizon that decides
which rows the trade backfill is allowed to spend its budget on. A constant that
nobody can re-check becomes folklore (gotcha #35 sat at "~2-3 months, undated" for
ten weeks and no code could act on it), so the measurement ships with the constant.

Uses the PUBLIC Kalshi API — no key, no admin token, no database. It is therefore
safe to run from anywhere, including a session that has already spent its
production-read budget.

    python3 scripts/probe_kalshi_retention.py                    # series sweep
    python3 scripts/probe_kalshi_retention.py TICKER [TICKER...]  # named tickers

Reading the output: ``/markets`` 404 means the market is gone. ``/trades`` answers
200 with an EMPTY LIST for a market that no longer exists — it does not 404 — so
trades alone can never tell you whether a price is missing or merely untraded.
That conflation is the trap the horizon exists to avoid.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Series that carry enough settled volume to date the cliff. Game series live
# under the ...GAME suffix; the bare league prefix is the championship market.
DEFAULT_SERIES = ("KXNBAPTS", "KXNHL", "KXMLBHRR", "KXNASDAQ100U")


def _get(path: str, **params) -> tuple[int, dict | None]:
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "bainluck-retention-probe"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(2 + 3 * attempt)
                continue
            return exc.code, None
        except Exception:
            return -1, None
    return 429, None


def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


_TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    )
}


def age_from_ticker(ticker: str) -> float | None:
    """Age in days read out of the ticker's own ``-26MAR07`` date segment.

    A purged market cannot tell us when it settled — it 404s — so without this the
    probe can date the surviving side of the cliff and not the dead side, which is
    exactly the half that sets the bound.
    """
    match = _TICKER_DATE.search(ticker)
    if not match:
        return None
    yy, mon, dd = match.groups()
    month = _MONTHS.get(mon)
    if not month:
        return None
    try:
        ts = datetime(2000 + int(yy), month, int(dd), tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


def probe_ticker(ticker: str, close_iso: str | None = None) -> dict:
    """Probe one market: is it still there, and does it still have trades?"""
    market_status, market = _get(f"/markets/{ticker}")
    trades_status, trades = _get("/markets/trades", ticker=ticker, limit=100)
    n_trades = len(trades.get("trades", [])) if trades_status == 200 and trades else 0
    result = None
    if market_status == 200 and market:
        result = (market.get("market") or {}).get("result")
        close_iso = close_iso or (market.get("market") or {}).get("close_time")
    return {
        "ticker": ticker,
        "age_days": _age_days(close_iso) or age_from_ticker(ticker),
        "market_status": market_status,
        "trades_status": trades_status,
        "n_trades": n_trades,
        "result": result,
        "recoverable": market_status == 200 and n_trades > 0,
    }


def sweep_series(series: str, max_pages: int = 25) -> list[tuple[str, str]]:
    """Return (close_date, ticker) for every settled market the API will hand over.

    The depth this reaches is itself a finding: settled-event pagination stops long
    before the retention horizon, so tickers we already hold in our own DB are the
    only way to probe the older end.
    """
    cursor, pages, found = None, 0, []
    while pages < max_pages:
        params = {
            "status": "settled",
            "series_ticker": series,
            "limit": 200,
            "with_nested_markets": "true",
        }
        if cursor:
            params["cursor"] = cursor
        status, data = _get("/events", **params)
        if status != 200 or not data:
            break
        events = data.get("events", [])
        for event in events:
            for market in event.get("markets") or []:
                close = market.get("close_time") or market.get("expiration_time")
                if close and market.get("ticker"):
                    found.append((close[:10], market["ticker"]))
        cursor = data.get("cursor")
        pages += 1
        if not cursor or not events:
            break
    found.sort()
    return found


def _print(row: dict) -> None:
    age = f"{row['age_days']:.0f}d" if row["age_days"] is not None else "?"
    print(
        f"  {row['ticker']:46} age={age:>6} /markets={row['market_status']:>4} "
        f"/trades={row['trades_status']:>4} n={row['n_trades']:>3} "
        f"result={str(row['result']):>5} recoverable={row['recoverable']}"
    )


def main(argv: list[str]) -> int:
    rows: list[dict] = []
    if argv:
        print(f"### probing {len(argv)} named tickers")
        for ticker in argv:
            row = probe_ticker(ticker)
            rows.append(row)
            _print(row)
            time.sleep(0.15)
    else:
        for series in DEFAULT_SERIES:
            markets = sweep_series(series)
            if not markets:
                print(f"### {series}: no settled events returned")
                continue
            oldest, newest = markets[0][0], markets[-1][0]
            print(f"### {series}: {len(markets)} markets, pagination reaches {oldest}..{newest}")
            picks = {markets[0], markets[len(markets) // 2], markets[-1]}
            for close, ticker in sorted(picks):
                row = probe_ticker(ticker, close_iso=close + "T00:00:00Z")
                rows.append(row)
                _print(row)
                time.sleep(0.15)

    present = [r["age_days"] for r in rows if r["market_status"] == 200 and r["age_days"]]
    purged = [r["age_days"] for r in rows if r["market_status"] == 404 and r["age_days"]]
    print("\n### bounds")
    if present:
        print(f"  oldest still present : {max(present):.0f} days")
    if purged:
        print(f"  youngest purged      : {min(purged):.0f} days")
    if present and purged:
        print(
            f"  => retention is >= {max(present):.0f} and < {min(purged):.0f} days. "
            "Update BOTH bounds in app/utils/kalshi_retention.py together."
        )
    else:
        print("  inconclusive — probe both an old and a recent settled ticker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
