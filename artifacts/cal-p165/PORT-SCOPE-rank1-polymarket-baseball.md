# Rank 1 `polymarket/baseball` — the port, scoped

**CAL-P165, 2026-08-31.** Directive `930` Item 2 handed this over deliberately unscoped:
*"scope the port first, then land R3 and M1 on top."* This is that scoping. **No code was
ported in this session** — the session's build capacity went to the CERT-626 repair's
blocker (see `REPORT`). The design is banked and RULED in
`artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md` §9.3 and is **not re-derived here.**

## 0. THE HEADLINE CORRECTION — the port is roughly 10x smaller than the directive says

Directive `930` (and `929` behind it) size this as **"9,866 insertions across 28 files"**.
Measured today from the repo root against current master:

```
git diff --stat "origin/master...origin/program/calibration-99" -- backend frontend
  → 16 files, 6,004 insertions, 71 deletions
```

The directive's larger figure was measured before master moved; part of that branch has since
landed by other routes. **But the file count is not the real correction — the composition is.**

⚠️ **Measure this from the REPO ROOT.** A relative `-- backend` pathspec evaluated from
`backend/` matches nothing and the three-dot diff reads **EMPTY** — a clean-looking zero that
means "you are standing in the wrong directory", not "there is nothing to port". This session
hit exactly that and briefly believed the branch was already merged.

## 1. WHAT IS ACTUALLY ON `program/calibration-99`, SPLIT BY WHETHER THE SHIP NEEDS IT

`origin/program/calibration-99` @ `9d0e98f8`, **808 behind / 8 ahead**, merge-base
`ee25e1cd`. Eight commits, CAL-P099 → CAL-P104, dated 2026-08-26.

### 1a. NEEDED — the producer predicates (this is the whole port)

| file | lines | why |
|---|--:|---|
| `backend/app/tasks/precompute_calibration.py` | subset of **+801** | R1 + R2 live here. **Only 83 of the 801 added lines mention an R1/R2 symbol** (`half_spike` 72, `pair_coherence`/`PAIR_SUM_TOLERANCE` 11). The other ~718 are CAL-P099–P104's CAS write-set and fold work, on issue **#2212**, and are NOT this ship. |
| `backend/tests/test_half_spike_pair_exclusion.py` | +504 | R1's guard, ports with it |
| `backend/tests/test_published_pair_coherence_p100.py` | +974 | R2's guard, ports with it |
| `backend/tests/evals/fixtures/calibration_fingerprint_derived_map.json` | +231 | **regenerated, never hand-merged** |
| `backend/tests/test_calibration_fingerprint_coverage.py` | +86 | tripwire pins move; each needs its history recorded |

### 1b. NOT NEEDED — measurement lane (ruling 134) and a different workstream

| file | lines | what it is |
|---|--:|---|
| `backend/scripts/fold_published_pair_coherence.py` | +808 | fold/measurement |
| `backend/scripts/fold_half_spike_pair.py` | +538 | fold/measurement |
| `backend/scripts/fold_pair_disposition.py` | +395 | fold/measurement |
| `backend/app/utils/repair_apply_plan.py` | +521 | **#2212 pair-opening repair — a different ship** |
| `backend/scripts/derive_pair_opening_repair_plan.py` | +315 | same, #2212 |
| `artifacts/cal-p097/pair_opening_repair_plan.json` | +14,501 | same, #2212 (artifact) |
| `backend/scripts/measure_2098_mode_price_collision.py` | ±47 | measurement |

**So: ~1,700 lines of fold script and ~15,300 lines of #2212 repair plan are sitting inside
the number that has been deterring this port.** The producer-side transplant is on the order
of **100–250 lines plus two guard files**.

## 2. THE CONFLICT SURFACE, MEASURED

`git merge-tree --write-tree HEAD origin/program/calibration-99` → **EXIT 1, four conflicts**:

| file | verdict |
|---|---|
| `backend/app/tasks/precompute_calibration.py` | 🔴 **the only real one.** Both branches edit the frozen file heavily — ours `+336` (RULE E), theirs `+801`. Transplant R1/R2 by hand; do **not** merge the branch. |
| `backend/tests/evals/fixtures/calibration_fingerprint_derived_map.json` | derived — **regenerate**, do not resolve |
| `backend/tests/test_calibration_fingerprint_coverage.py` | tripwire pins — re-pin with history, do not resolve |
| `artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md` | prose, trivial |

🔴 **Do not `git merge program/calibration-99`.** It carries 808-behind history and two
workstreams this ship does not want. **Cherry-pick the predicates, not the branch.**

## 3. THE ARMS, AND WHERE EACH ONE COMES FROM

K′ = **R1 + R2 + R3 + M1** (design §4/§9.3). Every arm load-bearing; dropping R2 alone puts
the cell back over the bar at 3.10.

| arm | predicate | where it is today |
|---|---|---|
| **R1** | both legs of a two-leg O/U market open at exactly `ROUND(opening_probability,4) = 0.5000` | **PORT** — `half_spike_pair_exclusion`, calibration-99 only (45 refs). **0 refs on our head.** |
| **R2** | two-leg O/U, opening pair sums to 1 within `PAIR_SUM_TOLERANCE` (0.02) and the **published** pair does not; both legs leave | **PORT** — `published_pair_coherence_filter`, calibration-99 only (4 + 7 refs). **0 refs on our head.** Shipped there with **"NO ECE CLAIM"** — read that before reusing its numbers. |
| **R3** | Polymarket market name matches `%player props%` **and** published prices sum to **> 1.15** | **BUILD HERE.** The `1.15` is **RULE E's own constant**, already on our branch — not a fitted threshold. |
| **M1** | one row whose published price landed in `[0.45, 0.55]` having opened more than 0.25 away | **BUILD HERE** (design §7) |

Verified today: `half_spike_pair`, `published_pair_coherence` and `PAIR_SUM_TOLERANCE` all
return **0 matches** on `HEAD:backend/app/tasks/precompute_calibration.py`. The port is real
and nothing has quietly landed it.

## 4. THE TWO THINGS THAT WILL BITE

1. ⚠️ **The allowlist entry is TEMPORARY BY DESIGN.** It must ship with
   `temporary_by_cell["polymarket/baseball"]` carrying the revert condition.
   `test_temporary_by_cell_is_empty_because_no_temporary_cell_shipped` **will go red the
   moment the tuple is added** — deliberately, to force the revert condition to be written.
   That red is the design working. Do not delete the test.
2. ⚠️ **Scope, not `is_nonexclusive_bundle`.** The design REFUSES extending RULE E's flag to
   this cell (measured 8.35; RULE E alone is 9.02). The `(source, category)` allowlist is
   shared; **the predicate behind each entry is not.**

## 5. THE HONEST EDGE, CARRIED FORWARD VERBATIM FROM THE DESIGN

> 2.71 against a 3.0 bar is **0.77σ under it** — a pass, and not a comfortable one. And
> because the temporary population is expected to *return*, this cell will be re-scored when
> it does. **Crossing rank 1 off is a claim about the curve as it will be published, not a
> claim that the cell is permanently solved.**

Expected: 4.71 → **2.71 pp**, 17,827 rows, **excess-outcomes 78,782 → 0**, holdout OLD 2.90 /
NEW 2.63. Record a prediction **before** the code, as CAL-P162 did.

## 6. RECOMMENDED ORDER FOR THE NEXT SESSION

1. **Do not start until CERT-63x (the RULE E head) has graded.** Both ships edit the frozen
   file; building rank 1 on top of an ungraded rank 2/3 stacks a second cert on an unproven
   one, which is how this branch reached four certs on one ship before.
2. Transplant **R1** alone → its guard → fingerprint regen → measure.
3. Transplant **R2** → guard → measure. (R2's solo delta is −0.11 pp; it is load-bearing only
   in conjunction, so do not judge it alone.)
4. Build **R3** on RULE E's existing `1.15` constant.
5. Build **M1** (§7).
6. `temporary_by_cell` + the revert condition, last, when the red forces it.
