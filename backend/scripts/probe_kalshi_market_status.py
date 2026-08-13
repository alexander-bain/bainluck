#!/usr/bin/env python3
"""Measure Kalshi's live market ``status`` vocabulary, and which values carry a result.

CAL-P049 (#1818). The sibling of ``probe_kalshi_retention.py``, and it exists for
the same reason: ``app/utils/kalshi_market_status.py`` carries a set that decides
whether ``futures_markets.status`` says ``resolved``, and a constant nobody can
re-check becomes folklore. This one had already rotted — the poll tested
``status in ("closed", "settled")`` when ``settled`` does not exist as a market
status and ``closed`` is precisely the value that carries NO result, so the
predicate matched none of the real settlements and one non-settlement, and the
poll rewrote every finalized event back to ``'open'`` on every cycle.

Uses the PUBLIC Kalshi API — no key, no admin token, no database. Safe to run
from anywhere, including a session that has spent its production-read budget.

    python3 scripts/probe_kalshi_market_status.py                 # vocabulary sweep
    python3 scripts/probe_kalshi_market_status.py EVENT_TICKER... # named events

Reading the output: the ``result`` column is the load-bearing one. A status that
never carries a result is not a settlement no matter how terminal it sounds, and
a predicate that treats it as one writes ``resolved`` over markets nobody graded.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

BASE = "https://api.elections.kalshi.com/trade-api/v2"

#: Event-listing statuses to sweep. Kalshi's EVENT status and its MARKET status
#: are different vocabularies — a ``closed`` event holds ``finalized`` markets —
#: so all three listings are swept to see the full market-level range.
EVENT_LISTING_STATUSES = ("open", "closed", "settled")

PAGE_LIMIT = 100


def _get(path: str, **params) -> tuple[int, dict | None]:
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _markets_of(event_body: dict | None) -> list[dict]:
    """Pull nested markets out of a single-event response.

    NOTE the shape trap, hit live while writing this: ``GET /events/{ticker}``
    returns BOTH a top-level ``markets`` key (EMPTY) and the real list under
    ``event.markets``. Reading the top-level key gives ``[]`` for a perfectly
    healthy settled event — an empty 200 that means nothing at all (gotcha #53).
    """
    if not event_body:
        return []
    event = event_body.get("event") or {}
    return event.get("markets") or event_body.get("markets") or []


def _tally(markets, into: Counter) -> None:
    for m in markets:
        status = m.get("status")
        result = m.get("result")
        into[(status, "has_result" if result not in (None, "") else "no_result")] += 1


def main(argv: list[str]) -> int:
    tally: Counter = Counter()

    if argv:
        print(f"### named events ({len(argv)})")
        for ticker in argv:
            code, body = _get(f"/events/{ticker}", with_nested_markets="true")
            markets = _markets_of(body)
            statuses = Counter(m.get("status") for m in markets)
            results = Counter(m.get("result") for m in markets)
            print(
                f"  {ticker:34s} HTTP {code}  markets={len(markets):4d}  "
                f"statuses={dict(statuses)}  results={dict(results)}"
            )
            _tally(markets, tally)
    else:
        for listing in EVENT_LISTING_STATUSES:
            code, body = _get(
                "/events",
                status=listing,
                with_nested_markets="true",
                limit=PAGE_LIMIT,
            )
            events = (body or {}).get("events") or []
            n_before = sum(tally.values())
            for ev in events:
                _tally(ev.get("markets") or [], tally)
            print(
                f"### /events?status={listing:8s} HTTP {code}  "
                f"events={len(events):4d}  markets={sum(tally.values()) - n_before}"
            )

    if not tally:
        print("\ninconclusive — no markets came back. Re-run; do NOT read an empty")
        print("response as evidence that a status value is gone (gotcha #53).")
        return 1

    print("\n### market.status vocabulary observed")
    print(f"  {'status':14s} {'has_result':>11s} {'no_result':>10s}   verdict")
    statuses = sorted({s for s, _ in tally})
    result_carrying = []
    for status in statuses:
        with_r = tally.get((status, "has_result"), 0)
        without_r = tally.get((status, "no_result"), 0)
        if with_r and not without_r:
            verdict = "RESULT-CARRYING"
            result_carrying.append(status)
        elif with_r:
            verdict = "MIXED — investigate before trusting"
            result_carrying.append(status)
        else:
            verdict = "never carries a result"
        print(f"  {str(status):14s} {with_r:11d} {without_r:10d}   {verdict}")

    print("\n### compare against the shipped constants")
    # ``python3 scripts/x.py`` puts backend/scripts on sys.path, not backend — so
    # without this the diff silently degrades to "couldn't import" and the probe
    # reports only half its job. Add the package root explicitly.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from app.utils.kalshi_market_status import (  # noqa: PLC0415
            MEASURED_ON,
            RESULT_CARRYING_STATUSES,
            TERMINAL_STATUSES,
        )
    except Exception as exc:
        # Name the failure. "couldn't import" with no reason is how a probe ends
        # up reporting a green half-run for months.
        print(f"  cannot diff the constants — import failed: {exc!r}")
        return 0

    observed = set(result_carrying)
    print(f"  measured_on                : {MEASURED_ON}")
    print(f"  RESULT_CARRYING (shipped)  : {sorted(RESULT_CARRYING_STATUSES)}")
    print(f"  RESULT_CARRYING (observed) : {sorted(observed)}")
    missing = observed - set(RESULT_CARRYING_STATUSES)
    stale = set(RESULT_CARRYING_STATUSES) - observed
    unknown = set(statuses) - set(TERMINAL_STATUSES) - {None}
    if missing:
        print(f"  !! observed but NOT shipped: {sorted(missing)} — settlements are being missed")
    if stale:
        print(f"  ?  shipped but not observed: {sorted(stale)} — harmless, but re-date the table")
    if unknown:
        print(f"  .  non-terminal statuses   : {sorted(unknown)}")
    if not missing:
        print("  => shipped set covers every result-carrying status observed.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
