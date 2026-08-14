# LAT-P057 — the tail attack: design, with the premises measured first

**Status:** DESIGN ONLY. No code was written this window (directive: code-free; the depth cap holds
until the `-48/-49/-50/-51` sweep lands).
**Measured:** 2026-08-14, ~15:2x–15:5x PDT, production v3817 / `f6dc46ca`, PG **17.10**, Standard 0.
**Purpose:** `-51`'s warmer treats the head. #1866's tail is untreated and the issue cannot close
while that is true. The directive asked for the plan against the *cause*.

---

## 0. The stated mechanism did not survive measurement

The decomposition handed to this window named the mechanism as:

> a matcher seq-scanning a 977MB table for 13–21s every 15 minutes, evicting 578MB of trigram index
> from 1GB shared_buffers

Four of those five figures are exactly right. **The causal claim is wrong**, and it is wrong in the
direction that matters — it points the fix at something worth **under 1%** of the problem.

| claim | measured | verdict |
|---|---|---|
| 977 MB table | `futures_markets` heap = **977 MB** (1,024,663,552 B) | ✅ exact |
| 578 MB of trigram index | `ix_futures_outcomes_name_trgm` 407 MB + `ix_futures_name_trgm` 172 MB = **579 MB** | ✅ exact |
| 1 GB shared_buffers | `shared_buffers` = 131072 × 8 kB = **1 GiB** | ✅ exact |
| 13–21 s scans | the two scans run **13,820 ms** and **21,438 ms** mean | ✅ exact |
| **"a matcher … every 15 minutes"** | **not the matcher, and not every 15 minutes** | ❌ **wrong** |

**What those two scans actually are.** They are not `match_prediction_markets` — that task filters
`event_id IS NULL AND status = 'open'` and carries a `LIMIT`. They are `_compute_link_rate` in
`app/routes/admin_matching.py:513` and `:610`, driven by the beat entry
`precompute-admin-link-rate`, `crontab(minute="*/10")` — an **admin health metric**, every **10**
minutes, not 15.

**And they are not the evictor.** Their combined physical read volume is **24.6 GB/day** against a
database-wide **2,820 GB/day**: **0.87%**. Fixing them changes nothing measurable about the tail.

### The number that governs everything

```
whole-database physical reads   79.1 MB/s      (2,820 GB/day, over a 61.14-day pg_stat_statements window)
shared_buffers                  1,024 MB
────────────────────────────────────────
buffer-pool turnover            ~12.9 seconds
```

**The entire buffer pool is replaced roughly every 13 seconds.** Eviction is not an event that
happens on a schedule; it is the steady state. There is no 15-minute sawtooth to dodge because
there is no quiet interval to dodge into.

This independently explains LAT-P056's empirical finding that warm residency "is gone by 60 s" —
that window had no mechanism for it and had to withdraw the residency claim after two simulations
disagreed. Two unrelated instruments now converge: measured decay ≈ 60 s, and predicted turnover
≈ 13 s (a hot page survives several turnovers under clock-sweep, so the same order). **The residency
model LAT-P056 withdrew was right about the phenomenon; it was measuring it with the wrong tool.**

Corroborating figure: whole-database lifetime cache hit ratio is **96.18%** on **103 TB** read.
96% sounds healthy and is not — for this workload it means ~3.9 TB genuinely fetched from disk.

---

## 1. Measured premises

All from production v3817 unless noted. `pg_stat_statements` window = **61.14 days**; the view holds
**4,945 of 5,000** entries, so it is **at its cap and evicting** — and *errored statements are never
recorded*, so any query that hits its `statement_timeout` is invisible here and every mean below is
a mean over **successful runs only**.

**Instance**

| | |
|---|---|
| plan | Heroku Postgres **Standard 0** (4 GB RAM), PG 17.10 |
| `shared_buffers` | 1 GiB · `effective_cache_size` 3 GiB · `work_mem` 8 MB |
| storage | **51 GB / 64 GB (79.75%)** — near the plan cap, independent of latency |
| extensions | `pg_stat_statements`, `pg_trgm`, `plpgsql` — **no `pg_buffercache`**, **no `unaccent`** |

**Relations**

| relation | heap | notable indexes |
|---|---|---|
| `futures_odds_snapshots` | 19 GB (38 GB total) | — |
| `futures_outcomes` | 1,141 MB | `..._name_trgm` **407 MB** (GIN) |
| `futures_markets` | **977 MB** | `ix_futures_name_trgm` **172 MB** (GIN) |
| `events` | 158 MB | — |

Row counts: `futures_markets` 783,858 · `futures_outcomes` 3,365,515 · `events` 150,789 ·
`teams` 9,083 · open futures markets **68,618** (avg name 50 chars).

**Top evictors, ranked by physical reads per day** — this ranking is the design's whole basis, and
it had never been taken:

| # | GB read/day | calls/day | MB read/call | mean ms | what it is |
|---|---|---|---|---|---|
| 1 | **533.7** | 1,110 | 492.2 | 2,742 | `golf.py:2286` `_build_completed_tournament` identity scan |
| 2 | **268.5** | 1,205 | 228.1 | 1,372 | `UPDATE futures_markets sub SET event_id = parent.event_id FROM futures_markets parent` |
| 3 | 108.6 | 3,085 | 36.0 | 301 | `INSERT INTO futures_odds_snapshots … SELECT fo.id` |
| 4 | 100.2 | 91.7 | 1,118.5 | 6,306 | a `COUNT(*) FILTER` aggregate |
| 5 | 81.0 | 4.8 | 17,344.8 | 335,941 | `SELECT DISTINCT fos.outcome_id …` |
| 6 | **51.1** | 280.6 | 186.6 | 2,746 | `SELECT MAX(created_at) FROM futures_markets WHERE source = $1` |
| 7 | 48.8 | 151.6 | 329.5 | 3,179 | another `futures_markets` projection |
| 8 | 48.0 | 141.0 | 348.3 | 8,820 | `UPDATE futures_markets SET max_movement_24h …` |
| — | **24.6** | 144 | 132 / 257 | 21,438 / 13,820 | **the two scans the decomposition named** (0.87%) |
| — | 19.6 | 3,156 | 6.3 | 274.0 | **the `selectinload` companion LAT-P056 queued as the tail fix** (0.70%) |

Top 12 ≈ 1,367 GB/day ≈ **48%** of all physical reads.

### Premise-check that kills the queued candidate — stated before the work, not after

LAT-P056 queued this for the tail:

> The typeahead futures pool selects whole `FuturesMarket` ORM entities with
> `selectinload(FuturesMarket.outcomes)`. … Column-pruning it is **recall-neutral** (same markets,
> same outcomes, fewer columns).

Recall-neutral, yes. **I/O-neutral too**, and the tail is I/O:

- Measured: **812 blocks physically read per call** (156,747,682 / 192,965), mean **274.0 ms**.
  812 random reads × ~0.34 ms ≈ 276 ms — the mean is *entirely* accounted for by random I/O.
- Postgres is a **row store**. Selecting fewer columns from the same rows reads the **same heap
  blocks**. The one escape is TOAST, and `futures_outcomes` has essentially none: heap 1,141 MB +
  indexes 1,982 MB = 3,123 MB = its total relation size exactly.
- So `load_only` removes wire bytes and Python object construction. It does **not** remove the 812
  reads. **Predicted tail effect: ≈ 0.**

**The counter-example is in this codebase, and it is the #1 evictor.** `golf.py:2246`'s comment
records a prior latency fix of exactly this family: golf major pages were 503ing at Heroku's H12
boundary, and the fix split the query into a phase 1 that selects four columns **and no outcomes**
and a phase 2 that re-selects matched ids **with** outcomes. That worked — because it removed *an
entire second query over a 1.1 GB table*, not because it narrowed a column list. **Dropping the
relationship load is the win; narrowing scalar columns on the same rows is not.** Any tail queue
that says "column-pruning" must say which of those two it means.

---

## 2. Options

### Option A — fix the top evictors (query shape + index)

**A1 · the golf identity scan — 533.7 GB/day, 19% of all physical reads in the database, from one query.**

```python
# app/routes/golf.py:2286, inside _build_completed_tournament — REQUEST PATH
select(FuturesMarket.id, FuturesMarket.source, FuturesMarket.external_id, FuturesMarket.name)
.where(or_(FuturesMarket.external_id.ilike("golf_%"),
           FuturesMarket.llm_sport_category == "golf"))
```

No `status` filter, no date bound: it reads every golf market ever, 1,110×/day, 492 MB each, mean
**2.74 s** — on a user-facing route. The `OR` is what defeats the indexes: `external_id ILIKE
'golf_%'` is prefix-anchored and *would* be indexable under `text_pattern_ops`, and
`llm_sport_category` has a btree, but OR'd together the planner falls back to a seq scan.

Two behaviour-preserving shapes, in increasing cost:
- rewrite the `OR` as a `UNION` of two indexable branches (set-identical by construction), and/or
- add an expression index `lower(external_id) text_pattern_ops` + rely on `ix_futures_markets_sport_id`
  for a `BitmapOr`.

⚠️ **Gotcha #31:** an index on a 977 MB table must not be created inside an Alembic migration —
Heroku's release phase times out (~5 min) and a `CONCURRENTLY` build hangs the release into an
outage. It has to be built manually. ⚠️ And `psql`/TCP 5432 egress is blocked from an agent session,
so **this step needs Alex or a `heroku run:detached` one-off** — it is not something this lane can
self-serve.

**A2 · the `MAX(created_at)` scan — 51.1 GB/day.**
`SELECT MAX(created_at) FROM futures_markets WHERE source = $1` reads **186.6 MB per call**, 280×/day,
mean 2.75 s — to return one value. `ix_futures_markets_source` is on `source` alone. A composite
`(source, created_at DESC)` makes it an index-only scan of one tuple. Same gotcha #31 caveat.

**A3 · the `event_id` self-join UPDATE — 268.5 GB/day.** 1,205 calls/day at 228 MB each. Not read
closely this window; named as the second-largest target and **owed a premise-check of its own**
before anyone touches it.

**A1 + A2 ≈ 585 GB/day ≈ 21% of all physical reads.** Adding A3 ≈ 30%.

### Option B — schedule isolation

**B1 · cadence↔TTL.** `precompute-admin-link-rate` and `precompute-admin-matured-linkage` run
`*/10`; `precompute-admin-audit-all` runs `*/15`. All three cache with `ex=3600` — TTL 1 hour,
described in their own module docstring as *"generous so a few skipped beats never empty it."*
**They recompute six times more often than their own cache expires.** Aligning cadence to TTL is a
free 6× cut with zero freshness loss relative to the contract the cache already advertises.

Worth **~20 GB/day (0.7%)**. Real hygiene; **not a fix**, and must not be sold as one.

**B2 · moving work to a quiet window.** There is no quiet window: 79.1 MB/s is continuous and
typeahead traffic is all-day. **Rejected on measurement.**

### Option C — buffer sizing (plan upgrade)

Heroku fixes `shared_buffers` per plan tier; it is not tunable on Standard. So this is a plan move.
At a constant 79.1 MB/s, turnover scales linearly:

| plan | RAM | ~shared_buffers | pool turnover |
|---|---|---|---|
| **Standard 0 (today)** | 4 GB | 1 GiB | **12.9 s** |
| Standard 2 | 8 GB | ~2 GiB | ~26 s |
| Standard 3 | 15 GB | ~3.75 GiB | ~48 s |
| Standard 4 | 30 GB | ~7.5 GiB | ~97 s |

Even the largest step buys ~97 s of residency against a 579 MB index that must survive between
arbitrary user keystrokes. **Buying cache buys a linear factor against a throughput problem; it does
not solve it.**

It should still probably happen — **for storage**: 51/64 GB (79.75%) is a near-term operational
ceiling regardless of latency. **Recommendation: raise it to Alex as a storage decision and refuse
to let latency be its justification.** (Costs not quoted here; they need confirming, not guessing.)

### Option D — a dedicated typeahead index table

Stop letting the search bar read the transactional tables at all. One narrow table — `entity_id`,
`entity_type`, `display_text`, `search_text`, a few rank hints — one row per searchable entity.

Sizing from the census: teams 9,083 + open markets 68,618 + open-market outcomes (a few hundred
thousand) + concepts ≈ **~380k rows**. At ~120 B/row ≈ **46 MB heap**; a trigram GIN scaled from the
measured 172 MB / 783,858 rows ≈ **~90 MB**. **Total ~140 MB** — versus 579 MB of trigram index
today sitting over two multi-GB heaps.

A 140 MB working set touched on every keystroke is one the clock-sweep will *keep*, even at 79 MB/s
turnover, because it is small and constantly re-referenced. This is the option that actually changes
the regime rather than the constant.

Costs and risks, stated: a migration slot; a freshness path (incremental upsert on write plus a
periodic reconcile); a second copy of truth, which means a staleness sentinel is part of the
deliverable, not a follow-up; and a recall proof — 0 of 46 gold dispositions may change, plus the 26
real-Postgres `test_search_recall_contract` cases.

### Option E — extend the warmer

`-51`'s warmer at 30 s is, in hindsight, **well matched to a 13 s turnover** — LAT-P056's cadence
self-correction (from `*/2 min`, which would have warmed nothing) now has a mechanism behind it
rather than an empirical rule. Extending it from the 8-query head deeper into the tail is cheap and
additive, but a warmer cannot cover a long tail by construction: the tail is the set of queries
nobody predicted.

---

## 3. Recommendation

**A sequence, because no single option both fits one queue and fixes the tail.**

1. **LAT-P057 (next code queue): A1 + A2.** ~21% of all database physical reads, from two queries.
   A1 is independently a user-facing fix — a 2.74 s request-path query on golf tournament pages.
   Neither touches ranking, so the 46 gold probes become an **armed null control** (ruling 050).
   *Blocking dependency:* index creation needs Alex or a `heroku run:detached` one-off (gotcha #31 +
   blocked 5432 egress). Land the query-shape rewrite first if the index has to wait — the `UNION`
   rewrite is behaviour-preserving on its own.
2. **Then: Option D**, as its own queue with a migration slot and a staleness sentinel in scope.
   **This is the one that closes #1866's tail.**
3. **Fold in: B1**, cadence↔TTL, in whichever queue already touches the beat file (declare
   `beat_schedule_change: true`, gotcha #12).
4. **Escalate, don't own: Option C.** Storage is at 79.75%. Alex's call, on storage grounds.
5. **Not now: A3**, until its own premise-check is taken.

**Explicitly rejected:** the queued `selectinload` column-pruning (§1 — I/O-neutral by the row-store
argument, worth 0.70% even if it were free), and B2 schedule isolation (no quiet window exists).

---

## 4. Pre-registered prediction, per ruling 050

Recorded **before** the work, with a halt attached, so it can falsify the model rather than score
the change.

**For A1 + A2:**

| surface | prediction | halt |
|---|---|---|
| 46 gold probes | **0 of 46 dispositions change. 39/44, MRR 0.8913043478260869.** | **any** movement HALTS — nothing here touches ranking, so movement means something believed surface-local is not |
| golf completed-tournament route | p50 **2.74 s → < 500 ms** | no improvement ⇒ the plan is not what the ranking assumed; re-read `EXPLAIN` before iterating |
| DB physical read rate | **79.1 → ~62 MB/s**; pool turnover **12.9 → ~16.5 s** | flat ⇒ `pg_stat_statements` attribution is wrong |
| **#1866's typeahead tail** | **SMALL, possibly NULL: 0–15% improvement.** Explicitly **not** predicted to be fixed. | **improvement > 30% ⇒ the continuous-throughput model is wrong**, the periodic-eviction model deserves re-opening, and the next window must **say which** |

That last row is the point of writing this down. A 21% cut in read volume moves turnover from ~13 s
to ~16.5 s, which is nowhere near enough to hold 579 MB of trigram index resident. **A1+A2 is worth
doing on its own merits and is predicted not to fix the tail.** If it does fix the tail, this
document's model is wrong, and that is a more valuable result than the latency.

**For Option D**, when it is staged: predict the tail collapses toward `/search`-like numbers
(`/search` p50 measured **407 ms** the same afternoon, against a typeahead tail of 1.2–5.2 s), and
predict **0 of 46** dispositions change. If recall moves at all, the table is not equivalent to the
thing it replaced and it does not ship.

---

## 4b. The sawtooth test I ran to falsify §0 — and why it came back inconclusive

If the decomposition's periodic-eviction model were right, typeahead latency should show a sawtooth
keyed to the matcher's `crontab(minute="5,20,35,50")`. That is directly testable without deploying
anything, so I tested it rather than arguing from the throughput number alone.

**Method.** 60 samples over 22 minutes (22:33:07 → 22:54:58 UTC), one every ~22 s, cycling six
never-warmed tail queries (`borussia`, `sacramento`, `eurovision`, `reykjavik`, `kilkenny`,
`wolverhampton`), against v3817 with **no warmer deployed** (`-51` is unmerged). Capture:
`capture-lat-p057-typeahead-sawtooth.json`.

```
overall   n=60   p50 1,661 ms   mean 2,256 ms   min 1,047 ms   max 10,295 ms

minutes since the matcher fired:
  + 0- 2   n=16   p50 2,486 ms
  + 3- 5   n=14   p50 1,824 ms
  + 6- 8   n= 8   p50 1,285 ms
  + 9-11   n= 8   p50 1,594 ms
  +12-14   n=14   p50 1,825 ms
```

That looks like a sawtooth. **It is not safe to read as one**, because the same data shows a strong
monotone trend across the run that is fully confounded with it:

```
first half  p50 2,540 ms        second half  p50 1,557 ms
```

The run began two minutes before a matcher fire, so "early in the run" and "soon after a fire"
largely coincide. And six queries repeated ten times each **warm their own pages** — the sampler is
an unintentional warmer. A 39% decay across 22 minutes of self-warming is the more parsimonious
explanation for both tables. **Verdict: inconclusive, and reported as inconclusive.** A powered
version needs many hundreds of *distinct, never-repeated* tail queries across several hours; owed,
not done.

**Two things it did establish, which are worth more than the failed test:**

1. **Repetition holds residency for minutes, even at 13 s pool turnover.** Six queries at 3
   requests/min stayed measurably warmer over 20 minutes. That is LRU working, and it is direct
   support for warming as a strategy — `-51`'s 30 s warmer is well-founded, independent of whether
   the periodic model is right.
2. **The tail is worse than the number in circulation.** #1866's tail has been quoted at ~1.2 s.
   Truly cold queries measured **p50 1,661 ms, mean 2,256 ms, and a worst case of 10,295 ms** — a
   ten-second typeahead response, in production, today. Whatever fixes the tail should be sized
   against that, not against 1.2 s.

## 5. Instrument gaps, named rather than worked around

- **`pg_buffercache` is not installed**, so residency cannot be measured directly — only inferred
  from throughput ÷ pool size. This is precisely why LAT-P056's two residency simulations
  disagreed and the claim had to be withdrawn. Installing it (`CREATE EXTENSION pg_buffercache`,
  a catalog-only operation) would turn the central premise of this document from an inference into
  a direct read. **Recommended as the cheapest instrument this program could acquire.**
- **`pg_stat_statements` is at its 5,000-entry cap** (4,945 held) and evicts, and **never records
  errored statements** — so timing-out queries are invisible and every mean above is over
  successful runs only. The link-rate kalshi scan (max 88,879 ms against a 90 s `statement_timeout`)
  is very likely timing out sometimes and undercounted here.
- No pre-`-45` `/search` p50 baseline exists, so "unchanged" was never gradeable (see
  `lat-p049-search-deploy-checks-2026-08-14.md`). Registered now at **407.1 ms**.
