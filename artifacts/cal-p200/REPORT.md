# CAL-P200 — a falsy sweep in this lane inspects one site in seven, and nobody measured that before calling the class closed

**Queue:** `program/calibration-190-the-rebuild-survives-a-deploy` (CAL-P200)
**Session:** 2026-09-01, ~11:44–12:0x PT
**Pillar:** TRUTH · **Ship it serves:** the published calibration curve (rider work under the `985` freeze)
**Status:** measurement only. No `app/` write, no `frontend/` write, no merge, no deploy.

---

## 0. One paragraph

Under the `985` hard deploy freeze there was nothing to build and nothing to grade, so this session
took the top open question from the conveyor's bank: **the non-numeric falsy sweep** (`''` / `[]` /
`{}`), the successor to CAL-P198's numeric sweep, which closed NEGATIVE and which the conveyor
recorded as CLOSING the class — before CAL-P199 found a string instance inside its own scanned
files. The sweep was built with a **two-sided** control arm and both arms pass. Its direct result is
**NEGATIVE**: within what it can see, `P199-1` remains the only instance. But building it forced the
P199 lesson to be applied reflexively, and that is where the actual finding is: **neither sweep ever
measured what fraction of its population it could classify.** Measured now, on the same corrected
denominator: **P198 inspected 13.4%** of the falsy-capable sites in its four modules and its
negative was recorded as a class verdict; **P200 inspects 15.2%** across twenty modules. Both are
minority instruments. A control arm proves a sweep can *see* the class; it says nothing about *how
much* it looked at.

---

## 1. What was run

| artifact | what it is | exit |
|---|---|--:|
| `sweep_falsy_nonnumeric.py` | the non-numeric falsy sweep, 20 calibration modules, two-sided control | 0 |
| `sweep-nonnumeric-output.txt` | its full output — 97 sites | — |
| `coverage_of_the_sweep.py` | the reflexive companion: what fraction could the sweep TYPE? | 0 |
| `coverage-output.txt` | its full output | — |

Both harnesses bootstrap the repo root themselves and were **run from `/tmp`** to prove it.

### The shape the sweep encodes (stated, per the P199 control-arm lesson)

> A value typed `str` / list-like / dict-like, whose EMPTY value is a meaningful state, subjected to
> a truth test (`if x:` / `not x` / `x or default`), so "empty" is silently conflated with "absent".

**Type oracle: annotations, not name heuristics.** Dataclass fields, annotated assignments,
annotated parameters and return types build a per-module name→category map; a name annotated with
two different categories anywhere in the module is marked `conflict` and **excluded**, so the sweep
under-reports rather than asserting a type it cannot prove. Expression-level inference supplements
it (`str(...)`, f-strings, `.get(k, "")`, literals, comprehensions, slices of a typed base).

### The control arm is TWO-SIDED — and that is the point

| arm | site | requirement | result |
|---|---|---|---|
| **A · positive (STRING)** | `calibration_phase_ledger.py:1360` `record.detail = detail or None` | must surface | **PASS** |
| **A · positive (STRING)** | `calibration_phase_ledger.py:1128` `if self.detail:` | must surface | **PASS** |
| **B · negative (NUMERIC)** | `calibration_phase_ledger.py:1299` `.get(name, 0) or None` | must **NOT** surface | **PASS** |
| **B · negative (NUMERIC)** | `calibration_main_build.py:1613` `completed_mean if completed_mean else mean_ms` | must **NOT** surface | **PASS** |

Arm A proves the detector can see the class at all — this is what P198 had. **Arm B is the new
half:** it proves the detector is genuinely *typed* and has not degenerated into "flag every truth
test", which would make a long hit list as meaningless as a short one. A one-sided control can only
fail in the direction of blindness; it cannot catch a detector that has gone indiscriminate.

---

## 2. The direct result — NEGATIVE, and honestly bounded

97 sites across 20 modules. Every substitution-shaped site (`or` / `ifexp`, 45 of them) was triaged
by hand. **No new instance of the class survived triage.** The three that looked strongest, and why
each died:

* **`calibration_main_build.py:1713` — `unit_costs = _unit_costs_from(runner) or prior_unit_costs`.**
  Hypothesis: the CAL-P163 fix handles the all-empty case but a *partial* measurement would drop the
  unmeasured phase, where the sibling directly below it (`_unit_worst_from` → `merge_history`)
  merges. **Dead:** `_unit_costs_from` only ever returns a single-key dict (`{PHASE_FUTURES: …}`), so
  there is no partial case. The wholesale-replace/merge asymmetry is real and is deliberately
  documented (a level vs a ring); it is not reachable as a defect.
* **`calibration_staged_futures.py:2099` — `return not cursor.owner or cursor.owner == owner`.**
  An empty owner string passes any ownership check. **Not a defect:** the docstring states "a cursor
  with no owner is unclaimed and anyone may take it" — the falsy empty *is* the intended semantics.
* **`precompute_calibration.py:5017–5182`** — the ~16-site block of
  `int(rows[0].X) if rows and rows[0].X is not None else 0`. **Not a defect:** the block is
  explicitly reasoned about in-comment, and the module already distinguishes `_int0` from
  `_int_or_none` by argument ("reporting zero there would claim … when the honest answer is that
  nobody looked"). The authors are ahead of the detector here.

**So: within its coverage, the class has exactly one known member, `P199-1`.** That is the honest
statement. The next section is why "within its coverage" is doing more work than it looks.

---

## 3. 🔴 THE FINDING — `P200-1`: neither sweep measured its own coverage

The P199 lesson was *"a passing control is only as broad as the TYPE of the hit it encodes."* Applied
to P200 itself, the next question is: **of the sites that could carry this defect, how many can the
detector classify at all?** Nobody had asked it. Measured:

| | population | falsy-capable | classified | **coverage** | blind |
|---|--:|--:|--:|--:|--:|
| **P198** (numeric, 4 modules) | 238 | 67 | 9 | **13.4%** | 86.6% |
| **P200** (non-numeric, 20 modules) | 1543 | 427 | 65 | **15.2%** | 66.0% |

*Denominator, both rows: truth-test sites minus those that structurally cannot carry the defect —
boolean-shaped expressions (comparisons, `not`, and predicate calls like `isinstance`/`any`/
`startswith`) and the benign `X or 0` idiom where the fallback equals the falsy value it replaces.*

**P198 closed NEGATIVE on 13.4% of its population, and the conveyor recorded the class CLOSED.**
CAL-P199 then found a member of the adjacent class inside two of the very files P198 had scanned.
The conveyor's diagnosis was that P198's *control arm* was type-limited — true, and it was. But that
diagnosis is incomplete: even a perfectly-typed control would have left 86.6% of the population
unclassified. **The control-arm defect and the coverage defect are independent, and only the first
one has been recorded.**

### The correction I had to make to my own number

The first run of the coverage companion reported **77.4% blind**. Hand-sampling 24 sites from the
UNTYPED bucket showed it was inflated: `isinstance(...)` calls (boolean, cannot be empty) and the
`X or 0` idiom (fallback equals the falsy value, nothing is conflated) were both being counted as
blind spots. Corrected, the figure is **66.0%**. This is recorded rather than quietly fixed because
publishing 77.4% would have been the same overstatement this finding exists to warn about — and
because a reader comparing to an earlier draft should see why the number moved.

### The generalizable clause

> **A control arm proves a sweep can SEE the class. It says nothing about what FRACTION of the
> population the sweep looked at. A negative result needs both, and a sweep that reports neither its
> coverage nor its denominator cannot close a class — only narrow it.**

Every `EXHAUSTED` / `SPENT` / `CLOSED` marker in this conveyor was set by an instrument that
reported a hit count and never a coverage figure.

---

## 4. What this does NOT claim

* It does **not** say P198 was wrong. Its nine sites were correctly classified and correctly cleared;
  its control passed. The claim is about the scope its negative can support, not its correctness.
* It does **not** say there are undiscovered falsy bugs in the blind 66%. Hand-sampling 24 of those
  sites found **zero** defects — they were predicate calls, `X or 0` self-substitutions, and
  `isinstance` guards. **The blind fraction is a measured unknown, not a measured problem.** Anyone
  citing `P200-1` as "there are more bugs in there" is misciting it.
* It does **not** touch the group-key hazard. `category` is a *data value* the digest cannot see at
  any line; this is a finding about detector coverage. **Eleven consecutive sessions have now filed
  a park that leaves the group-key hazard untouched.**
* It is **OPERATOR-visible, not user-visible.** It does not belong on `TOP-PRODUCT-DEFECTS.md`.

---

## 5. Live state re-verified this session

| thing | value | note |
|---|---|---|
| input fingerprint (local predictor @ HEAD) | `e2040f90154fae876f0fb65f5abf74c3` | unchanged, **35th session** |
| `origin/master` | `b5c59f38fd1847ccb503f7ea2ad7f1f4a055c5d8` | 🟢 **HELD STILL** — first time in four sessions; `985` is being honoured |
| `/api/calibration` `generated_at` | `2026-08-31T04:37:36Z`, `availability: stale` | **freeze still ON** — the `985` lift signal has not fired |
| phase ledger `updated_at` | `2026-09-01T18:24:55.805978Z` | unchanged from P199; the 11:51 PT relaunch has not written a beat yet |
| `units_banked` / `terminal` / `published` | 55 of 128 / `cancelled` / `false` | inherited, not re-derived |

**Not re-run this session:** P185's datagolf discriminator. P199 ran it (0 rows, quiescent) and the
conveyor's instruction is to run it *before grading a publish*, not hourly. No publish to grade.

---

## 6. Compliance

* **`985` hard deploy freeze:** honoured. No master merge, no Heroku-triggering push. Branch push
  only, which triggers no release.
* **`980` / PROCESS-V2 clause 2:** one unmerged branch on this lane. Within limit.
* **clause 3:** not self-merge-eligible — no cert has ever been staged for this branch.
* **clause 6:** `P200-1` and `P200-2` filed to `.claude/handoff/PARKED-MEASUREMENTS.md`, not to the
  conveyor.
* **clause 7:** no question left open; the stated defaults were acted on.
* **clause 8:** `TOP-PRODUCT-DEFECTS.md` read before ITEM 3. No calibration build item open.
