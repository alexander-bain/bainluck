#!/usr/bin/env python3
"""Align Kalshi's OWN hourly candles with the rows we stored from them.

Why this exists (CAL-P1084, #4730). `KalshiAPIService.get_market_candlesticks`
reduces a candle to (bid+ask)/2 and falls back to whichever side is non-zero.
Its docstring names the flaw and names `_backfill_kalshi_price_history` — a
calibration feeder — as a consumer it deliberately left alone. This tool proves
what that costs on real markets, by running BOTH reducers over the venue's own
payload and putting the result next to the row in `futures_odds_snapshots`:

  * `shipped`  — the reducer in `kalshi_api.get_market_candlesticks` today
  * `chart`    — `event_chart_backfill.normalize_candle`, the corrected one
  * `trade`    — the candle's own `price.close_dollars`, i.e. what traded

Both reducers are RE-IMPLEMENTED here on purpose: this tool has to be runnable
against production data from a laptop without importing the app, and the two
implementations are eight lines each. If either moves in `backend/`, this file
is stale and its header says so — check before quoting its numbers.

Usage:
    source ~/.claude/.env
    python3 tools/cal-1084-candle-vs-stored.py <event_ticker> [max_markets]

Reads BAINLUCK_API / ADMIN_TOKEN for the stored side; the venue side is a public
Kalshi read (no key) via the series/event structure, never a guessed ticker
(standing notice 26).
"""
import json
import os
import sys
import time
import urllib.request

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def _dollars(block, *keys):
    if not isinstance(block, dict):
        return None
    for k in keys:
        v = block.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def shipped_reducer(candle):
    """`kalshi_api.get_market_candlesticks` — bid/ask only, no spread guard."""
    bid = _dollars(candle.get("yes_bid"), "close_dollars") or 0.0
    ask = _dollars(candle.get("yes_ask"), "close_dollars") or 0.0
    if bid > 0 and ask > 0:
        price = (bid + ask) / 2
    elif ask > 0:
        price = ask
    elif bid > 0:
        price = bid
    else:
        return None
    # the writer's own filter: `if prob <= 0 or prob >= 1: continue`
    return None if price <= 0 or price >= 1 else price


def chart_reducer(candle, wide=0.10):  # event_chart_backfill.WIDE_SPREAD_DOLLARS
    """`event_chart_backfill.normalize_candle` — trade beats a wide book."""
    bid = _dollars(candle.get("yes_bid"), "close_dollars")
    ask = _dollars(candle.get("yes_ask"), "close_dollars")
    last = _dollars(candle.get("price"), "close_dollars", "mean_dollars", "previous_dollars")

    def usable(v):
        return v is not None and 0.0 < v < 1.0

    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        if (ask - bid) <= wide:
            return (bid + ask) / 2.0
    if usable(last):
        return last
    if usable(bid) and not usable(ask):
        return bid
    if usable(ask) and not usable(bid):
        return ask
    if usable(bid) and usable(ask):
        return (bid + ask) / 2.0
    return None


def stored_rows(tickers):
    """captured_at -> probability, per ticker, from futures_odds_snapshots."""
    api = os.environ["BAINLUCK_API"].rstrip("/")
    token = os.environ["ADMIN_TOKEN"]
    in_list = ",".join("'" + t.replace("'", "") + "'" for t in tickers)
    sql = f"""
        SELECT fo.external_id,
               extract(epoch FROM s.captured_at)::bigint AS ts,
               s.probability
        FROM futures_odds_snapshots s
        JOIN futures_outcomes fo ON fo.id = s.outcome_id
        WHERE fo.external_id IN ({in_list})
          AND s.bookmaker = 'kalshi'
    """
    req = urllib.request.Request(
        f"{api}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": 5000}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    out = {}
    for tk, ts, prob in body.get("rows") or []:
        out.setdefault(tk, {})[int(ts)] = float(prob)
    return out


def main():
    event = sys.argv[1]
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    ev = _get(f"{KALSHI}/events/{event}?with_nested_markets=true")
    markets = (ev.get("event") or {}).get("markets") or ev.get("markets") or []
    markets = markets[:cap]
    stored = stored_rows([m["ticker"] for m in markets])

    start = int(time.time()) - 45 * 86400
    end = int(time.time())
    print("ticker\tplayer\tresult\tts\tvenue_bid\tvenue_ask\ttrade\tshipped\tchart\tstored")
    for m in markets:
        tk = m["ticker"]
        try:
            raw = _get(
                f"{KALSHI}/markets/candlesticks?market_tickers={tk}"
                f"&period_interval=60&start_ts={start}&end_ts={end}"
            )
        except Exception as e:  # purged, rate-limited, or gone
            print(f"{tk}\t{m.get('yes_sub_title')}\t{m.get('result')}\tVENUE_ERROR\t{e}")
            continue
        candles = (raw.get("markets") or [{}])[0].get("candlesticks") or []
        for c in candles:
            ts = c.get("end_period_ts")
            sh = shipped_reducer(c)
            if sh is None:
                continue  # the writer stored nothing for this candle
            ch = chart_reducer(c)
            tr = _dollars(c.get("price"), "close_dollars")
            st = stored.get(tk, {}).get(int(ts))
            print(
                f"{tk}\t{m.get('yes_sub_title')}\t{m.get('result')}\t{ts}\t"
                f"{_dollars(c.get('yes_bid'), 'close_dollars')}\t"
                f"{_dollars(c.get('yes_ask'), 'close_dollars')}\t"
                f"{'' if tr is None else round(tr, 4)}\t{round(sh, 4)}\t"
                f"{'' if ch is None else round(ch, 4)}\t{'' if st is None else round(st, 4)}"
            )
        time.sleep(0.2)


if __name__ == "__main__":
    main()
