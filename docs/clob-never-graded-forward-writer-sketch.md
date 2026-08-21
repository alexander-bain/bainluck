# CLOB `never_graded` forward writer — DESIGN SKETCH (CAL-P086A)

**Status: SKETCH. Nothing here is built, scheduled, or licensed to write.**
This document exists so the next window starts from a design instead of a finding.
It is item 3 of CAL-P086A, whose directive says in as many words: *"design-only
sketch for the CLOB cohort's writer (the class with NO writer at all), consuming
the census dispositions — sketch, not build, it needs its own window."*

Source of the problem statement: `C-WINNER-WRITER-1` (codex, 2026-08-21), verdict
**BLOCK**, finding `[P1]` — *"The 142,162 eventless rows have theoretical venue
paths but no complete automatic path for the dominant PM shape."*

---

## 1. The hole, stated precisely

Every other winner-writing rail is excluded from this cohort **structurally**, not
by accident of tuning:

| rail | why it cannot own a `0x…` never-graded row |
|---|---|
| Gamma winner backfill | `GET /markets/{id}` takes a **numeric** Gamma id and answers **422** to a condition_id (measured 2026-08-07, CAL-P003). The rail correctly refuses and hands the row off — ~9,748 per run. |
| Polymarket WebSocket | its subscription query joins `Event` and requires `FuturesMarket.event_id IS NOT NULL` (`polymarket_ws.py:109-123`). These rows have no event. |
| Score / box-score resolvers | require a linked event and real scores. |
| Kalshi paths | wrong venue. |
| **CLOB resolver** | **can** grade them — `map_clob_to_outcome(..., event_linked=False)` resolves a direct Yes/No market to `resolved_direct` — but `clob_resolve_drain`'s **scheduled** invocation passes no cohort, so `_load_cohort` selects `_COHORT_DROPPED`, whose `HAVING bool_or(fo.resolution_source = ANY(:srcs))` over an **all-NULL** source set is NULL, never TRUE. |

So the mapper exists, the refusals exist, the cursor discipline exists — and the
scheduled consumer selects a predicate that excludes the population **by
construction**. CAL-P065 (#1912) made the cohort *expressible* and the handoff
*honest*; it deliberately did not authorize the writer. That was correct apply
discipline and it is also why this cannot be counted as an operating drain.

**Scale (codex's exact census):** 142,162 / 305,660 missing-winner markets
(46.51%) have no `event_id` — Polymarket 119,766, Kalshi 22,396. Note the
amplifier/root-cause split: Polymarket ALSO has 148,166 missing rows *with* an
event, so absent linkage is not the root cause. Do not build this rail expecting
it to close the whole gap.

---

## 2. What this rail is FOR — and what it is not

**It is the forward writer: it stops the bleeding.** New `0x` condition-ID rows
cross into `resolved` continuously (the producers in item 2 of this same queue),
and today not one of them has an automatic owner.

**It is NOT the backlog drain.** The ~25,264-market never-graded backlog is the
**attended apply** bound to a reviewed `ApplyPlan` (#1912, currently blocked). A
sketch that quietly grows into "and then it also drains history" is how an
attended apply becomes an unattended one. Keep the two separable, permanently:

> A forward writer earns its licence by being **bounded and continuous**. A
> backlog drain earns its licence by being **reviewed and attended**. Neither
> licence implies the other, and a rail that holds both has neither.

---

## 3. Consuming the census dispositions

The census already exists and already reports the right shape:
`clob_resolve_never_graded_census` (dry-run, writes nothing) tallies each sampled
market into `_COUNTERS`:

```
resolved_direct · resolved_name_match · resolved_ordinal · resolved_score_based
void · integrity_skipped · ambiguous_skipped · not_found
```

plus `by_vintage`, `clean_resolvable`, `clean_rate`, and a deliberately
conservative `verdict` ∈ `PASS` (≥50 fetched **and** clean_rate ≥ 0.50) /
`FAIL_LOW_YIELD` / `INSUFFICIENT_SAMPLE`.

The writer consumes those dispositions directly — **the same classifier, the same
refusals, no second opinion**:

| disposition | forward writer does |
|---|---|
| `resolved_direct` | **write** (authoritative, per-market commit) |
| `resolved_name_match` | **write** |
| `resolved_ordinal` | **refuse in v1.** Needs `enable_ordinal` + its own cumulative cap; it is the tier most likely to be confidently wrong. |
| `resolved_score_based` | **refuse** — needs event linkage this cohort lacks. |
| `void` | **leave untouched** (honest floor) |
| `integrity_skipped` | **leave untouched** — the mandatory integrity guard is not negotiable |
| `ambiguous_skipped` | **leave untouched.** This is the rail working: the no-event Yes/No-vs-Over/Under specimen is *correctly* ambiguous, and guessing it is how you get a wrong winner, which poisons calibration worse than a missing one. |
| `not_found` | count, do not cache dead without a definitive answer (gotcha #36) |

⚠️ **The existing census is vintage-stratified over the WHOLE cohort.** Its
clean_rate is therefore a claim about history, not about the forward flow. **Run
the census against the forward slice specifically before building** — a rail
sized on the wrong denominator is the thing that makes a bounded writer look
either useless or reckless.

---

## 4. The selector — and the connection to item 2

The obvious selector is `_COHORT_NEVER_GRADED` plus recency. There is a better
one available **as of this queue**, and it is the reason items 2 and 3 shipped in
the same window.

Item 2 makes every `status='resolved'` write record *why* it happened, in
`market_metadata.resolution_gate`. A row that resolved with
`reason = closed_without_terminal_price` is, by definition, a market the venue
closed and nobody could grade — **which is exactly this rail's intake**, stated by
the producer at the moment of the write rather than inferred later by a `HAVING`
over NULLs.

So the forward selector should be:

```
source = 'polymarket'
AND status = 'resolved'
AND external_id LIKE '0x%'
AND market_metadata -> 'resolution_gate' ->> 'proof_kind' = 'named_reason'
AND (market_metadata -> 'resolution_gate' ->> 'at')::timestamptz > :floor
AND <the never_graded HAVING: no winner, all sources NULL>
```

Two properties worth having on purpose:

1. **It is a positive selector, not a residue.** The existing predicate says
   "nothing graded this" — a statement about absence, which is true of rows that
   are merely *early* as well as rows that are *stuck*. The gate stamp says "a
   producer resolved this and had no winner", which is the actual intake
   condition. (Gotcha #53's shape again: the residue and the real population
   were reading the same.)
2. **It gives the rail a real age floor.** `resolution_gate.at` is the moment the
   row entered the class. Gotcha #41 in BOTH directions: oldest-first *within* a
   floor. Oldest-first alone walks the 142k backlog and never reaches today's
   rows; newest-first alone never reaches anything that slipped.

⚠️ **Migration reality:** the stamp only exists on rows resolved *after* item 2
deploys. For the transition window the rail needs the union of the stamped
selector and the legacy `never_graded` HAVING bounded by `id`/`created_at`.
Say so in the code; do not let a reader assume the stamp is total.

---

## 5. Shape of the task

```
clob_forward_grade_never_graded(limit, floor_days, dry_run=True)
```

- **Reuses** `clob_resolve_drain`'s machinery: `_fetch_and_map`, the integrity
  guard, `_tally`, per-market commit (gotchas #6/#13/#34), and — unchanged —
  `_next_cursor_decision`, which already holds errored ids and never wraps while
  errors remain. It is the pattern CAL-P086A's Gamma fix was transposed FROM;
  do not re-derive it.
- **Write tiers:** `("resolved_direct", "resolved_name_match")`. `enable_ordinal`
  stays `False`.
- **Licensing:** its own constant, distinct from `_WRITE_SOURCE_NEVER_GRADED`'s
  attended-apply licence. A beat must not be able to reach the attended rail's
  authority by passing a different argument.
- **Bound:** small `limit` (start ~300, the drain's current default) and a
  **cumulative Redis-tracked cap** for the first weeks, exactly as the ordinal
  tier was capped at 2,000 until sanity was verified.
- **Terminal:** `clob_terminal(...)` with `owned_backlog`, so a run that writes
  zero against a five-figure backlog reads **NOT-GREEN** rather than
  `health: healthy`. Non-negotiable — the absence of this is half of why the
  original hole survived. Enrol in `ENFORCED_TASKS` **with a terminal**, or the
  enrolment is a no-op that still reports green.
- **Beat:** ⚠️ a new scheduled task requires a `beat_schedule_change: true`
  declaration for serialized Integrator review, and an allowlist entry in
  `tests/test_tasks_wiring.py` (gotcha #12). **Not done in CAL-P086A.**

## 6. Verification before it is allowed to write

1. Forward-slice census returns `PASS` (≥50 fetched, clean_rate ≥ 0.50).
2. `dry_run=True` over ≥1 full forward page, dispositions read plausibly, and
   `ambiguous_skipped` + `integrity_skipped` are **non-zero** — a run that
   refuses nothing has not proved it can refuse (ruling 050).
3. A `null-movement control` on winner grades (ruling 050) — a slice the rail is
   told to grade and must leave alone.
4. Post-write re-census confirming the written rows carry
   `resolution_source = <the new licence's source>` and exactly one winner per
   exclusive market.

## 7. Open questions — for Alex / Fable, not for the implementer

1. **Does the forward writer wait on #1912's attended apply?** Codex's fix-sketch
   says *"after the attended backlog is resolved"*. The counter-argument is that
   the forward rail is what stops the backlog growing while #1912 is blocked, and
   the two touch disjoint rows if the age floor is set at the apply's ceiling.
   **Recommendation: run them disjointly, floor the forward rail above the
   apply's reviewed id set.** Needs a ruling; it is a scope decision, not a
   technical one.
2. **`resolved_ordinal` in v2?** It is the largest incremental yield and the
   largest wrong-winner risk. Should not ride in on v1's licence.
3. **Kalshi's 22,396 eventless rows.** Out of scope here — Kalshi's ticker
   carries an explicit result without an event FK, so its 11–13% gap is a
   different defect with a different owner. Do not let this rail grow a second
   venue.
4. **Retention.** Kalshi's measured 74–86 day cliff (gotcha #35) does **not**
   apply to Polymarket CLOB, so there is no cliff race forcing this early —
   confirm against the price-history work before relying on it.

---

*Sketch only. No task registered, no beat entry, no write licence, no migration.*
