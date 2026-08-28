# LAT-P109 — cold search was a coin flip, and the coin is a 4 MB pending list

**Cycle 81 · 2026-08-28 · branch `program/latency-94`, cut from master `0e2414cd`**
**Ship: cold `/api/events/search` stops randomly costing an extra second (#2255).**

---

## 0. The cold path, first (ruling 137)

The opening needle read **REFUSED** — the third consecutive refusal in this lane,
and for the third time the same cause. `LAT-P109-open`, slug `0e2414cd`,
uptime 2,266 s, taken `2026-08-28T21:22:20Z`:

```
surface        path key          graded  cold  cold%  p50 cold
Discover open  discover_native        5     0     0%         —
               discover_web           5     0     0%         —
tab loads      sports_native          5     0     0%         —
               sports_web             5     0     0%         —
               search_trending        5     0     0%         —
               my_stuff_stats         5     5   100%      19.0
cold search    search_cold            6     6   100%     787.5

🔴 POOL TOO THIN TO PUBLISH
   - only 2 of 7 member paths produced a cold sample (floor 4)
   - only 2 of 3 graded surfaces went cold (missing: Discover open)
```

Five of the seven member paths **cannot be made to go cold any more**. LAT-P101's
prewarm and LAT-P103's cross-worker shared build reached production yesterday and
a fresh principal now gets `shared_hit` at ~60 ms on every `/api/feed` shape.
That is LAT-P108's finding, unchanged and now reproduced by an independent run —
it is Alex's open DECIDE item in `YOUR-TURN.md` and this cycle did not decide it.

**What the refusal still tells you is the whole reason for this queue.** Of the two
members that CAN still go cold, one costs 19 ms and the other costs **787.5 ms**.
Cold search is now, by a factor of forty, the slowest thing a user can reach on
the graded pool — and it is one of the three surfaces Alex named by hand.

Its six samples: **433 · 463 · 566 · 1,009 · 1,258 · 1,945 ms.** A 4.5x spread over
six obscure single-word terms. That spread, not the median, is what this report is
about.

---

## 1. The spread is not the terms — the same term does both numbers

`kaiserslautern`, twice on the same slug, minutes apart: **727 ms**, then
**179 ms**. Nothing about the query changed.

Per-stage attribution over **32 fresh terms never probed before** (the route's own
`debug_timing=true`, which also bypasses the response cache, so every sample is a
genuine build):

| stage | batch A (16 terms, 21:28Z) | batch B (16 terms, 21:34Z) |
|---|---|---|
| **total** | **387.5 ms** | **362.5 ms** |
| `futures` | **262.5 ms (68 %)** | **197.5 ms (54 %)** |
| `event_count` | 32.0 | 52.0 |
| `event_page` | 27.5 | 50.5 |
| `event_odds_query` | 36.5 | 16.5 |
| `teams` | 4.5 | 6.0 |

`futures` was the largest stage on **32 of 32** terms. Everything below is about
that stage.

---

## 2. The same query, twice, 5.4x apart

The futures stage is one statement (plus its two `selectinload`s). It was compiled
out of the route itself — `_futures_name_match_term`, `_build_expanded_ilike`,
`_build_league_ticker_match`, `_expanded_tsquery`, `_SEARCH_FUTURES_WINDOW`, all
called, not re-typed — so the SQL explained is the SQL served.

`EXPLAIN (ANALYZE, BUFFERS)`, term `cremonese`, two passes eleven minutes apart,
**identical output both times** (29 candidates in, 20 rows out):

| node | pass A | pass B |
|---|---|---|
| `Append` (the UNION of the recall arms) | **148.9 ms** | **27.8 ms** |
| ├ `Bitmap Index Scan ix_futures_name_trgm` | 50.2 ms / 617 blk | 19.5 ms / 617 blk |
| └ `Bitmap Index Scan ix_futures_outcomes_name_trgm` | 87.6 ms / 689 blk | 4.0 ms / 214 blk |

Same plan, same rows, **5.4x**. The move is entirely in the two trigram index
scans, and it is entirely in **blocks read**, not in rows returned.

---

## 3. The proof is a pattern that matches nothing

A `%zzqqxxvv%` probe returns zero rows. It can do no useful work, so whatever it
costs is pure overhead. On `futures_outcomes.name`:

```
21:27Z   49.9 ms   507 shared blocks   0 rows
21:29Z    0.3 ms    31 shared blocks   0 rows
```

A GIN entry-tree descent for an absent key is a handful of pages. **507 pages is
the GIN pending list being read start to finish** — and
`current_setting('gin_pending_list_limit')` on production is **`4MB`**, which is
512 × 8 kB pages. The number is not approximately the limit; it *is* the limit.

### It is a sawtooth, and it is the steady state

Zero-match probes on every trigram index in the search path, every 46 s,
`21:30:22Z → 21:38:51Z` (12 rounds, blocks read):

| index | t+0 | t+46 | t+92 | t+138 | t+184 | … | t+506 | peak ms |
|---|---|---|---|---|---|---|---|---|
| `futures_markets.name` | 530 | 530 | 531 | **→24** | 25 | | 28 | **92.2** |
| `futures_outcomes.name` | 93 | 100 | 141 | 170 | 208 | | 391 | **86.7** |
| `events.home_team_name` | 118 | 118 | 132 | 148 | 161 | | 216 | **116.1** |
| `events.away_team_name` | 118 | 118 | 132 | 148 | 162 | | 216 | **85.4** |
| `teams.name` | 14 | 14 | 15 | 15 | 15 | | 16 | 8.3 |

A flush was caught live on `futures_markets.name` between t+92 and t+138 (531 → 24
pages). Refill rates: `futures_outcomes` ~50 pages/min, the two `events` indexes
~20 pages/min each. `teams` is write-quiet and stays flat, which is the control —
the sawtooth tracks write volume, not index size.

**So a search that lands near the top of the sawtooth pays the whole 4 MB on each
of the four trigram indexes it touches, and one that lands just after a flush pays
nothing. That is the 433 → 1,945 ms spread, and it is a coin flip the user loses
about half the time.**

Quote the BLOCKS, not the ms — LAT-P032's rule, and it holds here too: block
counts were stable across passes at a given point on the sawtooth while wall time
swung 6.5 → 92 ms on the *same* 530 blocks, purely on buffer-cache state.

### Autovacuum is not the answer, and that is measured too

Autovacuum also flushes pending lists, but it fires on the table's dead-tuple
threshold — hundreds of thousands of rows on a 3.2 M-row table. The sawtooth above
IS what autovacuum currently produces. The only thing emptying these lists today is
whichever unlucky INSERT crosses 4 MB.

---

## 4. The fix, and why it is a task rather than the one-line DDL

`ALTER INDEX … SET (gin_pending_list_limit = '256kB')` is the smaller, permanent
form of this fix and it is the right end state. It is **DDL**, and ruling 080 makes
a migration slot an integrator-owned artifact that a lane requests and never takes.
So the slot is **requested, not taken** (see the report's Alex/Integrator ask), and
the shippable form today is:

**`app/tasks/gin_pending_lists.py` — `flush_search_gin_pending_lists`, beat every
2 minutes on `background`.** It calls `gin_clean_pending_list()` on each of the
seven declared indexes.

Why this is safe to leave on:

- **It changes nothing a reader sees.** `gin_clean_pending_list` moves entries that
  are *already in the index* from the pending list into the tree. Same rows, same
  order, same recall, before and after. It is not a cache: nothing to warm, nothing
  to invalidate.
- **It creates no new work.** The merge is work an inserting backend would do at the
  4 MB limit anyway. This moves it off the read path and off whichever poll happened
  to cross the line.
- **Permission is verified, not assumed.** `gin_clean_pending_list` is restricted to
  the index owner; all seven indexes are owned by the application role
  (`pg_class.relowner` = `u73crpn2b2tvgm`, the same role the app connects as) and
  none carries a `reloptions` override.
- **The pool is a frozen literal, never a `pg_index` predicate.** A predicate would
  silently adopt every GIN index anyone adds later, including ones this claim was
  never measured on.
- **2 minutes is derived, not picked.** At the measured refill rates the worst case
  between passes is ~100 pages (~10 ms/index) against the 512-page peak (50–92
  ms/index) it replaces. Shorter buys progressively less; longer lets
  `futures_outcomes` — the most expensive of the seven — get most of the way back.
- **The budget bounds the longest uninterrupted operation**, one index flush
  (`PER_INDEX_TIMEOUT_MS = 15 s`), not the loop boundary.
- **One bad index must not wipe the pass** (gotcha #42): per-index try/except inside
  a per-index savepoint, damage in `errors`, and the summary speaks
  `task_verdict`'s vocabulary so a pass that flushed nothing reports `failed`
  rather than an invocation that merely returned (gotcha #53).
- **Rollback is a config var, not a revert.** `SEARCH_GIN_FLUSH_ENABLED`, default
  ON, **not needed at deploy.**

---

## 5. Gates

- **Full suite: `20,818 passed / 0 failed / 112 skipped / 61 xfailed`, ONE run (847.17 s),
  EXIT CODE 0 read BY VALUE**, on the final code tree `f4e1fd60` (HEAD `87f18201`).
- 🔴 **An earlier run was genuinely RED — 2 failed — and both were the gate working.**
  `20,816 passed + 2 failed = 20,818`; the two runs reconcile exactly. Both failures were
  the declared beat ledgers refusing a new `background` interval beat, which is precisely
  what they exist to do; they are argued and re-derived in §5a below.
- ⚠️ **A run between those two exited 1 with FOUR failures that were not verdicts.**
  `test_alembic` (×3) and `test_discover_provenance` (×1) went red under
  `pytest <abs-path>/tests --rootdir …`, an invocation forced by a `cd` that the harness
  had reset. All four pass from `backend/` (`38 passed`, re-run to confirm) — they resolve
  migration paths relative to the working directory. A story about the harness, not the
  tree (gotcha #124), and the reason the authoritative run above was re-taken rather than
  explained away.
- **New guards:** `backend/tests/test_gin_pending_lists.py`, 26 tests.
- **RED-proven ten ways.** Each mutation applied alone from a `cp` backup, restored
  and **sha256-verified** before the next; the harness refuses any pattern matching
  other than exactly once. All ten caught:

  | # | mutation | verdict |
  |---|---|---|
  | M1 | pool-membership check deleted (the interpolation guard) | RED |
  | M2 | per-index `statement_timeout` deleted | RED |
  | M3 | a zero-flush pass reports `complete` | RED |
  | M4 | per-index `except` narrowed (one bad index wipes the pass) | RED |
  | M5 | savepoint dropped | RED |
  | M6 | the disabled switch becomes a no-op | RED |
  | M7 | an index silently dropped from the pool | RED |
  | M8 | the beat moves to the `realtime` queue | RED |
  | M9 | `expires` longer than the beat period | RED |
  | M10 | the beat entry renamed out of the allowlist | RED |

  ⚠️ M9's first run exited **4** — `no tests ran`, because the harness named a test
  class that does not exist. Exit 4 is a story about the harness, not a verdict
  (gotcha #124); it was re-run against the correct target and came back RED.

- **ruff:** ZERO NEW. `app/tasks/__init__.py` carries the same 4 pre-existing E402
  on master (verified by running ruff against `origin/master`'s copy of the file);
  the two new files are clean.
- **black:** both new files formatted. `app/tasks/__init__.py` deliberately NOT run
  through black — master's copy is not black-clean and reformatting it would turn a
  30-line change into a whole-file diff.
- **Backend only.** No frontend, iOS, route, model, migration or DDL change.

### 5a. Two declared ledgers moved, and both are argued rather than absorbed

`BACKGROUND_INTERVAL_FLOOR` **4 → 5**. Its own comment demands that a new interval beat on
`background` "should be argued in a report, not discovered later inside a filter nobody
re-reads". So: the pass is seven `gin_clean_pending_list()` calls with no table scan and no
third-party call; `expires: 110`, under its own 120 s period, means the ~7 minutes the
settlement sweep holds the slot **drop** their stale fires instead of queueing four flushes
to run back to back the moment it releases; and 120 s is inside the floor's own
`<= 180 s` rule rather than an exception to it. `background` and not `realtime` (the
2-minute live price poll, which maintenance must not contend with) or `heavy` (25-minute
calibration passes, behind which a 2-minute beat is meaningless).

`BACKGROUND_BEAT_COUNT` **106 → 107**, explicit **61 → 62**, fall-through **unmoved at 45**
— RE-DERIVED by running the census over the assembled schedule and printing it, never
incremented (#1910). That constant's own standing note warns it has conflicted on three
consecutive integration cycles; **the note's premise was checked rather than inherited** —
Q426's `link-tournament-matchups` is present in `origin/master` @ `0e2414cd`, so its
"unmerged" caveat is stale, while the four unmerged branches that genuinely touch this file
are named in the READY token.

---

## 6. Parked

| id | finding |
|---|---|
| **P109-1** | (filed on #2255) `ALTER INDEX … SET (gin_pending_list_limit = '256kB')` on the seven trigram indexes is the permanent form of this fix and removes the need for the beat task. Needs an integrator-owned migration slot (ruling 080). |
| **P109-2** | (filed on #2255) **`ix_events_home_trgm` / `ix_events_home_team_name_trgm` are DUPLICATE indexes** — same table, same column, same opclass — and so are the `away` pair. Four indexes doing the work of two: double the write amplification, double the pending list, on the two most-scanned GIN indexes in the database (5.75 M and 5.60 M scans). Dropping the duplicates is DDL and needs the same slot. |
| **P109-3** | The outcome recall arm is 60–89 % of the futures candidate query on every term measured (43–81 ms of a 49–130 ms `Append`) and contributes 4–35 of 15–129 candidates. LAT-P032 already ruled this a **recall-semantics** change that must not be bolted onto a latency queue; re-recorded here with fresh numbers, still not touched. |
| **P109-4** | The futures stage's API-measured cost (197–262 ms p50) exceeds its SQL cost even at the sawtooth peak. The residual is ORM hydration of 20 `FuturesMarket` rows plus two `selectinload`s. Outcomes-per-open-market is p50 2 / p90 8 / p99 32 / max 400, so the `outcomes` load is small on the median and long-tailed. Unattributed, not blamed. |
| **P109-5** | The needle has now refused **four times running** (LAT-P108 twice, this cycle twice) on the same cause. Five of seven member paths can no longer be driven cold. Alex's DECIDE item; nothing in this lane can resolve it. |
| **P109-6** | The closing read's `search_cold` member went 6/6 WARM at 2–4 ms with `q=0`, then MISSED at 570–2,773 ms four minutes later. Cause not established; `warm_search_head` ruled out by measurement (attested head = one term, `red sox`). If it is a concurrent window on the shared `obscure` list, the needle needs a term set nobody else probes. |

---

## 7. The needle — REFUSED TWICE, and the second refusal is a new fact

| read | time | cold members | verdict |
|---|---|---|---|
| `LAT-P109-open` | `2026-08-28T21:22:20Z` | **2 of 7** (`my_stuff_stats` 19.0 · `search_cold` 787.5) | REFUSED (floor 4) |
| `LAT-P109-close` | `2026-08-28T22:22Z` | **1 of 7** (`my_stuff_stats` 18.0) | REFUSED (floor 4, and n=5 under a floor of 8) |

Both on `0e2414cd` — **this branch has not deployed, so neither read measures it.**
They are the before picture, and the series is `882 → 873 → 940 → 1273 → refused
→ refused`.

The five `/api/feed`-and-trending members failing to go cold is LAT-P108's
finding, reproduced. **The closing read added a sixth: `search_cold` went 6/6
WARM at 2–4 ms with `q=0`**, meaning the search response cache held all six
obscure terms at that instant.

🔴 **That warmth was transient and the cause is NOT established.** Four minutes
later a manual probe of four of the same terms returned `x-search-cache: miss`
at **570 / 779 / 1,244 / 2,773 ms**, so nothing about the endpoint got faster. Two
candidates, neither confirmed here:

- a concurrent window probing the same documented `obscure` term list (it is
  shared across the measurement bus, and the response TTL is short), or
- a warmer path not yet identified. **It is not `warm_search_head`** — that was
  checked, not assumed: its attested head over 30 days
  (`session_id IS NOT NULL`, `>= 2` distinct sessions) is exactly one term,
  `red sox`, last seen 2026-08-12.

Recorded as **P109-6**, not guessed at.

🔴 **This instrument's own contamination is declared, because it cuts the other
way.** This cycle put ~50 uncached `/api/events/search` requests through
production, which warms shared buffers and writes `search_query_logs` rows
(#1916). Every one used a term set DISJOINT from the needle's `obscure` list
except `kaiserslautern`, `sanfrecce` and `randers`, and all three of those went
through `debug_timing=true`, which bypasses the response cache on read and on
write. The bias it can introduce is **downward**, so it cannot manufacture the
slow numbers this report is built on — only hide them.

```
NEEDLE: latency REFUSED @ 2026-08-28T22:22:00Z — 1/7 cold members against a
floor of 4. Series 882 -> 873 -> 940 -> 1273 -> refused -> refused. No number is
published: the pool is warm, not fast, and a null is not a fast number.
```
