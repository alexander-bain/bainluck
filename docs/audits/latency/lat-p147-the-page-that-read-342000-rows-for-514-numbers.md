# LAT-P147 — the page that read 342,059 rows to return 514 numbers

**Issue #2328 · branch `program/latency-132` · base `origin/master` `944c466e`**
**Pillar: FORMATTING (the tournament hub).**
**Ship: the US Open page stops making you wait four to thirteen seconds once a
minute — on the day the main draw starts.**

---

## How this target was chosen, and the two paths that looked bigger

The lane's ranking instrument is the slow-event ring
(`/api/admin/latency-slow-events`, every request over 5 s, 500 entries, 7-day
TTL). Read whole, it ranked like this by 24-hour impact:

| path | n(24h) | p50 | db | banked |
|---|---:|---:|---:|---|
| `/api/playoffs/{league_slug}` | 51 | 14,480 | 11,300 | — |
| `/api/events/typeahead` | 69 | 6,640 | 5,482 | LAT-P143 |
| `/api/teams/{identifier}/prop-families` | 33 | 12,078 | 284 | LAT-P145 |
| `/api/events/{event_id}/related-futures` | 42 | 8,678 | 7,205 | LAT-P144 |
| `/api/event/{key}` | 13 | 14,822 | 10,682 | LAT-P146 |
| `/api/events/search-suggestions` | 7 | 12,782 | 12,708 | — |
| **`/api/tournaments/{slug}`** | **7** | **6,551** | **6,321** | **—** |

🔴 **THE RING IS SIX DAYS WIDE AND THE CODE UNDER IT CHANGED FIVE TIMES.** Both
paths above this one that carried no banked token were already fixed, and taking
either would have been a cycle spent re-tilling:

* **`/api/playoffs/{league_slug}`** — the biggest number on the board, and
  LAT-P145 explicitly left it as "first in line". Its last slow event is
  **2026-08-29 14:36 PDT**, twenty-nine minutes after LAT-P133 merged (14:07) and
  two hours after LAT-P132 (12:43). Measured directly instead of inferred: all
  **fourteen** league grids served in **0.35-2.19 s** (`golf` 1.34 s on a 737 kB
  payload), and the hourly warm report shows eleven leagues warmed in 54.4 s with
  three building empty out of season. The path is fixed. P145's note is stale and
  this audit retires it.
* **`/api/events/search-suggestions`** — 13 events, all `q=7`, all db-dominant.
  Last one **2026-08-29 21:54**, thirteen minutes before LAT-P139 merged (22:07).
  Also fixed.

The general clause, because this will recur: **a slow-event ring is a record of
what the code USED TO DO.** Rank on it, then re-measure the top of the ranking on
today's deploy before spending a cycle on it. Two of the three biggest un-banked
paths here were already dead.

`/api/tournaments/{slug}` survived that filter: its two most recent events are
**2026-08-30 01:14 (10,997 ms)** and **01:54 (6,790 ms)**, both on the current
deploy, and the trend across six days runs the wrong way — 5.0 s → 11.0 s.

---

## What a reader was waiting for

`GET /api/tournaments/us-open` is the only registered tournament, and the main
draw starts **2026-08-30 11:00 ET** — the page's highest-traffic day of the year.

It holds a **60-second** Redis TTL (`CACHE_TTL_SECONDS`), deliberately short:
`#1767` shipped a league route that rebuilt once per 24 h and served the stale
copy for the other 23 h 55 m, and the module's own comment refuses to inherit
that shape for a page whose subject is freshness. But there is **no serve-stale
and no single-flight**, so the TTL's cost lands on whoever arrives next.

Measured on production `944c466e`, 2026-08-30, `x-timing-split` server time, four
reads spaced across two TTL expiries:

```
A  immediate            7,529.7 ms   db=7,329.8  app=199.9  q=3  maxq=6,730.5
B  after 70 s idle     12,812.7 ms   db=12,629.9 app=182.8  q=3  maxq=11,932.8
C  immediate               28.5 ms   db=0.0      app=28.5   q=0  maxq=0.0
D  after 70 s idle      4,173.0 ms   db=3,963.9  app=209.1  q=3  maxq=3,620.2
```

`db` is **95-98%** of the wall. One of the three queries is **87-93%** of the db.
Warm is **28.5 ms**. So the page is not slow — it is instantaneous, punctuated
once a minute by somebody paying for everyone.

---

## The query

`_load_prices` asks when each pinned outcome was last actually observed:

```sql
SELECT outcome_id, max(captured_at)
FROM futures_odds_snapshots
WHERE outcome_id IN (<514 register-pinned ids>) AND probability IS NOT NULL
GROUP BY outcome_id
```

`EXPLAIN (ANALYZE, BUFFERS)` on the real register population:

```
Aggregate (Sorted)                                     514 rows out   1,096 ms
  Index Only Scan ix_..._outcome_bookmaker_captured  342,059 rows in
  Shared Hit 173,444 + Read 2,310 = 175,754 blocks
```

**342,059 index tuples read to return 514 numbers**, ~1.4 GB of buffer traffic.

An aggregate cannot skip: to produce one row per group PostgreSQL must visit
every row of every group. And the buffer volume — not the CPU — is why the same
statement costs 3.6 s one minute and 11.9 s the next. Warm it is 1.1 s; under any
pressure at all it is not.

The id list is **bounded by a committed register** (514 outcomes: 118 board, 56
slate, 4 prop, 336 reach) and `idx_fos_outcome_captured (outcome_id,
captured_at)` already exists. So the same answer is 514 top-1 index probes.

---

## What changed

One statement, moved to `app/utils/latest_observation.py` and rewritten as a
correlated top-1 per outcome. Measured on production, same 514 ids, same minute,
**running the statement the branch actually ships** — compiled from the shipped
subquery against the postgresql dialect, not a hand-typed lookalike:

| | before | after |
|---|---:|---:|
| executed row query | **1,766 ms** | **118 ms** |
| plan | Aggregate over 342,059 rows | Index Only Scan, `loops=514`, 0.14 ms each |
| buffer blocks | **175,754** | **3,407** |
| result set | 514 rows | **514 rows, 0 diffs** |

The equivalence was re-run a second time in six chunks of ~90 ids, because on the
un-chunked call **the OLD form had by then started exceeding `db-query`'s 10 s
row-path timeout while the new one returned in 118 ms** — which is the defect
restating itself. Chunked, both forms complete: `514 = 514`, **byte-identical, 0
diffs**.

`_load_series` is untouched. It is a different question (a daily mean over a
30-day window), it measured **310 ms**, and it is already bounded by a cutoff and
`MAX_SERIES_ROWS`. A guard pins that it was left alone.

---

## Three things that are counter-intuitive, and all three are load-bearing

**1. `probability IS NOT NULL` is a dead predicate, and it is kept.**
`futures_odds_snapshots.probability` is `NOT NULL` in the live schema, so
PostgreSQL removes the clause during planning — it is absent from the plan of the
old form *and* the new one. It costs nothing while the column stays non-nullable
and it states the caller's actual question. Kept.

**2. `captured_at IS NOT NULL` is the whole correctness argument.**
`ORDER BY x DESC` is **NULLS FIRST** in PostgreSQL. Without this predicate an
outcome holding one NULL-`captured_at` row reports `None` where `max()` — which
skips NULLs — reports its real newest observation.

> 🔴 **The column is nullable in the deployed database and NOT NULL in the
> model.** `information_schema` says `is_nullable = YES`; `models.py` declares
> `captured_at: Mapped[datetime]` with a `server_default`. The database is the
> one that executes the query. Currently 0 rows hold a NULL (measured over the
> newest 5,000,000 ids), so this is a live hazard with an empty population, not a
> live bug — which is exactly the kind that ships.

**3. `DESC NULLS LAST` is the trap, and it is banned by a test.**
It is the spelling a later reader reaches for, because it looks like the safe one
and makes predicate 2 seem redundant. It is answer-identical and **19x slower**,
measured on the same population in the same minute:

```
DESC (NULLS FIRST) + IS NOT NULL     124 ms      3,503 buffer blocks
DESC NULLS LAST    + IS NOT NULL   2,408 ms    177,719 buffer blocks
```

It stops matching the index's own ordering, so each probe stops being a one-row
backward scan and becomes a `Sort` over the whole group — the aggregate's cost
back again, wearing a safer-looking clause. **The answer stays correct and only
the plan changes**, so nothing but a measurement or an assertion can catch it.
There is an assertion.

---

## Why the guards assert on rendered SQL, and why a real-Postgres gate would lie

Neither way this rewrite can be wrong is reachable by executing rows in this
suite, and a test that pretended otherwise would be a false green.

* **SQLite sorts the other way.** `ORDER BY x DESC` yields `[3, 1, None]` there
  (verified in-session) against PostgreSQL's NULLS FIRST. A SQLite behavioural
  test of the NULL case passes whether the predicate is present or not.
* **A real-PostgreSQL gate cannot reach it either, and this is the sharper
  half.** Both real-Postgres gates in this repo build their schema with
  `Base.metadata.create_all`. The model says `Mapped[datetime]`, so the generated
  column is `NOT NULL` — the gate would be **physically unable to hold the row
  that breaks the query**. It would refuse the input and report green.

So the artifact under test is the statement **as PostgreSQL receives it**,
compiled against the postgresql dialect — the same string that produced the
measurements above. It is compiled from the shipped subquery and never typed out
in the test file: a copy would keep proving that a string in a test file has the
right shape while the module drifted away from it.

The general clause: **before writing a gate, ask what its oracle can represent.**
"Run it against a real database" is not automatically stronger than a shape
assertion when the schema the gate builds is not the schema that is deployed.

---

## Gates

| gate | result |
|---|---|
| full backend suite | **22,828 passed / 0 failed / 124 skipped / 61 xfailed**, 1,023 s |
| collect reconciliation | 23,013 = 22,828 + 124 + 61 exactly; **22,990 without the new file**, which is what LAT-P145 and LAT-P146 each independently measured for master — so the new file's **23** is measured, not derived |
| new guards | **23**, `tests/test_latest_observation_lat_p147.py` |
| mutation battery | **15/15 killed, exit 0** (`scripts/evals/latest_observation_mutations.py`) |
| residue scan | **CLEAN on the commit** — 359 needles, 1,590 broad checks over 6 changed files |
| ruff | clean on both changed modules and the new test |
| smoke (`test_startup.py`) | 4 passed |
| frontend | **not run and not owed** — zero frontend files |

### The two findings the gates produced

**M13 survived the battery's first run, and the survivor was the finding.**
Dropping the outer `.where(FuturesOutcome.id.in_(ids))` — which turns the outer
scan into one index probe per outcome in the *entire table* — went unnoticed
because the assertion covering it was reading a statement the **test helper** had
built, complete with the test's own `WHERE`. A self-oracle. Fixed by adding a
driven assertion that renders what `load_latest_observed_at` actually handed the
session; the reconstructed one is deleted and a comment says why.

**The semantic merge gate caught five reds that textual merge could not.**
`_load_prices` is shared with the ux stack, which adds `current_yes_bid`,
`volume_24h` and `volume_updated_at` to its `SELECT` for a liquidity mark. The
row double in this file was strict, so on the three-way merged tree five tests
died on `AttributeError: '_Row' object has no attribute 'current_yes_bid'` — a
test file with no opinion about liquidity asserting ownership of a statement it
merely borrows. The double now reads an unset column as `None`. **This was found
by running the merge, not by reading it.**

---

## Merge posture — measured as a DELTA from `944c466e`, not as a list

`git merge-tree --write-tree` against every live branch, each compared against
the identical check from the base, so the answer is what THIS branch adds:

* **All six live latency branches (`-126` … `-131`): zero conflicts, zero
  pre-existing.** Nothing here touches what LAT-P141…P146 touch, including
  `scan_mutation_residue.py` — the new `SHAPES` entry sits at its alphabetical
  position between `ios_duel_percent_served_pair` and `league_context_grid_cache`,
  nowhere near the `search_word_test` neighbourhood LAT-P144 and LAT-P146 both
  append to, and nowhere near the two-line hunk six consecutive latency branches
  have collided on.
* **The ux stack (`ux-131` … `ux-135`): exactly ONE new conflict**, and it is two
  lines of imports. Every other ux conflict (`routes/playoffs.py`) is master's
  already and unchanged by this branch.

```
<<<<<<< program/ux-135-raw-category-keys
from app.utils.market_liquidity import grade_liquidity
from app.utils.tournament_advancement import build_advancement
=======
from app.utils.latest_observation import load_latest_observed_at
>>>>>>> HEAD
```

**Resolution: keep all three, alphabetically —** `latest_observation`,
`market_liquidity`, `tournament_advancement`.

**`_load_prices`'s body auto-merges**, which is not luck. The fix was placed
inside the window ux's hunks do not reach (they change the function's first query
and its signature; this changes the second query), and
`test_route_tournaments.py`'s one edited test sits at line 103, clear of every ux
hunk in that file (18 / 181 / 233 / 258).

**The semantic half was run, not assumed.** The two commits were cherry-picked
onto `program/ux-135-raw-category-keys` in a scratch worktree, the import
conflict resolved as above, and the tournament + liquidity suites run against the
merged tree: **293 passed**, with ux's own new suites individually confirmed to
have RUN rather than skipped — `test_market_liquidity_ux157` 27 passed,
`test_tournament_match` 40 passed, `test_tournament_event_link` 30 passed.

---

## Parked

* **P147-1 — `/api/tournaments/{slug}` still has no serve-stale and no
  single-flight.** A reader still pays the (now much smaller) build once a
  minute, and a burst still pays it N times over. Closing it means editing
  `get_tournament`'s cache head, which the ux stack rewrites inside a 317-line
  hunk — the one region of this file where a conflict would be expensive rather
  than trivial. Deliberately not taken. **First in line once the ux stack
  merges** — and unlike P145's version of that sentence, this one comes with the
  instruction to re-measure first. → `PARKED-MEASUREMENTS.md`
* **P147-2 — `routes/golf.py:3525` holds the same `max(captured_at)` shape** and
  is the obvious second caller for `latest_observation`. Not widened into this
  ship; its population is not the same shape and its cost is unmeasured.
  → `PARKED-MEASUREMENTS.md`
* **P147-3 — the model and the deployed schema disagree about
  `futures_odds_snapshots.captured_at`** (`Mapped[datetime]` vs
  `is_nullable = YES`). A `NOT NULL` migration would make predicate 2 dead like
  predicate 1 and let a real-Postgres gate represent the column honestly. It is
  DDL on a very large table — an Alex action, not a lane action.
  → `MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`
* **P147-4 — `scripts/evals/_mutation_guard.py` recovers ACROSS WORKTREES.**
  `MANIFEST_DIR` is a hardcoded `/tmp` path and `recover()` walks every manifest
  it finds, so this lane's battery tried to restore the ux lane's files **while
  the ux lane's battery was mid-run**. Only a filesystem permission error stopped
  it; between two same-permission worktrees it would have silently corrupted
  another lane's run and voided its verdicts. Filed, not fixed here — it is
  shared infrastructure every live branch touches. → issue + `PARKED-MEASUREMENTS.md`
* **P147-5 — the three out-of-season leagues (`la-liga`, `champions-league`,
  `ncaa-women-basketball`) build empty, so the warm publishes nothing and every
  reader rebuilds live.** Cheap today (0.5-2.2 s measured) and correct by design
  (`_grid_payload_usable` must not let an empty build overwrite a good grid), but
  it means those three slugs have no cache at all. Report only.
