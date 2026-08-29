# LAT-P129 — the grid that read 911,217 rows to find 37

**2026-08-29 · Pillar: DISCOVER · branch `program/latency-115`, cut from current master `d9b76e9b`**

**Ship: when the English Premier League or Bundesliga grid actually has to be rebuilt, the user who
lands on it stops waiting twenty-two seconds — and, on EPL, stops getting a 503.**

Stated precisely, because the flattering version is available and wrong. A warm read is 0.31 s and
this queue does not touch it. What it touches is the **rebuild**, and §2a establishes exactly who
pays that and when.

---

## 1. The surface, established before anything was measured

P127 and P128 both paid for this lesson, so it runs first: **gotcha #155 answers "will this
collide?", not "does anyone wait on this?", and the caller grep is the cheaper of the two.**

`fetchChampionshipGrid` → `GET /api/playoffs/{league_slug}` has **four** real callers:

| caller | surface |
|---|---|
| `frontend/app/sport/[sport]/[league]/page.tsx:235` | the league page |
| `frontend/app/sport/[sport]/[league]/team/[team]/page.tsx:67` | the team page |
| `frontend/app/playoffs/[sport]/page.tsx:580` | the championship grid page |
| `ios/.../Services/APIClient.swift:1015` | the native grid screen |

Three web surfaces and one native one. Not another `fetchMarketMoves`.

It has a fifth consumer that P128 discovered from the other end: `_compute_league_context` calls
`get_playoff_grid_cached`, so the **event detail page** pays this rebuild too whenever the shared
key is cold.

## 2a. ⚠️ Who pays the rebuild, and how often — measured, not assumed

A queue that quotes a 22 s number without saying how often anyone meets it is quoting the
flattering half. So:

```
GET /api/playoffs/epl          200  0.308 s  wall=26.9  db=0.0  q=0   teams=20   (warm)
GET /api/playoffs/bundesliga   200  0.349 s  wall=26.7  db=0.0  q=0   teams=18   (warm)
```

Neither carries `stale` / `stale_reason`, so both are genuine warm hits, not last-good serves.
**Most reads of these pages are already fast and this queue does not change them.** The rebuild is
reached like this:

| state | what the user gets |
|---|---|
| warm key present (TTL **3900 s**) | 0.31 s |
| warm cold, `:stale` present (TTL **24 h**) | last-good, instantly — **no rebuild is triggered** |
| **both cold** — after ~24 h without one, or after any deploy | the full rebuild: 21.7 s, or **503** |

🔴 **And soccer is never warmed for it.** `GRID_WARM_LEAGUES = ["mlb", "nba", "nhl", "golf"]`
(`tasks/precompute_category_pages.py:307`) — the hourly beat does not cover EPL, Bundesliga, La
Liga, Champions League or MLS. Their keys exist **only** because some user, or some measurement
window, already paid the 22 seconds to build one.

The two keys read above were built at **14:56:21Z** and **14:55:58Z** — during LAT-P128's own
measurement pass. The reason EPL is warm this afternoon is that the previous cycle rebuilt it.

So the honest scope of this ship: **the unlucky user, once per stale window and once after every
deploy**, plus **the event detail page** (P128 routed `_compute_league_context` through this same
key), plus the hourly warm beat for the four leagues it does cover — MLB's candidate scan measured
**19,905 ms → 10,686 ms** on the same change. And it makes **P128-2** — widening
`GRID_WARM_LEAGUES` to soccer, a decision priced at `GRID_WARM_TIMEOUT_S = 120` per league, serial —
affordable for the first time, which is the thing that would make these pages fast for everyone.

## 2. The reading

Taken with `?top=11`, which fails `cache_eligible` (`not debug and hours is None and top == 10`) and
so neither reads nor writes the shared key — an uncached rebuild that leaves production's cache
exactly as it found it.

```
GET /api/playoffs/epl?top=11         503  25.383 s  wall=25122.9 db=22811.3 q=6  maxq=17102.3 unfinished=1
GET /api/playoffs/bundesliga?top=11  200  21.664 s  wall=21334.8 db=21310.7 q=9  maxq=15041.4
GET /health                (control) 200   0.273 s
```

`db` is **99.9 %** of wall on the one that completed, and a single query is **70 %** of `db`. EPL
does not merely run slowly: it crosses the wrapper's 25 s `asyncio.wait_for` and answers **503**.

## 3. The defect

`get_playoff_grid` finds a league's candidate markets three ways. Two of them match on
`external_id`:

* **A** — `external_id` starts with an Odds API sport key (`soccer_epl%`)
* **B.1** — `external_id` starts with a Kalshi series ticker (`KXMLB%`)
* **B.2** — `llm_sport_category` matches **and** the market name matches a league name pattern
  (Polymarket)

Written as one flat `OR`, that predicate spans two unrelated columns. No single index can serve it,
so Postgres stops trying:

```
Gather  (actual_time=16319.039 rows=37)
  -> Parallel Seq Scan on futures_markets  (actual_time=15854.085 rows=18 loops=2)
       Filter: ((external_id ~~* 'soccer_epl%' AND status = ANY('{open,closed,resolved}'))
             OR (llm_sport_category = 'soccer' AND (name ~~* ... ) AND status = ANY('{open,closed}')))
       Rows Removed by Filter: 455571
       Shared Read Blocks: 60442     Shared I/O Read Time: 6804.105
Execution Time: 16502.924 ms
```

**911,217 rows read to return 37.**

### The number that makes it absurd

| source | rows in `futures_markets` |
|---|---:|
| polymarket | 645,219 |
| kalshi | 265,631 |
| datagolf | 330 |
| **odds_api** | **12** |

Path A can only ever match an Odds API market. There are **twelve** of them. Finding them costs a
645,219-row Polymarket scan and a 265,631-row Kalshi scan.

### Isolating it

| branch, run alone | time | rows |
|---|---:|---:|
| **A** — `external_id ILIKE 'soccer_epl%'` | **12,540 ms** (Seq Scan) | **0** |
| **B** — `llm_sport_category='soccer' AND name ILIKE …` | **633 ms** (BitmapAnd over `ix_futures_name_trgm` + `ix_futures_markets_status`) | **37** |

The branch that contributes **every row** costs 633 ms. The branch that contributes **nothing**
costs 12.5 seconds — and, OR-ed together, drags the other one onto a sequential scan with it.

## 4. The fix

`models.py` already documents the pairing, one line apart:

```python
source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'odds_api', 'kalshi'
external_id: Mapped[str] = mapped_column(String(200), nullable=False)        # sport_key or event_ticker
```

Which of the two `external_id` holds **depends entirely on `source`**. `LeagueConfig.sport_keys` is
The Odds API's id space; `LeagueConfig.external_id_prefixes` is Kalshi's. The fix writes that
already-documented pairing where a query planner can read it:

```python
GRID_ID_SPACE_SOURCE = {"sport_keys": "odds_api", "external_id_prefixes": "kalshi"}
```

and scopes each external-id branch to its owning source. Nothing about which markets belong to a
league changed. The construction moved into `_build_grid_market_filters(config)`, a pure function,
so it can be tested without a request.

| query | before | after | rows |
|---|---:|---:|---:|
| EPL candidate scan | **16,503 ms** Parallel Seq Scan | **2,473 ms** BitmapOr | 37 → 37 |
| EPL resolved backfill | **6,246 ms** Parallel Seq Scan | **375 ms** BitmapOr | 16 → 16 |

**19,901 ms off a request whose wall was 25,123 ms.** Every other league gains the same way —
Path A becomes an index scan over 12 rows, Path B.1 over the Kalshi partition instead of the table.

## 5. 🔴 Why the fast answer was NOT shipped

`source = 'kalshi' AND external_id >= 'KXMLB' AND external_id < 'KXMLC'` gets an **Index Scan on
`uq_futures_source_external`: 396 ms, 34,415 rows, 0 removed by filter** — against 8,225 ms for the
`ILIKE` form. Twenty times faster than what shipped, on the branch that shipped slowest.

It was rejected. This database's collation is **`en_US.UTF-8`**, and under a non-C collation a
`>= 'KXMLB' AND < 'KXMLC'` range is **not** the same set as the prefix `KXMLB%` — collation ordering
is not byte ordering. It returned the same 34,415 rows today; that is a coincidence of the current
data, not an equality. This is precisely why Postgres itself refuses to use a plain btree for
`LIKE 'x%'` under a non-C collation, and the correct form — a `text_pattern_ops` index — needs a
migration this lane cannot take (gotcha #31, and 5432 egress is blocked).

> **A range is only a prefix in C collation.** A 20× speedup that is right on today's rows and
> undefined on tomorrow's is not a speedup, it is a deferred incident.

Parked as **P129-3** with the measurement attached.

## 6. The narrowing is lossless, measured rather than assumed

Scoping by source is a real semantic narrowing: a Polymarket row whose `external_id` happened to
start with an Odds API sport key would no longer be claimed by Path A. So it was measured, not
argued, across the **whole table** — every prefix in every league config:

| population | rows scanned | matches |
|---|---:|---:|
| non-`odds_api` rows matching any of the **18** configured sport keys (3 chunks) | 911,215 / 911,217 / 911,217 | **0** |
| non-`kalshi` rows matching any of the **7** configured ticker prefixes | 911,205 | **0** |
| rows with `source IS NULL` | 911,217 | **0** |

Then per league, as a gate rather than a spot check —
`backend/scripts/lat_p129_verify_equivalence.py`:

```
league                    OLD-minus-NEW rows   exec_ms   verdict
bundesliga                                 0     14903   IDENTICAL
champions-league                           0     14371   IDENTICAL
epl                                        0      5410   IDENTICAL
golf                                       0     59546   IDENTICAL (chunked)
la-liga                                    0     10393   IDENTICAL
mlb                                        0      4981   IDENTICAL
mls                                        0      4471   IDENTICAL
nba                                        0     24601   IDENTICAL
ncaa-basketball                            0     24117   IDENTICAL
ncaa-football                              0      6470   IDENTICAL
ncaa-women-basketball                      0     10079   IDENTICAL
nfl                                        0      9374   IDENTICAL
nhl                                        0      7546   IDENTICAL
wnba                                       0      9340   IDENTICAL
PASS — all 14 leagues: NEW differs from OLD only by source scoping, and that scoping loses ZERO rows
```

Two halves, both required. A **structural** check strips the `source = …` conjuncts from the new
SQL and asserts what remains is byte-identical to master's expression — so the only difference is
the scoping. Then the **population** check counts `OLD AND NOT NEW` directly.

### 🔴 The first version of this proof reported eight false differences

It asked for `WHERE (OLD) IS DISTINCT FROM (NEW)`, which evaluates both predicates over all 911,217
rows and blew the 25 s ceiling on the eight biggest leagues. The script printed:

```
epl   None   None   DIFFERS -> {'error': 'query_failed', 'reason': 'statement_timeout' ...
```

**`statement_timeout` is a story about the harness, not a difference** (gotcha #54 read on a
db-query error instead of an exit code). The rewrite exploits the fact that `NEW` only ever *adds* a
conjunct, so `NEW ⇒ OLD` and the symmetric difference collapses to `OLD AND NOT NEW` — one cheap
term per prefix, chunked when a league has five of them. The harness now distinguishes
`HARNESS FAILURE` from `ROWS LOST` and exits **2** rather than **1** when it could not measure,
because "I could not tell" must never print as "identical".

## 7. The guard suite asserts the SHAPE, not just the rows

The defect selected exactly the right markets. Its only symptom was in a query plan. A test that
checked results would have passed against the bug, and a timing test would merely have got
*slower* — so the guards assert the emitted predicate's shape.

`backend/tests/test_playoff_grid_source_scoped_candidates_lat_p129.py` — **96 tests, exit 0**:

* **`test_every_external_id_predicate_is_scoped_by_source`** — load-bearing, over all 14 leagues ×
  both filters. Walks the real SQLAlchemy expression tree and fails if any `external_id ILIKE` term
  is not conjoined with a `source =`. Restore the flat `OR` and this **fails**; it does not get
  slower.
* **`test_sport_keys_scope_to_odds_api_and_tickers_scope_to_kalshi`** — 🔴 **the second door.**
  Scoping *both* id spaces to `kalshi` satisfies the guard above, keeps the plan fast, and silently
  drops every Odds API market. The pairing itself is pinned, per league, per prefix.
* **`_matches`** — a ~25-line evaluator over the actual clause object (`=`, `ILIKE`, `IN`, `AND`,
  `OR`). The behavioural tests therefore exercise the expression the route hands to SQLAlchemy
  rather than a re-implementation of it, with no database.
* **`test_foreign_source_carrying_another_id_space_is_not_matched_by_that_path`** — states the one
  behaviour the fix changes, instead of leaving it to be discovered: a Polymarket decoy with a
  sport-key `external_id` is no longer claimed by Path A, and the same row is still found through
  Path B.2 once it looks like what it is.
* **`test_status_split_is_preserved`** — ticker paths may see `resolved`, the category path may not.
  Collapsing them is a latency regression dressed as a simplification.
* **`test_bare_filter_carries_no_status_term`** — the resolved backfill ANDs its own
  `status == 'resolved'`; a status term in the bare filter would make it silently return nothing.
* **`test_league_pattern_to_ilike_is_unchanged`** — pins the regex→ILIKE conversion, including the
  broken multi-word forms (§9).

### Battery — 8/8 killed, exit 0

```
denominator: 8 mutants queued against app/routes/playoffs.py
baseline: suite on the unmutated tree -> exit 0 (GREEN)

M-FLAT             killed   restore the defect — flatten both id spaces into a bare OR
M-BOTH-KALSHI      killed   scope BOTH id spaces to kalshi — fast plan, Odds API markets vanish
M-SWAP             killed   swap the pairing — sport keys to kalshi, tickers to odds_api
M-DROP-TICKER      killed   drop the Kalshi id space entirely
M-STATUS-COLLAPSE  killed   let the category path see resolved markets too
M-BARE-STATUS      killed   leak a status term into the bare filter the backfill reuses
M-NONAME           killed   stop pushing the league name filter to SQL
M-PATTERN          killed   'repair' the regex->ILIKE conversion so \s+ becomes % (widens every grid)

8/8 killed, 0 survived, 0 harness failures
```

Each mutant asserts its anchor was found and that the edit reached disk before the suite runs — a
mutation that fails to apply reports green and proves nothing.

## 8. 🔴 A second defect found on the way, and deliberately NOT fixed

`get_playoff_grid`'s resolved backfill references `league_patterns` and `league_exclude`:

```python
for market in resolved_markets:
    if league_patterns and not any(p.search(market.name or "") for p in league_patterns):
```

**Neither name is ever bound in that function.** They are locals of
`_market_passes_league_filter`, a different function, and there is no module-level fallback. The
block is wrapped in `try: … except Exception as e: logger.warning("resolved backfill failed
(non-critical)")`, which catches the `NameError`.

So the backfill has been running its query, paying for it, and discarding the result at the first
loop iteration — for as long as the reference has been wrong. It is on master, unchanged by this
queue, and confirmed absent from master's copy of the function by `git show HEAD:` as well as the
working tree.

**It is not fixed here.** Repairing the `NameError` would make the backfill start populating empty
grid columns — a change to what the grid *shows*, on a surface with a Sentinel and a documented
contamination history. That is a content ship needing its own before/after, not a rider on a
latency one. Parked as **P129-1** with the exact lines.

What this queue *does* do is stop the dead query costing 6.2 seconds.

## 8a. Gates — every exit code read BY VALUE (#54), nothing piped

| gate | result |
|---|---|
| **backend suite, all 949 test files** | **21,601 passed / 0 failed / 124 skipped / 61 xfailed, 940.8 s, SIX chunks, EVERY chunk EXIT CODE 0** |
| collect reconciliation | 21,601 + 124 + 61 = **21,786** = branch collect exactly; master base **21,690**, **+96**, and the new file collects **exactly 96** |
| new suite | **96 passed, exit 0** |
| mutation battery | **8/8 killed, 0 survived, 0 harness failures, exit 0** |
| equivalence gate (production, 14 leagues) | **PASS, exit 0** |
| residue scan **ON A COMMIT** | **CLEAN exit 0** — 216 needles, 616 broad checks; same two pre-existing `typeahead_warmer` drifts as master |
| ruff, changed paths | `playoffs.py` branch **10** vs master **10** → **net 0**; the three new files **0** |
| frontend build (ESLint gate) | **exit 0** |
| frontend typecheck (TS gate) | **exit 0, 70 = baseline 70** |
| `merge-tree` vs `origin/master` | **exit 0**, tree `83d03f63` |
| `merge-tree` vs `-108`…`-114`, `calibration-118` | **ALL exit 0** |
| `merge-tree` vs `ux-122` | 1 — `FeedCard.tsx`, **not this branch** (`ux-122` is exit 1 against `origin/master` alone; LAT-P129 touches zero frontend files) |

### 🔴 Why the suite is six chunks and not one run

The first attempt was launched as one background run and **died at 24 % with exit 144 and no
verdict line** — zero failures up to the kill. 144 is not a pytest exit code (pytest uses 0–5), so
per gotcha #124 it is a story about the harness, not a result, and it was not reported as one. A
second, fully-detached launch produced no process and no output file at all.

The cause was visible in `ps`: **two other lanes were running full backend suites concurrently**
(`--junitxml=/tmp/uxp173/backend.xml` and one more). Under that contention a single ~16-minute run
could not survive. Six chunks of ~160 files each finish in 1–5 minutes apiece, each returns its own
readable exit code, and their totals reconcile to the collect count exactly — which a single killed
run cannot do.

**No test was skipped by the chunking**: the 949 files are the complete `tests/**/test_*.py` set,
partitioned by stride, and 21,601 + 124 + 61 = 21,786 = the branch's full collect.

### ✅ No `SHAPES` collision this cycle

The battery is `backend/scripts/lat_p129_mutation_battery.py` — not `evals/*_mutations.py` — so
`scan_mutation_residue.py`'s registry does not require an entry, and this branch stays clear of the
hunk `-108`/`-111`/`-113` share. The trade is stated rather than hidden: the battery is therefore
**not** covered by the residue scanner, so it restores from a byte-for-byte backup, asserts the
restore in a `finally`, and the tree was verified clean at the final head.

## 9. Parked

* **P129-1 — the resolved backfill raises `NameError` on every invocation.**
  `app/routes/playoffs.py`, the `if empty_cols:` block: `league_patterns` / `league_exclude` are
  unbound. Swallowed by `except Exception`, logged as "resolved backfill failed (non-critical)".
  Fixing it changes grid CONTENT. Needs its own ship and a before/after on the affected columns.
* **P129-2 — `_league_pattern_to_ilike` produces dead patterns for every multi-word rule, and it
  is not a rounding error: 33 of the 51 configured patterns.**
  `re.sub(r"\\[bs]", "", …)` strips the `\s` **before** the `\s+ → %` rule can fire, so
  `\bPremier\s+League\b` becomes the literal `Premier+League`, and the alternation strip leaves
  `\bAL\s+(?:East|West|Central)\b` as `AL+:East|West|Central`. Neither matches anything.

  | league | dead / total | league | dead / total |
  |---|---:|---|---:|
  | mlb | **7 / 8** | ncaa-women-basketball | **4 / 5** |
  | la-liga | **3 / 3** | ncaa-basketball | 3 / 5 |
  | champions-league | 2 / 3 | epl | 2 / 3 |
  | nfl | 2 / 3 | nhl | 2 / 3 |
  | golf | 2 / 5 | ncaa-football | 2 / 5 |
  | bundesliga | 1 / 2 | mls | 1 / 2 |
  | nba | 1 / 2 | wnba | 1 / 2 |

  🔴 **`la-liga` is 3 of 3** — it has no working name pattern at all, so its Polymarket path can
  match nothing, and its grid is fed by Path A alone. EPL survives on `\bEPL\b`; MLB on `\bMLB\b`.
  Repairing the conversion **widens every grid's candidate set** — a matching change with its own
  before/after, not a latency one. Pinned by a test so it cannot be "tidied" into existence by
  accident.
* **P129-3 — the Kalshi branch could be 20× faster with a `text_pattern_ops` index.**
  Measured: `source='kalshi' AND external_id >= 'KXMLB' AND external_id < 'KXMLC'` is an Index Scan
  on `uq_futures_source_external`, **396 ms / 34,415 rows / 0 removed**, vs **8,225 ms** for the
  `ILIKE` form. Correct only in C collation; this DB is `en_US.UTF-8`. Needs a migration slot and
  `CREATE INDEX CONCURRENTLY` via psql (gotcha #31), which needs Alex — 5432 egress is blocked.
* **P129-4 — the same OR-across-columns shape survives in three more functions in this file.**
  `_query_tournament_db_markets` (golf, ~line 1571), `_build_upcoming_golf_event_grid` (~2037), and
  `_get_team_progression_for_event_uncached` (~3944). Each is a different surface and needs its own
  caller grep and its own reading before it is touched. The fix is mechanical once a surface earns
  it: `_build_grid_market_filters` is already the shared shape.
* **P129-5 — `_get_team_metadata` ORs one `ILIKE '%name%'` per team over the whole `teams` table.**
  Not measured this cycle; noted because it is in the same request.
* Carried unchanged from LAT-P128: **P128-1** (the proven 21.9× bookmaker skip-scan — needs a
  POPULATION, not a patch) · **P128-2** (`GRID_WARM_LEAGUES` covers only mlb/nba/nhl/golf) ·
  **P128-3** — **this queue is P128-3's answer** · **P127-1** (BLOCKED on `-109`) · **P127-3**
  (**NEEDS ALEX**) · **P127-4** · **P127-5** · **P126-1** · **P125-A** · **P125-1** · **P125-2** ·
  **P124-1**–**P124-5** · **P110-4** (#2260) · **P122-5** (option b/c, **FIFTEENTH** consecutive
  cycle).

## 10. The sentence worth keeping

**An `OR` across two columns is a decision to read the whole table.** The planner will not tell you;
it will just stop using indexes. And the branch that costs the most is not the branch that returns
the rows — here the one contributing every result ran in 633 ms while the one contributing *nothing*
ran for 12.5 seconds and dragged the other down with it.

Its corollary, paid for in §5: **a range is only a prefix in C collation** — and a 20× win that is
accidentally correct is not a win.
