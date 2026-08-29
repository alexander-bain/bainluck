# LAT-P132 — the 17.9 seconds of "app time" that were a query

**Pillar: DISCOVER.**
**Ship: landing on the men's college basketball grid stops erroring.**

Issue **#2302** (split out of #2301 by LAT-P131). Branch `program/latency-118`, cut from
**CURRENT MASTER `cf616910`**. `migration_slot: none` · `beat_schedule_change: FALSE` · no config
var · **no DDL** · backend only · **3 files** · zero frontend files.

🔴 **The warm-list half of this ship is NOT in this branch, and that is a base decision, not an
omission.** `#2302` names `tests/test_precompute_grids_budget.py` as the test to update — that file,
`GRID_WARM_LEAGUES`' thirteen-league form, and the whole pass budget belong to **LAT-P131 on
`program/latency-117`, which is still unmerged**. The conveyor's standing rule is *branch from
CURRENT MASTER, never stack on unmerged latency branches*, and INT-151 produced a same-day worked
example of why: git auto-merged `sport_keys.py` with no conflict and silently dropped a function
q435 depended on. Adding `ncaa-basketball` to master's four-league list would have manufactured
exactly that hazard against `-117`.

**The whole diff for that half is written and gated** — 18 tests green, 13/13 mutants killed — and
is banked verbatim at `.claude/handoff/ARTIFACT-LAT-P132-warmlist-followon.patch`, parked as
**P132-5**, applicable the moment `-117` merges. It is not undone; it is unstackable.

**The 503 does not wait for it.** The 503 is caused by the candidate scan, which this branch fixes
for every visitor, warm list or not.

---

## The harm, read from the 24 h buckets and not from `count`

Sentry, `statsPeriod=24h`, 2026-08-29 (gotcha #49 — `count` is LIFETIME):

| issue | 24 h | lifetime |
|---|---|---|
| `Playoff grid ncaa-basketball: request timed out after 25s — attempting last-good` | **9** | 12 |
| `HTTPException: Playoff grid for 'ncaa-basketball' timed out and no last-good payload is available` | **7** | 9 |
| same, `golf` | 1 | 1 |
| same, `ncaa-women-basketball` | 1 | 1 |

Nine timeouts, **seven of which reached a user as a 503 with nothing behind them**. 🔴 Lifetime 12
against 9 in the last 24 h means this is **new and accelerating**, not a long tail — and
🔴 **two of those seven 503s are this session's own reproductions.** The organic figure is five, and
saying so is cheaper than having it found.

## The finding, and it is not the one the issue was filed with

`#2302` was filed on this reading, from LAT-P131's production sweep:

```
/api/playoffs/ncaa-basketball?top=11
wall=25131.2; db=7260.3; app=17870.9; q=4; maxq=7099.6; unfinished=1   → HTTP 503
```

and its caution said, in bold: *"🔴 17.87 s of the 25 s is `app`, not `db`. Profile the `app` half
before touching SQL. The 7.26 s of db time is not the problem here and optimising it cannot close a
25 s wall."*

🔴 **That split is partial, and it says so in its own last field.** `app/utils/request_timing.py`
defines `unfinished` as *"statements that started but never recorded a finish … counted rather than
silently dropped, so a partial `total_ms` announces itself instead of reading as a fast request."*
An unfinished statement contributes **nothing** to `db`; `app` is `wall − db`; therefore **the whole
duration of an in-flight query is reported as application time.** `q=4` is the number of statements
that *completed*. The fifth was still running when the wall fired, and it was 17.87 seconds long.

The instrument was not wrong. It announced the partiality in the field next to the number, and the
reading took the ratio anyway.

**Re-measured on production 2026-08-29, the same URL, minutes apart:**

| attempt | result | wall | db | app | q | maxq | unfinished |
|---|---|---|---|---|---|---|---|
| 1 | **200** | 20,801 | 20,128 | 673 | 26 | 15,337 | — |
| 2 | **503** | 25,140 | 6,471 | **18,669** | 4 | 6,351 | **1** |
| 3 | **200** | 21,558 | 20,980 | **578** | 26 | **16,159** | — |

The two runs that **finished** report `app` at 578–673 ms and one query at **15.3–16.2 s**. The run
that **died** reports `app` at 18,669 ms and four queries. Same code, same data, three minutes
apart. There is no Python problem. There is one query, it takes about 16 s of a 21 s request, and
whether the request survives is a coin flip against a 25 s wall.

🔴 **A second P131 claim falls with it: "the one league that cannot be built at all."** It builds,
and it builds a *complete* page: **68 teams, 6 columns**, `movers_degraded` absent, the field
opening Florida / Duke / UConn / Illinois. Two 200s today with real payloads. It straddles the wall,
exactly like NFL — which P131 described correctly in the very same document. This also means
`_grid_payload_usable` will publish it, so warming it cannot clobber the 24 h `:stale` mirror with
an empty grid: the case P131 built that guard for does not arise here.

---

## The query

`get_playoff_grid`'s candidate scan:

```python
stmt = select(FuturesMarket).where(market_filter_with_status)
```

**LAT-P129 already fixed most of this and left a measurable remainder.** P129 stopped the predicate
sequentially scanning all 911,217 rows by scoping each external-id path to the source that owns its
id space. What that leaves is:

```
Bitmap Heap Scan on futures_markets   (actual rows=90)
  Recheck Cond: ((source = 'odds_api' OR source = 'kalshi') OR (status IN (...) AND name ILIKE ...))
  Rows Removed by Filter: 265,961
  Exact Heap Blocks: 73,643
  Shared Read Blocks: 41,318
```

`source = 'kalshi'` was the **only** term in the id-space arm an index could serve, because
`external_id ILIKE 'KXMARMADROUND%'` is not index-usable in any form: `ILIKE` never uses a btree,
and this database collates `en_US.UTF-8`, so even a case-sensitive `LIKE 'x%'` would need
`text_pattern_ops`. So Postgres bitmapped *the whole of Kalshi* — 266K rows — and rechecked every
one of them in the heap to return 90.

**P129 found this too, wrote the answer, measured it at 20×, and REJECTED it:**

> 🔴 **A 20× FASTER ANSWER WAS WRITTEN, MEASURED, AND REJECTED.** `external_id >= 'KXMLB' AND
> < 'KXMLC'` is an Index Scan on `uq_futures_source_external`: 396 ms / 34,415 rows / 0 removed vs
> 8,225 ms. This DB is **`en_US.UTF-8`**, and **a range is only a prefix in C collation** — which is
> why Postgres itself refuses a btree for `LIKE 'x%'` here. Same rows today is a coincidence, not an
> equality. Parked **P129-3** (needs `text_pattern_ops` + a migration slot + Alex, gotcha #31).

P129 is right about the form it wrote. This ship does not argue with it; it changes the form until
the objection no longer applies.

---

## Why this range is a proof and P129's was a coincidence

Two differences, and both are load-bearing.

**1. The `ILIKE` is conjoined, never replaced.** The emitted predicate is `range ∩ ILIKE`, so the
range can only ever *remove* rows — it can never admit a wrong one. An over-wide bound is free.
That collapses the risk surface from "wrong rows and missing rows" to "missing rows" alone.

**2. The low bound drops the prefix's last character.** `low = prefix[:-1]`, not `prefix`.

* **Low bound.** Every string that starts with `prefix` (in any case) carries at least one more
  *non-ignorable* character than `prefix[:-1]` — namely `prefix[-1]`, which the helper guarantees is
  ASCII alphanumeric. Its PRIMARY weight sequence therefore strictly extends the bound's, and it is
  greater **at the primary level**, where no case, accent or punctuation tie-break is ever consulted.
  `>= prefix` has no such argument, and the counter-example is concrete: glibc sorts lowercase
  *before* uppercase at the tertiary level, so a hypothetical `'kxmlb…'` row sorts BELOW `'KXMLB'`
  and would be silently dropped. `'KXML'` cannot have that problem.
* **High bound.** `prefix[:-1] + succ(prefix[-1])`, and `succ` is **refused** unless it stays inside
  the same ASCII class — `z`, `Z` and `9` are rejected because `{`, `[` and `:` are punctuation,
  which `en_US.UTF-8` ignores at the primary level, so a bound ending in one does not mean what it
  looks like it means. Within a class, every collation orders `b < c`, so a prefix match differs
  from the bound at that character's primary weight and is strictly less.

Neither bound is a claim about today's rows. **That is the whole difference from P129-3**, and it is
why this needs no `text_pattern_ops`, no migration slot, and no Alex gate: it uses
`uq_futures_source_external`, the `(source, external_id)` unique btree **already on the table**.

A whole-table census is kept as corroboration, not as the argument (2026-08-29, all 25
`(source, prefix)` pairs configured by all 14 league configs): **zero** rows match `ILIKE prefix%`
while falling outside the *tighter* `[prefix, high)` range — 54,120 matching Kalshi rows, 9 matching
Odds API rows. The shipped range is a strict superset of the one censused, so zero there implies
zero here. A direct re-census under the shipped bounds completed 3 of 6 chunks — 27,077 matches,
0 out of range — and 🔴 **the other 3 were `statement_timeout`, which is a story about the harness
and not a difference** (P129's own lesson, applied to P129's own successor).

---

## Measured

`EXPLAIN (ANALYZE, BUFFERS)` on the **exact predicate the builder emits**, rendered from the real
clause object rather than retyped, production 2026-08-29:

| league | OLD ms | NEW ms | rows OLD = NEW | heap blocks | read blocks |
|---|---|---|---|---|---|
| **ncaa-basketball** | **24,465** | **984** | 12 = 12 | 73,644 → **161** | 43,237 → 681 |
| **nba** | **22,804** | **586** | **9,042 = 9,042** | 74,137 → 5,033 | 45,669 → 1,104 |
| ncaa-football | 926 | 1,171 | 13 = 13 | 314 → 314 | 332 → 0 |

🔴 **Row counts are identical in every pair, including NBA's 9,042** — an equivalence measured on a
large result set, not inferred from a twelve-row one.

`ncaa-football` is the honest null and is printed rather than dropped: its arms were already
index-served, its heap block count does not move, and 926 → 1,171 ms is trigram-scan variance.
Not every league gains.

🔴 **`mlb` and `wnba` could not be measured this way and that is an instrument limit, not a result.**
Their name patterns render `'%AL+:East|West|Central%'`, and `:East` inside the admin `db-query`
rail's `text()` parses as a bind parameter (gotcha #45). SQLAlchemy binds the pattern as a parameter
on the real path, so production is unaffected. **They are unmeasured, not unchanged.**

The bench agrees with the request: attempt 3's `maxq=16,159 ms` **is** this scan.

### The instrument was corrected before any number was quoted

The first sweep hand-wrote the predicate and got `'%March%Madness%'` where the code emits
`'%March+Madness%'` — `_league_pattern_to_ilike` deletes `\s` before it can convert `\s+` to `%`
(a known defect, parked **P129-2**, *"33 of 51 name patterns"*). Those numbers reported 90 candidate
rows where production sees 12. **They were discarded, not reconciled**; every table above is
rendered from `_build_grid_market_filters`' own clause object via `literal_binds`.

---

## What shipped

**1. `app/routes/playoffs.py` — `external_id_prefix_range` + `_external_id_prefix_condition`.**
One helper, consumed by `_build_grid_market_filters`, so **both** filters it returns — the candidate
scan and the resolved backfill that reuses the bare form — get the bound. All 14 leagues, both
sources.

**2. (banked, not shipped here — P132-5, rides `-117`'s merge.)**
`app/tasks/precompute_category_pages.py` — `ncaa-basketball` joins `GRID_WARM_LEAGUES`, discharging
the exclusion P131 wrote; `KNOWN_UNBUILDABLE` goes empty with a new test pinning it empty; and
`test_grid_timeout_is_recorded_not_swallowed` stops asserting `timeout_s == GRID_WARM_TIMEOUT_S`, an
equality that held only because `mlb` was **last** in the warm list and was handed everything left —
it becomes 13th of 14 and its share becomes a real bound, so the assertion now pins what #1484
actually asks of the rail (*the deadline that bound is the one written down*) rather than the
constant it happened to equal. `scripts/lat_p131_mutation_battery.py`'s `M-READD-UNBUILDABLE` mutant
inverts to `M-DROP-NCAAB`: it added `ncaa-basketball` to the warm list, which becomes the correct
state, so it would have **SURVIVED** and turned 13/13 into a 12/13 nobody re-read.

Gated on the `-117` base before it was set aside: **18 tests green, 13/13 mutants killed, exit 0.**

🔴 **Its position in the list — last — is the one thing there that is not measured, and it is last
*because* it is not measured.** Predicted ~6.4 s (21.6 s observed, minus the 16.2 s `maxq` this ship
removes, plus ~1.0 s for the replacement scan) — but a prediction is not a measurement, and the
ordering's only job is to give the tail slack, so an unmeasured league belongs where being wrong
costs least. N goes 13 → 14, so the guaranteed floor moves 13.8 s → 12.9 s and the typical pass goes
~131 s → ~137 s against a 180 s budget. The 120 s per-league ceiling, the pass budget, and
`_grid_payload_usable` all bound the damage if the prediction is wrong.

---

## Guards

**`tests/test_grid_external_id_range_lat_p132.py` — 223 tests.** The defect was invisible in
results: the predicate selected exactly the right rows and its only symptom was a query plan. So
these assert **shape and bounds**, never results.

* the **landmine**: every `(source, prefix)` pair any league config declares must yield a range — a
  new prefix that cannot be bounded FAILS here instead of silently costing 16 s at 03:00;
* every `external_id ILIKE` in **both** filters for **all 14 leagues** is accompanied by exactly one
  lower and one upper bound, **counted**, so one league quietly losing its bounds is caught;
* **the second door**: the range must never *replace* the `ILIKE` — that is faster still, identical
  on today's rows, and is precisely P129-3's rejected form;
* the bounds sit in the **same `AND` group** as their own `ILIKE`, so the NCAA range can never be
  hoisted onto the MLB arm;
* 🔴 `low == prefix[:-1]` and `low != prefix`, asserted per configured prefix — **the one character
  the proof lives in**, pinned so tightening it back is a failure and not a subtlety;
* the successor sweep, **executed over every permitted last character**, not three hand-picked ones;
* ten refusals (`''`, one-char, `z`/`Z`/`9`, `_`, space, `%`, non-ASCII, an already-wildcarded
  prefix), and a test that a refused prefix still emits **the exact predicate that shipped before**
  — slow is a correct answer; a missing grid column is not.

**`tests/test_playoff_grid_source_scoped_candidates_lat_p129.py`** — P129's evaluator over the real
clause object had to learn `>=` and `<`. 🔴 It models **`C` collation** (Python compares code
points) while production is `en_US.UTF-8`, and the two disagree on exactly the thing this ship
reasons about. That is written into the evaluator: fixtures stay canonical-case, and the
collation-sensitive half is proved in the docstring and measured on production, **not asserted here,
where it could only be asserted wrongly.** All 96 of P129's tests pass unchanged otherwise — the
behavioural proof that the range changed no answers.

**Battery.** `scripts/lat_p132_mutation_battery.py`: **12/12 killed, 0 survived, 0 harness
failures, exit 0**, restore SHA-256 identical, both suites run per mutant so a mutant cannot satisfy
the new file by breaking P129's. 🔴 **One mutant SURVIVED on the first run and it was the mutant
that was wrong, not the guard** — it wrapped `prefix_conditions` in a redundant `or_()`, which
changes nothing, so surviving was correct. Recorded in the file rather than quietly swapped: a
surviving mutant is a claim about the guard until you prove it is a claim about the mutant.

---

## Owed after merge + deploy

1. **Re-run the three readings in the table above** against production and confirm
   `/api/playoffs/ncaa-basketball?top=11` lands well under the 25 s wall. Nothing post-deploy is
   claimed here.
2. **Read `/api/admin/category-precompute/last`** for the per-league `duration_s` of the leagues
   already in the warm list — several of them pay this same scan and should have got cheaper, which
   also re-derives the ascending order P132-5 needs.
3. **Apply `ARTIFACT-LAT-P132-warmlist-followon.patch` when `-117` merges** (P132-5) and re-gate it
   on the merged base — it was gated on `-117`, not on `-117 + master`.
4. Production is `6b4cd014`; `-116` and `-117` are unmerged and the merged `-108`…`-115` run is
   **not yet deployed**, so every production number in this document is pre-P129-deploy.

## Parked

* **P132-1** — `_league_pattern_to_ilike` renders `\s+` as a literal `+`, so the `ncaa-basketball`
  category arm matches **12** rows where the intended pattern matches **90**. Already parked as
  **P129-2** (*33 of 51 patterns*); re-stated here only because repairing it will make this grid
  heavier again, so it and this ship must be measured together.
* **P132-2** — `mlb` and `wnba` cannot be plan-measured through the admin `db-query` rail at all
  (gotcha #45, `:East` parses as a bind param). Either the rail escapes `:` or the grid bench needs
  a different instrument; today the two most expensive grids are the two that cannot be read.
* **P132-3** — the same unindexable `external_id ILIKE` shape lives in three more functions here
  (`_query_tournament_db_markets`, `_build_upcoming_golf_event_grid`,
  `_get_team_progression_for_event_uncached`); this helper is now the thing they would call.
  Already parked as **P129-4**; it is cheaper now that the helper exists.
* **P132-4** — **read `unfinished` before reading the `app`/`db` ratio.** This cycle spent its
  opening hour profiling Python that did not exist because a split with `unfinished=1` was read as
  if it were whole. Offered as a gotcha, not a queue.
* **P132-5** — **the warm-list half, banked and unstackable.**
  `.claude/handoff/ARTIFACT-LAT-P132-warmlist-followon.patch`: `ncaa-basketball` joins
  `GRID_WARM_LEAGUES` (last), `KNOWN_UNBUILDABLE` empties with a test pinning it empty,
  `test_grid_timeout_is_recorded_not_swallowed` stops asserting the ceiling, and P131's battery
  mutant inverts. **Apply when `program/latency-117` merges, and re-gate on that base.** 18 tests
  and 13/13 mutants green on `-117` alone.
