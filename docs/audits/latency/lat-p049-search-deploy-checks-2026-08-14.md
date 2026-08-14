# LAT-P049 — the five `/search` deploy checks, taken

**Owed since:** `program/latency-45` merged into `6d3fba9e` and deployed as **v3812** (2026-08-14
11:07 PDT). `READY-latency-LAT-P049.md` listed five deploy checks and recorded *"No production
read"*; none of the five ever produced a durable result. Routed back to this lane by the C-PM audit.

**Taken:** 2026-08-14, 15:24–15:35 PDT (22:24–22:35 UTC).
**Against:** production `api.bainluck.com`, Heroku **v3817**, `/api/health` `commit=f6dc46ca`
(verified, not assumed). Deployed ~1h before the reads, so this is outside the post-deploy warm-up
window that makes latency unreadable.
**`-45` is upstream:** `git cherry origin/master program/latency-45` = **0**.

Captures in this directory are the raw bytes returned by production. Their SHA256 values are listed
in `SHA256SUMS.txt` and reproduced in the durable comment on #993.

---

## Verdict table

| # | check as worded | expectation | verdict |
|---|---|---|---|
| 1 | `/api/events/search?q=grammys` → `event_concepts[0]` is `event:awards:grammys`, and no key in `teams[]`/`event_concepts[]` starts with `_` | present, clean | ✅ **PASS** |
| 2 | `/api/events/search?q=red sox` → `teams[0]` is Boston Red Sox (alias path) | present | ✅ **PASS** |
| 3 | `/api/events/search?q=tour de france` → the cycling concept is **present** | present | ⚠️ **VACUOUS — specimen expired.** Re-taken on a live cycling specimen: **PASS** |
| 4 | `/api/events/typeahead?q=tour de france` → the cycling concept is **absent** (#1846, live) | absent | ⚠️ **VACUOUS *and* OBSOLETE.** Specimen expired; #1846 was fixed on `-47`/v3814. Re-taken as a control: **#1846's fix confirmed live** |
| 5 | `/search` p50 unchanged | unchanged | ⛔ **UNGRADEABLE as worded** — no pre-`-45` p50 was ever captured. Measured now as a first baseline: **p50 407.1 ms** |

Two checks passed as written, two had expired specimens and were re-taken by substitution with the
substitution declared, and one cannot be graded because its "before" does not exist. Nothing was
ticked that was not exercised.

---

## Check 1 — `grammys` ✅

`raw-search-grammys.json`

```json
"event_concepts": [
  { "key": "event:awards:grammys", "name": "The Grammys", "domain": "awards", "market_id": 56775571 }
]
```

`event_concepts[0].key == "event:awards:grammys"`. Keys present on the row: `domain`, `key`,
`market_id`, `name` — **no key starts with `_`** on any row of `event_concepts[]` or `teams[]`.
The private-evidence strip is holding on a non-empty bucket.

## Check 2 — `red sox` ✅

`raw-search-red-sox.json`

```
teams[0]  id=10709  Boston Red Sox     slug=boston-red-sox-mlb
teams[1]  id=12912  Worcester Red Sox  slug=worcester-red-sox
```

Boston at rank 1, its Triple-A affiliate at rank 2 — the alias path resolves and orders correctly.
No `_`-prefixed keys.

## Check 3 — the cycling concept in `/search` ⚠️→✅ by substitution

`raw-search-tour-de-france.json` returns **every bucket empty** — `teams`, `event_concepts`,
`results`, `futures`, `futures_families` all `[]`, `total_results: 0`.

That is not a drop; there is nothing to drop. Verified against the database rather than inferred:

```sql
SELECT id, name, status FROM futures_markets WHERE name ILIKE '%tour de france%'
```

returns **29 rows, every one `status = 'resolved'`** — the 2026 Tour settled 2026-07-26 / 2026-08-09.
This is the third specimen in this program pinned to a live market that later settled.

**Substituted with a live cycling specimen** (`Vuelta a Espana 2026: Winner`, id `58675941`, `open`,
resolves 2026-09-20 — one of only 3 open cycling markets in production):

`raw-search-vuelta-a-espana.json`

```json
"event_concepts": [
  { "key": "event:cycling:vuelta-2026", "name": "Vuelta a España 2026", "domain": "cycling", "market_id": 58675941 }
]
```

The concept a resolver-less domain mints from its own market is **present and rank 1** in `/search`.
Check 3's mechanism passes.

## Check 4 — the deliberately-absent typeahead specimen ⚠️→ #1846 confirmed fixed

This check was written to confirm #1846 **live** — "the cycling concept is absent from `/typeahead`".
Two things have changed under it: the specimen expired (check 3), and **#1846 was fixed** on
`program/latency-47`, merged as `92f66962`, deployed alone as **v3814**. So the check's expectation
is now inverted, and grading it as written would assert a bug that has been repaired.

Re-taken as a **control on the class**, using the specimen #1846's own closing comment substituted
in (tennis, also resolver-less):

`raw-typeahead-us-open.json` — `GET /api/events/typeahead?q=us open`, v3817

```
1  event_concept  2026 Women's US Open Winner (Tennis)   event:tennis:2026-women-s-us-open-winner-tennis
2  event_concept  2026 Men's US Open Winner (Tennis)     event:tennis:2026-men-s-us-open-winner-tennis
3  event_concept  US Open Men's Singles                  event:tennis:us-open-men-s-singles-winner
4  futures        2026 Women's US Open Winner (Tennis)
5  futures        2026 Men's US Open Winner (Tennis)
6  futures        US Open Men's Singles Winner
7  futures        Will the US reopen its embassy in Iran?
```

Three concept rows at ranks 1–3, above the markets they were built from. On v3806 this query
returned **five futures rows and zero concepts**. **#1846's fix is confirmed live on v3817 by an
independent read, not by the READY file's own account of itself.**

### But the substitution surfaced a defect the closing comment could not have seen

The same read on the **cycling** specimen does **not** behave like tennis:

| query | `/search` `event_concepts` | `/typeahead` `event_concept` rows |
|---|---|---|
| `us open` | — | **3** (ranks 1–3) |
| `vuelta a espana` | **1** — `event:cycling:vuelta-2026` | **0** |
| `vuelta` | — | **0** (returns the futures market, 2 events, 1 team) |
| `vuelta a espana 2026` | — | **0** (returns the futures market only) |

`/search` mints `event:cycling:vuelta-2026` and ranks it first; `/typeahead` never emits a cycling
concept row **for any phrasing tried**. Because it is absent under every phrasing — including the
one whose text most exactly names the concept — this is **not** #1846's provenance drop (which is
phrasing-sensitive by construction, and which the `us open` control shows working). It reads as a
**concept-pool discovery gap**: the cycling concept is built on the `/search` path and is not built
on the `/typeahead` path at all.

That is a new, non-expiring finding, filed separately. It does **not** re-open #1846: #1846's
mechanism is the blanket `_derived` flag, and that mechanism is measurably fixed.

## Check 5 — `/search` p50 ⛔ ungradeable as worded, measured as a baseline

`capture-lat-p049-check5-search-p50.json`. 4 queries × 5 samples, warm (one discarded warm-up pass
per query), 1.2 s spacing, v3817:

| query | p50 | min | max |
|---|---|---|---|
| `grammys` | 411.1 ms | 402.9 | 476.7 |
| `red sox` | 640.1 ms | 632.8 | 789.6 |
| `vuelta a espana` | 319.1 ms | 310.6 | 340.1 |
| `italian grand prix` | 395.1 ms | 379.8 | 663.3 |
| **aggregate (n=20)** | **407.1 ms** | — | p90 **663.3 ms** |

Control, same window: `/api/health` p50 **236.2 ms** — the network + TLS floor from this client.
So `/search` server time is roughly **171 ms** at p50, well inside the 2 s action threshold.

**"Unchanged" cannot be graded.** `READY-latency-LAT-P049.md` recorded *"No production read"* for
`-45`, so no pre-deploy `/search` p50 exists anywhere to compare against. The number above is
therefore registered as the **first durable `/search` p50 baseline**, not as a confirmation. The
check was unfalsifiable the moment it shipped without a "before", and saying so is the result.

Worth carrying into the tail work: **`/search` at 407 ms is roughly 3× faster than `/typeahead`**,
whose cold tail measured 3.0–6.4 s in the same session.

---

## Reproduction

```bash
source ~/.claude/.env
curl -s -G "$BAINLUCK_API/api/events/search"    --data-urlencode "q=grammys"
curl -s -G "$BAINLUCK_API/api/events/search"    --data-urlencode "q=red sox"
curl -s -G "$BAINLUCK_API/api/events/search"    --data-urlencode "q=vuelta a espana"
curl -s -G "$BAINLUCK_API/api/events/typeahead" --data-urlencode "q=us open"
curl -s -G "$BAINLUCK_API/api/events/typeahead" --data-urlencode "q=vuelta a espana"
```

Every capture in this directory is unedited response bytes. `SHA256SUMS.txt` pins them.
