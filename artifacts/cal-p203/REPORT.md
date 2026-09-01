# CAL-P203 — the live bank is in the row the conveyor does NOT read, and the row it does read is a beat-END copy

**Session:** 2026-09-01 ~12:26–12:5x PT · **Branch:** `program/calibration-190-the-rebuild-survives-a-deploy`
**Pillar:** TRUTH · **Ship this rides:** none — this is a READ session under the `985` freeze. Nothing built, nothing merged, nothing deployed, `app/` and `frontend/` untouched.
**Harness:** `artifacts/cal-p203/bank_liveness_two_rows.py` — 4 control arms across 2 axes, exit 0, runs from any cwd.

---

## 0. Freeze and protocol state (all checked, in order)

| check | result |
|---|---|
| `ls` runner inbox (open) | only `973-burndown-conveyor.md.running`. **No new Fable directive.** |
| `ls` runner inbox (close) | re-checked at session end — still nothing new. |
| input fingerprint (start **and** end) | `e2040f90154fae876f0fb65f5abf74c3` — local predictor at HEAD reproduces live. **Unchanged P185→P203, thirty-eight sessions.** |
| `origin/master` | `b5c59f38fd1847ccb503f7ea2ad7f1f4a055c5d8` — **unchanged for a FOURTH session.** Empty diff. `985` honoured by every lane. |
| `/api/calibration` `generated_at` | `2026-08-31T04:37:36Z`, `availability: stale`. 🔴 **FREEZE STILL ON.** |
| `TOP-PRODUCT-DEFECTS.md` (clause 8) | unchanged — only items 12 and 21 mention calibration; **no calibration-lane build item open.** |
| P185 discriminator | **0 rows** — quiescent. (P185–P189, P199, P202, P203 all 0.) |
| branch | 16 commits ahead, pushed. **Not merged** — `920`, `960`, `985`. |

---

## 1. The finding

### 1.1 What the conveyor instructs

ITEM 1b, of `calibration:main:phase_ledger`: **"Check `updated_at` FIRST."**
ITEM 3 step 1: **"grade … progress on `units_banked`."**

Both name the **same** durable row.

### 1.2 What `staged:units_banked` actually is

It is not measured by the ledger. It is a **copy**:

```
backend/app/tasks/calibration_main_build.py:1411
    runner.ledger.record_gauge("staged:units_banked", len(committed))
```

`committed` is read moments earlier out of a **different** durable row,
`calibration:main:staged_futures`, inside `_record_staged_convergence()` — which by
its own docstring runs *"on EVERY terminal"*, i.e. **at beat END**.

The source row is rewritten **per unit**:

```
backend/app/tasks/precompute_calibration.py:4726
    if not await save_staged_cursor(cursor, terminal=TERMINAL_PARTIAL):
```

and `calibration_staged_futures.py:1250` says so verbatim:

> "the cursor is re-serialised in FULL after every unit (per-unit `save_staged_cursor`,
> which is what caps a SIGKILL's cost at one unit)"

**So the two are never sampled at the same instant.** The ledger's copy is stale for the
entire duration of a beat — and a beat is planned against `PHASE_DEADLINE_MS` ≈ 23 min.

### 1.3 The operational cost, measured on the live row

P200, P201, P202 — and this session at 19:26Z — each read the ledger's `updated_at`,
found it unmoved at `18:24:55Z`, and could not tell whether Alex's 18:51Z attended
relaunch had happened. **CAL-P202 wrote three readings and recorded "this lane cannot
separate them."**

One query separated them. At **19:24:13Z** the staged cursor already held:

| field | value |
|---|---|
| `generation` | `1788290163654` = **2026-09-01T19:16:03.654Z** — a NEW generation |
| `owner` | `b9f90add-…:69` — a NEW owner (the ledger's was `e1c6c0b6-…:11`) |
| `committed_units` | **60** (the ledger's copy said **55**) |
| `lease_expires_at` | `19:55:13.248Z` |
| `task` | `precompute_calibration_main` — the rebuild, **not** the repair task |
| `terminal` | `partial` |

**The relaunch had happened, at 19:16:03Z, and had banked 5 units.**

### 1.4 The confirmation, observed live in-session

The ledger wrote at **19:38:34Z** — its first movement since 18:24:55Z — and published
**exactly** the generation (`19:16:03.654Z`), owner (`b9f90add-…:69`) and bank (**60**)
that the staged cursor had been showing since **19:24:13Z**.

> **The staged cursor carried the ledger's answer 14 minutes and 21 seconds before the
> ledger did.**

Bank observed flat at 60 across 12 samples spanning 19:28:11 → 19:40:09 (the futures
phase had been cancelled at its bound; the beat was finishing other phases).

### 1.5 The instrument

`lease_expires_at` is stamped **per unit** (`staged_lease()` = `time.time() + LEASE_S`,
`calibration_main_build.py:1248`), and `LEASE_S = HARD_LIMIT_MS/1000 + 300 = 1,860 s`
(31 min). Reconciled against the live row to **0.07 s**. So it is a genuine per-unit
heartbeat, and gives a conservative liveness bound:

```sql
SELECT identity, updated_at,
       payload->>'generation' AS generation, payload->>'owner' AS owner,
       payload->>'lease_expires_at' AS lease,
       jsonb_array_length(COALESCE(payload->'committed_units','[]'::jsonb)) AS bank_now,
       payload->'stages'->>'staged:units_banked' AS ledger_copy, now()
FROM durable_state_snapshots
WHERE identity IN ('calibration:main:staged_futures','calibration:main:phase_ledger')
```

* generations **differ** ⇒ a beat is in flight that the ledger has not reported yet.
* `lease_expires_at > now()` ⇒ that run **may** still be alive (conservative upper
  bound by construction — a SIGKILLed run holds its lease past the point it could be
  alive; it is **not** proof of liveness).
* `bank_now` is the live level; the ledger's is a beat-END copy.

---

## 2. Control arms — 4 across 2 axes, all PASS

| arm | axis | what it proves |
|---|---|---|
| **A1** known-hit | correctness | Observation A (19:26Z) ⇒ `DIVERGED`, live bank 60 > ledger copy 55, cursor 59.3 min ahead. **And the counterfactual: ledger-only would have been wrong** — the arm fails if ledger-only happens to be right, because then there is no defect. |
| **A2** negative control | correctness | Observation B (19:42Z, after the ledger caught up) ⇒ `CONVERGED`, both rows report 60. **The instrument must not cry wolf.** |
| **B1** distinctness | non-vacuity | A1 and A2 must yield **different** verdicts — otherwise the guard's string is common to both arms and says nothing. |
| **B2** provenance | honesty | Identities must be in the named population; every ms-epoch generation must independently reconstruct to a wall clock that **precedes its own row**; the lease must reconcile to `updated_at + LEASE_S` (drift 0.07 s). `LEASE_S` is parsed from its **definition site** and the parser **raises** if the formula changed, rather than re-deriving it (P201-3's lesson). |

**Coverage, stated in the marker's own noun.** Population = the **2 bank-bearing durable
rows**. The conveyor's standing instruction reads **1 of 2** — the beat-END copy. This
instrument reads 2 of 2.

---

## 3. What this does NOT show

* 🔴 **No wrong published number, and none is possible by this route.** The publication
  gate is `is_complete(cursor, chunks)` (`precompute_calibration.py:4753`), whose
  docstring reads *"Finalization and publication gate on this"* — it reads the
  **cursor**, not the ledger. **Verified, not assumed.** The cost is entirely to the
  **operator** reading the ledger — which is exactly what P200–P202 paid.
* **Not proof the rebuild is running right now.** The lease is an upper bound on
  liveness, not a heartbeat of health.
* **Not a reason to lift `985`.** It changes what an operator should READ, not what a
  deploy costs.

---

## 4. Two side observations on standing conveyor claims (recorded, not graded)

* **`P199-2`'s envelope takes a third out-of-envelope member.** The 19:38:34Z beat
  cancelled two units against a bound of `406,117 ms`:
  `d21fd0e13c54804a` at `406,220` (**103 ms** outside — in envelope) and
  `7d371b9a0a9841ad` at `454,376` (**48,259 ms** outside — 91× the 531 ms envelope).
  Reinforces P199-2: **not every cancellation is a fence event.** Still not an argument
  to widen the fence.
* **`staged:beats_to_publish` went 3 → 5 while the bank rose 55 → 60.** The ETA moved
  *away* from publication while progress was made — consistent with `P198-1` (the ETA
  has no term for cancelled units; this beat cancelled 2 of 7). **Continue to use
  `/api/calibration` `generated_at`'s DATE as the freeze-lift signal, per `985`.**

---

## 5. Disposition

Parked to `.claude/handoff/PARKED-MEASUREMENTS.md` as `P203-1`, `P203-2`, `P203-3`
(PROCESS-V2 clause 6 — measurement does not get its own queue). **All OPERATOR-visible;
none belongs on `TOP-PRODUCT-DEFECTS.md`.** No build proposed. Filed against #2052.
