# CAL-P202 — the group-key hazard is 1 of 4, not 1 of 1

**Session:** 2026-09-01, ~12:1x–12:4x PT. Read-only. No writes to `app/` or `frontend/`.
**Harness:** `artifacts/cal-p202/group_key_digest_coverage.py` — exit 0, four control arms across
two axes, runs from any cwd (proved from `/tmp`). Output: `harness-output.txt`.

---

## 0. Session state (measured, in order)

| check | result |
|---|---|
| inbox `ls` (open) | `972-burndown-conveyor.md.running` only. No new Fable directive. |
| input fingerprint | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 37th session** |
| `origin/master` | `b5c59f38` — **unchanged, THIRD quiet session.** Empty diff. `985` honoured. |
| branch | `program/calibration-190-…` @ `a1eb6313`, **15 commits** ahead |
| `/api/calibration` `generated_at` | **`2026-08-31T04:37:36Z`** ⇒ 🔴 **`985` FREEZE STILL ON** |
| phase ledger `updated_at` | `2026-09-01T18:24:55.805978Z` — unmoved; `units_banked` 55, `terminal` cancelled, `published` false |
| P185 discriminator | **0 rows** — quiescent |
| `TOP-PRODUCT-DEFECTS.md` | items 12 + 21 only; **no calibration-lane build item open** |

**Nothing to grade, nothing to build.** Standing job fell through to ITEM 3 §5.

⚠️ **One observation for the next session, not a verdict.** Alex's relaunch was stated for
11:51am PT = **18:51Z**. At **19:20Z** — 29 minutes later, i.e. **past one full
`PHASE_DEADLINE_MS` window (1,380,000 ms ≈ 23 min)** — the ledger had still not moved. `971`/`972`
correctly warn against reading an unmoved ledger *minutes* after a relaunch as a failure; this is
now past a whole window. It is still not a verdict: I cannot distinguish "relaunch slipped" from
"beat running long" from "write pending". **Re-read `updated_at` first thing.**

---

## 1. The question

ITEM 6 has carried this for twelve consecutive sessions:

> `category` IS a `GROUP_KEY_COLUMNS` member (`calibration_staged_futures.py:208-214`) …
> **All three guards are blind to it.**

and, separately:

> **No sweep in this run has ever had the digest's columns as its population.**

**Q11** (CAL-P201's question) asks: *what node type / population does the instrument enumerate, and
does it match the NOUN in the marker it set?* The marker's noun is **a group-key column**. Its
recorded population is **one** column. Nobody has ever enumerated `GROUP_KEY_COLUMNS` against what
the digest can actually observe.

---

## 2. Result — 1 of 5 observed, 4 blind, marker covers 25%

The Stage A roster read (`precompute_calibration.py:2696`, `_staged_roster…`) selects **exactly**:

```sql
SELECT market_id, source, vm_id, is_grouped FROM virtual_market ORDER BY market_id
```

and both digest builders — `generation_fingerprint` (Stage A, global) and the plan-time member
builder inside `plan_units` (Stage B, per unit) — hash **exactly those four fields**. Extracted by
AST, not asserted:

```
generation_fingerprint  ['is_grouped', 'market_id', 'source', 'vm_id']
plan_units              ['is_grouped', 'market_id', 'source', 'vm_id']
```

Against the population:

| group key | digest | derivation |
|---|---|---|
| `bucket_idx` | 🔴 **BLIND** | `LEAST(FLOOR(adj_opening_probability*10)::int,9)` ← `raw_cp = COALESCE(fo.calibration_probability, fo.opening_probability)` |
| `source` | 🟢 OBSERVED | — |
| `category` | 🔴 **BLIND** | `COALESCE(fm.llm_sport_category,'uncategorized')` |
| `price_moved` | 🔴 **BLIND** | `cp IS NOT NULL AND cp IS DISTINCT FROM opening_probability` |
| `is_nonexclusive_bundle` | 🔴 **BLIND** | `(nbm.market_id IS NOT NULL)` ← `market_result_shape.win_count ≥ 2` ← `fo.is_winner` |

> **observed 1/5 · BLIND 4/5**
> **the recorded hazard names 1 of the 4 blind columns = 25.0% of its own named population**
> **UNRECORDED: `bucket_idx`, `price_moved`, `is_nonexclusive_bundle`**

This is the same shape as `P201-1`: the marker is not *wrong*, it is **narrow by a factor of four**,
and the three it omits were never enumerated because nothing ever walked the population its own noun
names.

**Why the omission was structural, not careless.** Eligibility is `fm.status = 'resolved'` (plus the
datagolf-residual exclusion) — and `category` is *selected* by `market_info` but does not gate. So
the roster is a set of MARKETS, and the digest is a digest of **roster membership**. Every group key
except `source` is computed *downstream*, per unit, from outcome/market columns the digest never
observed. A change to any of them is invisible **by construction**, not by oversight.

---

## 3. Are the three unrecorded ones LIVE? Graded one by one — two yes, one unproven

A writer count is not a defect count. The harness reports **call sites** (21 `SET
calibration_probability`, 11 `SET opening_probability`, 56 `SET is_winner`, 3 `SET
llm_sport_category`); the grading below is a hand read. A blind column only matters if a writer can
land on a row **already in the roster** (`status='resolved'`) **and actually change the key**.

### 🔴 `price_moved` — **LIVE, and the sharpest instance in this report**

`backfill_winners.py:8055` (the "stuck closing line" repair):

```sql
WHERE fm.status = 'resolved' … AND fo.calibration_probability = fo.opening_probability   -- price_moved is FALSE
UPDATE futures_outcomes fo SET calibration_probability = ls.probability                  -- price_moved becomes TRUE
```

**The writer's own `WHERE` clause selects precisely the rows whose group key it is about to flip.**
It is scoped to `status='resolved'` — i.e. exclusively to rows in the eligible roster — batched
`LIMIT 2000`, on the 6-hourly `backfill_winners`. `:8104` is the same class, cursor-paged.

**Live size, bounded:** the `cp = opening` predicate **saturates a 20,000-row bound in 586 ms**.
⚠️ **That is a floor, not a total** — the unbounded count times out at 10 s. It says the cohort this
repair rewrites is at least five figures, nothing more.

### 🔴 `bucket_idx` — **LIVE**

Same two writers. `raw_cp = COALESCE(cp, opening)`, so rewriting `cp` from `= opening` to the
closing line moves the value, and a moved value can cross a `FLOOR(p*10)` boundary. Also
`backfill_winners.py:2587` (the sign-flip repair) sets `cp = 1.0 - cp` on resolved markets — a
0.2→0.8 move, i.e. bucket 2 → bucket 7.

**This is the one that concerns me most and I am deliberately not over-claiming it.** `bucket_idx`
is the calibration curve's **x-axis**. The `UnitChunk.key` docstring's standing defence of the
demotion-to-measurement design is that staleness is *"late inclusion, not a wrong number"* — which
is exactly right for roster membership. It is **not obviously the same claim for a price rewrite**:
a banked unit contributes its outcome's mass to the bucket that outcome had **when its unit ran**,
and units bank across many beats. I have **not** measured how many rows that is, or whether any
published bucket moved. **Do not repeat this as "the curve is wrong."** It is an open question, and
it is a measurement-lane question.

### ⚠️ `is_nonexclusive_bundle` — **UNPROVEN**

56 `SET is_winner` sites, most keyed `WHERE fo.id = :oid` with no status filter, so a second winner
graded on an already-resolved ≥3-outcome market would flip the key false→true. The *cohort* is
large — a bounded count of kalshi resolved markets already in the bundle state **saturates 5,000 in
2.3 s** — but **a large resting cohort is not a transition rate.** I have not shown one market that
crossed while banked. **Graded UNPROVEN, not LIVE.**

---

## 4. Control arms — four, two axes (all held)

| arm | axis | assertion | why it exists |
|---|---|---|---|
| **A1 positive** | detector sensitivity | `source` must read OBSERVED | a detector that calls everything BLIND would "find" 5/5 |
| **A2 known hit** | detector sensitivity | `category` must read BLIND | **reproduces the recorded hazard** — rule (i); without it a zero would have been unbelievable |
| **B1 distinctness** | population honesty | `is_grouped` ∈ digest set, ∉ `GROUP_KEY_COLUMNS` | proves the extractor read the **digest**, not an echo of the population |
| **B2 provenance** | population honesty | imported tuple == the source literal | proves the population cannot go stale against the module |

The extractor **raises** rather than reporting a number when it meets a `_get(row, …)` key it cannot
resolve (gotcha: *a source-scan guard must RAISE on what it cannot parse*), and `check_derivations()`
aborts if any recorded SQL anchor has moved.

---

## 5. Honest scope limits

* **No fix.** ITEM 6 forbids it, and it is correct to: adding `category` (or a price, or a winner
  count) to the digest invalidates carried reads on every enrichment tick. **A fold's call under
  ruling 134.** This report widens the recorded hazard; it does not propose to close it.
* **Nothing here is a demonstrated wrong published number.** Two columns have demonstrated live
  writers; neither has a measured effect on a served bucket. `is_nonexclusive_bundle` is unproven.
* **Both live counts are saturated bounds** (≥20,000; ≥5,000), not totals. Stated as floors.
* **The finding is methodological first.** Same as `P201-1`: an instrument answered a narrower
  question than its marker's noun, and twelve sessions inherited the narrow version.
* **`P201-1`'s warning applies to me too.** My denominator is *"group keys the digest cannot
  observe"* = **4**, not 5 — grading the marker against all five would have inflated the gap to
  20%/80% by counting `source`, which is correctly covered. Stated so it can be checked.

---

## 6. What this does NOT touch

Every earlier park in this run (`P196-1/2/3`, `P197-1`, `P198-1/2/3`, `P199-1/2/3`, `P200-1/2`,
`P201-1/2/3`) sits outside the four hashed functions, so its price is zero rebuild cost. **This one
is different in kind and should not be filed the same way:** it is *about* the digest's columns, so
it is the first result in this run that lands **on** the hazard rather than beside it. It still does
not change any digest, hash any new column, or touch `precompute_calibration.py`. **The hazard
remains unguarded — it is now recorded at its true width.**
