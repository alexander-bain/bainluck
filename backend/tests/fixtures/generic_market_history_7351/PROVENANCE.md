# Fixture provenance — #7351 generic-market history acceptance

Read by `tests/integration/test_generic_market_history_7351_real_pg_redis.py`.
Nothing here is a credential; every request below was an unauthenticated public GET.

## Saved inputs from the #7351 brief (byte-identical copies)

Copied from `artifacts/other-model-generic-market-history-execution/inputs/`.
sha256 equals that folder's `SHA256SUMS`, and the test re-asserts each digest.

| file | what it is |
|---|---|
| `59165099-detail.json` | production `GET /api/futures/59165099`, fetched 2026-09-20T02:54:46Z |
| `59165099-history.json` | production `GET /api/futures/59165099/history?hours=168` |
| `59165099-timeline.json` | production `GET /api/futures/59165099/probability-timeline?hours=168&top=50` |
| `59165099-kalshi-7d-hourly.json` | Kalshi candlesticks, `period_interval=60`, `start_ts=1789268262&end_ts=1789873062`, fetched 2026-09-20T02:57:42Z |
| `59165099-kalshi-event.json` | Kalshi event read naming ticker `KXCAPGAINDOWN-26AUG-27JAN01` |

## REAL Kalshi responses fetched for this candidate (3 of the brief's 8 permitted provider GETs)

The brief's saved 7-day hourly response answers one of the three tiers the
existing fill requests. The other two tiers, and the fill's actual 31-day hourly
window, could not be answered from saved evidence, so they were fetched once
each — for the named ticker only — and saved unmodified. The test freezes its
clock at these requests' `end_ts` (1789875752 = 2026-09-20T03:42:32Z), so the
fill under test issues THESE EXACT requests and `test_B1` asserts that it does.

```
2026-09-20T03:42:32Z GET https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=KXCAPGAINDOWN-26AUG-27JAN01&period_interval=1&start_ts=1789789352&end_ts=1789875752      -> kalshi-1m-24h.json      (200, 2 candles)
2026-09-20T03:42:42Z GET https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=KXCAPGAINDOWN-26AUG-27JAN01&period_interval=60&start_ts=1787197352&end_ts=1789875752     -> kalshi-60m-31d.json     (200, 63 candles)
2026-09-20T03:42:43Z GET https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks?market_tickers=KXCAPGAINDOWN-26AUG-27JAN01&period_interval=1440&start_ts=1787093355&end_ts=1789875752   -> kalshi-1440m-life.json  (200, 27 candles)
```

`test_A2` proves the brief's ten saved hourly candles are, record for record, a
subset of `kalshi-60m-31d.json`.

## SYNTHETIC — everything Polymarket, and every Kalshi candle built by `_candle()`

No Polymarket byte in the test is a measured venue response. The Gamma event,
the condition id (`0xabab…`), both CLOB token ids and every `prices-history`
body are constructed inside the test file in the venues' documented shapes, to
exercise the REAL `PolymarketAPIService` parser and the real fill. They prove the
code path and the identity rules. They are NOT evidence of a live Polymarket
recovery, and nothing in the delivery claims one.

The field / dense / one-point / empty-book Kalshi shapes are likewise synthetic
candles in the real candle shape, built by the test's `_candle()` helper.
