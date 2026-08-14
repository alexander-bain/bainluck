#!/usr/bin/env python3
"""Compare our ``futures_markets.resolution_date`` against Kalshi's OWN timestamps.

CAL-P061 (#1868). 3,928 Kalshi markets carry an ``api_settlement`` all-loser grade
with a ``resolution_date`` that has **not arrived yet**. Two readings were possible
and they need different fixes: either the grade is premature, or the date is wrong.
This probe answers it from the venue rather than from the record of the venue.

WHAT IT MEASURES, per market, from ONE public payload (``GET /events/{ticker}``,
reading the TOP-LEVEL ``markets`` key — see :func:`probe_event` on why the
``with_nested_markets`` pairing matters):

    settlement_ts             the moment Kalshi actually settled the sub-market
    expiration_time           what we currently store as resolution_date
    expected_expiration_time  Kalshi's own realistic expiry estimate
    close_time                when trading stopped
    can_close_early           whether expiration_time is a backstop or a schedule

THE TRAP (gotcha #53). ``GET /events/{ticker}`` answers **HTTP 200 with
``markets: []``** for an event whose markets Kalshi has purged — the same shape as
a healthy event. "No settlement timestamp came back" is therefore not evidence
about settlement; it is not evidence about anything. Purged events are classified
``unaddressable`` and are EXCLUDED from the error distribution rather than folded
in as zeros, because averaging a retention artifact into a provenance measurement
is how you get a confident wrong number.

Public API: no key, no admin token, no database. The sample is supplied as JSON on
stdin or via --sample (the output of the CAL-P061 db-query), so this script never
needs production credentials.

    python3 scripts/probe_kalshi_resolution_date_provenance.py --sample sample.json
    python3 scripts/probe_kalshi_resolution_date_provenance.py --sample s.json --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"

#: Kalshi timestamp fields we compare. ``expiration_time`` is what the poller
#: currently writes; ``settlement_ts`` is the truth it should be measured against.
_TS_FIELDS = (
    "settlement_ts",
    "expiration_time",
    "expected_expiration_time",
    "latest_expiration_time",
    "close_time",
)


def _get(path: str, **params) -> tuple[int, dict | None]:
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "bainluck-cal-p061-provenance"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # Only 404 means "not there". Everything else is retried and then
            # surfaced — never collapsed into a None that reads as absence
            # (gotcha #36).
            if exc.code == 404:
                return 404, None
            if exc.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if attempt == 3:
                raise
            time.sleep(1 + attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(1 + attempt)
    return 0, None


def _parse_ts(val) -> datetime | None:
    if not val:
        return None
    s = str(val).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def probe_event(ticker: str) -> dict:
    """Return the venue's timestamp picture for one event ticker."""
    # ``with_nested_markets`` RELOCATES the markets, it does not gate them, and the
    # two halves of that pair must be read together. Measured 2026-08-14 on
    # ``KXNBAPTS-26JUN13NYKSAS``:
    #
    #     with_nested_markets=true   ->  event.markets = 58, top-level markets = []
    #     bare / =false              ->  event.markets = [], top-level markets = 58
    #
    # "Nested" means nested INSIDE ``event``. We read bare + top-level here, which
    # is a valid pairing. Mixing the halves — passing ``true`` and then reading the
    # top-level key — yields ``markets: []`` for every event alive or dead, which is
    # byte-identical to the retention cliff this probe exists to measure. That is
    # gotcha #53 in its most expensive costume: the false reading is the ALARMING
    # one, so it reads as a discovery rather than as a bug. It cost this window a
    # full 311-event run and a retracted production-bug claim before the shape of
    # the response was checked instead of assumed. Check the shape, not the count.
    status, body = _get(f"/events/{urllib.parse.quote(ticker)}")
    if status == 404 or body is None:
        return {"verdict": "event_404"}

    markets = body.get("markets") or []
    if not markets:
        # 200 with an empty list. NOT "never settled" — see the module docstring.
        return {"verdict": "unaddressable"}

    out: dict = {"verdict": "answered", "n_markets": len(markets)}
    for field in _TS_FIELDS:
        vals = [_parse_ts(m.get(field)) for m in markets]
        vals = [v for v in vals if v is not None]
        # The writer takes max() across the event's sub-markets, so mirror that
        # to test whether the mechanism reproduces exactly.
        out[f"max_{field}"] = max(vals) if vals else None
        out[f"n_{field}"] = len(vals)
    out["any_can_close_early"] = any(bool(m.get("can_close_early")) for m in markets)
    out["all_can_close_early"] = all(bool(m.get("can_close_early")) for m in markets)
    out["statuses"] = sorted({str(m.get("status") or "") for m in markets})
    out["results"] = sorted({str(m.get("result") or "") for m in markets})
    return out


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="JSON from the CAL-P061 db-query (default: stdin)")
    ap.add_argument("--json", dest="json_out", help="write full per-market rows here")
    ap.add_argument("--sleep", type=float, default=0.12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    raw = json.load(open(args.sample)) if args.sample else json.load(sys.stdin)
    cols = raw["columns"]
    rows = [dict(zip(cols, r)) for r in raw["rows"]]
    if args.limit:
        rows = rows[: args.limit]

    results = []
    for i, row in enumerate(rows, 1):
        ticker = row["external_id"]
        ours = _parse_ts(row["resolution_date"])
        venue = probe_event(ticker)
        rec = {
            "ticker": ticker,
            "cat": row.get("cat"),
            "band": row.get("band"),
            "our_resolution_date": ours.isoformat() if ours else None,
            **{
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in venue.items()
            },
        }
        settled = venue.get("max_settlement_ts")
        exp = venue.get("max_expiration_time")
        if ours and settled:
            rec["error_days"] = (ours - settled).total_seconds() / 86400.0
        if ours and exp:
            # Does our stored value reproduce max(expiration_time)? If yes, the
            # writer is named by measurement and not merely by code reading.
            rec["writer_match_seconds"] = abs((ours - exp).total_seconds())
        results.append(rec)
        if i % 25 == 0:
            print(f"  ... {i}/{len(rows)}", file=sys.stderr, flush=True)
        time.sleep(args.sleep)

    answered = [r for r in results if r.get("verdict") == "answered"]
    unaddr = [r for r in results if r.get("verdict") == "unaddressable"]
    e404 = [r for r in results if r.get("verdict") == "event_404"]
    errs = [r["error_days"] for r in answered if "error_days" in r]
    matches = [r["writer_match_seconds"] for r in answered if "writer_match_seconds" in r]

    print(f"\nCAL-P061 — resolution_date provenance probe  ({datetime.now(timezone.utc):%Y-%m-%d})")
    print(f"sampled: {len(results)}   answered: {len(answered)}   "
          f"unaddressable (200+empty): {len(unaddr)}   event_404: {len(e404)}")

    if matches:
        exact = sum(1 for m in matches if m <= 1.0)
        print("\nWRITER TEST — our resolution_date == venue max(expiration_time)?")
        print(f"  exact (<=1s): {exact}/{len(matches)} = {100*exact/len(matches):.1f}%")

    if errs:
        early = [e for e in errs if e > 0]
        print("\nERROR DISTRIBUTION — our resolution_date minus ACTUAL settlement_ts (days)")
        print(f"  n = {len(errs)}")
        print(f"  stored date LATER than settlement (i.e. wrong): "
              f"{len(early)}/{len(errs)} = {100*len(early)/len(errs):.1f}%")
        print(f"  min    {min(errs):10.2f}")
        for q, lbl in ((0.25, "p25"), (0.50, "median"), (0.75, "p75"),
                       (0.90, "p90"), (0.99, "p99")):
            print(f"  {lbl:6s} {_pct(errs, q):10.2f}")
        print(f"  max    {max(errs):10.2f}")
        print(f"  mean   {statistics.fmean(errs):10.2f}")
        buckets = [("<=0 (settled at/after stored date)", lambda e: e <= 0),
                   ("0-1d", lambda e: 0 < e <= 1),
                   ("1-7d", lambda e: 1 < e <= 7),
                   ("7-30d", lambda e: 7 < e <= 30),
                   ("30-180d", lambda e: 30 < e <= 180),
                   ("180-365d", lambda e: 180 < e <= 365),
                   (">365d", lambda e: e > 365)]
        print("\n  bucket                                count    share")
        for lbl, fn in buckets:
            n = sum(1 for e in errs if fn(e))
            print(f"  {lbl:36s} {n:6d}  {100*n/len(errs):6.1f}%")

        by_cat: dict[str, list[float]] = {}
        for r in answered:
            if "error_days" in r:
                by_cat.setdefault(r.get("cat") or "?", []).append(r["error_days"])
        print("\n  category            n    median_err_days")
        for cat, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
            print(f"  {cat:18s} {len(v):4d}    {_pct(v, 0.5):10.2f}")

    ece = [r for r in answered if r.get("any_can_close_early")]
    if answered:
        print(f"\ncan_close_early on >=1 sub-market: {len(ece)}/{len(answered)} "
              f"= {100*len(ece)/len(answered):.1f}%")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
