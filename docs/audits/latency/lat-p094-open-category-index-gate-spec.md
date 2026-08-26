# LAT-P094 — PRE-REGISTERED GATE SPEC: a partial index on the open-market category

> 🔴 **STATUS 2026-08-26 (LAT-P095): RETIRED — PENDING CONFIRM. Precondition P1 fails.**
> Modelled post-`-83`, `concepts` is **791.2 ms** (P1 requires ≥ 800 ms) and **4th** by stage
> p50, not top three (P1 requires top three) — behind `events` 1,208.6, `futures.market_load`
> 1,039.3 and `futures.UNATTRIBUTED` 905.9. Both clauses fail, so **the DDL does not run**,
> which §3 already calls a pass for this spec rather than a failure of it.
>
> **The retire rests on the RANK clause, not the p50 clause.** 791.2 vs 800 is an 8.8 ms margin
> on a flat-subtraction model; the rank clause's margin is 114.7 ms. And it is a **projection**:
> `-83` is not deployed, and the ring held **zero** post-deploy `/api/feed` misses when this was
> written (9.5-hour gap; feed-miss inter-arrival p50 272.3 s, p90 10,344.5 s).
>
> **Not deleted, deliberately.** If the post-`-83` measurement lands ≥ 800 ms and back in the top
> three, P1 passes and every bar below is live again, unchanged and still frozen before any DDL.
> Working: `docs/audits/latency/lat-p095-done-bar-and-the-next-target.md` § 4.

**Cycle:** LAT-P094 · **Written:** 2026-08-26, **before any DDL exists**
**Companion:** `docs/audits/latency/lat-p094-concepts-stage-single-scan.md`
**Ship it serves:** the feed loads fast even on a cache miss.

---

## 0. What this is NOT

It is **not** a migration, and it is not a request to run one now. `migration_slot: none` for
LAT-P094 and no DDL was executed in this cycle.

It is **not** a re-grade of anything. LAT-P088's trigram bar stands and
`ix_futures_name_trgm_open` stays dropped.

It is the artefact LAT-P090's standing rule requires: *any index proposal gets a NEW
pre-registered gate, written as a spec for a future attended batch, **bar frozen before any
DDL***. The reason that rule exists is that a lane which measures after the index has already
chosen the number it wants to see. So the numbers below are frozen today, against a database that
does not have the index.

---

## 1. The evidence this rests on

Measured on production 2026-08-26 (`POST /api/admin/db-query`, `EXPLAIN (ANALYZE, BUFFERS)`):

| quantity | value |
|---|---:|
| `futures_markets` rows | 871,381 |
| … with `status = 'open'` | 50,749 |
| … open AND `event_id IS NULL` | 43,662 |
| … open AND `event_id IS NOT NULL` | 7,087 |
| open rows in the three concept categories | 315 (mma 168 · motorsports 144 · cycling 3) |
| … of those, with `event_id IS NOT NULL` | 32 |

Every existing index carrying `llm_sport_category` is partial on `event_id IS NULL`
(`ix_fm_feed_open_sports`), so a read that must include the 32 linked rows cannot use one. The
concept tier's read therefore resolves to:

```
Index Scan using ix_futures_markets_status
  Filter: llm_sport_category = 'mma'
  rows=168 · Rows Removed by Filter=50,581 · Shared Hit=27,839 · 523.9 ms
```

LAT-P094 collapsed three such scans into one (1,109.5 ms → 453.4 ms p50, measured, shipped). The
**453.4 ms that remains is one scan of 50,749 rows to emit 315**, and no query rewrite reaches it.

---

## 2. The proposed DDL — frozen

```sql
CREATE INDEX CONCURRENTLY ix_fm_open_category
    ON futures_markets (llm_sport_category)
 WHERE status = 'open';
```

Deliberately NOT partial on `event_id`, because the 32 linked rows are exactly what makes the
existing partial indexes unusable here. Deliberately category-leading and nothing else: this index
answers one question — *which open markets are in category X* — and a wider one would be a
different proposal with a different bar.

**Run via `psql`, never via Alembic** (gotcha #31 — Heroku release timeout ≈5 min, and the May 22
outage is what that rule is made of). The Alembic revision, if any, records the index as already
present. Egress to 5432 is blocked from the agent sandbox (`reference_psql_5432_egress_blocked`),
so this is an **attended** batch: Alex runs the `psql` line with `!`.

---

## 3. THE PRECONDITION GATE — this can refuse the DDL without running it

Run all three **before** the `CREATE INDEX`. Any one failing means the DDL does not run, and that
outcome is a pass for this spec, not a failure of it.

- **P1 — the stage is still the target.** Re-read `/api/admin/latency-slow-events` over the
  `/api/feed` miss cohort. `concepts` must still be ≥ 800 ms p50 and still be in the top three
  stages. If LAT-P093's `canonical_counts` fix plus this cycle's consolidation have already moved
  `concepts` below that, the index is buying a stage that no longer costs, and the honest answer
  is to spend the DDL somewhere else.
- **P2 — the scan is still the cost.** `EXPLAIN (ANALYZE, BUFFERS)` of the consolidated read must
  still show `ix_futures_markets_status` with `Rows Removed by Filter` ≥ 20,000. If the planner has
  moved (a new index, a statistics change, a shrunken open population), the premise is gone.
- **P3 — index count.** `futures_markets` carries 20 indexes today. Every one is write amplification
  on a table the pollers write continuously. If the count has grown past 22 without a documented
  reason, this proposal queues behind an index audit rather than adding the 23rd.

---

## 4. THE BARS — frozen 2026-08-26, before any DDL

Measured the same way as § 1: `Execution Time` from `EXPLAIN (ANALYZE, BUFFERS)` through
`POST /api/admin/db-query`, **six interleaved round trips**, p50 reported. The pre-DDL control is
re-measured in the same session as the post-DDL arm, never inherited from this document — buffer
warmth alone moved the pre-DDL number between 87.9 ms and 552.7 ms in this cycle's own A/B, and a
comparison against a remembered number would be measuring the cache, not the index.

**GREEN — the index stays** requires ALL of:

1. **The plan changed.** The consolidated read uses `ix_fm_open_category`, and
   `Rows Removed by Filter` on the driving node is **< 1,000** (today: 50,434).
2. **The median.** Post-DDL p50 `Execution Time` ≤ **150 ms** against a same-session pre-DDL
   control of ≥ 300 ms. That is a 3× floor, chosen against a measured 453.4 ms and deliberately
   short of the ~5 ms the plan suggests, because a bar set at the best case grades the weather.
3. **Zero diffs.** The consolidated read returns byte-identical rows before and after, compared per
   category as sorted sets — the same check § 3 of the companion document ran to accept the
   consolidation.
4. **No stage regressed.** The four other `futures_markets` readers with an `ix_fm_feed_open_*`
   plan (`futures.candidate_base_fresh`, `futures.market_load`, the timely and volume pools) keep
   their current index in `EXPLAIN`. A new index that steals a plan from a tuned one is a
   regression wearing a win's clothes.

**RED — the index is DROPPED** on any of:

- The planner ignores it (a partial-index predicate mismatch, or the category is not selective
  enough for the planner's cost model — 3 of 50,749 for cycling is very selective, 168 is not
  obviously so at this table's statistics target).
- p50 ≥ 300 ms, i.e. under a 1.5× improvement.
- Any diff in the returned rows.
- Any of the four sibling readers changes plan.

**Dropping is the expected outcome of a RED, immediately and without discussion**, exactly as
`ix_futures_name_trgm_open` was dropped. A lane does not re-grade its own bar after the result.

---

## 5. What this is worth if it goes GREEN

At the bar (≤ 150 ms against 453.4 ms) the `concepts` stage loses a further ~300 ms, on top of the
656 ms LAT-P094 already took. Against the ring's 1,447.2 ms `concepts` p50 that is the stage
substantially gone, and against a 4,502.7 ms p50 miss it is ~7 %.

Stated plainly so the value is not oversold: **this is a third-order lever.** It is worth an
attended batch only if it rides along with other DDL, or if § 3's P1 still names `concepts` as a
top-three stage after LAT-P093 and LAT-P094 both land in production.

---

## 6. Where this is parked

`.claude/handoff/PARKED-MEASUREMENTS.md`, as **LAT-P094-1**. It comes back when a named ship needs
it — not on its own account.
