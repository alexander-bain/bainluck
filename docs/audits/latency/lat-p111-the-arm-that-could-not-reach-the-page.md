# LAT-P111 — the arm that could not reach the page

**Pillar:** DISCOVER (search is how a person finds the question they came for).
**Ship:** *searching `winner` or `champion` stops taking twenty seconds and
returning nothing.*

**Issue:** [#2261](https://github.com/alexander-bain/bainluck/issues/2261) (filed
this cycle, OPEN — nothing closed; closure needs measured production evidence
and this branch has not deployed).

Cycle 83, queue `runner-inbox/latency/016-coldpath-conveyor.md`. Taken from the
conveyor's own hand-off: LAT-P110 closed by naming cold search the slowest thing
in the needle pool by an order of magnitude — *"683.5 ms then 458.5 ms against
14–72 ms for every tab"* — and this is that item.

---

## 1. What a person actually waits for, before this change

Live production, `?debug_timing=1`, 2026-08-28:

| query | total | futures stage | `degraded` | futures returned |
|---|---:|---:|---|---:|
| `winner`   | **20,022 ms** | 19,665 ms | `["futures","teams"]` | **0** |
| `champion` | **20,015 ms** | 19,659 ms | `["futures","teams"]` | **0** |
| `oscars`   | 1,635 ms | 1,310 ms | — | 10 |

The first two rows are not a slow search. They are the **LAT-P005 failure mode
in production today**: the request burns its entire 20-second deadline, logs a
recall failure, and returns HTTP 200 with the primary result class missing. From
outside — and this is the whole reason it has survived — an empty futures bucket
is indistinguishable from "there are no markets about that".

`winner` and `champion` are not exotic. On a prediction-market site they are
close to the two most obvious things a person can type.

## 2. It is one arm, and that was measured before it was blamed

The futures stage is a single statement. Six terms profiled cold via
`?debug_timing=1` put `futures` at 54–92 % of every build:

| term | total | futures | rest |
|---|---:|---:|---:|
| `senate runoff` | 877 | **805** | 72 |
| `wimbledon` | 744 | **636** | 108 |
| `tour de france` | 427 | **369** | 58 |
| `nvidia earnings` | 364 | **317** | 47 |
| `ballon` | 295 | 116 | 179 |
| `emmy` | 120 | 65 | 55 |

`EXPLAIN (ANALYZE, BUFFERS)` on **the exact statement the ORM emits** (rebuilt
through the route's own helpers, not a hand-written equivalent), `oscars`:

```
Limit                                                        839 ms
  Sort
    Nested Loop
      Unique  <- Append (the UNION of recall arms)
        Bitmap Heap Scan futures_markets     84 rows    372 blk    23 ms   <- NAME arm
        Nested Loop                          67 rows            805 ms   <- OUTCOME arm
          Aggregate
            Bitmap Heap Scan futures_outcomes  2,334 rows  1,572 blk  583 ms
          Index Scan futures_markets_pkey      x931        3,735 blk  220 ms
```

**The name arm: 84 rows, 23 ms. The outcome arm: 67 rows, 805 ms.** And
`_futures_name_tier` is the FIRST `ORDER BY` key, so those 84 name matches are
tier 0 and those 67 outcome-only rows are tier 2. **Not one of the 67 could have
reached a twenty-row page.** The 805 ms bought nothing — not "little", nothing.

## 3. What this is NOT

LAT-P032 measured this same arm on `fed` and found it actively *harmful* — 7 of
20 result slots taken by substring collisions inside proper nouns
(Con***fed***eration, Vladimir ***Fed***oseev). It then deliberately left the arm
alone, and wrote down why: deleting a recall arm is a recall-semantics change,
and this lane does not bolt those onto a latency queue. **LAT-P002 was REVERTED
for exactly that.** #1732 carries the open question.

Nothing here is deleted. The candidate set the route can see is unchanged. The
arm is *skipped only in the case where the tier order proves it cannot matter*,
and merged in whenever it can.

## 4. The fix, and its proof

`_fetch_futures_window` fetches the window **tier-ordered**:

1. Run the tier<=1 arms (name, league-ticker, alias).
2. If they fill the window, **stop** — return them.
3. Otherwise the tier<=1 set is *complete* (the LIMIT did not bind), so run the
   outcome arm and append its rows, deduped by id.

Three lines are the whole proof:

* every row contributed by the outcome arm alone matches neither name, ticker
  nor alias, so `_futures_name_tier` scores it **2**;
* tier ASC is the first `ORDER BY` key, so every tier-2 row sorts below every
  tier-0/1 row;
* therefore when the tier<=1 arms fill the window, the full arm set returns those
  same rows in that same order — and when they do not, appending the tier-2 rows
  in their own order reconstructs the full page exactly.

### 4a. A coupled change, stated rather than smuggled in

The five `ORDER BY` keys **did not order a large, common class of rows at all**.

On `ballon`, ids `58598676..58598736` are one Kalshi series — "Will \<player\>
finish in the top 3/5 of the 2026 Ballon d'Or?". Every one carries tier 0,
`ts_rank_cd` `0.4000000059604645`, `market_tier` 3, `volume` NULL, and an
`updated_at` identical **to the microsecond** (one ingest batch). Every declared
key is a tie, so which twenty of them filled a twenty-row window was decided by
the **plan**.

Measured: two different plans over the same data returned pages differing in
**12 of 20 rows**, while the same plan twice was perfectly stable. That is why
this has been invisible — it looks deterministic right up until an unrelated
planner change quietly reshuffles somebody's search results.

`FuturesMarket.id.asc()` is appended as a final key. It is **not** a relevance
signal and does not pretend to be one: it orders only rows already equal on every
signal the route declares. It is also what upgrades the tier split from
answer-identical-in-practice to answer-identical.

### 4b. Equivalence, on production data

For each term: fetch the ordered ids of the full query, the tier<=1 query and the
outcome-only query, run the merge, compare.

**21/21 identical — same ids, same order.** 8 hit the skip, 13 went through the
merge. Terms: the needle's own set (`ballon`, `wimbledon`, `nvidia earnings`,
`tour de france`, `senate runoff`, `emmy`, `hurricane`) plus every term prior
latency cycles argued about (`fed`, `president`, `nba champion`, `masters
winner`, `us recession 2026`, `world series`, `stanley cup`, `super bowl`, `world
cup`, `best picture`, `nfl mvp`, `nba finals`, `march madness`, `election`).

🔴 **Run WITHOUT the total order, the same comparison mismatched on 4 of 21** —
and the control (the current query against itself) was stable, so it was not
noise. Chasing those four is what found §4a. They are recorded here because a
reader deserves to know the identity claim was *tested and initially failed*,
not assembled from a proof that was never at risk.

### 4c. Cost, quoting blocks

`EXPLAIN (ANALYZE, BUFFERS)`, blocks (hit+read) — **blocks, not ms**, because
wall time here swings several-fold on an identical plan as the buffer cache warms:

| query | full | tier<=1 | |
|---|---:|---:|---|
| `winner`   | **>25 s, TIMED OUT** | 26,782 → 20 rows in **2,826 ms** | now answers |
| `champion` | **>25 s, TIMED OUT** | 26,740 → 20 rows in **1,559 ms** | now answers |
| `fed`      | 36,672 | 2,338 | **−94 %** |
| `oscars`   | 7,158 | 797 | **−89 %** |
| `world cup`| 6,124 | 2,688 | −56 % |
| `president`| 6,023 | 3,876 | −36 % |
| `nba champion` | 8,248 | 6,594 | −20 % |
| `election` | 15,055 | 12,638 | −16 % |

`winner` and `champion` are the ship: both currently exceed the deadline and
return nothing; both now return a full twenty-row window well inside it.

**The honest other side.** When the skip does *not* fire, the stage issues two
statements instead of one, and the tier<=1 half is work the single statement was
already doing. Measured on the low-recall terms this costs roughly the tier<=1
query on top — `senate runoff` 304 blocks against a 1,207-block full query,
~25 % more blocks / ~16 % more wall. Those are queries that already answer in
~200 ms, so it is not a user-visible cost, but it is a real one and it is not
being hidden. The merge path was chosen over a cheaper "probe then re-run the
full query" precisely because that variant paid the *expensive* arm twice.

## 5. Guards

* **`tests/test_search_futures_tier_split.py` — 54 tests.** The load-bearing one
  is a randomised property test (40 seeds, corpus sizes straddling the window on
  both sides) asserting the split page equals the unsplit page, plus the window
  boundary walked explicitly at 0/1/19/20/21/50. It drives the REAL
  `_fetch_futures_window` — the function takes its query builders as parameters
  — against a model of the ORDER BY, because the seeded CI database is always
  small and a data-volume test would prove nothing, while the ordering property
  is volume-independent and is the entire basis of the optimisation.
* Identity alone is satisfiable by changing nothing, so the suite also asserts
  the **absence** of the second query when the skip fires, and its **presence**
  when it does not.
* **`scripts/evals/search_tier_split_mutations.py` — 8/8 killed.** Nothing on
  disk is mutated: the function's source is mutated as a string and `exec`'d with
  the real module dict as its globals, which is the shape `test_mutation_guard.py`
  names as preferred and which is immune by construction to the
  SIGTERM-leaves-a-mutant-behind failure. The two that matter are
  **M3-never-skip** (the no-op "fix" — every page still correct, 805 ms still
  paid; only the absence assertions catch it) and **M2-always-skip** (recall
  deleted while the response stays a 200).
* Registered in `scan_mutation_residue.py`'s `SHAPES` with a declared `TARGET`,
  so Pass A asserts each needle is still PRESENT in `events.py` — a harness whose
  needles have drifted reports 8/8 killed while testing nothing.

### Guards re-pointed, deliberately

Four source-shape guards anchored on text this change moved. Each was re-pointed,
none was weakened, and each invited exactly that in its own message:

| guard | old anchor | new anchor |
|---|---|---|
| `test_recall_arms_are_combined_with_a_union` | `union(*_futures_arm_selects)` | `union(*_selects)` |
| `test_the_tier_key_sorts_ahead_of_the_rank` | `futures_query = (` | `def _futures_window_query(` |
| `test_futures_stage_is_rearmed_with_the_live_deadline` | `futures_result = await db.execute(futures_query)` | `await _fetch_futures_window(` |
| `search_word_test_mutations:futures-window-back-to-a-literal` | the old `.limit(...)` block | the same block inside the builder |

One guard was **added** rather than re-pointed:
`test_the_second_futures_query_rearms_the_bound_too`. The stage is now two
statements, and the second is the expensive one — a re-arm covering only the
first would restore the exact defect LAT-P005's re-arm exists to prevent, inside
the stage that was fixed for it. It has a behavioural twin in the new suite, with
a negative control so it cannot pass on a re-arm that fires unconditionally.

## 6. Observability

`?debug_timing=1` now reports `futures_outcome_arm`, beside `_stage_ms` rather
than inside it (`total_ms` sums that dict's values, so a string member there
would be a TypeError on every timing request and nowhere else). Four values, and
the fourth is the point: `skipped` · `merged` · `absent` (there was no outcome
arm to skip — LAT-P010 drops it for short single terms) · `not_reached` (the
deadline was already spent). Crediting `absent` as `skipped` would count a saving
this change did not make; that is mutant M7.

## 7. Post-deploy checks OWED to the first window after this reaches a release

1. **`GET /api/events/search?q=winner&debug_timing=1`** — must return a
   non-empty `futures` bucket with **no** `degraded` key. This is the ship. Same
   for `q=champion`.
2. **`futures_outcome_arm` reads `skipped`** on `winner`, `champion`, `fed`,
   `oscars`, `ballon`, and **`merged`** on `senate runoff`, `nvidia earnings`,
   `nfl mvp`. A field that reads `skipped` everywhere is M2 shipped.
3. **Recall did not move.** Run the search recall gate; `masters winner` and
   `us recession 2026` are outcome-arm-dependent (both took the merge path here)
   and must still resolve.
4. **The page is stable.** Fetch `?q=ballon` twice and diff the ids — §4a means
   this should now be identical by construction, where before it was identical
   only by plan stability.
5. **Quote the BLOCKS, not the ms** on any EXPLAIN re-run: wall time on these
   statements swung 8× on an identical plan as the buffer cache warmed.

## 8. Parked

* **`CREATE INDEX ON futures_outcomes (market_id) INCLUDE (name)`** — would make
  the outcome arm's 1,572-block heap scan an index-only scan and remove the need
  to skip it at all. `migration_slot: none` this cycle: ruling 080 makes the slot
  integrator-owned and gotcha #31 binds (never `CREATE INDEX CONCURRENTLY` in
  Alembic). **REQUESTED on #2261, never taken.** Parked as P111-1.
* **`winner` still costs ~2.8 s and `champion` ~1.6 s** even after the split.
  That is the common-word head the `search_cache` docstring already argues no
  string index can fix; the response cache and `search_head_warmer` are the
  intended answer and both are live. Parked as P111-2 — it is a real number, it
  is 7× better than a timeout, and it is not this ship.
* **The two `typeahead_warmer_mutations` needle drifts** (M4, M6) reported by
  `scan_mutation_residue.py` are **pre-existing on master** — verified by running
  the scanner in a clean master worktree, not assumed. Not touched here; parked
  for the owning lane.
