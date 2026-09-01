# CAL-P209 — Q17 on its own answer: the cursor_reason vocabulary is 20 tokens, not 15

**Session:** 2026-09-01, ~23:38Z → ~00:0xZ. **Issue:** #2052. **Branch:** `program/calibration-190-…`.
**Directive:** `979-burndown-conveyor.md` (self-staged by CAL-P208), ITEM 3 step 5 — Q17 on its
three named unrun targets.

---

## HEADLINE

**Q17 run on all three targets it named. One CONFIRMED, two honest NEGATIVES.**

The confirmed one is the uncomfortable one: **P208-1's own producer count was low.** P208 asked
"how many outcomes can this classifier emit, and how many can its reader name?" and answered
*15 emitted, 11 of them bank-wiping, rubric names 1 = 9.1%*. But one of P208's fifteen is the
**f-string template** `f"envelope_{read.status}"`, and a template is not a token. `read.status`
has **five** reachable values at that branch, so the deployed code emits **20** distinct
`cursor_reason` values, **15** of which wipe the bank, and the rubric names **1 of 15 = 6.7%**.

> **Q17's first application to a Q17 result widened it by a third.** The failure mode Q17 detects —
> a reader that knows fewer names than the producer emits — is exactly the failure mode a *counter*
> of that gap falls into when it counts a dynamic token as one.

**Nothing was built. Nothing was merged. Nothing was deployed. The freeze was honoured.**
The lane opened owing no check and closes owing no check.

---

## 1. STANDING COMMANDS — all three clean, nothing to grade

| check | result |
|---|---|
| fingerprint predictor | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 43rd session** |
| master | `c139713996b7e957ac4eb239c82faf3b3f84ce10` — unchanged; production `v3981` still matches |
| curve `generated_at` | **`2026-08-31T04:37:36Z`**, `availability: stale` — **not** `2026-09-02` ⇒ 🔴 **FREEZE STILL ON** |
| `temporary_excluded` / `temporary_by_cell` | both **absent** — no publish, RULE E ungradeable |
| inbox | only `979` (this lane's own, `.running`). No new Fable directive |
| `STANDING-NOTICES.md` | re-read; mtime `14:57 PT`, clause 2 **materially unchanged** — freeze resumed |
| `TOP-PRODUCT-DEFECTS.md` | 24 items; only 12 (✅ DIAGNOSED) and 21 (lane1's) touch calibration. **No calibration-lane build item** |

**Both bank-bearing rows (ITEM 1b), 23:38Z and 23:44Z:**

| row | updated_at | generation | bank | ledger copy |
|---|---|---|---|---|
| `staged_futures` (cursor) | 23:21:22Z | `1788304500129` | **80** | — |
| `phase_ledger` | 23:33:52Z | `1788304500129` | — | **80** |

Generations **AGREE** ⇒ converged, no beat in flight. **80/128, 48 to go.** Next beat 00:15:00Z
(`crontab(minute=15)`). At the measured +5/beat this is ~10 beats out — **beyond this session**, so
no publish was available to grade and no poller was armed.

🟢 **The cursor's `input_fingerprint` is the NARROW `78143607db6fd8116af5fadeffef6799`** — it has
**not** reverted to `e2040f90…`, which the conveyor flagged as a real finding if seen. The ledger
row still carries the WIDE digest, which is correct: the two rows stamp different things.

P185's datagolf discriminator was **not** run — the conveyor says run it before grading a publish,
and there was no publish.

---

## 2. 🔴 P209-1 — THE PRODUCER EMITS 20 TOKENS, NOT 15; 15 WIPE THE BANK, NOT 11

**Harness:** `artifacts/cal-p209/cursor_reason_vocabulary_width.py` → `vocabulary_width.json`.
All source read via `git show c1397139:<path>` — the **deployed** sha, never the worktree (which is
on `calibration-190` and does not contain CERT-697).

**Population, in the noun the marker uses:** *distinct string VALUES that can reach*
`record_stage(f"staged:cursor_reason:{reason}")` *at `precompute_calibration.py:4598`.* Not sites,
not constants — **values**, because a value is what an operator reads off a ledger key and looks up.

### What was actually counted

| | P208-1 | measured |
|---|--:|--:|
| static constants defined & emitted | "14" | **15** |
| dynamic token template | 1 | 1 template → **5 values** |
| **TOTAL distinct values** | **15** | **20** |
| **values that WIPE the bank** | **11** | **15** |
| rubric names, of the wipes | 1 | 1 |
| **coverage** | **9.1%** | **🔴 6.7%** |

The five expansions, with the provenance the harness printed:

```
envelope_unavailable    <- failed_read default, 2 call sites (durable_snapshots.py:198, :241)
envelope_malformed      <- decode_envelope, 5 sites (durable_state.py:273,278,283,290,314)
envelope_wrong_type     <- decode_envelope (durable_state.py:258)
envelope_wrong_version  <- decode_envelope (durable_state.py:308)
envelope_stale          <- decode_envelope (durable_state.py:325)
```

All five are **structurally** reachable — that is what makes them tokens an operator can meet — but
they are **not equally likely**, and the artifact says so per token rather than implying they are:

* `envelope_unavailable` / `envelope_malformed` / `envelope_wrong_type` — **LIVE**. Any DB error,
  session failure, torn write or non-dict payload.
* `envelope_wrong_version` — **on a schema bump only.**
* `envelope_stale` — **only after a 14-day gap.** `STATE_MAX_AGE_S = 14 * 86400`
  (`calibration_main_build.py:226`) and the cursor is rewritten per banked unit.

### Why the collapse matters and is not pedantry

Every one of the five returns `blank, INVALIDATE` (`calibration_main_build.py:1296`), and every
INVALIDATE path returns a cursor with `committed_units = ()`. So all five **wipe the bank**, and
each writes a **different ledger key** — the recording site interpolates the reason into the key
name itself. An operator meeting `staged:cursor_reason:envelope_malformed` on a beat where the bank
went to zero is looking at a key that appears in no constant, no docstring, and no rubric. It is
not searchable to a name; it is searchable only to an f-string.

### 🔴 The sharpest sub-result: `envelope_wrong_version` SHADOWS `schema_mismatch`

`REASON_SCHEMA = "schema_mismatch"` exists, is documented, and is one of the three tokens whose
splitting-out has its own comment in `calibration_staged_futures.py`. It checks
`raw.get("schema") != STAGED_FUTURES_SCHEMA` — the **payload's inner** schema field
(`calibration_staged_futures.py:1637`).

But `decode_envelope` checks the **envelope's** `schema_version` against the *same* constant, and it
runs **first** — inside `read_snapshot`, before `load_staged_cursor` ever sees a payload. So on an
actual schema bump the operator gets **`envelope_wrong_version`**, the token with no constant and no
prose, and **`schema_mismatch` — the token written for exactly that case — cannot fire.**
`schema_mismatch` is reachable only in the narrow torn-write case where the envelope version is
RIGHT and the inner field is wrong.

The same shadowing shape holds for `envelope_malformed` vs `malformed`: two different checks in two
different modules, one word apart, with nothing telling an operator they are different layers.

**Severity: OPERATOR-visible. It is a defect in the RUBRIC and in the token vocabulary's
discoverability, not in the code's behaviour.** The bank is wiped correctly in all fifteen cases;
what is wrong is that eleven of them cannot be looked up. 🔴 **NOT FIXED** — naming the dynamic
tokens would be a change to a live classifier's key namespace under a deploy freeze, and it is a
fold's call under ruling 134.

### The control arms — all six clauses

| clause | how it was met | result |
|---|---|---|
| **(i) reproduces a KNOWN hit** | the extractor must recover `legacy_fingerprint_accepted`, which P208 observed LIVE at 22:36:02Z | ✅ recovered |
| **(ii) states the SHAPE** | a dynamic f-string reason whose interpolated value is an enum owned by a **different module** | stated in the artifact |
| **(iii) reports the FRACTION classified** | 15 reason-emitting return sites found, **15/15 = 100.0%** classified, zero unclassified | ✅ a total, not a floor |
| **(iv) names the POPULATION in the marker's noun** | "distinct cursor_reason string VALUES" — vs P208's "tokens" | stated |
| **(v) FAILS when the status quo would have been right** | `expansion_beyond_one_token`; if `read.status` had ≤1 reachable member the harness prints `VOID (collapse was harmless)` | measured **4** ⇒ `collapse_harmful: true` |
| **(vi) shape guard** | every AST fact asserted; exits **2** and voids on any drift | see below |

🟢 **The shape guard earned its keep on the first run.** It tripped on
`durable_state.py:235` — `EnvelopeRead(status=status, …)` inside `failed_read`, where `status` is a
**parameter**, not a constant. The harness refused to silently skip a `status=` it could not resolve
(the *scan-must-RAISE* rule) and exited 2 with the finding void. The fix was to resolve parameters
explicitly against the signature default plus call-site overrides — **not** to loosen the guard.
Had it skipped quietly, `envelope_unavailable` would have been missed and the answer would have been
19/14 instead of 20/15.

---

## 3. 🟢 P209-2 — Q17's OTHER TWO NAMED TARGETS BOTH COME BACK NEGATIVE

Recorded so no future session re-runs them. Both readers **already name their own gaps**, which is
the honest opposite of the P208-1 shape.

**Target A — `FLOOR_STATUSES` vs "the phase that DIED".**
A phase is exactly one of **7** statuses (`calibration_phase_ledger.py:141-147`):
`pending · running · complete · resumed · timeout · cancelled · failed`.
`DONE_STATUSES` = 2, `FLOOR_STATUSES` = 3, leaving `pending` and `running` in neither.
**But `failing_phase` — the sole consumer — names the gap in its own docstring:**

> *"Read after `close_open_phase` has run, which is what moves the in-flight phase into a floor
> status. Returns `None` when no phase is in one — a run that died between phases, or before the
> first began, has no failing phase to name, and naming the nearest one anyway is how the original
> line came to be wrong."*

The reader knows precisely which outcomes it cannot name and returns `None` rather than guessing.
**NEGATIVE. This is also a Q7 pass — docstring and guard agree.**

**Target B — `terminal` values vs the publish-grade reader.**
The producer emits **6** (`TERMINAL_COMPLETE · PARTIAL · FAILED · CANCELLED · HARD_LOSS ·
OVERLAP_REFUSED`). The reader is `_phase_ledger_verdict` in `task_verdict.py`.

⚠️ **A first pass on this target looked positive and was wrong** — `overlap_refused` is absent from
`_TERMINAL_COMPLETE`, `_TERMINAL_PARTIAL` and `_TERMINAL_FAILED`, which looks exactly like the
P208-1 shape. There is a **fourth** set, `_TERMINAL_NO_WORK` (`task_verdict.py:63`), which contains
it, and the reader also has an explicit `UNKNOWN` fallthrough for anything unnamed.
**6/6 covered. NEGATIVE.**

🔴 **The lesson worth carrying more than either result: Q17's own answer is only as good as the
enumeration of the READER's side.** Q17 found a real gap on target C by counting the producer
properly, and almost manufactured a false one on target B by counting the reader improperly. **Count
both sides exhaustively, and grep for a fourth set before concluding there are three.**

---

## 4. WHAT THIS DOES NOT SHOW — the near-miss discipline

🔴 **P209-1 is NOT the group-key hazard and must not be read as touching it.** It is a third
member of the "reader knows fewer names than the producer emits" family (with `P208-1`), and the
conveyor's ITEM 6 already warns that this family is **the most seductive near-miss** to the hazard.
Its population is **`cursor_reason` token VALUES vs a rubric**. The hazard's population is
**roster COLUMNS vs a digest**. One is about naming outcomes; the other is about reading inputs.
**The hazard remains unguarded and P209 built nothing toward it.**

🔴 **P209-1 does not weaken PC-1.** P208's load-bearing arm was the negative control on
`committed_units` (70 → 71 across the digest change), not the token. Widening the token vocabulary
makes the case for that choice **stronger**, not weaker: there are now 15 ways to wipe a bank under
a name the rubric cannot interpret, up from 11. **PC-1 stays GREEN.**

🔴 **Layer 1's honest limits are unchanged** and this session touched none of them: it covers the
23% class only; falsifier #1 cannot be graded for weeks; the cutover was graded on an idle-gap
boundary and a mid-beat release is still untested. **A green PC-1 plus a clean Q17 pass is still not
"the rebuild survives a deploy". Do not build layer 2.**

---

## 5. FILED

| id | what | severity | fixed? |
|---|---|---|---|
| `P209-1` | cursor_reason vocabulary is **20 values / 15 wipes / 6.7% named**, not 15/11/9.1% — P208-1 collapsed a dynamic f-string into one token; plus `envelope_wrong_version` **shadows** `schema_mismatch` | OPERATOR | **NO** — key-namespace change under a freeze; ruling 134 |
| `P209-2` | Q17's other two named targets (`FLOOR_STATUSES`, `terminal`) are **NEGATIVE** — both readers name their own gaps; target B nearly produced a false positive from a missed fourth set | — | n/a |

Neither belongs on `TOP-PRODUCT-DEFECTS.md`. No decision is owed to Alex.

## 6. ARTIFACTS

| file | what |
|---|---|
| `cursor_reason_vocabulary_width.py` | the six-clause control-armed harness; AST-only, reads the deployed sha, **exits 2 and voids** on shape drift |
| `vocabulary_width.json` | its output: verdict `CONFIRMED`, 100% site coverage, per-token reachability |
| `REPORT.md` | this file |

🟢 **Reusable:** the harness is the worked example for *"this count includes a DYNAMIC token — how
wide is it really?"* Re-point it by changing `STAGED`/`MAIN_BUILD` and the `reason_sites(...)`
function list. Its `envelope_status_domain()` is a general pattern for resolving an interpolated
enum across module boundaries, including parameter-bound values.
