# #5343 fixture provenance

Source bytes, unedited. Each file is Polymarket Gamma `GET /events/{id}` on the
public API (`https://gamma-api.polymarket.com`), captured by lane1 for #5343.
These are the PROVIDER's payloads. Bain Luck never served them, and no test
that reads them proves anything about production.

| File | Event | Captured (UTC) | sha256 |
|---|---|---|---|
| `gamma-event-106884.json` | "Fed rate cut by...?" (economy/fed tags), negRisk false, 13 markets, 6 of them closed | 2026-10-12T00:49:13Z | `5ce0eea19067bd1691544f8d650a501bb3a3ef3b31fd2c8f630267883068c224` |
| `gamma-event-86832.json` | "Which companies will be acquired before 2027?" (tech/business tags), negRisk false, 19 markets, 5 of them closed | 2026-10-12T00:49:16Z | `70627d0daa3f87869dc0df399fa7424c28066e65a8f7837d5e732d69f54885c7` |

Also read (not copied; owned by #8466):
`../polymarket_leg_dates_8466/gamma-event-1038648.json` — "US-Iran ceasefire
continues through...?" (politics/geopolitics tags), 6 markets, captured
2026-09-24T20:58:22Z, sha256 `c9211815549d19cd8e7d38d360236ed0d9adf3aa67c086c27da0c71c596d0c3c`.

How the tests use them: `tests/provider_event_fixtures_5343.py` turns one Gamma
event into the rows ingestion would store. That means a parent row, plus one
child per market whose Yes price is positive, because ingestion skips the rest
(`app/tasks/polymarket.py`, the sub-market loop's `prob <= 0: continue`). The
roster key (`polymarket_event_roster`) is NOT written by ingestion today. When
a test stamps it, the test is supplying the proposed ingestion contract. That
is builder-owned input, not stored evidence.

86832 is the held-out event. It appears only in the held-out tests, and no
source file names it.
