# CAL-P211 — the post-publish measurement, and why it is a refusal instead

**Written 2026-09-01 ~23:1x PT.** Directive `calibration/978` asked for the drain to be relaunched
and babysat "until the curve publishes", then measured. It did not publish, and this file states
why the relaunch was **not** performed — verified independently, from source and from the live
ledger, not inherited from the previous session's report.

---

## 1. The directive's trigger fired; its action was already unsafe

| the directive said | measured at 22:51 PT |
|---|---|
| `run.6277` banks a few units then stops itself (~50 min) | **no drain dyno is alive.** `heroku ps -a bainluck` lists only the 6 standing dynos |
| "the moment the cursor goes cold with the bank < planned" | **bank 5 / planned 128**, `cursor_age_s` 926 and climbing (1,778 by 23:05) |
| "launch the CORRECTED one-off yourself" | **NOT DONE — deliberately.** See §2 |

The directive was written at **21:46 PT**. The refusal it could not know about landed at **22:27 PT**
and was reported at **22:41 PT** (`alex-inbox/calibration-020`). The directive is 55 minutes older
than the fact that invalidates its action.

## 2. Why a relaunch was refused — verified from source, not taken on trust

`backend/app/utils/calibration_publish_gate.py`:

* **L852** `if drift < -POPULATION_TOLERANCE:` → `reject("population_shrink", …)`
* **L68** `POPULATION_TOLERANCE = 0.05`
* Measured drift: `(728,641 − 930,149) / 930,149 = **−21.66%**` against a **−5%** limit.
* **L922-937** Rule 3 then adds `category_collapse` for every category over `CATEGORY_MIN_N = 1000`
  falling more than `CATEGORY_DROP_TOLERANCE = 0.20` — crypto 4,625 → 0 is a 100% drop.

None of that is stochastic. The drift is a property of the **deployed predicate**, so every future
rebuild is refused for the same reason. And the live phase ledger shows a refusal is not free:

```
outcome.gate            = refuse          terminal            = failed
checkpoint_action       = invalidate      staged:units_banked = 0
staged:served_units     = 128             population_version  = q268
input_fingerprint       = e2040f90154fae876f0fb65f5abf74c3
```

`checkpoint_action: invalidate` is the binning. A relaunch under q268 buys a full
Postgres-saturating rebuild whose only possible outcome is another refusal that throws itself away.
**That is why the drain was not relaunched, and it is the one thing directive 978 could not know.**

## 3. The escape hatch is real — same file, L831

```python
if verdict.version_bumped:
    return verdict          # returns BEFORE Rule 2 (shrink) and Rule 3 (collapse)
```

A declared version bump is the lawful way to publish a deliberate methodology shrink. That is what
`program/calibration-211-the-curve-publishes-under-a-declared-version` builds. It is **unmerged**
and gated on Alex's call, because emptying the compatibility list takes /calibration dark.

## 4. THE DARK WINDOW IS HOURS, NOT ~26 HOURS

`calibration-020` and the (now deleted) freeze-window pin both carried a **~26-hour** estimate. The
live phase ledger does not support it. Measured, from `calibration:main:phase_ledger`:

| quantity | value | source |
|---|--:|---|
| `staged:unit_ms_mean` | **91,844 ms** (91.8 s) | ledger, over completed units |
| units in a full build | **128** | `staged:units_planned` |
| ⇒ pure build time | **~3.3 h** | 128 × 91.8 s |
| `unit_worst_history` mean | 103.7 s ⇒ **~3.7 h** | 24 recorded worst-unit samples |
| `plan.feasibility…units_per_beat` | **13** | ledger |
| ⇒ UNASSISTED recovery | **ceil(128/13) = 10 hourly beats** | the plan's own arithmetic |
| futures phase per full beat | **20.4 min** | `history.futures`, 8 full beats — consistent with 13 × 91.8 s |

Two independent routes (mean-unit-cost and per-beat-throughput) agree. The honest range is
**~3.3–3.7 h of build**, with an unassisted beat-only recovery of **~10 h**; the attended one-off
drain lands between them. The ~26 h figure appears to be a prose estimate that was never
re-measured — it is **not** in the ledger.

**Consequence for the decision: the dark window is cheapest right now.** Started tonight it ends
overnight; started at 9am it is dark across the working day.

## 5. The headline, measured live — unmoved and ungraded

`python3 backend/scripts/calibration_scorecard.py --live` (repo root), **EXIT 0**, 23:10 PT:

| quantity | 17:45 baseline | **now** | moved? |
|---|--:|--:|:--:|
| `generated_at` | 2026-08-31T04:37:36Z | **2026-08-31T04:37:36Z** | no |
| `population_version` | q268 | **q268** | no |
| `total_outcomes` | 930,149 | **930,149** | no |
| **`mce_closing_line`** | 1.86 pp | **1.86 pp** | no |
| **cells at bar** | 31 / 49 | **31 / 49** | no |
| `producer_beats_missed` | 44 | **49** | 🔴 **+5** |

The only number that moved is the one counting failures. CAL-P162's pre-registered **32/48 / 1.78 pp
(band 1.70–1.86)** is **not consumed** — it stays armed for the first q269 curve, as do the
comparator and both its controls.

`nonexclusive_bundle_filter` is still absent from the 44 top-level keys. Under PRE-REGISTRATION §3
that is only meaningful *after* a publish, so it grades nothing tonight; PC-1 was already answered
via the gate's count bridge in `calibration-020` §3.

## 6. What this branch changes

| file | change |
|---|---|
| `app/tasks/precompute_calibration.py` | `CALIBRATION_POPULATION_VERSION` q268 → **q269**; `COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` → **`()`**; new `PREVIOUS_PUBLISHED_POPULATION_VERSION = "q268"` (measured off the live payload) and `POPULATION_VERSION_DARK_WINDOW_ACCEPTED = "q269"` |
| `tests/test_calibration_result_authority_299.py` | the rollover guard becomes **two-armed** (lit path unchanged; dark path must be accepted *for this version by name*), plus an inheritance control and a bump-shape pin |
| `tests/test_calibration_population_growth_1955.py` | the duplicate guard: stale `q267` literal → `PREVIOUS_PUBLISHED_POPULATION_VERSION`, and the declared-dark arm asserts the cost is real |
| `tests/test_staged_rebuild_survives_a_deploy.py` | freeze-window fingerprint pin **deleted per its own written instruction** (both its conditions met; re-baselining was explicitly ruled out) |
| `tests/evals/fixtures/calibration_fingerprint_derived_map.json` | regenerated; **only `source_sha256` moved** — no hashed root or by-value input changed |

### The guard was proven red before it was trusted green

| mutation | expectation | result |
|---|---|---|
| `POPULATION_VERSION_DARK_WINDOW_ACCEPTED` → `"q268"` (stale acceptance, current q269) | REFUSE | 🟢 **EXIT 1**, `assert 'q268' == 'q269'` with the inheritance message |
| `COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` → `("q267",)` (non-empty but wrong predecessor) | REFUSE | 🟢 **EXIT 1**, names `'q268'` as the one it must contain |
| restored | PASS | 🟢 61 passed |

Both arms fire, so neither is vacuous. The inheritance control is what stops
`accepted == current` from being satisfiable by any commit that edits both constants together.

## 6b. Gates — run, not assumed

| gate | command | result |
|---|---|---|
| smoke | `pytest tests/test_startup.py` | 🟢 **EXIT 0**, 4 passed |
| calibration surface | `pytest tests/ -k "calibration or population or rollover or staged or beats_to_publish"` | 🟢 **EXIT 0**, 3,123 passed / 24 skipped |
| **full backend suite** | `pytest tests/ -q` | 🟢 **25,895 passed, 158 skipped, 61 xfailed, 0 failed** (20:51) |
| ruff | `ruff check <changed>` | 🟢 All checks passed |
| black | — | **not run, deliberately.** All four touched files are already non-black-clean on `origin/master` and black is in no CI workflow; reformatting would bury a 5-line semantic diff in a whole-file rewrite |
| frontend build / typecheck | — | **not run — no frontend file is touched.** Backend Python + one JSON fixture only |

Branch `program/calibration-211-the-curve-publishes-under-a-declared-version` @ `e714a850`, pushed.
**No cert staged and no READY token written** — the merge is gated on Alex, not on a grade.

## 6c. Live state through the session (the babysit log)

| time PT | bank | cursor_age_s | ledger generation / gate | curve |
|---|--:|--:|---|---|
| 22:51 | 5 / 128 | 926 | 1788326490717 · `refuse` | 2026-08-31, q268, 1.86 pp |
| 23:05 | 5 / 128 | 1,778 | unchanged | unchanged |
| 23:17 | — | — | unchanged (no new candidate) | — |
| 23:27 | **10** / 128 | 269 | unchanged | unchanged |

No drain dyno ran at any point. The bank rising 5 → 10 on a cold cursor is the **hourly beat**
re-accumulating on its own, walking toward another complete candidate that the gate will refuse and
bin for the same reason. That is the standing cost of leaving the decision open, and it is why
"wait and see" is not a neutral option.

## 7. What is NOT claimed

* **Not** that q269 fixes the curve. It makes the curve *publishable*; `cells_at_bar` is graded on
  the first q269 artifact against the pre-registration, and `done` still needs Alex's eyeball at
  49/49.
* **Not** that the batch's numbers are right — only that they are now *declarable*.
* **Not** merged, not deployed, not certed. Alex's call is unresolved and this branch waits on it.
