# LAUNCH-READINESS LEDGER
# The answer to "will this ever land," maintained as a list instead of a feeling.
# Refresh: every Monday scoreboard session updates the State column; any lane
# that moves a gate updates its row in the same change. Lives at
# docs/LAUNCH-LEDGER.md. v1 seeded by Fable 2026-08-12 (evening).

The launch gate is #678 (App Store submission), held INTENTIONALLY until the
gates below are green (ruling: the hold is the plan, not a delay). "Green"
always means measured-and-observed, never claimed.

## Gate 1 — Calibration credibility (the ruled gate for #678)

### 🔴 RED. Definition REPLACED 2026-08-13 (Alex) — read this before reading the rows.

**The gate is: the cohort calibration health sentinel is GREEN at full granularity.**

It is **not** producer health. It is **not** a combined ECE number. It is **not** a count of
green exam items. Those are the three definitions this gate has lied under, and the lie was
caught the only way it could be — by an eyeball. Alex's skeptical read of the live page on
2026-08-13 returned **COMMUNICATES (pass)** on the presentation and **the data does not survive
the audit** underneath it: defects a machine should have computed were found by a human looking
at a chart.

That is the failure. A gate whose evidence is a person remembering a webpage cannot be green,
because nothing enumerates what it did not look at. So the gate now reads a machine verdict:

> **GREEN only when EVERY cell in the cohort grid is GREEN, NOT-PROVABLE-with-a-plan, or a
> registered exception.** Any RED cell, or any NOT-PROVABLE cell without a plan, holds the gate.

Alex adjudicates cell health **never again** — his eyeball returns to taste only.

The sentinel does not exist yet, so the gate is **RED by definition, not by measurement**, and
that is the honest state: an unbuilt instrument is not a passing one. This is the same
NOT_COVERED discipline the completeness sentinel already applies — an unmeasured cell is
explicitly not-provable, never silently green.

| item | state 2026-08-13 | evidence / what's between it and green |
|---|---|---|
| **Cohort health sentinel** | 🔴 **NOT BUILT** | **THE gate.** Grid = category × source × market-shape × probability-band, granularity chosen by "could a broken subcohort hide inside this cell", not by what renders nicely. Per cell: ECE/MCE/Brier, n, and a verdict — GREEN (within the ruled ≤5pp guardrail) / RED / NOT-PROVABLE (below min-n, explicit). Reds auto-file P2 + `needs-triage` at birth with the cell's evidence attached. Its first full run's red list REPLACES all standing category worklists |
| Exceptions registry | 🔴 NOT BUILT | Ruled no-authority markets (MLB total bases, NCAAB 1H, …) live in a NAMED registry the sentinel reads. An exception is visible and cited, never implicit — an implicit exclusion is indistinguishable from a miss |
| Producer health | 🟢 RECOVERED | Fresh publish 18:16Z, 13 clean beats, ruling 009 freeze lifted with numbers. **Demoted from gate evidence to a precondition** — it was never the thing being asked |
| Settlement contamination | 🔴 COUNTING | 85 wrong-scored games found by 339S census; 339T is censusing which settled markets graded against them. Every contaminated grade gets an Alex MC before correction — never unattended |
| Sub-category charts | 🟡 SUPERSEDED | Was "survives skeptical audit + Alex eyeball". The audit happened and the eyeball is what found the warts, which is the argument for the sentinel. Folded into the sentinel row above |
| Kalshi settlement sync (#1818) | 🟢 **APPLIED 2026-08-13** | 417 stuck markets flipped attended, 100% exact match, population to **0**; `settled_by_result_only` 2,300 → 0. Becomes the sentinel's **first before/after specimen** — golf was 89% of the original population, and 11,837 golf outcomes flipped with only 29% carrying a cal_prob, so ~8,380 are newly unblocked for cal-price backfill |
| 40–50% band capture | 🔴 OPEN | Traded cohort −5.5pp over 45k outcomes, plus baseball's 50% bucket — likely ONE investigation into stale final pre-resolution price capture. Upstream of every cohort, so it runs in parallel with building the sentinel rather than behind it. Our-bug-first order: capture → linkage → grading → denominator → only then market blame |

## Gate 2 — Data completeness (added 2026-08-12; the Sox class)

| item | state | evidence / next |
|---|---|---|
| Absorption fix (#1779) | 🟡 CERTIFIED, UNMERGED | PR #1801, CI 15/15, codex C-CERT-1801 running. HARD DEADLINE: merge before Aug 16 (cross-wired BOS games) |
| Team binding (#1798) | 🟡 ENDPOINT SHIPPED | 153 miswired sides censused; repair runs post-merge via admin rail |
| Season backfill | 🟡 STAGED | 339T: 301 missing / 241 mis-keyed / 114 misdated / 85 wrong-scored, keyed by provider id, dry-run→census→apply, gated on #1801 deploy |
| Completeness sentinel (#1796) | 🔴 FILED | Needs implementation + a green streak. Closes the CLASS: "what should exist, exists" checked daily |

## Gate 3 — The six reliability classes (each needs a sentinel green streak)

| class | state | note |
|---|---|---|
| Search miss | 🟡 IMPROVING | Gold set 41/44; president + nba-champion fixed this week; scorer spec ratified (Q325 pending) |
| Unmerged duplicates | 🟡 CENSUSED | #1754 narrowed; 3,613 surplus team rows risk-tiered, 577 never-merge guardrail |
| Missing/illegible props | 🔴 OPEN | #1773 p1: iOS Discover no-probabilities + dead swipe — flagship native bug, unowned this week |
| Stale resolved-state | 🟡 MIXED | League freshness FIXED (99.6% stale → fresh, verified). New find 08-12: Masters R3 leader shows live % on a settled event (p1, filed) |
| Sub-Kalshi UX | 🟡 MOVING | Hero threshold ruled 10→5; native chart ruled; interestingness blend revived DARK pending Alex calibration eyeball |
| Meta: Alex-before-sentinel | 🔴 OPEN | Both rage-shake incidents this week reached Alex before any sentinel. #1796 + drift sentinel shrink this; green = a fortnight where no defect's first reporter is Alex |

## Gate 4 — Native readiness

| item | state | note |
|---|---|---|
| Swift 6 migration (#1775) | 🟡 SCOPED | Closed number: 15 declarations, 10 in one file; execution unscheduled |
| #1773 fix | 🔴 OPEN | Same row as Gate 3; listed twice because it blocks both |
| Submission mechanics (#678) | ⏸ PARKED | Intentionally; unblocks when Gates 1–3 green |

## Gate 5 — The Alex test

A fortnight of daily use without falling back to Kalshi, including at least
one live Sox game followed end-to-end on BainLuck. Not started; starts when
Gates 1–4 are green. This is the ship gate, and it is the same test that
found the Sox hole — which is why it works.

## What changed this week (why the trend supports landing)

Defect discovery is outpacing defect creation, measured: three programs
falsified their own staged premises and shipped the corrected fix in-session
(page queue → identity register; index → planner stats; time limit → OOM).
One rage shake became a proven mechanism, a certified fix, a season census,
and a sentinel class — in ~24 hours. League freshness, search recall, and
event probabilities (118/118 dark → 8/8 lit across seven leagues) all moved
green with production evidence. The machine that turns holes into fixes is
the launch asset; this ledger just makes its progress legible.
