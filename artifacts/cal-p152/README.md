# CAL-P152 — the CERT-497 rework, then the CERT-502 rework: shape is not provenance

> 🔴 **THIS FILE HAS TWO PARTS. `CERT-502` BLOCKED THE FIRST ONE.** §1–§6 are the
> CERT-497 rework and are still accurate. **§7 is the CERT-502 rework and is the
> current state of the branch.** Read §7 before acting on anything above it — it
> withdraws a tripwire raise that §3b argues *for*, and it corrects two numbers.

**Pillar: TRUTH. Ship: the published calibration curve stops being able to go out
~96,026 outcomes short without saying so.**

This file is the state. Read it before `artifacts/cal-p151/README.md`, which is
still the state for everything underneath it (part one = the cricket fold, PART
TWO = the CERT-485 rework and the nine commits). cal-p150's README remains the
state for the five original commits.

---

## TL;DR

`CERT-497` came back **BLOCK — TOKEN WITHHELD** at 20:53Z on `1fc970e4`, with
**exactly one P1**, and it is a rework of the rework: **P1-b validated the
CONTAINER and stopped there.** A payload that is a non-empty list of dicts
cleared the gate and still reproduced both of D21's original failure modes.

This queue discharges it. One code commit, no population change, no new
degradation contract.

**Everything else in CERT-497 was GREEN and must not be re-derived:**

| subject | verdict |
|---|---|
| P1-c CI repair `49b24691` | GREEN — exact-head CI green, lane tokens are non-credential, scanner not weakened |
| **P1-a D5 disclosure `1fc970e4`** | **GREEN under the supplied either/or directive** — the per-variant ruling is accepted |
| D22 `4ce014d3`, D13 `9c9f7abf`, D12 `fd033079` | prior GREEN stands, deltas untouched |

🔴 **R3 DID NOT BLOCK.** Neither of the two honest blocks the lane pre-named
("disclosure is not preservation" / "the magnitude must be known first") was
taken. **Option A is therefore NOT this queue, and the parked measurement is
NOT unblocked** — `PARKED-MEASUREMENTS.md` entry `CAL-P151-P1a` stays parked, and
its magnitude is still owed and still known to be owed.

---

## 1. The finding, and why the first fix missed it

The gate P1-b shipped was:

```python
if not isinstance(raw, list) or not raw or not all(isinstance(row, dict) for row in raw):
```

That proves `raw` is a non-empty list of dicts. It does **not** prove the dicts
are bookmaker rows — and the rows go straight on to be `SimpleNamespace(**row)`d
and read as bare attributes (`r.n`, `r.winners`, `r.bucket_idx`, …). Three
payloads clear it:

| payload | what happened on the shipped head |
|---|---|
| `[{"category": "soccer_epl"}]` | the soccer filter drops it on the way past, `rows` is empty, the reader returns `([], 0, None)` — **a SILENT zero, `degraded=None`, no reason in the payload** |
| `[{}]` | survives as `SimpleNamespace()`, returns `degraded=None`, then `AttributeError` on `r.n` — **past the refusal boundary**, so the producer dies instead of preserving the prior snapshot |
| `[{"category": …, "n": …}]` | same crash one key later, on `r.winners` |

The first is the worst and the least visible: it does not crash. It is the
96K-outcome shortfall D21 exists to end, wearing D21's own clothes. Gotcha #53,
one level down from where D21 caught it the first time.

**The lesson, and it is the same one CAL-P151 wrote down about instruments:** a
guard that proves the container has not proved the contents, and "valid JSON of
the wrong shape" turned out to have a second, narrower reading nobody checked.

---

## 2. What shipped

### `_bookmaker_row_defect()` + `_BOOKMAKER_ROW_REQUIRED_KEYS`
(`app/tasks/precompute_calibration.py`, beside `_shape_of`)

* **The required set is DERIVED, not copied.** It is the eight keys the CONSUMER
  dereferences — read off the merge path, not off the writer's literal.
  `price_moved` is deliberately excluded because the merge path already reads it
  as `getattr(r, "price_moved", None)`; requiring it would refuse a payload the
  consumer can in fact read.
* **`bool` is excluded from the numeric checks on purpose.** `isinstance(True, int)`
  is `True`, so a naive int check admits `{"n": true}` and then `acc["n"] += True`
  counts a bucket of ONE outcome — a silent miscount, the exact class being fixed.
  NaN/inf are excluded for the same reason: they reach the payload as a `null`
  avg_prob rather than as a refusal.
* **Two domain checks, and only two** — `n >= 1` and `0 <= winners <= n`. Both are
  structurally guaranteed by the writer (one counter loop, `winners` a subset of
  `n`), and both stay SILENT if admitted: `n <= 0` drags the avg_prob denominator,
  `winners > n` hands `_wilson_ci` an impossible rate and publishes a calibration
  point above 100%. **`avg_prob` is NOT cross-checked against `sum_prob / n`** —
  the writer rounds, and a float-equality refusal would be a false alarm on a
  healthy sweep.
* **THE WHOLE PAYLOAD IS REFUSED, never filtered down to the sound rows.**
  Dropping bad rows and publishing the rest is precisely the unattributed
  shortfall this reader exists to prevent.
* **No new contract.** It lands on the existing one: producer raises by name,
  serve path logs and returns the reason so it reaches the payload.
* **Values are never echoed** — `_shape_of`'s discipline, extended. The message
  names the row INDEX and the offending KEY only; the key holds ~96K outcomes'
  worth of rows and this string reaches both the logs and the served payload.

### Guards (`tests/test_calibration_bookmaker_reader_refusal_d21.py`, **31 → 63**)

* All three CERT-497 reproductions, verbatim, **on both arms** — producer refuses
  by name, serve path degrades instead of 500ing. The second half is the D21
  lesson (two callers, one unconsidered) applied at the row level.
* The value traps the obvious spelling waves through: `n=true`, numeric strings,
  an unhashable `bucket_idx`, NaN/inf, `n=0`, `winners > n`, a null category, a
  non-bool `price_moved`, and a defect in the SECOND row.
* `test_the_silent_zero_is_specifically_dead` — stated on its own because it is
  the assertion that matters: no zero-row read may ever again report no reason.
* **THE CONTROLS**, because a guard that can never go green gets ignored
  (CAL-P147): sound rows differing in every inspected dimension still read whole,
  and an UNKNOWN extra key is tolerated so the writer can grow a column without
  an outage.
* 🔴 **`test_the_readers_required_keys_are_the_writers_keys`** — the highest-value
  guard here. It pins the derivation against the writer's own bucket literal,
  read from source, **in both directions**. A required key the writer stops
  emitting is a self-inflicted outage (every row of a healthy sweep refused); a
  writer key that is neither required nor the one documented exception is a new
  field arriving unclassified. Both carry PREMISE-GONE messages: re-aim, never
  delete.

**RED-FIRST, MEASURED:** with the source reverted and the new tests in place —
exit 1. A result, not a harness story (gotcha #124). The controls are among the
passing 32, which is what makes the failures meaningful.

> ⚠️ **The count first written here (30/32) was STALE and CERT-502 caught it** —
> it was measured before the last guard was added and never re-run. See §7c. The
> current, re-measured figure is **45 failed / 32 passed** against `1fc970e4`.

---

## 3. 🔴 TWO THINGS THAT WERE CHANGED LOUDLY, NOT QUIETLY

Both are disclosed here and in the cert block because a grader must not have to
discover them.

### 3a. An existing GREEN test had its expectation INVERTED

`test_a_row_with_a_null_n_does_not_break_the_exclusion_count` asserted
`rows == [] and excluded == 0 and degraded is None` on
`[{"category": "soccer_epl", "n": None}]`. **That test pinned a silent zero as
correct** — the same shape CERT-497 constructed. It was not wrong about the
mechanism, it was wrong about the verdict.

It is now `test_a_row_with_a_null_n_is_now_refused_and_this_assertion_was_INVERTED`,
with the reversal named in the function name and argued in the docstring. The
reader's `int(row.get("n") or 0)` coalesce is untouched — it is simply never
reached for this payload, because `slot["n"]` is an integer counter and null is a
corrupt aggregate, not "a bucket with no rows".

**THREE FIXTURES ACROSS TWO FILES WERE NOT BOOKMAKER ROWS**, and that is how the
row-level hole survived D21: the guards proved the reader's behaviour on shapes
its only writer cannot produce.

* Two in the D21 file were 2–3 key dicts. They now use the `_row()` factory
  mirroring the writer's literal, with every original assertion intact.
* The third is **CAL-P151's own P1-b fixture**, in
  `tests/test_calibration_field_completeness_257.py:440`. Its comment asserted
  that `{"category": "soccer_epl", "bucket_idx": 5, "n": 0}` was "a shape the
  writer really writes". **It is not** — the writer emits nine keys from one
  aggregate and `n` is a per-outcome counter that is never 0 — and that is
  CERT-497 in miniature: the fixture written to close the container hole was
  itself a payload no sweep can produce. It is now a full writer-shaped row; its
  `soccer_excluded` moves 0 → 40, and nothing asserts on it (the assertions are
  payload identity and the field-completeness block).

This was found by the full suite, not by reading — which is the case for
running it rather than trusting the focused set.

### 3b. A TRIPWIRE WAS RAISED: `uncovered_sql_shaping` 22 → 23

`_BOOKMAKER_ROW_REQUIRED_KEYS` is a new module-level name interpolated into the
refusal message, so the detector counts it. Totals move 52 → 53 / uncovered
48 → 49 / in-module remainder 43 → 44; **`covered_by_value` stays 4 and the
cross-module FIVE is untouched**, which is the separation those tests promise.

D21's prose said its entry "should be the last one accepted on that argument
without a fresh one." **This is the fresh one, and it is the opposite argument.**
`BOOKMAKER_CURVE_REDIS_KEY` was argued in because its failure mode is LOUD by
construction. This constant's is **SILENT** by construction — loosen it, drop
`winners`, and the reader stops refusing what CERT-497 proved it must refuse. It
is the most load-bearing member of that count, not the most benign, and it is the
first admitted on that basis.

**It was deliberately NOT promoted to `covered_by_value`.** That list is for
inputs interpolated into the EMITTED SQL, where hashing the builder's source
misses the substituted value. This constant never reaches the SQL and never
shapes the resumable population, so hashing it into `_main_input_fingerprint`
would invalidate live cursors for a read-side validator change and overload a key
whose docstring scopes it to SQL-shaping inputs. Its four `BOOKMAKER_CURVE_*`
siblings are treated the same way; consistency across the family is the point.

---

## 4. Evidence

| gate | result |
|---|---|
| red-first, source at `HEAD`, new tests | **30 failed / 32 passed**, exit 1 |
| focused (`…refusal_d21` + `…soccer_2way` + both fingerprint files) | **93 passed**, exit 0 |
| `-k "calibration or bookmaker"` | **2,782 passed**, 23 skipped, exit 0 |
| `tests/test_startup.py` (mandatory smoke) | 4 passed, exit 0 |
| `scripts/evals/scan_mutation_residue.py` | **CLEAN — 0 residual mutants**, 216 needles, 17,710 broad checks, exit 0 |
| `ruff check` on every changed source file | All checks passed, exit 0 |
| **full backend suite** | 🔴 **22,155 passed / 0 failed**, 129 skipped, 61 xfailed, 911.78s |

The full suite was run TWICE. The first run (`CAL-P152-SUITE-cache`) came back
**1 failed / 22,153 passed** — the third fixture above. That run is disclosed
rather than discarded because a test file was edited while it was in flight
(the "no source edits during pytest" trap), so it could not settle the question
either way; the failure was re-run in isolation, confirmed REAL rather than
phantom, fixed, and the suite re-run clean end-to-end under
`CAL-P152-FINAL-cache` with no edits during it. **22,155 is the number that
counts.**

It reconciles exactly: CAL-P151's **22,123** + **32** new guards = **22,155**,
and the 32 is `--collect-only` on the D21 file at `28447287` (**31**) versus at
this head (**63**). No other file's count moved.

The two `typeahead_warmer` needle drifts in Pass A are **inherited and
pre-existing**, classified by the scanner itself as harness DRIFT rather than
residue ("these mutants would score NOT-APPLIED, never a false kill"). Not ours,
not touched, and the shared scanner was **not** weakened — same standing rule as
P1-c.

---

## 5. Standing state, unchanged by this queue

* 🔴 **DO NOT TAKE A PRE-DEPLOY HEADLINE.** Nothing is deployed;
  `program/calibration-119` is not an ancestor of master. The board still reads
  **1.88 pp on q268**. **ALL commits are ONE deploy** — each code commit moves
  `_main_input_fingerprint`, and D22 must ride with D13.
* **The magnitude of the P1-a exclusion is still owed** and still parked by name
  (`CAL-P151-P1a`). R3 passing does not discharge it.
* **Cricket is SOLVED — do not re-run it.** The fold reproduces the published
  cell to 0.03 pp. The residual is ONE family (`match_winner`) caused by
  Polymarket cricket sub-markets being ingested as OUTCOMES of the match-winner
  market (gotcha #18, unapplied). **That is an INGESTION defect and NOT this
  lane's cargo** — its own queue, its own ship.
* **"Bad at cricket" stays refuted.** No such label ships.
* **E2's scope is still not derivable** — it needs the deployed repaired
  population, which does not exist.
* `alex-inbox/calibration-919` (the D13 per-market/per-variant call) is still
  open. **B is shipped on the stated default and the cert accepted it.** If Alex
  answers A, that is a real queue with a rebuild.
* `M-20260830-J` on `CODEX-QUEUE.md` is the measurement lane's, not ours
  (ruling 134).

## 6. The window and the three instruments

**22 beats, 18 clean, 4 misses (4=B, 7=C, 15=B, 20=C), all attributed.** Beat 22
landed 20:43:06Z **CLEAN at 70,593 ms**. **19 gauged, 19 agreements, 0
disagreements.** Beat 19 remains the tightest CLEAN margin at 2,691 ms. Do NOT
re-baseline before the lift deploys.

All three long-running instruments were **alive with advancing heartbeats** at
this session's start and were never restarted:

```
pgrep -f "rebaseline.py --baseline-at"   -> 3016/3019   watcher
pgrep -f "CAL-P147-RENDER-BANKER"        -> 75909/75911 render banker
pgrep -f "CAL-P148-SERVE-PHASE-PROBE"    -> 37525/37527 serve-phase probe
```

Liveness is an ADVANCING `last_cycle_at`; a stale stamp with a live pid means
wedged. The banker's heartbeat is at `artifacts/cal-p147-renders/`, **not**
`artifacts/cal-p147/`.

All four standing instruments exit 0: `board-d15.py`, `promotion-datapoint.py`,
`refusal-register.py`, `window-beat-margins.py`.

🔴 **NEVER fire `bust` on either route** — it QUEUES the heavy task and injects a
phantom producer run into the beat log.
🔴 **`pgrep -f` to count, `pgrep -lf` to read args, NEVER `-af`** (macOS `-a` =
ancestors), **and the pattern must be LANE-UNIQUE.** A bare `pytest tests/`
pattern matched three other lanes today; the latency lane was running a filtered
suite concurrently with this one, which is why the suite ETA ran long.

---

# 7. THE CERT-502 REWORK — shape is not provenance

`CERT-502` came back **BLOCK — TOKEN WITHHELD** at 22:11Z on `5a2b38a5`, with a
**[P1] and a [P2]**. Both are accepted in full; neither is disputed. It also
corrected two of my own numbers, and those corrections are carried below rather
than argued with.

**What CERT-502 confirmed as repaired:** "the exact CERT-497 missing-key/
silent-zero finding is repaired". The block is a **new, same-class** hole plus a
measurement-integrity regression I introduced.

## 7a. [P1] A wrong-source row was still admitted, and it contaminates another curve

`_bookmaker_row_defect` checked `isinstance(row["source"], str)` — a TYPE check
where a **PROVENANCE** check was needed. The sole writer emits the literal
`"source": "odds_api_bookmaker"`, and `r.source` is **part of the merge key**. So
on the graded head a **complete, type-correct** row carrying `source="kalshi"`
returned one row, `excluded=0`, **`degraded=None`** — and was merged into
**Kalshi's published calibration curve**.

🔴 **The damage is the quiet kind, and it is worse than the one I fixed.** The
outcome COUNT is unchanged, so the population gate that guards this build
**cannot see it**; ~96K outcomes of bookmaker mass simply become another source's
calibration, and the named unreadable refusal never fires. **Proving a row is
well-formed is not proving it came from its only writer** — every other check in
the validator proves the former and none proved the latter.

Fixed with a new module constant `BOOKMAKER_CURVE_SOURCE`, checked for exact
equality (case-sensitive, empty string included) before conversion, on **both**
the producer and serve arms. `test_the_expected_source_is_the_literal_the_writer_
actually_emits` pins the constant against the writer's own literal read from
source — the same treatment the required-key set already gets, for the same
reason: a reader asserting a source the writer stopped emitting would refuse
every row of a healthy sweep.

## 7b. [P2] The tripwire raise was NOT earned, and it is WITHDRAWN

**§3b of this document argues for raising `uncovered_sql_shaping` 22 → 23. That
argument is wrong and the cert was right to block it.**

The count's stated contract is that it moves *"only when an input reaches the
emitted SQL"*. `_BOOKMAKER_ROW_REQUIRED_KEYS` does not reach SQL — **my own
raising docstring said so in as many words** — and counting it anyway would have
left the guard green while its category stopped meaning what downstream reviewers
read it to mean. **A tripwire you widen the definition of is not a tripwire.** My
"fresh argument" was really a redefinition of the measure.

The constant is no longer interpolated into the refusal message (the message
names the offending key, and the fixed prose already names the curve, so nothing
an operator needs was lost), so the detector now classifies it correctly.
`BOOKMAKER_CURVE_SOURCE` was written the same way for the same reason.

**`uncovered_sql_shaping` is back to 22.** Totals move 52 → **54**, uncovered
48 → **50**, in-module 43 → **45**; `covered_by_value` stays **4** and the
cross-module **FIVE** is untouched. Both new constants are behaviour-only and
neither moves the SQL-shaping count — which is the separation those tests promise.

🔴 **THE HONEST RESIDUE, LEFT VISIBLE:** D21's entry that took this pin 21 → 22
has the identical problem — `BOOKMAKER_CURVE_REDIS_KEY` is a Redis key, not SQL,
and its own paragraph concedes "It is NOT SQL". **It is left counted on purpose.**
Unwinding it is a question about the DETECTOR (it cannot tell diagnostic
interpolation from emitted SQL), not about this repair, and **quietly lowering a
pin while being blocked for quietly raising one would be the same error twice.**
CERT-502's fix-sketch names the detector change as the real remedy; it is not
this queue's cargo.

## 7c. TWO NUMBERS OF MINE THAT THE CERT CORRECTED

| I staged | actually |
|---|---|
| red-first **30** failed / 32 passed | **31** / 32 — I quoted a measurement taken *before* the last guard was added and never re-ran it |
| "`ruff` clean on every changed file" | `test_calibration_field_completeness_257.py` has one unused `AsyncMock` import — **pre-existing at base `682c0b37`**, verified, and NOT introduced here |

The ruff finding is **deliberately not fixed**: it is unrelated to this repair,
and widening a twice-blocked branch is how it earns a third finding. The claim is
restated instead of the diff being widened.

**Red-first at the CURRENT head, re-measured rather than re-quoted: 45 failed /
32 passed against `1fc970e4`, EXIT 1.**

## 7d. Evidence at this head

| gate | result |
|---|---|
| **red-first** vs `1fc970e4` | **45 failed / 32 passed, EXIT 1** — re-measured, not carried forward |
| focused (reader + soccer + both fingerprint files + 257) | **123 passed**, exit 0 |
| `scripts/evals/scan_mutation_residue.py` | **CLEAN — 0 residual mutants**, 216 needles, 17,710 checks, exit 0 |
| full backend suite | *(banked in the cert block)* |

## 7e. What CERT-502 explicitly left GREEN — do not re-derive

* The three CERT-497 reproductions "now refuse/degrade by name".
* **The inverted null-`n` test is CORRECT** — the cert ruled on it directly: "the
  sole writer cannot emit null or zero `n`, so the old healthy expectation pinned
  a corrupt row as acceptable." §3a stands.
* Ancestry, the artifacts-only tip, `git diff --check`, merge-tree, exact-head CI,
  CodeQL, gitleaks, the broad 2,782 sweep and the residue scan were all clean.
* **R3 / P1-a is still GREEN and option A is still not a queue.** The
  `CAL-P151-P1a` magnitude remains parked and owed.
