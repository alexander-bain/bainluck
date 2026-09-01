# CAL-P201 — Q10 on the orphan census: it classified 41.4%, and the unseen 59% holds three instances

**Session:** 2026-09-01 ~11:58–12:3x PT · lane `calibration` · branch
`program/calibration-190-the-rebuild-survives-a-deploy`
**Queue:** self-staged `971-burndown-conveyor.md`, ITEM 3 step 5 → question bank **Q10**
**Pillar:** TRUTH · **Ship:** none — this is a parked measurement under PROCESS-V2 clause 6.
Nothing built, nothing merged, nothing deployed, nothing in `app/` or `frontend/` touched.

---

## 0. Session state (all three opening checks, plus the freeze signal)

| check | value | verdict |
|---|---|---|
| input fingerprint | `e2040f90154fae876f0fb65f5abf74c3` | 🟢 unchanged — **36th session** |
| `origin/master` | `b5c59f38fd1847ccb503f7ea2ad7f1f4a055c5d8` | 🟢 **held still**, empty diff vs `970`/`971` |
| `/api/calibration` `generated_at` | `2026-08-31T04:37:36Z` | 🔴 **FREEZE ON** (`985`'s date signal) |
| ledger `updated_at` | `2026-09-01T18:24:55.805978Z` | unmoved — **expected, not a stall** (below) |
| inbox | `971` running; nothing newer than `985` | no new Fable directive |
| `TOP-PRODUCT-DEFECTS.md` | items 12 + 21 only, unchanged | no calibration-lane build item open |

**The unmoved ledger is expected and must not be read as a failed relaunch.** Alex relaunched at
11:51 PT = **18:51 UTC**; this session opened at **18:58 UTC**, seven minutes later. The ledger is
written at *beat end*, not at launch. `units_banked` still 55/128, `terminal cancelled`,
`outcome.published false` — identical to `970`. Re-read it next session; do not inherit these.

`985` is being honoured: master has now stopped moving for the first time in four sessions.

---

## 1. What was asked

The question bank's newest and (per `971`) highest-value item:

> **Q10 — "this sweep closed NEGATIVE. What FRACTION of its population did it CLASSIFY?"**
> Turn it on every SPENT/EXHAUSTED/CLOSED marker.

`971` suggested re-pointing `artifacts/cal-p200/coverage_of_the_sweep.py` at another sweep's module
list. ⚠️ **That instruction is looser than it reads and the next session should not follow it
literally:** that tool imports its classifier from `sweep_falsy_nonnumeric` and buckets *truth-test
sites by operand type*. Pointed at new modules it reports **the falsy sweep's** coverage on those
modules — not the other sweep's coverage. Q10 on a different sweep needs an instrument built around
*that sweep's own population definition*. This session built one.

**Target chosen:** the **no-production-consumer census** (P197 `proof_1` §E, widened by P198
`census_no_production_consumer.py`). It is the strongest Q10 target in the repo because it did not
merely close a class — it issued two verdicts the conveyor now repeats as standing law:

* *"`PhaseLedger.failed_phase` has no production consumer"*
* *"five others … are consumed in-module: internal machinery, not dead. **Do not re-report those
  five.**"*

and the question bank records it as **"which ledger KEY has NO reader?" SPENT** on the ledger module
(P197) and on `calibration_staged_futures` / `calibration_main_build` /
`calibration_staged_disclosure` (P198).

---

## 2. The instrument

`artifacts/cal-p201/census_coverage_and_precision.py` — runs from any cwd, bootstraps the repo root,
**exit 0 = all four controls held**. Output: `census-coverage-output.txt`. Measured axes:

* **AXIS 1 — population.** The census's `public_members()` walks `tree.body` and keeps only
  `FunctionDef`/`AsyncFunctionDef`. Compared against a **scope-aware** public surface.
* **AXIS 1b** — the census's *own* detector re-run over the bucket it never enumerated.
* **AXIS 2 — detector precision.** `refs()` is `\bname\b` over the **raw** line, so comments,
  docstrings and `__all__` string entries count as consumers. Re-run with comments and string
  literals blanked via `tokenize`.

**Two-sided controls on both axes** (the P200 pattern — a positive that must surface *and* a
negative that must not). All four PASS:

| arm | assertion | result |
|---|---|---|
| A1-positive | `PHASE_DEADLINE_MS` is in the surface, **not** in the census population | PASS |
| A1-negative | `record_gauge` is in **both** (population not vacuously empty) | PASS |
| A2-positive | `failed_phase` has no production-**code** consumer (P197 reproduces) | PASS |
| A2-negative | `record_gauge` **does** have one (no false alarm) | PASS |

**Honest denominator.** The script never descends into a function body: a local cannot have an
external consumer, and counting locals is exactly the inflation P200 had to retract (77.4% → 66.0%).
A first exploratory cut here made that same mistake — `ast.walk` swept up in-function assignments and
reported 27.6% coverage on the ledger module. That number is **wrong and is not used**; the
scope-aware figure is 35.0%.

---

## 3. `P201-1` — the census classified **41.4%** of its population *(the finding)*

```
TOTAL  125 enumerated / 302 public names  =  41.4% COVERAGE
never in scope, by kind: {'constant': 108, 'field': 56, 'class': 13}
```

| module | enumerated | public surface | coverage |
|---|--:|--:|--:|
| `calibration_phase_ledger.py` | 50 | 143 | **35.0%** |
| `calibration_staged_futures.py` | 35 | 90 | **38.9%** |
| `calibration_main_build.py` | 37 | 56 | **66.1%** |
| `calibration_staged_disclosure.py` | 3 | 13 | **23.1%** |

It enumerated **100% of callables and 0% of constants, fields and class names.**

🔴 **Why that specific gap voids the specific marker.** The question bank recorded the marker as
*"which ledger **KEY** has NO reader?"* — but **a ledger key is a constant**:

```python
# backend/app/utils/calibration_staged_disclosure.py:105
GAUGE_UNITS_BANKED = "staged:units_banked"
```

On `calibration_staged_disclosure.py` the census enumerated **3 of 13** names, and **all 10 it missed
are constants** — i.e. the gauge-key names themselves. **The population that answered the "which
ledger key has no reader" question contained no keys.** The instrument answered *"which ledger
**method** has no reader"*, which is a different question with the same words.

⚠️ **Scope limit, stated plainly.** P197 and P198 were not wrong about what they examined — every
callable they cleared is correctly cleared, and §5 below confirms the "do not re-report those five"
verdict holds. The defect is that a callable-only result was recorded as a *class* verdict.

---

## 4. `P201-2` — two "consumed" verdicts rest on **prose only**, and both are real

```
members the census called CONSUMED : 123 of 125 scanned
...of which the evidence is PROSE ONLY: 2
```

Both hand-verified repo-wide (`grep`), both survive, and they are **different shapes**:

### (a) `calibration_staged_futures.py:1514` — `decode_staged_cursor`

No production caller. Production calls only `decode_staged_cursor_detailed`
(`calibration_main_build.py:1272,1297`) — a **distinct token**, so this is not a substring artifact.
Its only non-test references are an `__all__` **string** (line 127) and a **docstring** (line 1952).
Tests do call it (`test_calibration_staged_futures.py:1208`,
`test_calibration_convergence_p024.py:262`).

🔴 **This sits on one of P198's own three target modules, which the census reported as zero
orphans and zero test-only.** The zero is a detector artifact: the raw regex saw the `__all__`
string and the docstring and called it consumed.

### (b) `calibration_main_build.py:498` — `PhaseRunner.deadline_exceeded`

```python
def deadline_exceeded(self) -> bool:
    return self.ledger.remaining_ms(elapsed_ms=self.elapsed_ms()) <= 0
```

**No caller in `app/` and none in `tests/`.** The three other repo hits are unrelated string
literals (`tournament_register_sentinel.py:270`, `board_sentinel.py:1164`) and one comment. The test
file `test_calibration_unit_window_p038.py:138` defines **its own same-named stub**, which is what
made the raw detector see a reference.

It is dead because it was **superseded and left behind** — `precompute_calibration.py:4353` says so
in the past tense:

> *"The loop's only **prior** gate was ``deadline_exceeded()`` — 'is there any time left' — which is
> not the question."*

**Ruled out:** no `import *` of any calibration module, no `__all__` in the ledger module, no
`getattr` access by any of these names.

---

## 5. `P201-3` — one orphan in the bucket the census never saw

```
ORPHANS found in the never-enumerated bucket: 1
    backend/app/utils/calibration_phase_ledger.py:236   PHASE_DEADLINE_MS
```

```python
#: The one absolute deadline every phase is planned against.
PHASE_DEADLINE_MS = SOFT_LIMIT_MS - CLEANUP_MARGIN_MS      # 1_500_000 − 120_000 = 1_380_000
```

**Zero references in `backend/app` and zero in `backend/tests`.** Every consumer re-derives the
subtraction instead:

* `test_calibration_elastic_budget_p109.py:210` — `available = SOFT_LIMIT_MS - CLEANUP_MARGIN_MS`
* `test_calibration_window_slack_p072.py:444-445` — the same subtraction twice
* `artifacts/cal-p144/*.py` (×3) — hard-coded literal `1_380_000` under the same name
* `docs/CALIBRATION-EXIT-EXAM.md:572` — refers to it by name as though it were live

🟢 **And the conveyor re-derived it too.** `971` ITEM 2 states the window formula by hand —
`window = (soft_limit_ms − cleanup_margin_ms) − elapsed = 1,380,000 − elapsed` — and adds:
**"The second formula was never written down before — write it down and stop re-deriving it."**
It *had* been written down, as a named constant with the docstring *"the one absolute deadline every
phase is planned against"*, since before this run began. It is simply unread, so eleven sessions of
conveyor prose re-derived a constant that already existed.

⚠️ **Severity, honestly: LOW.** The two live re-derivations compute from the same two constants, so
behaviour tracks correctly if `CLEANUP_MARGIN_MS` changes. The exposure is documentation drift and a
missing single source of truth — **not** a live wrong number.

### The "five" verdict HOLDS

Re-checked by hand: `phase_feasibility`, `feasible_phases`, `unit_projection`, `declared_ms`,
`slack_target` all have genuine in-module **call sites or dict values** (e.g. `declared_ms` at
lines 692/699, `phase_feasibility` at 545/578). 🟢 **"Internal machinery, not dead" is correct.
Do not re-report those five.**

---

## 6. Scope limits — what this does NOT say

* 🔴 **The three code instances are MINOR.** A thin test-only wrapper, one dead 2-line method, and an
  unread constant whose value is re-derived correctly elsewhere. **The valuable finding is `P201-1`,
  the methodological one.** Do not cite this report as "the census was wrong" — it was *narrow*, and
  its narrowness was recorded as breadth.
* 🔴 **"There are more orphans in there" is a MISCITING.** The unseen bucket was 177 names and running
  the detector over all of them yielded **exactly one**. The 58.6% blind fraction is a measured
  **UNKNOWN that has now been largely resolved**, not a measured problem.
* ⚠️ **Axis 2 covered only the 125 names the census enumerated.** Prose-only precision on the
  constant/field bucket was not separately measured.
* 🔴 **None of this touches the group-key hazard.** `P201-1/2/3` are a population-coverage figure, a
  detector-precision figure and three unread names. **No digest, no `GROUP_KEY_COLUMNS`, no
  `category`.** Listed here so the next session does not count them toward the hazard — which
  remains untouched and still only recorded, never guarded. **Twelve consecutive sessions now.**
* ⚠️ **`P201-1` is the one most likely to be miscounted against the hazard**, for the same reason
  `P200-1` was: it is *about* an instrument's blind spot, and the hazard is *also* a blind spot.
  **Different blindness.** This measured the population of a *reader census*; the hazard is a
  `GROUP_KEY_COLUMNS` member absent from a *digest*. No sweep in this run has ever had the digest's
  columns as its population.
* **All three are OPERATOR-visible. None is user-visible. None belongs on
  `TOP-PRODUCT-DEFECTS.md`,** and build lanes do not add items there anyway.
* **Nothing was fixed.** All three are a fold's call under ruling 134, and `985` forbids the deploy
  regardless.

---

## 7. Compliance

| rule | status |
|---|---|
| `985` hard deploy freeze | 🟢 honoured — no merge, no master push, no Heroku-triggering change |
| `960` / `920` not-to-merge | 🟢 honoured |
| PROCESS-V2 (2) WIP ≤ 2 branches | 🟢 one branch |
| PROCESS-V2 (3) self-merge | 🟢 not eligible — no cert ever staged for this branch |
| PROCESS-V2 (6) no instrument as its own queue | 🟢 parked to `PARKED-MEASUREMENTS.md`, not the conveyor |
| PROCESS-V2 (7) no closing question | 🟢 ITEM 5 is decisions-taken; nothing asked |
| PROCESS-V2 (8) `TOP-PRODUCT-DEFECTS.md` read first | 🟢 read; unchanged |
| ruling 134 lane roles | 🟢 read-only measurement, parked; nothing built |
| `YOUR-TURN.md` | 🟢 not touched |

**Files touched:** `artifacts/cal-p201/` (new) and the two bus writes. **No `app/`, no `frontend/`,
no tests, no worktrees created.**
