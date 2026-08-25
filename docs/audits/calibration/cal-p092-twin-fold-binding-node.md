# CAL-P092 addendum — the published-twin fold's binding node, and the index that unblocks Gate 5

**Ordered by Alex, mid-P092, 2026-08-24.** Not part of the WHICHPRICE evidence round; a separate
deliverable that the same window produced because the same window had the transport.

> *"CAL-P086B's 'Celery's ceiling, not the query's' premise is refuted by execution, and chunking is
> already closed, so the route is QUERY COST. … run the plan-only EXPLAIN of the headline fold via the
> db-query rail … identify the binding node … and produce the `CREATE INDEX CONCURRENTLY` DDL as a
> copy-paste attended psql block for Alex (never in Alembic, gotcha #31), with a projected cost delta
> from the plan. The apply's Gate 5 now runs through this index."*

---

## §0 — What run.2917 settled, and what it therefore costs to keep believing

`run.2917` was the attended `--bank` at the 5,400 s one-off dyno ceiling. Its durable artifact:

| field | value |
|---|---|
| `fold_duration_s` | `5402.0` |
| exception | `QueryCanceledError` |
| `db_rows` | `0` |

**CAL-P086B's premise is refuted by execution, not by argument.** That premise was that the fold's wall
was Celery's `soft_time_limit` — an *enclosure* problem, fixable by moving the fold somewhere with a
longer leash. It was given the longest leash available (5,400 s, attended, no Celery) and it hit that
one too. The wall is not the container. **The wall is the query.**

Two other routes were already closed before this one opened, which is what makes this the remaining
one rather than merely the newest:

- **chunking** — CAL-P086B closed options 1/2/3 under #2076;
- **`soft_time_limit`** — closed by run.2917 above.

One thing this addendum is careful *not* to do: treat "the fold has never completed" as evidence about
the data. It is evidence about the query. `db_rows 0` here is a cancellation, not a census — gotcha #53,
which is the reason the twin's failure path writes a failure rather than an empty payload (CAL-P087's
`-87` legs, confirmed working by this same artifact).

---

## §1 — Method: why plan-only, and what that buys and costs

The read rail's `{"explain": true}` composes `EXPLAIN (FORMAT JSON)` **without** `ANALYZE`. It does not
execute. That is the only reason this investigation is possible at all: **a query that has never once
run to completion cannot be profiled, only planned.** `EXPLAIN ANALYZE` on this fold would need >5,400 s
and the rail's ceiling is 25 s.

It also costs something, and the cost is stated up front rather than in a footnote:

- **Planner cost is not runtime.** CAL-P085 measured *this fold's* cost model understating its real time
  by `>= 2.35x`. Nothing below converts a cost into a second, and no reader should.
- **A cost RATIO between two plans of the same query is the usable signal.** Both plans are wrong in
  the same direction by roughly the same factor; the quotient survives what the operands do not.
- **No `hypopg`.** The installed extensions are `pg_stat_statements`, `pg_trgm`, `plpgsql`. Hypothetical
  indexes are unavailable, so the projection is derived from **rewritten query variants**, not from a
  simulated index. §3 states exactly where that substitution is faithful and where it is not.

Transport: `backend/scripts/explain_twin_fold_liquidity_index.py` (committed, this round). It builds the
frozen fold via `published_population_fold_sql()`, strips comments, asserts single-statement, and
**asserts the site census before rewriting anything** — 6 full-predicate sites + 1 wide-spread site = 7.
A proxy that silently rewrites fewer sites than the baseline contains would understate the delta and
would look conservative while being wrong, so that count is a hard failure, not a warning.

Artifact: `artifacts/cal-p092/twin-fold-binding-node.json` (13,814 bytes).
All four plans returned `truncated: false`; EXPLAIN round trips 92–199 ms.

---

## §2 — The binding node

Root `Total Cost` **10,341,997.2**, `Plan Rows` 277.

Top self-costs (total cost minus children's total cost):

| self cost | share of root | node |
|---:|---:|---|
| **7,693,583.2** | **74.4%** | **`WindowAgg` [CTE `ranked_outcomes`]** |
| 568,198.1 | 5.5% | `Sort` (d18) |
| 494,040.7 | 4.8% | `Sort` (d3) |
| 164,490.0 | 1.6% | `Seq Scan` [`futures_outcomes`] |
| 157,118.0 | 1.5% | `Seq Scan` [`futures_outcomes`] |

**The binding node is `WindowAgg[ranked_outcomes]` at 74.4% of the plan.** It is not binding because
window functions are expensive. It is binding because **seven correlated `SubPlan`s hang off it**, and
every one of them is the same shape:

```
SubPlan 3 / 6 / 7 / 8 / 10 / 11   Index Scan  ix_futures_odds_snapshots_outcome_id
    Index Cond: (outcome_id = fo_N.id)
    Filter:     ((yes_bid > '0'::numeric) OR (last_price > '0'::numeric))
    Total Cost: 1087.70   Plan Rows: 795

SubPlan 9                          Index Scan  ix_futures_odds_snapshots_outcome_id
    Index Cond: (outcome_id = fo_2.id)
    Filter:     (last_price > '0'::numeric)
    Total Cost: 1087.21   Plan Rows: 491
```

**`Filter:` on an `Index Scan` is the whole finding.** The index answers `outcome_id = ?` and then
Postgres fetches **every** matching heap tuple to evaluate the liquidity predicate, because
`ix_futures_odds_snapshots_outcome_id` carries only `outcome_id`. `outcome_id`'s `n_distinct` is
**190,271** against ~190M rows — **~999 snapshots per outcome** (the planner's own `rows=999` in §3
confirms it). So each of the seven sites is a ~999-tuple heap sweep, per outcome, to answer a yes/no
question.

**Alex's prime suspect is confirmed exactly**, and named precisely: it is the correlated
`EXISTS` over `futures_odds_snapshots` — `kalshi_liquidity_exists_sql`, `precompute_calibration.py:436`,
inlined at 7 sites by the population CTE builder.

**The second suspect is NOT binding.** The "resolved-path index gap" the perf-r2 cert named shows as
`Seq Scan[CTE market_info]` self 131,644.8 (filter `status='resolved' AND NOT COALESCE(...)`) plus four
`Seq Scan[futures_outcomes]` at 157,118.0–164,490.0. Together ~6% of the plan. **Fixing it would not
move this query**, and it is recorded here so nobody spends a window on it expecting the fold to
complete afterwards.

---

## §3 — The projection, and the substitution it rests on

Four plans, same fold, same rail, same session:

| variant | what it is | `Total Cost` | vs baseline |
|---|---|---:|---:|
| `baseline` | the frozen fold, verbatim | **10,341,997.2** | 1.0000x |
| `proxy_a` | all 7 sites: predicate removed from the `EXISTS` body | **3,813,783.3** | **0.3688x** |
| `proxy_b` | 6 sites rewritten, site 7 left verbatim | **6,157,538.4** | **0.5954x** |
| `floor` | all 7 `EXISTS` replaced by `TRUE` | 2,519,808.8 | 0.2436x |

Root `Plan Rows` is **277 in all four**. That matters more than it looks: the subplans sit in the
`ranked_outcomes` target list, not in a `WHERE`, so rewriting them **changes per-loop cost without
changing any row estimate**. The comparison is therefore like-for-like rather than a different query
that happens to be cheaper.

**Why `proxy_a` is a faithful stand-in for the partial index.** With the predicate moved into an index
*predicate*, the planner sees a scan on `outcome_id` with **no residual `Filter`** — which is exactly
what the rewritten body produces. The plans confirm the shape change, and it is a better one than
predicted:

```
baseline   Index Scan       cost 1087.70   rows 795   Filter: ((yes_bid > 0) OR (last_price > 0))
proxy      Index Only Scan  cost  147.24   rows 999   Filter: none
```

**`Index Only Scan`** — the heap is not touched at all. **7.39x cheaper per loop**, and the binding
node collapses `7,693,583.2 → 1,200,467.6` (**−84.4%**).

**Where the substitution is not faithful, stated rather than buried:**

1. `proxy_a` scans the *existing* full index (190M entries, `rows=999`). The real partial index holds
   only the liquid subset (~75%, `rows≈750`) and is smaller, so it should be **slightly cheaper** than
   the proxy. The proxy is conservative here.
2. `Index Only Scan` costing assumes a well-set visibility map. `futures_odds_snapshots` is
   append-mostly, so this is likely, but it is an assumption and not a measurement.
3. `floor` removes the subplans entirely. It is **not achievable and not proposed**; it exists only to
   bound how much of the plan is attributable to the predicate at all — `7,822,188.4` of `10,341,997.2`.

**Projected delta, therefore:**

- **Candidate A: `0.3688x` baseline — a 63.12% cost reduction, capturing 83.5% of the recoverable.**
- **Candidate B: `0.5954x` baseline — a 40.46% cost reduction, capturing 53.5% of the recoverable.**
  And `proxy_b` is **pessimistic for B**, because it leaves site 7 scanning the full 190M-entry index
  rather than B's ~140M-entry partial one. B's true figure sits between 40.5% and 63.1% and **cannot be
  pinned without `hypopg`**. It is reported as the measured lower bound, not interpolated.

**What this does not say.** It does not say the fold will finish. It says the plan's dominant node
drops by 84%, on a cost model this fold is known to under-report by `>= 2.35x`. If the real wall is
~2x the ceiling rather than ~10x, A clears it; if it is ~10x, A alone does not. **The only test is
running it.** Gate 5's re-run after the index IS that test, and it should be read as a measurement, not
a confirmation.

---

## §4 — The two candidates, and why the choice is a disk decision

`futures_odds_snapshots`: **~189,998,928 rows, 39 GB total, 19 GB of it indexes.** Database **53 GB**.

Liquid fraction, `TABLESAMPLE SYSTEM (0.05)`: 72,053 / 95,469 = **75.5%** (a second independent sample
read 72.8%). Call it **~140M index entries** either way.

Sizing is calibrated against this table's *own* indexes rather than a formula, because btree
deduplication dominates and a formula cannot see it:

| existing index | bytes / heap row | why |
|---|---:|---|
| `idx_fos_outcome_captured (outcome_id, captured_at)` | **44.15** | `captured_at` is ~unique per outcome — dedup fully defeated |
| `futures_odds_snapshots_pkey (id)` | 27.03 | unique by construction |
| `ix_futures_odds_snapshots_outcome_id (outcome_id)` | **13.87** | ~999 dupes per key — dedup at its best |
| `ix_fos_outcome_bookmaker (outcome_id, bookmaker)` | 11.88 | `bookmaker` `n_distinct` = **11** |

And the statistics that place the candidates on that scale (`pg_stats`):

| column | `n_distinct` | `null_frac` | `avg_width` |
|---|---:|---:|---:|
| `outcome_id` | 190,271 | 0.000 | 4 |
| `last_price` | **540** | 0.447 | 4 |
| `yes_bid` | 382 | 0.316 | 4 |

### Candidate A — recommended

```sql
CREATE INDEX CONCURRENTLY ix_fos_outcome_liquid_evidence
    ON futures_odds_snapshots (outcome_id, last_price)
    WHERE yes_bid > 0 OR last_price > 0;
```

Serves all six OR-sites with a pure index condition and no residual, **and** serves the seventh
(the weather wide-spread guard, `last_price > 0`) fully in-index because `last_price` is a key column.

**Projected: 0.3688x — 63.12% cost reduction. Est. size ~2.1–3.0 GB.** `last_price` has `n_distinct`
540 and `avg_width` 4, so `(outcome_id, last_price)` deduplicates well — closer to the `bookmaker`
analogue (11.88 B/row) than the `captured_at` one (44.15). **Upper bound if dedup is fully defeated:
~6.1 GB** (140M × 44.15). Budget for the upper bound; expect the lower.

### Candidate B — the smaller fallback

```sql
CREATE INDEX CONCURRENTLY ix_fos_outcome_liquid_evidence
    ON futures_odds_snapshots (outcome_id)
    WHERE yes_bid > 0 OR last_price > 0;
```

**Measured floor: 0.5954x — a 40.46% cost reduction (true value higher, see §3). Est. size ~1.9 GB**
(140M × 13.87). Site 7 keeps a heap recheck, but over the liquid subset only.

### Candidate C — considered and rejected

`... (outcome_id) INCLUDE (last_price) WHERE ...` looks like A's benefit at B's size. It is not:
**btree deduplication is disabled for indexes with non-key columns**, so C costs roughly what A costs
while giving up A's ability to use `last_price` as a leading-edge key. Not proposed.

### The implication A depends on, and what happens if it fails

Site 7's restriction is `last_price > 0`; A's index predicate is `yes_bid > 0 OR last_price > 0`.
Postgres proves a query restriction implies an OR-predicate when it implies **at least one disjunct** —
here `last_price > 0` implies itself, an identical clause, which `operator_predicate_proof` resolves.

**This is a documented planner property, not something this round measured**, and it cannot be measured
without building the index. **If the planner declines the implication, site 7 simply falls back to the
existing full-index path — which is precisely `proxy_b`'s measured 0.5954x.** So A's downside is B's
number, not a regression. That is a good property and it is why A is recommended despite resting on an
unverified implication.

NULL semantics align in both directions: `yes_bid > 0` on NULL is NULL, `NULL OR NULL` is NULL, so
all-NULL rows are excluded from the index and excluded by the query identically.

---

## §5 — The attended block for Alex

**Never in Alembic (gotcha #31).** `CREATE INDEX CONCURRENTLY` on 190M rows takes far longer than
Heroku's ~5-minute release-phase timeout; putting it in the migration chain hangs the release and takes
the site down, which is exactly the May 22 `odds_snapshots` outage. This must be run attended, by a
human, from a psql session.

This window cannot run it: TCP 5432 egress is blocked from the sandbox, and `heroku pg:*` is
unavailable here. **Copy-paste, run in a terminal you can watch.**

```bash
# ── PRE-FLIGHT (do not skip; each line is a distinct failure this can hit) ─────

# 1. Disk headroom. The DB is 53 GB and Candidate A adds up to ~6 GB in the worst
#    case, plus transient build space. Confirm the plan's limit BEFORE starting.
heroku pg:info -a bainluck

# 2. Nothing long-running may be in flight. CREATE INDEX CONCURRENTLY waits for
#    every transaction older than itself to finish — a fold attempt, a backfill,
#    or an idle-in-transaction session will make it hang indefinitely while
#    LOOKING like it is building.
heroku pg:ps -a bainluck

# 3. No fold, no --bank run, no precompute during the build. Coordinate first.

# ── BUILD ─────────────────────────────────────────────────────────────────────
heroku pg:psql -a bainluck
```

```sql
-- CIC cannot run inside a transaction block. Do not wrap this in BEGIN/COMMIT.
SET statement_timeout = 0;
SET lock_timeout = '5s';
SET idle_in_transaction_session_timeout = 0;

\timing on

-- Candidate A (recommended). Expect 45–120 min on ~190M rows.
CREATE INDEX CONCURRENTLY ix_fos_outcome_liquid_evidence
    ON futures_odds_snapshots (outcome_id, last_price)
    WHERE yes_bid > 0 OR last_price > 0;

ANALYZE futures_odds_snapshots;
```

```sql
-- ── VERIFY (a CIC that fails leaves an INVALID index that costs disk and is
--    never used — and nothing tells you unless you ask) ──────────────────────
SELECT c.relname,
       i.indisvalid,
       i.indisready,
       pg_size_pretty(pg_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
WHERE c.relname = 'ix_fos_outcome_liquid_evidence';
-- REQUIRED: indisvalid = t AND indisready = t.
-- If indisvalid = f the build failed. Do NOT retry over it:
--     DROP INDEX CONCURRENTLY ix_fos_outcome_liquid_evidence;
-- then fix the cause (almost always a blocking long transaction) and rebuild.
```

**Rollback** is one line, non-blocking, and safe at any time:

```sql
DROP INDEX CONCURRENTLY ix_fos_outcome_liquid_evidence;
```

**Post-build confirmation, which this window CAN run** (plan-only, no execution):

```bash
source ~/.claude/.env
python3 backend/scripts/explain_twin_fold_liquidity_index.py --out /tmp/after.json
```

The `baseline` variant is the real fold. If the index is live and chosen, **baseline's own cost should
fall to approximately `proxy_a`'s 3.81M and its subplans should show `Index Only Scan` / `Filter: none`
on `ix_fos_outcome_liquid_evidence`.** Baseline staying at 10.34M means the planner did not adopt it —
check `indisvalid` first, then whether `ANALYZE` ran.

---

## §6 — What this changes for the apply

**Gate 5 now runs through this index.** The gate is a completed fold; the fold has never completed; the
binding node is named and the intervention is costed. The order is:

1. Alex runs §5 attended → `indisvalid = t`.
2. Re-run the plan-only script → confirm baseline adopts the index (§5's confirmation).
3. Re-run the fold → **this is the measurement, not the confirmation.** §3 is explicit that a 63% plan
   reduction on a cost model known to under-report by `>= 2.35x` does not guarantee clearing a wall
   whose true multiple is unmeasured.
4. If it still walls: the recoverable ceiling is `floor` at 0.2436x, i.e. removing the predicate
   *entirely* only reaches 2.52M. **Beyond that, no index fixes this fold and the shape has to change.**
   That is worth knowing before the next window spends itself on a second index.

## §7 — What this round does NOT claim

- Not that the fold will complete. §3 and §6 both say so.
- Not a runtime figure. Every number here is a planner cost.
- Not that Candidate A's OR-implication is proven — §4 states it is a documented property, unverified
  on this database, with B's measured number as the failure mode.
- Not that the perf-r2 cert's resolved-path index gap is a non-issue in general — only that it is ~6%
  of *this* plan and will not unblock *this* fold.
- Nothing about the WHICHPRICE evidence round. That is
  `docs/audits/calibration/cal-p092-whichprice-evidence-round.md`, and the fold module remains
  byte-identical to `e03076ae`. **This addendum proposes an index; it changes no SQL.**
