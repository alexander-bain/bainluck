# Fixture provenance — #7548 (all fetched 2026-09-20 UTC, unauthenticated public GETs)

| file | request | status | fetched (UTC) | kind |
|---|---|---|---|---|
| `gamma-event-741506.json` | `GET https://gamma-api.polymarket.com/events/741506` | 200 | 18:49:33Z | source bytes, verbatim |
| `clob-prices-history-larson-yes.json` | `GET https://clob.polymarket.com/prices-history?market=<Larson YES token>&startTs=1789819200&endTs=1789884000&fidelity=1` | 200 | 18:51:04Z | source bytes, verbatim |
| `dataapi-trades-larson.reduced.json` | `GET https://data-api.polymarket.com/trades?market=<Larson conditionId>&limit=500&takerOnly=false` | 200 | 18:51:16Z | source bytes REDUCED: 114 of 114 trades kept; wallet / pseudonym / profile / title fields dropped, nothing else touched. The verbatim body is in the delivery package under `source/`. |
| `bainluck-detail-56947465.json` | `GET https://api.bainluck.com/api/futures/56947465` | 200 | 18:49:00Z | saved served evidence |
| `bainluck-history-56947465.json` | `GET https://api.bainluck.com/api/futures/56947465/history?hours=168&top_n=50` | 200 | 18:49:00Z | saved served evidence |

Larson conditionId `0xd8e4484971dc78f997f3ecb75c41f942f2b2f0d2f12ecc827770f42ade8a7c85`;
YES token `80387649361663967783720414743451746455285579684363190637559405133484382266840`.

NOT a fixture, because nobody holds it: Gamma's payload at our capture instant
(2026-09-19T20:31:08Z). The test reconstructs it and says so at the top of the file.
