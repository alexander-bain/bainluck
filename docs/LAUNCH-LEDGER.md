# LAUNCH-READINESS LEDGER
# The answer to "will this ever land," maintained as a list instead of a feeling.
# Refresh: every Monday scoreboard session updates the State column; any lane
# that moves a gate updates its row in the same change. Lives at
# docs/LAUNCH-LEDGER.md. v1 seeded by Fable 2026-08-12 (evening).
# Refreshed 2026-08-17 (queue 359, lane1) against this week's measured evidence.

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
| **Cohort health sentinel** | 🟡 **BUILT / FILING** (was 🔴 NOT BUILT) | **THE gate, and it now exists.** Grid = category × source × market-shape × probability-band, granularity chosen by "could a broken subcohort hide inside this cell", not by what renders nicely. Per cell: ECE/MCE/Brier, n, and a verdict — GREEN (within the ruled ≤5pp guardrail) / RED / NOT-PROVABLE (below min-n, explicit). Reds auto-file P2 + `needs-triage` at birth with the cell's evidence attached. **The Gate-1 red list is now MACHINE-ENUMERATED** — it replaces all standing category worklists, and Alex's eyeball is formally off cell adjudication. Green needs a clean run at full granularity, which is now a measurement rather than a build |
| Exceptions registry | 🔴 NOT BUILT | Ruled no-authority markets (MLB total bases, NCAAB 1H, …) live in a NAMED registry the sentinel reads. An exception is visible and cited, never implicit — an implicit exclusion is indistinguishable from a miss. **Now the sentinel's binding dependency**: every cell it cannot except, it must red |
| Producer health | 🔴 **STOPPED, AND NOW ON A CLOCK — #1680 / #1977** (was 🟢 RECOVERED) | **Re-measured 2026-08-18 (CAL-P071); the previous wording was stale in the reassuring direction.** It published once more, on **2026-08-14T00:16:08Z**, and nothing since: `successes_24h 0`, `consecutive_failures 108`, terminal `cancelled` (*"futures generation incomplete — units banked, nothing published"*). **The precondition now has a DEADLINE**: that artifact ages out of `SERVE_MAX_AGE_S` at **`2026-08-21T00:16:07Z`**, after which nothing is servable at any tier. The first q268 build has banked **3 of 128** units; its last three beats banked 2, 1, 0, and an out-of-band beat banked 0 — so it is **stalled, not slow**, and more beats do not help. **The instrument said 13 beats when the truth was 125**, because `unit_projection` divided by the whole-beat ceiling instead of the phase's own budget (fixed, CAL-P071). Age-based staleness signalling DID land and is working — the page reads `degraded` with a dated provenance rather than pretending — so the silent half of this row is closed; what remains is the build itself. **Gate 0's equivalence read stays ARMED and unrun**: it needs a moved `generated_at`, and that is now blocked on the budget-share decision on #1977, not on time |
| Settlement contamination | 🔴 COUNTING | 85 wrong-scored games found by 339S census; 339T is censusing which settled markets graded against them. Every contaminated grade gets an Alex MC before correction — never unattended |
| Sub-category charts | 🟡 SUPERSEDED | Was "survives skeptical audit + Alex eyeball". The audit happened and the eyeball is what found the warts, which is the argument for the sentinel. Folded into the sentinel row above |
| Kalshi settlement sync (#1818) | 🟢 **APPLIED 2026-08-13** | 417 stuck markets flipped attended, 100% exact match, population to **0**; `settled_by_result_only` 2,300 → 0. Becomes the sentinel's **first before/after specimen** — golf was 89% of the original population, and 11,837 golf outcomes flipped with only 29% carrying a cal_prob, so ~8,380 are newly unblocked for cal-price backfill |
| 40–50% band capture | 🔴 OPEN | Traded cohort −5.5pp over 45k outcomes, plus baseball's 50% bucket — likely ONE investigation into stale final pre-resolution price capture. Upstream of every cohort, so it runs in parallel with building the sentinel rather than behind it. Our-bug-first order: capture → linkage → grading → denominator → only then market blame |

## Gate 2 — Data completeness (added 2026-08-12; the Sox class)

| item | state | evidence / next |
|---|---|---|
| Absorption fix (#1779) | 🟢 **CERTIFIED GREEN, STILL UNMERGED** | **`C-CERT-1801-R7` returned GREEN 2026-08-17** at `lane1/q352` @ `0d815942` (PR **#1864**): both R6 blockers dead, fourth rail refuses anchored/distinct-participant rows without going vacuous, census sees both destructive spellings, Sox 40/40 replay clean, **zero findings**. Re-derived against current master `3fce7867` — conflict-free, manifest overlap none. **The technical gate is discharged; only the merge remains.** Deadline slipped past Aug 16 on scheduling, not on the gate (Alex ruling, 08-17) |
| Team binding (#1798) | 🟡 ENDPOINT SHIPPED | 153 miswired sides censused; repair runs post-merge via admin rail |
| Season backfill | 🟡 STAGED, GATE NOW DISCHARGEABLE | 339T: 301 missing / 241 mis-keyed / 114 misdated / 85 wrong-scored, keyed by provider id, dry-run→census→apply. Gate reads "#1801-R5 merged AND deployed (ruling 048)". With R7 GREEN the blocker is **one Integrator merge of #1864 + #1806**, then deploy. Held **9 windows** (339T item 4) and **6** (341) |
| Completeness sentinel (#1796) | 🔴 FILED | Needs implementation + a green streak. Closes the CLASS: "what should exist, exists" checked daily |
| Cliff drain (#1884 → #1892) | 🟡 **#1884 CLOSED, #1892 OPEN** | The cold-watermark asyncpg DataError is fixed and #1884 is closed. Its successor #1892 is the **cap** — and queue 359's re-measurement overturns the alarm: the 74–86d at-risk band is **EMPTY (0 rows)**, so cliff loss is **~0/day**, not the inherited ~1,100/day. What is real is a 15,712-row residue of the drain's own empty answers that nothing revisits. Shipped: an at-risk second pass (2.6× margin) and a **convergence** verdict replacing a liveness-only reading |

## Gate 3 — The six reliability classes (each needs a sentinel green streak)

| class | state | note |
|---|---|---|
| Search miss | 🟡 IMPROVING | Gold set 41/44; president + nba-champion fixed this week; scorer spec ratified (Q325 pending) |
| Unmerged duplicates | 🟡 CENSUSED | #1754 narrowed; 3,613 surplus team rows risk-tiered, 577 never-merge guardrail |
| Missing/illegible props | 🟡 **FIXED, PHONE-VERIFY OWED** | #1773 p1 (iOS Discover no-probabilities + dead swipe) is **fixed in code**; what remains is Alex confirming it on an actual phone. Deliberately NOT green — a native fix with no device read is exactly the "code shipped ≠ verified" closure this ledger refuses. Still listed in Gate 4 |
| Stale resolved-state | 🟡 MIXED | League freshness FIXED (99.6% stale → fresh, verified). New find 08-12: Masters R3 leader shows live % on a settled event (p1, filed) |
| Sub-Kalshi UX | 🟡 MOVING | Hero threshold ruled 10→5; native chart ruled; interestingness blend revived DARK pending Alex calibration eyeball |
| Meta: Alex-before-sentinel | 🔴 OPEN | Both rage-shake incidents this week reached Alex before any sentinel. #1796 + drift sentinel shrink this; green = a fortnight where no defect's first reporter is Alex |

## Gate 4 — Native readiness

| item | state | note |
|---|---|---|
| Swift 6 migration (#1775) | 🟡 SCOPED | Closed number: 15 declarations, 10 in one file; execution unscheduled |
| #1773 fix | 🟡 FIXED, PHONE-VERIFY OWED | Same row as Gate 3; listed twice because it blocks both. **Alex owes one device read** — that is the whole remaining distance |
| Submission mechanics (#678) | ⏸ PARKED | Intentionally; unblocks when Gates 1–3 green |

## Gate 5 — The Alex test

A fortnight of daily use without falling back to Kalshi, including at least
one live Sox game followed end-to-end on BainLuck. Not started; starts when
Gates 1–4 are green. This is the ship gate, and it is the same test that
found the Sox hole — which is why it works.

## Standing certifications (source: `.claude/handoff/CODEX-REPORT.md`, runs of 2026-08-17)

A cert is the adversarial read on work a lane says is done. Two printed today, and they point
opposite ways — which is the point of running them.

| cert | verdict | what it means for the gates |
|---|---|---|
| **`C-CERT-1801-R7`** | 🟢 **GREEN — zero findings** | Certifies `lane1/q352` @ `0d815942` (PR #1864), **re-derived against current master `3fce7867`** rather than trusting the dated queue header — synthetic merge tree conflict-free, manifest overlap none. Event-9001 fourth-rail specimen refuses with the row surviving; deletion proven to require the full conjunction (no authoritative identity **and** no distinct participant IDs) with an executable converse control; both hostile census spellings (raw SQL and ORM `session.delete`) detected; false-positive Redis control clean; all four merging rails found; Sox 40/40 replay clean. **Gate 2's absorption row is technically discharged. The only thing between it and green is an Integrator merge.** |
| **`C-CERT-SENTRY-R3`** | 🔴 **BLOCK — 2× P1** | Certifies the **deployed** policy (q351 merged as `426d4e84`, Heroku v3823), not a stale branch. (1) **The budget forgets that every release resets every per-process allowance** — the reserve prices one stable four-child pool for a whole day, but one PASS-tier signature across four children over 12 releases executes **48** allowances, not 4; reset-aware total **184.25/day against a 164.47/day budget, 19.78 over**. All 161 focused tests pass because the release test and the reserve test never meet in one assertion. (2) **#1894 phase-two blindness survives quota restoration by construction** — an executable `IntegrityError` specimen fed 64,040× through the merged callable yields **1 passed / 64,039 `before_send` discards**. Quota and filter are **serial gates: fixing either alone restores nothing.** Queue 359's priority insert owns both; arms `C-CERT-SENTRY-R4`. **Deadline 2026-08-20** (quota reset) |

## What changed this week (why the trend supports landing)

Defect discovery is outpacing defect creation, measured: three programs
falsified their own staged premises and shipped the corrected fix in-session
(page queue → identity register; index → planner stats; time limit → OOM).
One rage shake became a proven mechanism, a certified fix, a season census,
and a sentinel class — in ~24 hours. League freshness, search recall, and
event probabilities (118/118 dark → 8/8 lit across seven leagues) all moved
green with production evidence. The machine that turns holes into fixes is
the launch asset; this ledger just makes its progress legible.

**Week of 2026-08-17.** The honest headline is that **the biggest movement is
blocked on merging, not on building**. `C-CERT-1801-R7` came back GREEN with
zero findings, so Gate 2's absorption row is technically finished — yet two
Gate-2 rows have now been HELD **nine** and **six** windows on a gate that
reads "merged AND deployed", and nothing in a working lane can discharge it
(ruling 017). Alex ruled 08-17 that the weekend gap was **scheduling, not the
gate**, and that the Integrator's next action is merging #1864 + #1806.

Two things got worse, and both got worse *silently*, which is the pattern
worth naming: the **calibration producer stopped on 08-02** and served a
15-day-old snapshot without a 503 (#1680), and **Sentry has accepted zero
error events since 07-29** while reporting nothing wrong. In both cases the
instrument's failure mode was indistinguishable from health — a stopped
producer reads like a fresh one, a muted channel reads like a quiet one.
Alex's response was to make each say so out loud: `/health` now **hard-fails**
when `error/accepted == 0` over 24h while transactions accept, and the
producer gains age-based staleness signaling. That is the same correction the
Gate-1 rewrite made in July, applied twice more.

Against that, two alarms got **smaller under measurement**, which counts as
progress of a less satisfying kind: the cliff clock (#1892) turned out not to
be running at all — the at-risk band is empty — and #1586's named page-cap
mechanism turned out to be an **instrument artifact**, with the real cause
(97.4% of fetched Kalshi events carrying zero markets) sitting one stage
upstream of the cap everyone wanted to raise. Both were caught by re-measuring
an inherited number instead of inheriting it.
