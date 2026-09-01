# CAL-P194 — the fingerprint's blind spot is the FIX BUDGET, and a fifth falsy zero

**Session:** 2026-09-01, ~17:12–17:5xZ / ~10:12–10:5x am PT. Read-only. No code committed.
**Directive:** `964-burndown-conveyor.md` (self-staged by CAL-P193 under ITEM 4 of `963`).
**Freeze:** `960` (D-G) in force. Ruling 009 freezes `precompute_calibration.py`. Nothing deployed,
nothing merged, no fold started.

---

## 0. ONE PARAGRAPH

No build directive arrived — **five sessions running**. State is static: same beat, same
fingerprint, same published curve. Two results, and the **second is the one that matters**.
🆕 **P194-1** is the *fifth* falsy-zero in the family: `_record_staged_rate` tests the SAME variable
(`completed_mean`) with `is None` at `calibration_main_build:1572` and with **truthiness** at `:1613`
and `:1615`, so a beat whose only completed unit costs 0 ms publishes
`staged:unit_ms_mean_completed = 0` ("a unit completed") **and** `staged:beats_basis:mixed`
("nothing completed") on the same beat — while silently reinstating the mixed mean that the CAL-P068
comment eight lines above exists to eliminate. 🔴 **P194-2 corrects an inherited claim that four
directives have carried: deleting the stale comment at `precompute_calibration:4370` does NOT move
the input fingerprint.** It is a MODULE-LEVEL comment 23 lines outside the nearest hashed function;
`_main_input_fingerprint` hashes the source of exactly **four functions**, and the line is provably
absent from the 163,885-char concatenation. 🟢 **The generalization is the payload: the entire
falsy-zero family — P192-1, P193-1, P194-1 — lives in files the fingerprint cannot see, so fixing
all three costs NO rebuild reset.** The fold has been priced as if it cost 26 hours. It does not.

---

## 1. STATE, MEASURED

| thing | value | vs P193 |
|---|---|---|
| fingerprint (live + local predictor) | `e2040f90154fae876f0fb65f5abf74c3` | unchanged — **29th session**, no fifth reset |
| `origin/master` | `9eb9e0866d4e398b457b02043e67f1633b7e41aa` | unchanged |
| `git diff --name-only 7d066c50 origin/master \| grep -i calib` | empty, exit 1 | **ALL-CLEAR** |
| ledger `updated_at` | `2026-09-01 16:32:11.447482+00:00` | **unchanged — same beat as P190–P194** |
| `staged:units_banked` | 45 / 128 | unchanged |
| `staged:units_this_beat` / `units_completed_this_beat` / `units_cancelled` | 7 / 5 / 2 | unchanged |
| `staged:beats_to_publish` / `beats_basis:completed` | 4 / 1 | unchanged |
| `staged:served_units` | 0 | unchanged |
| published curve | `generated_at 2026-08-31T04:37:36Z` | unchanged, 29th session |

**ETA `09-02T08:30–09:30Z`, not re-derived.** ITEM 3 steps 2, 3 and 4 are all gated on a publish or a
freeze-lift; neither happened, so none were run. Inbox at session start held `964…running` (this
directive, 22 `P193` hits — no collision) and **no `965`**.

🟢 **P194 also CONFIRMS the ETA's provenance rather than disturbing it** — see §2.4.

---

## 2. P194-1 — THE FIFTH FALSY ZERO, AND THE FIRST WHERE TWO TESTS OF ONE VARIABLE DISAGREE

### 2.1 The defect

`backend/app/tasks/calibration_main_build.py`, `_record_staged_rate` (`:1531`). `completed_mean` is
`float | None`, from `stage_completed_mean_ms`. It is tested **two different ways in one function**:

```python
:1570  completed_mean = runner.ledger.stage_completed_mean_ms(STAGED_UNIT_STAGE)
:1572  if completed_mean is None:              # <-- correct: None-vs-value
:1577      ...record_gauge("staged:unit_ms_mean_completed", int(completed_mean))
...
:1613  projection_mean = completed_mean if completed_mean else mean_ms      # <-- truthiness
:1615      "staged:beats_basis:completed" if completed_mean else "staged:beats_basis:mixed", 1
```

At `:1572` the author knows the distinction is `None` vs a value. Forty-one lines later the same
variable is asked a *different* question, and `0.0` answers it wrongly.

### 2.2 What one beat then publishes — demonstrated on the real classes

Built with `cpl.PhaseLedger(plan=cpl.derive_plan({}, floors={}), …)`; one unit recorded via
`record_stage_outcome(name, 0, completed=True)`. **No source edits.** (`reachability.py`.)

```
stage_completed_count      = 1
stage_completed_mean_ms    = 0.0
stage_completed_max_ms     = None      <-- P193-1: says NOTHING finished

:1572  completed_mean is None -> False  => records staged:unit_ms_mean_completed = 0
:1613  completed_mean truthy  -> False  => projection_mean falls back to the MIXED mean
:1615  basis flag recorded    -> staged:beats_basis:mixed
```

**That single beat's ledger asserts all four of these at once:**

| key | says |
|---|---|
| `staged:units_completed_this_beat` = 1 | a unit completed |
| `staged:unit_ms_mean_completed` = 0 | a unit completed, and cost 0 ms |
| `staged:beats_basis:mixed` = 1 | **nothing completed, so the basis fell back** |
| `stage_completed_max_ms` → `None` | **nothing of that name finished** (P193-1) |

The last two contradict the first two about the same beat.

### 2.3 Why the fallback is worse than a cosmetic flag

The CAL-P068 comment at `:1597–1612` is unusually explicit that the mixed mean is the defect it
exists to remove: *"the truncated observation drags the mean DOWN; a lower mean means more units
appear to fit per beat, which means FEWER beats appear to remain. The projection was optimistic by
construction."* The `or`-style fallback at `:1613` **silently reinstates exactly that** on the one
beat where a completed measurement was in hand. The comment's own failure direction, restored by the
line it sits above.

### 2.4 🟢 The direction is FAIL-SAFE for the ETA — the directive's proof stands

`staged:beats_basis:completed` can only be written when `completed_mean` is **truthy** — non-`None`
*and* non-zero. So the flag can never falsely claim `completed`; it can only under-claim. **The live
`beats_basis:completed = 1` therefore genuinely proves a non-zero completed measurement drove
`beats_to_publish = 4`.** ITEM 1's "the ETA is sound, do not re-derive it" is confirmed, not
undermined.

### 2.5 Reachability, and the honest limit

Reachable by the same argument as P193-1: `record_stage_outcome` floors with
`ms = max(0, int(duration_ms))` — *the same line* that eats P192's `-1` — so one completed unit at
0 ms gives `stage_ok_totals = 0, stage_ok_counts = 1` → mean `0.0`. 🟢 **Latent, not live:** the beat
in production reads `staged:unit_ms_mean_completed = 56,431` and `beats_basis:completed = 1`.
🔴 **Do not fix it.** Same fold as `P192-1` and `P193-1`. Parked `P194-1`.

### 2.6 Sweep bound — what I did and did not check

`or None` across `calibration_phase_ledger.py`: **2 hits.** `:1299` (P193-1) is the **only**
int-valued one; `:1360` is `detail or None` on a string and is intentional. `or 0`: 8 hits, all the
*inverse* coalescence (`None → 0`); the only one that could conflate "unknown" with "complete" is
`unit_projection:617` (`budget.units_total or 0` → `remaining` 0 → `beats_remaining` 0), and
⚠️ **it does not reach the live writer** — `calibration_main_build:1586` computes `remaining` from
the module constant `STAGED_FUTURES_BUCKETS`, not from `units_total`. Recorded as a dead end, not a
finding. **I did not sweep the other four calibration task modules.**

---

## 3. 🔴 P194-2 — THE `:4370` COMMENT IS FINGERPRINT-FREE. FOUR DIRECTIVES SAY OTHERWISE.

### 3.1 The inherited claim

`964` ITEM 3 step 4, carried from `961`/`962`/`963`:

> **Free one-line rider when the freeze lifts:** delete the stale claim at
> `precompute_calibration:4370` … ⚠️ It is a COMMENT in the frozen hashed module — **it moves the
> fingerprint. Not free during D-G.**

### 3.2 What the guard actually hashes

`_main_input_fingerprint` (`precompute_calibration:6514`) hashes `inspect.getsource` of **exactly
four functions** — `compute_calibration_payload` (4917–6285), `_calibration_population_ctes`
(2729–3780), `_virtual_market_ctes` (2607–2692), `_main_futures_sql` (4099–4347) — plus six named
constants. `inspect.getsource` returns a function's own block, **never the module around it** — the
docstring says so itself, three times, and calls it "the general rule this keeps re-teaching".

**Line 4370 is at MODULE LEVEL**, 23 lines past `_main_futures_sql`'s last line (4347). AST-checked:
enclosing scope `MODULE LEVEL`, inside a hashed function `False`.

### 3.3 Containment proof (`fingerprint-containment.py`)

```
LINE 4370: '#: it — which is why ``staged:beats_to_publish`` is absent from every ledger.'
hashed source chars: 163885
IS LINE 4370 IN THE HASHED SOURCE? -> False
```

Deleting a line that is not in the digest's input cannot change its output: the four functions'
concatenated source stays **byte-identical**, and `getsource` returns text, not line numbers.

### 3.4 Empirical cross-check — 42 commits, 26 wipes, zero counterexamples

Replaying P190's own sweep (`artifacts/cal-p190/sweep-three-digests-42-commits.jsonl`) and diffing
each `wide`-digest transition against the files it touched:

```
wide-digest transitions: 26
  of which did NOT touch precompute_calibration.py: 0
```

**The fingerprint has never once moved without `precompute_calibration.py` being edited** — over the
whole 42-commit window P190 measured.

### 3.5 What this does and does NOT license

🔴 **It does not unblock the edit.** Ruling 009 freezes the module and D-G freezes the deploy; both
still bind, and neither is this lane's to lift. **What changes is the PRICE.** The claim "not free
during D-G" priced this as needing to ride a deploy that was already resetting the fingerprint. It
does not. It is a one-line comment deletion that can ride **any** calibration deploy, at zero
rebuild cost, whenever ruling 009 is next opened for that file.

### 3.6 🟢 THE GENERALIZATION — this is the actual payload

The same containment argument prices the whole falsy-zero family:

| park | fix site | in a hashed function? | rebuild reset? |
|---|---|---|---|
| `P192-1` | `calibration_phase_ledger.record_stage` clamp | **no** — different module | **none** |
| `P193-1` | `calibration_phase_ledger:1299` | **no** — different module | **none** |
| `P194-1` | `calibration_main_build:1613/1615` | **no** — different module | **none** |
| `:4370` comment | `precompute_calibration`, module level | **no** — 23 lines outside | **none** |

**All four are invisible to `_main_input_fingerprint`. The fold that picks a falsy-zero convention
can fix every one of them without discarding the 45-unit bank.** Four directives have carried the
opposite intuition. Parked `P194-2`.

⚠️ **Stated precisely, and no wider:** this is a claim about the *input fingerprint and the staged
cursor*, not a claim that deploys are harmless. P190 §2.3's residual stands untouched — a deploy can
still interrupt an in-flight beat by other means, and layer 1's 23% is about a *different* question
(narrowing the digest so cosmetic edits INSIDE the four functions stop wiping).

---

## 4. THE QUESTION BANK

`963`/`964` recorded the bank as EMPTY, with questions 1, 2 and 5 live and P193 warning the streak is
"a streak, not an entitlement".

* 🟢 **Question 1 — *"what, exactly, does this guard compare — and what is therefore NOT in it?"* is
  now SIX FOR SIX, and this is its best payout yet.** P194-2 is question 1 pointed at
  `_main_input_fingerprint` itself. Every prior use aimed it at a *test* guard; the fingerprint is a
  **runtime** guard, and the same question worked unmodified. 🔴 **That is the extension worth
  carrying: the question is not about tests, it is about anything that claims to cover something.**
* 🟢 **P193's proposed accessor question paid** — P194-1 is the docstring-vs-caller shape, found
  deliberately this time rather than by accident. **Still live**, ~8 unread accessors remain.
* ⚠️ **P193's other proposal — "which of the 24 top-level ledger keys has NO reader?" — NOT RUN.**
  Untouched and still available. Check P188's artifact first.
* **Questions 3, 4 and both SPENT questions stay closed.** I re-ran none of them.

---

## 5. WHAT I DID NOT DO

* No code committed, no merge, no deploy, no cert staged. Branch gains only `artifacts/cal-p194/`.
* Did not run the P185 datagolf discriminator — ITEM 3 step 2 says before grading a publish, and
  there was none. **Seven consecutive sessions without it now.**
* Did not re-derive the ETA, the fence model, or the ring offset band.
* Did not touch the group-key hazard. 🔴 **P194-1 and P194-2 do not close it either** — the same
  note P191–P193 made, for the same reason: it is about which COLUMNS enter a digest, and these are
  an accessor's falsy zero and a comment's containment. ⚠️ **FIVE consecutive sessions have now
  filed a ledger-sweep park that leaves the group-key hazard untouched. It is still only recorded,
  never guarded.** ⚠️ **Caveat on P194-2's table:** it says these fixes cost no rebuild — that is
  about the *cursor*, and is emphatically NOT a claim that `category` is safe. `category` is a data
  value the digest cannot see at all; that is the hazard, not a cost.
* Did not sweep the other four calibration task modules for the falsy-zero class (§2.6).
