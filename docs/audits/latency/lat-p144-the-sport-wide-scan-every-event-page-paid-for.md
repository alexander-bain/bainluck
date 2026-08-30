# LAT-P144 — the sport-wide scan every event page paid for

**Pillar: FORMATTING / DISCOVER (event pages — product priority #3).**
**Ship: tapping a game stops re-deriving the whole sport's market list to tell you what the game means for the season.**

Issue **#2316**, parent **#1587**. Branch `program/latency-129`.

---

## 1. Picking the work

Organic reads first (ruling 127): `GET /api/admin/latency-stats` at 08:44 UTC, then
`GET /api/admin/latency-slow-events?limit=500` — the six-day ring of every production
request over 5 s, with per-stage attribution. Ranked by 24 h count:

| # | path | 6 d / 24 h | verdict |
|---|---|---|---|
| 1 | `/api/events/typeahead` | 99 / 76 | **banked** — LAT-P143 on `-128`, awaiting the Integrator |
| 2 | `/api/playoffs/{league_slug}` | 58 / 51 | **51 of 58 fall inside 08-29 14h–21h UTC and nothing since.** A burst, dormant 11 h — LAT-P129's surface. Parked **P144-4** |
| 3 | **`/api/events/{event_id}/related-futures`** | 52 / 34 | ✅ **TAKEN** — LAT-P143's declared next (P143-2), and unlike #2 it recurs across the whole window |
| 4 | `/api/teams/{identifier}/prop-families` | 31 / 30 | **banked** — LAT-P138, merged |
| 5 | `/api/feed` | 126 / 12 | **banked** — LAT-P141 on `-126` |
| 6 | `/api/events/search-suggestions` | 13 / 11 | **new, unbanked, and unranked by any prior cycle.** 7 of 13 landed in one hour on 08-30. Every sample: exactly 7 queries, `db_ms` ≈ total, `max_query_ms` ≈ `db_ms` — ONE query is ~99 % of a 12.8 s median. Parked **P144-5**, and it is the cleanest-shaped thing on this list |

`/api/events/search` — last cycle's subject — contributed **0** events in 24 h, which is
LAT-P139/P140 landing.

---

## 2. The defect

LAT-P136 gave this tier a shared cache and a mirror, and said plainly in its own docstring that
the BUILD was not made faster: *"which of the 14-16 queries dominates is a separate question …
it needs a production plan per event shape, not a guess."* It parked that as **P136-1**.

It is one query, and it is not about the event.

    SELECT futures_markets.id, futures_markets.market_tier FROM futures_markets ...

Production `pg_stat_statements`, 2026-08-30:
**8 fingerprints · 2,245 calls · mean 1,061 ms · max 30,773 ms · 2,381 s total.**

`EXPLAIN (ANALYZE, BUFFERS)` on production, baseball, the two shapes it takes:

| event shape | plan | blocks | time | rows out |
|---|---|---|---|---|
| live / upcoming | Bitmap Heap Scan | 31,497 | ~1,000 ms | 96 |
| finished | **Parallel Seq Scan** | **126,177** | 2,754 – 11,924 ms | 400 |

**911,788 rows scanned to return 96.** And the block count is *constant* at 126,177 while the
wall clock swings 4× across three runs in the same minute — `Shared I/O Read Time` 778 →
20,828 ms. The variance is buffer-cache luck on a 1,664 MB table, which is exactly the kind of
cost a memoised result removes rather than merely reduces.

Every input to that query derives from the event's **sport** — `ext_id_patterns`,
`compatible_sport_ids`, `llm_category`, `kalshi_roots`, the gender flags — or from
`event_is_finished`. Nothing else. The answer is shared by every event in the sport, and the
route was re-deriving it per event page.

---

## 3. Two fixes that looked right and were measured wrong

Both are written into `utils/season_market_discovery.py` beside the code, not only here,
because a disproof is worth exactly as much as the next reader's chance of finding it.

### 3.1 Index the predicate

The sport match is a four-arm OR; two arms match `external_id` by prefix. The database
collation is **`en_US.UTF-8`**, so a prefix `LIKE` cannot use a btree. Measured:

    source='kalshi' AND external_id LIKE 'KXMLB%'              Seq Scan   126,137 blocks  1,860 ms  34,463 rows
    source='kalshi' AND external_id >= 'KXMLB' AND < 'KXMLB~'  Index Scan       4 blocks   15.6 ms       0 rows

The range form is 470× cheaper **and wrong** — zero rows where the `LIKE` returns 34,463,
because en_US collation is not byte order. That divergence is precisely why Postgres refuses to
rewrite the `LIKE` itself, and it is the whole argument that no query rewrite closes this. An
index here is a MIGRATION. Parked **P144-1**, appended to the standing slot request.

A UNION-of-arms rewrite was measured too, and it does not help: split into arms, the indexed
category arm costs 2,370 blocks but the two `external_id` arms **each still cost the full
31,497-block heap fetch**, because evaluating `external_id` for all 55,512 open markets is the
cost. Total 34,000 blocks against 31,497 — worse.

### 3.2 Delete the un-indexable arms

Very tempting. For baseball they contribute **zero** rows the indexed category arm does not
already return, and of 17,967 tier-1-4 open markets **17,966 carry a category** — the single
exception is a polymarket row matching no prefix the expensive arms search for.

Checked across twelve sports before the idea was discarded, and it is **wrong**:

| sport | arm | rows it alone contributes | their categories |
|---|---|---|---|
| americanfootball | KX ticker | **17** | `other` 8, `economics` 5, `basketball` 2, `baseball` 1, `soccer` 1 |
| basketball | KX ticker | **1** | `football` |
| tennis | `sport_id` | **46** | `table_tennis` |

They are a working correction for classification gaps. Deleting them deletes markets off the
page.

⚠️ The tennis 46 look like a **different bug** — a `tennis%` sport-key prefix reaching table
tennis, so a tennis event page carries 46 table-tennis markets. That is a content question for
the MATCHING lane and not something a latency queue gets to decide. Parked **P144-2**.

---

## 4. What shipped

The query is unchanged. **Who runs it** changed.
`app/utils/season_market_discovery.py` memoises the result on exactly
`(sport_key, event_is_finished)` — about two entries per sport, ~60 keys site-wide.

Three decisions worth naming:

* **Two TTLs.** 300 s when markets are found (tiers 1-4 are season-long); **60 s when none
  are.** An empty *discovery* is cached even though this tier's *payload* cache deliberately
  refuses to store empty answers — an empty payload is an answer shown to a reader, an empty
  discovery is an internal index, and re-running a 126,177-block scan to re-learn "still none"
  is the exact pathology here: a boxing event measured **7.03 s to return 511 bytes**. The
  shorter TTL is so a sport recovers in a minute, not five.
* **No in-process L1.** The sibling tier keeps one; that dict predates its Redis layer and was
  carried across rather than chosen. Here it would buy a ~1 ms round trip against a ~1,061 ms
  query while adding a second, per-worker staleness horizon.
* **One input is not a pure function of the key,** and it is named in the module rather than
  glossed: the finished-event filter carries `updated_at >= NOW() - 90 days`, whose boundary
  moves with the clock. A market can sit up to `TTL_FOUND` past aging out — 5 minutes against a
  90-day window, 0.004 %. It is a real approximation and it is why the TTL is short.

`debug=1` bypasses in both directions, the rule the cache ladder at the top of this route
already follows.

---

## 5. Measurement, both sides

**Before**, six DISTINCT baseball_mlb event pages, first touch each, `debug=1` (which bypasses
every cache level, so each is a genuine cold build), production, 2026-08-30 09:12 UTC:

    22.8  17.6  8.1  5.4  14.6  12.4 s        median ~13.5 s · total 80.9 s

The ring's own attribution for those same six requests: 16-18 queries each, and
`max_query_ms` is **77–93 %** of `db_ms` in five of six (18,116 / 15,803 / 11,426 / 10,517 /
5,555 ms). Re-measuring the discovery query in isolation minutes later, same shape, same load:
**11,924 / 2,754 / 6,461 ms**. The dominant query is the discovery query.

**After — stated as arithmetic, because it is not deployed.** The Integrator merges; this
session cannot measure the post side on production and does not claim to. One of those six
builds runs the query; the other five read ~60 bytes from Redis. The removed component is the
measured 2,754–11,924 ms.

⚠️ **`pg_stat_statements` could NOT causally attribute my own probes** and this is stated
rather than glossed: between two reads its fingerprint count for this family fell 8 → 3 with
`calls` unchanged at 2,245 — entries were evicted under the 5,000-entry cap. The population
figures in §2 are a real read at one moment; they are not a before/after instrument, and no
delta is quoted from them.

**Post-deploy verification is a COUNT, not a p50.** `latency-slow-events` filtered to this
path, expecting the 34-per-24 h population to fall sharply, plus the per-request `queries`
count dropping by one on a hit. A p50 read will barely move — the p50 was never the defect.

---

## 6. Gates

| gate | result |
|---|---|
| backend suite, six chunks | see report |
| new guards | 37, exit 0 |
| mutation battery, 20 mutants | **20/20 killed, 0 survived, 0 harness failures**; targets restored SHA-256 identical |
| residue scan **on the commit** | **CLEAN** — 364 needles, 1,370 broad checks |
| `test_mutation_guard.py` | 9 passed |
| startup smoke / `from app.main import app` | 4 passed / exit 0 |
| `merge-tree` vs `origin/master` + 4 live branches | 0 conflicts from this diff |
| frontend gates | not run — zero frontend files in the diff |

The `program/ux-131` merge reports one conflict in `backend/app/routes/playoffs.py`, a file
this diff does not touch; it reproduces between `ux-131` and `origin/master` alone, so it is
that branch's rebase debt and not this one's.

---

## 7. Two things this queue got wrong on the way

* **It set out to delete the expensive arms.** The reachability query said 17,966 of 17,967
  tier-1-4 open markets carry a category and the one exception matches nothing — which reads as
  a proof that the `external_id` arms are dead weight. It is not one: those rows have a
  category, just the *wrong* one, so they are invisible to a query that asks "is the category
  NULL". Only the twelve-sport row-identity diff found the 17 / 1 / 46. **The check that
  disproved the plan was the one run to confirm it.**
* **A mutant survived, and it was a real hole.** M8 — a write that drops `event_is_finished`
  and always publishes to the live slot — passed every test, because a finished build MISSES
  either way and that is exactly the bug. It only becomes visible when a *second* finished
  event is expected to HIT. The guard added for it says so in its docstring.

---

## 8. Parked

**P144-1** a prefix-searchable index on `futures_markets.external_id` (migration; appended to
the standing slot request) · **P144-2** `sport_id` prefix matching puts 46 table-tennis markets
on tennis event pages (MATCHING lane, content) · **P144-3** the series-market query at the
bottom of the same build shares the expensive `sport_filters` OR but also matches both team
names, so it is not sport-cacheable · **P144-4** `/api/playoffs/{league_slug}`, 51 events in a
single 7-hour burst then silence — needs a cause, not a fix · **P144-5**
`/api/events/search-suggestions`, 11 events over 5 s in 24 h, median 12,782 ms, and **one query
is ~99 % of every one of them** — the cleanest-shaped unbanked item on the board.

Carried unchanged: **P143-1**, **P143-3**, **P143-4**, **P143-5**, **P142-1**…**P142-4**,
**P141-1**…**P141-6**, **P140-1**…**P140-3**, **P129-1**…**P129-5**, **P116-1**.

---

## 9. Contamination declared

* Organic `latency-stats` + `latency-slow-events` read **first**, before any probe (ruling 127).
* ~30 `db-query` statements against `futures_markets` / `futures_outcomes` /
  `pg_stat_statements`, of which ~14 were `EXPLAIN ANALYZE`. Read-only; they warm buffer pages,
  which is why every claim is reported in **blocks** as well as ms.
* 14 `/api/events/{id}/related-futures?debug=1` with `X-Bainluck-Origin: harness` — `debug`
  bypasses the cache in both directions, so no cache was written or displaced.
* 1 `/api/feed?limit=30` and 1 `/api/events` with the harness origin.
* `needle_latency.py` — its own pool, run with nothing else probing (P110-4).
* No writes of any kind to production.
