# CAL-P063 — Sentinel red-list triage, annotated

Window: 2026-08-17 (PT). Queue: CAL-P063. Branch: `program/calibration-60`.
Scope: read-mostly, merge-independent. **No market data was written; no code path changed.**

The ledger rule makes this list REPLACE the standing category worklists. This document is that
list, annotated per cell with linking evidence, plus registered predictions and the post-apply
re-read plan.

---

## 0. Instrument provenance — read this before any number below

**Every measurement here was taken from production PostgreSQL through the read-only `db-query`
rail on 2026-08-17.** None of it is derived from the published `/api/calibration` snapshot.
Nothing below is STALE-INSTRUMENT.

Three provenance facts that the next reader needs, because two of them correct a carried caveat:

1. **#1680's carried text is itself out of date.** It says "no calibration publish since
   2026-08-02". Measured today, `GET /api/calibration` returns
   `generated_at: 2026-08-14T00:16:07.908709+00:00`. The producer is **not** stopped since 08-02;
   it last published 2026-08-14. It is still **3.5 days stale against an hourly beat**, so the
   condition #1680 tracks is real — but the date in it is wrong and should not be quoted forward.
2. **The published snapshot is therefore unusable as a post-apply instrument.** Any re-read that
   consults `/api/calibration` before a forced recompute is verified is STALE-INSTRUMENT and must
   be labelled so. Verification is `?bust=1` + task-metrics, **never** `generated_at`
   (`reference_calibration_recompute_verify`).
3. **The Calibration Sentinel is NOT affected by that staleness.** It mines `futures_outcomes`
   directly. Its numbers are live. Its *evidence packs*, however, have defects of their own — §1.

**Reproduction fidelity.** The cohort reconstruction used below is exact where it could be
checked: #1142 reproduces the sentinel's published `n = 14,315` and `MCE = 21.33pp` to the
decimal. #1143 reproduces `19.55pp` against a filed `19.52pp` (the cell was filed 2026-07-20; a
month of new rows accounts for the drift). Numbers here can be trusted to be the same population
the sentinel flagged.

**Declared NOT-RUN (never reported as zero, per gotcha #53):**

| Measurement | Status |
|---|---|
| `#1895` resolution_source × is_winner census | **NOT-RUN** — statement_timeout ×3 |
| `#1145` resolution_source × is_winner census | **NOT-RUN** — statement_timeout ×3 |
| `#1895/#1144/#1145/#1896` post-gate band curves | **NOT-RUN** — exceed the ~10 s ceiling |
| ITF migrating cohort's own curve (§3, P-4) | **NOT-RUN** — statement_timeout |

---

## 1. Instrument defects found while triaging (these change how the list is READ)

These are not findings *about* the cohorts; they are findings about the detector that produced
them. Four of the ten cells cannot be read at face value until I-1 is understood.

### I-1 — `_cohort_where` silently drops the `series` and `structure` dimensions

`backend/app/tasks/calibration_sentinel.py:458-473`. The function builds the WHERE clause used by
the **evidence pack** (`_sample_rows`, `_placeholder_fraction`). It honours `source` and
`category` and nothing else. Its own docstring says *"Series/structure dims are honored where
present."* They are not.

Consequence: for any cohort keyed by `series` or `structure`, the "Sample high-cp rows" table in
the issue body is drawn from the **whole source or whole category**, not the cohort. The evidence
attached to the red cell is not evidence of the red cell.

This is visible on the face of the filed issues and was the thread that opened this triage:

- **#1142** is titled `series=KXNHLGOAL` (NHL goals). Every sample row is `KXATPMATCH-*` (tennis),
  `KXMLBKS-*`, or `KXATHLETEMENTION-*`.
- **#1143** is titled `series=KXMLBTB` (MLB total bases). Its samples are LoL, CS2, NCAABB and
  ATP; exactly **one** of twelve is actually `KXMLBTB`.

Worse than mismatched: in both cells the off-cohort samples are all `cp≈0.995, winner=✓` — they
read as *healthy*, directly contradicting the cohort census printed six lines above them. A reader
who trusts the evidence pack is steered away from a real break.

Affected: **#1142, #1143, #1896, #1145** (series- or structure-keyed).
Clean: **#1895, #1144** (source+category only — `_cohort_where` honours both).

The **census** is not affected. Buckets are folded from a scan grouped by
`series_family`/`structure_class` (`_FUTURES_MINING_SQL`), so MCE and the bucket table are
cohort-correct. Only the evidence pack leaks. That is why #1142's MCE reproduced exactly.

### I-2 — `classify_coverage` takes the MAX over known classes, never the union

`calibration_sentinel.py:229-237`. It picks the single largest overlap fraction and compares it to
`SENTINEL_COVERAGE_THRESHOLD = 0.40`. A cohort that two shipped exclusions cover 30% + 14% scores
`0.30` and files as UNEXPLAINED.

This is not hypothetical — it is why two of the six calibration cells exist, and one of them by a
rounding margin:

| Cell | Largest class | Threshold | Margin |
|---|---|---|---|
| **#1896** tennis/binary | `malformed_binary` **39.6%** | 40.0% | **filed UNEXPLAINED by 0.4pp** |
| **#1144** poly/politics | `mex_normalization` **37.6%** | 40.0% | filed UNEXPLAINED by 2.4pp |
| **#1895** poly/mma | `malformed_binary` 30.2% (+ `poly_placeholder` 14.0%) | 40.0% | union ≤44.2% would have cleared |

### I-3 — the issue renderer omits `kalshi_prop_threshold` from the overlap list

`calibration_sentinel.py:621-626` iterates a hard-coded tuple of six class names.
`kalshi_prop_threshold` — added by CAL-P013 precisely so the sentinel could name the exclusion the
curve already ships — is **counted in the diagnosis but never printed**. On #1142 and #1143, the
single class that explains the cell is the one the reader cannot see. Both cells are 100%
ladder-named; neither issue body contains the words.

### I-4 — the capture axis has no n-floor and no season-window awareness

`backend/app/utils/capture_census.py:224-243`. The only guard is `if games == 0: continue`. There
is no minimum sample size and no consultation of `app/utils/season_windows.py`.

**#1900 files a REAL P2 off four games.** This re-creates, on the capture axis, exactly the
crying-wolf class that `season_windows.py` was written to kill for the grid sentinel and for the
watchdog's Tier-1 coverage-drop alarm (CLAUDE.md, r197). The playbook's own Step 0 sets the bar at
n ≈ 30 and it is not applied here.

---

## 2. The annotated red list

Legend — **(a)** EXPLAINED-BY-STAGED-REPAIR · **(b)** NEEDS-NEW-INVESTIGATION ·
**(c)** EXCEPTIONS-REGISTRY candidate.

### Headline: **not one cell is explained by a staged repair.**

The four staged repairs are #1852 (fabricated losses), #1868 (premature grades), #1870 (PM
evidence hole), #1109/#1888 (month-tag contamination). Their reach against this list:

- **#1852 and #1868 are Kalshi graders.** They cannot move a Polymarket cohort. Four of the six
  calibration cells are Polymarket-dominated. Measured on the largest — **#1896's zero-winner mass
  is 98.1% Polymarket** (27,774 markets vs 523 Kalshi), so the two Kalshi repairs reach at most
  **1.9%** of it.
- **#1870 changes no grade and no price.** It fills `volume` and teaches the writer to record a
  confirmed zero. `price_moved` is a price comparison that consults no volume (the issue says so
  itself). It **cannot move any MCE on this list.** It is correctly on the stack; it is not an
  explanation for any red cell.
- **#1109/#1888 is the only staged repair that reaches this list at all**, and it reaches it by
  moving rows *between* categories rather than by fixing a grade. See P-4.

| # | Cohort | Verdict | Linking evidence |
|---|---|---|---|
| **1142** | kalshi · KXNHLGOAL · MCE 21.33 | **(c)** CLOSE | 100% of 14,315 outcomes are ladder-named `"Player: N+"`, `mutually_exclusive=false`. Shipped CAL-P013 exclusion drops **3,299**; the five miscalibrated bands (cp≥0.50) total **3,298** — a one-row match. **Published MCE = 3.69pp**, under the 5.0pp threshold. Filed UNEXPLAINED only because of I-2/I-3. |
| **1143** | kalshi · KXMLBTB · MCE 19.52 | **(c)** for cp≥0.90 **+ (b)** residual | 100% ladder-named. Shipped exclusion drops the 90-100 band (11,184 rows, actual 46.4% vs pred 97.9%). **Published MCE = 7.57pp — still above threshold.** Residual is real: bands 20-30 (−8.5pp, n=5,918), 30-40 (−14.0, n=4,269), 40-50 (−19.0, n=2,538) — three adjacent, same direction, n≥200, passes playbook Step 0. Bands 60-80 *over*-resolve (+17.5, +11.2): the ladder is wrong in **both** directions, which no exclusion explains. |
| **1895** | polymarket · mma · MCE 19.39 | **(b)** | Structure, not grading: **41.3% multi-winner, 28.9% zero-winner, only 29.8% one-winner.** Just 1,780 of 5,978 outcomes sit in a well-formed market. The sentinel's own `esports_multi_bundle` predicate (≥3 outcomes, ≥2 winners) would cover the 41.3% — it is **hard-gated to `category='esports'`** in the mining SQL, so mma scores 0.0% on a class it structurally *is*. Polymarket ⇒ #1852/#1868 unreachable. |
| **1896** | tennis · binary · MCE 18.86 · n=137,144 | **(c)** dominant **+ (b)** residual | Zero-winner mass **33.6%** of outcomes / 28,297 markets, of which **98.1% Polymarket** (PM tennis binary: 42.9% of markets have *both* legs graded loser). Already dropped from the published curve by the `clean_vms has_winner>=1` gate. Filed UNEXPLAINED by **0.4pp** (I-2). **OWED:** `malformed_binary` requires `mutually_exclusive=true`; unverified for PM tennis — if false, the vm gate is the only thing catching these and grouped vms leak. |
| **1144** | polymarket · politics · MCE 18.49 | **(b)** | Break is entirely the 90-100 band (n=2,978, pred 99.2% → actual 33.2%). `mex_normalization` 37.6%, again just under threshold (I-2). resolution_source census: **8.3% NEVER GRADED** — `is_winner=false` with `resolution_source NULL`, i.e. a column default standing in for a grade (gotcha #53 inside our own writer, same shape as #1870's finding); plus a named `all_losers` source at 2.5% (491 rows), `pass2_loser` 0.7%, `pass2_guess` 0.3%. Polymarket ⇒ #1852/#1868 unreachable. |
| **1145** | hockey · binary · MCE 17.42 | **(b)** — highest-value new one | **Definitively not the fabricated-loss family.** Zero-winner mass is only 6.5%, and the dominant defect is the 0-10 band **over**-resolving: pred 1.6% → actual **43.1%** (+41.5pp, n=1,658). Fabricated losses can only push actual *down*. A +41.5pp low-band inversion at n=1,658 is a sign-flip/wrong-side signature and is mechanically distinct from every other cell on this list. |
| **1897** | capture · NFL/moneyline | **(c)** season artifact | 19 games, **2026-08-07 → 2026-08-16 — preseason only**; the regular season has not started. The detector's assertion "a game without a winner market is impossible" is not true of NFL preseason. I-4. |
| **1898** | capture · WNBA/moneyline | **(b)** — the one credible capture cell | 73 games, 2026-07-19 → 2026-08-16, continuous in-season. 0.85/game ⇒ ~11 games genuinely short of a winner market. This one should be worked. |
| **1899** | capture · EPL/other | **(c)** below noise floor | n = 27 markets, under the playbook's ~30 floor. The events table shows **2** EPL fixtures in the window, both 2026-07-27 friendlies. I-4. |
| **1900** | capture · Ligue 1/moneyline | **(c)** below noise floor | Filed off **4 games**. Events shows 2, 2026-07-27 → 2026-08-06 — preseason. One missing market flips the ratio. I-4. |

**Tally: (a) 0 · (b) 5 · (c) 5** (two cells split (c)+(b)).

---

## 3. Registered predictions

Registered under **ruling 050** — with the caveat that **ruling 050 does not exist as a file.**
`docs/rulings/` and its index both stop at **047**; rulings 048–060 live only in queue prose, as
CAL-P061 already flagged for Fable. CI is green because it checks index ↔ files in both directions
and *both sides are empty*. I have deliberately **not** minted a `050-*.md`, because I would be
guessing the content of a ruling I did not write, and a wrong file is worse than a missing one.
These predictions are therefore banked here and are graded from here.

Each is falsifiable and each states what would refute it.

| ID | Prediction | Refuted by |
|---|---|---|
| **P-1** | The attended applies for **#1852 + #1868 + #1870** move **#1895, #1896, #1144 and #1145 by < 1.0pp MCE each**. Mechanism: the first two are Kalshi-only graders and these cohorts are Polymarket-dominated (#1896's zero-winner mass measured 98.1% PM); the third writes no grade and no price. | Any of the four moving ≥1.0pp. That would mean a repair reached a population I have measured it cannot reach, and my source attribution is wrong. |
| **P-2** | **#1142 does not move.** Published MCE stays **3.69pp ± 0.5**, n stays 11,016 ± 200. No staged repair touches KXNHLGOAL. | Any movement. Would indicate an apply with wider blast radius than declared. |
| **P-3** | **#1143's residual survives the applies.** Post-apply published MCE stays **> 5.0pp** (measured today 7.57pp), and the 20-50% under-resolution keeps its sign. | Residual dropping under 5.0pp — which would mean the 20-50% band *was* a grading artifact after all, and #1143 reclassifies (b) → (a). |
| **P-4** | Applying the **#1109/#1888** ITF repair migrates **14,407 resolved cp-bearing outcomes** into `category='tennis'` (14,508 ITF cp-rows minus the 90 markets / 101 rows already tagged tennis). **#1896's n rises ~137,144 → ~151,500 (+10.5%)**, and the donor cohorts fall by **baseball −8,003, football −2,960, basketball −3,282**. ITF is 2-outcome (13,807 outcomes / 6,946 markets ≈ 1.99), so it lands in `tennis × binary` — #1896's exact cohort. | n moving by materially less than +10%, or the donors not falling by the stated amounts. |
| **P-5** | **The direction of #1896's MCE under P-4 is UNDETERMINED.** I attempted to measure the ITF cohort's own curve and it **timed out — NOT-RUN.** I am explicitly declining to predict the sign. It is owed before the applies, not after. | n/a — this registers an obligation, not a claim. Grading it means *having measured it*. |
| **P-6** | **No capture cell moves.** #1897–#1900 are ingestion/classification; no staged repair touches them. #1897/#1899/#1900 will still fire on the next sweep, because the season boundary and the small n are unchanged and I-4 is unfixed. | Any of them clearing without a code change — which would mean the slate moved, not the bug. |

**Standing caveat on all of the above:** the pre-values are DB-measured today. If any post-apply
read is taken from `/api/calibration` without a verified forced recompute, it is
**STALE-INSTRUMENT** and grades nothing.

---

## 4. Post-apply re-read plan

**Gate 0 — restore the instrument before reading it.** Force a calibration recompute and verify
via `?bust=1` + task-metrics, not `generated_at` (`reference_calibration_recompute_verify`). Until
that passes, the published snapshot is 3.5 days old and every read off it is STALE-INSTRUMENT.
Note the known 1–4 minute post-deploy 503 window (`project_calibration_post_deploy_503`) — a 503
here is not a regression.

**Gate 1 — re-read from the DB, not the snapshot.** Re-run the exact queries behind §2 (they are
reproducible from this document; each is a bounded aggregate under the ~10 s ceiling). Grade P-1,
P-2, P-3, P-6.

**Gate 2 — grade P-4 with a before/after census** of `KXITFMATCH-%` by `llm_sport_category`, and
`#1896`'s n. Both were measured today, so the "before" side is already banked above.

**Gate 3 — discharge P-5 first.** Measure the ITF cohort's own band curve before the applies run.
It timed out from this window; it needs either a narrower slice (by season/date) or the heavy
worker. **Do not let the applies land with P-5 undischarged** — otherwise a shift in #1896 is
uninterpretable, because we will not know whether it came from the repair or from the arrival of
a differently-calibrated population.

**Gate 4 — re-run the sentinel in backtest mode**
(`?inline=true&file_issues=false&suppress_known=false`) and confirm the ten fingerprints
re-derive. Cells classified **(c)** should be closed with an exclusion reference rather than
re-filed; that requires I-2/I-3 to be fixed first, or they will re-file on the next beat.

**Ordering note.** Gates 0 and 3 are *pre*-apply obligations, not post-apply steps. Everything
else is post-apply.

---

## 5. What this queue deliberately did not do

The four instrument defects in §1 are real and each has a small fix. **None was shipped here.**
CAL-P063 is read-mostly and merge-independent by directive, and the `-54…-59` stack is waiting on
R3 GREEN with the attended applies queued behind it. Adding sentinel behaviour changes to that
wave would put merge risk in front of the applies for no gain — the defects mis-*classify* cells,
they do not corrupt data, and this document already supplies the corrected reading for all ten.

They are filed as issues instead, so they survive this window without touching the stack.
