# How we grade, and what changed

**This file is the human-readable history of the accuracy page's METHOD — not of its numbers.**

Ruling **D134** (Alex, 2026-09-11): grades are corrected *in place* under the best current method.
We do **not** keep old grade values. What we keep is the METHODOLOGY history — so that anyone can
read what rule was in force on a given date, and why it changed.

That is a deliberate trade, and this file is the half that makes it honest. Storing old grades would
let you *see* a previous verdict; storing the method plus the retained evidence lets you *reproduce*
one, which is strictly stronger — and it means a page can never quietly show two numbers computed
two different ways.

## How to read an entry

Each entry is one methodology change, newest first:

* **What changed** — in plain English, for a reader who does not know our internals.
* **Why** — the defect or ruling that forced it.
* **Ruled by** — Alex, a numbered ruling, or a review.
* **Code** — the merge sha, so the exact rule is recoverable.
* **Population version** — the `q…` label the accuracy page carries while this rule is in force.
* **What it affected** — row counts by cell, measured, not estimated.

A `CERT-####` id is the reference number of the independent review a change passed before it went
live; it is here so the review is findable, and nothing in an entry depends on knowing what one is.

## Reproducing a past grade

We keep the *evidence* (prices, snapshots, resolutions), not the old verdicts. So an auditor
re-grades by checking out the sha in the entry's **Code** row and running it against the retained
evidence for that period. That is what D134 means by "the old method stays runnable" — the rule is
recoverable from version control, and the inputs it consumed are still in the database.

---

<!--
SEEDING IS INCOMPLETE. D134 asks for one entry per methodology change since ruling 009, and this
file currently carries ONE. Do not read the absence of an entry as the absence of a change.

Fable's list, 2026-09-11 11:17am PT, and where each stands after CAL-P1113's pass:
  * D80    -> written up, under "Execution changes"; effect measured (the 17-piece beat, refuted).
  * D112   -> NOT written up, and deliberately: it is not on master. See "Not in force" below.
  * D119   -> written up, under "Execution changes"; effect measured (two post-release beats).
  * #4745  -> written up as a grading-method entry; effect measured (34,615 rows).
  * #4853  -> still open (it is a ship-ORDER issue, not itself one methodology change). Its
              constituent fixes get entries as they land; D112 is one of them.
  * #5141  -> written up (PR #5141 = issue #5085), under "Execution changes". Its effect row is
              PENDING: CERT-2596 owes a post-deploy beat >5 units and no beat has completed since.
  * CU-3 / #5275 (the shape -> semantic recut) -> not landed.

Each needs its "what it affected" row MEASURED rather than recalled, which is why they are not
being back-filled from memory here. Whoever writes one: take the row counts from the artifact or
rebuild that accompanied the change, and say so.
-->

> **This ledger is seeded but not complete.** It carries every methodology change this lane can
> measure as of 2026-09-11. What is knowingly missing is named at the foot of the file, under "Not
> in force, or not yet measured". Do not read the absence of an entry as the absence of a change.

---

## 2026-09-11 — ten sportsbooks quoting one match are not ten forecasts

**Population version:** `q269` (unchanged — this changes no forecast, only the error bar around a
group of them) · **Code:** _pending merge_ (PR #5322) · **Issue:** #5305, the sportsbook half
**Ruled by:** the standing calibration-truth bar, applying D62 (an error bar decides whether a cell
is on the repair queue); no separate Alex ruling required.

**What changed.** Nothing about how a grade is computed. What changed is how confident we say we
are about a *group* of grades — and that decides which groups go on the repair list a reader never
sees but which drives everything we fix. For the sportsbook curves, one tennis match is quoted by
about ten sportsbooks, so it lands in the data as roughly ten rows. Treating those as ten
independent opinions makes our error bar about three times too small, and a too-small error bar
declares a problem "established" when the data cannot establish it. We already had the remedy built
— a method that measures the real replication instead of assuming it away — and it simply had not
been applied to these two groups. This entry is a **coverage** change, not a new rule.

**What it affected.** Measured, not estimated, with
`scripts/calibration_bookmaker_cell_fold.py --grain game_bucket --sigma`; both folds reproduce the
published error figure exactly (6.53 vs 6.53, 10.19 vs 10.19), so this measures the real pipeline
and not a re-implementation of it:

| group | rows | matches | quotes per match | published error | error bar before | error bar measured | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| men's US Open (sportsbooks) | 1,306 | 124 | 10.53x | 6.53pp | 2.91 | **1.57** | no longer established — leaves the repair queue |
| women's US Open (sportsbooks) | 1,325 | 126 | 10.52x | 10.19pp | 5.60 | **3.08** | still established — stays, and is a real defect |

Served effect, measured by rescoring the live payload with the new ledger: repair queue **11 → 10**
groups, and the scorecard's "groups at the bar" needle **40 → 41 of 51**.

**Read that needle move correctly, because it is not an improvement.** "Groups at the bar" is
defined as *material minus queued* — that is, "not on the repair queue" — so it bundles genuinely
passing groups together with groups that are over the bar but can no longer be established. The
men's US Open error is still 6.53pp against a 2.5pp bar. Nothing about that curve got better; we
stopped claiming we could prove it from 124 matches.

**Why.** Of the eight sportsbook groups measured this way to date, **eight of eight** had their
error bar cut (by 1.7x to 3.3x) and **five of eight** came off the repair queue. A rule that mis-sizes the error bar
in one direction, on every group of one whole source, is not a rounding matter — it was routing
this lane's work.

**Still owed on this entry.** The 40 → 41 claim is measured locally against the live payload; it is
proved on production only when the deployed scorecard reads `sigma_overlay.ledger_cells: 22`. The
ledger is read when the scorecard is computed, so the number moves on the next publish, not at
deploy.

---

## 2026-09-11 — a threshold ladder is one forecast, not forty

**Population version:** `q270` (from `q269`) · **Code:** _pending merge_ · **Issue:** #5305
**Ruled by:** the standing calibration-truth bar; no separate Alex ruling required.

**What changed.** Some markets ask one question by listing many rungs of the same number — Kalshi's
"Price of NVIDIA A100 compute by Apr 30" is a single market carrying forty outcomes, "Above $0.77"
through "Above $1.15". Those forty are nested readings of one number: if the price ends above $1.15
then it is also above $1.14, and so on. We were counting each rung as its own forecast, so one
question contributed roughly thirty correlated predictions to the accuracy score — and because
thirty-eight of that specimen's forty rungs came true while their average quoted price was about
0.44, the effect was not merely a bigger sample, it was a biased one.

From this change, a ladder like that contributes **one** forecast: the rung nearest 50%, which is the
most informative one, chosen by the same rule every other single-question market already uses.

**What did NOT change, and this is the load-bearing part.** A market that lists *disjoint* bins —
"peaks at #1", "#2-5", "#6-10" — is a genuine distribution: exactly one comes true and the prices sum
to about 1.0. Every one of those bins is still its own forecast. The two kinds look identical from the
market's shape label alone, so the rule keys on the outcomes' own resolutions: only a market that
resolved **more than one** outcome true is treated as a ladder. Measured before shipping, in the cells
this affects: Kalshi entertainment holds 507 ladders but **651** single-winner bin markets, and
collapsing on shape alone would have deleted all 651 — real, well-formed data.

**Why.** One question read forty times is not forty forecasts, and scoring it as forty made the
affected cells' accuracy figures mean something other than what the page says they mean.

**What it affected.** _Pending the measured rebuild._ Population sized in advance: Kalshi holds 19,097
ladder-shaped markets across 282,870 outcomes; Polymarket weather 8,527 / 88,957 and economics
1,632 / 13,923. Polymarket's large sports categories are two-outcome over/unders and are untouched.
The per-cell row counts and the exact published-population drop go here when the first rebuild under
`q270` completes — this row is not filled in from an estimate.

**Expected consequence, stated plainly because it is not an improvement everywhere.** A cell needs
1,000 published forecasts to be scored at all. Kalshi tech currently shows a score computed on 1,578
rows that come from only about 113 separate questions; once those collapse it will likely fall below
the threshold and **stop showing a score**. That is the correct outcome — it never had enough separate
questions to earn one — but it should be read as a cell becoming honest, not as a cell improving.

---

## 2026-09-10 — a lone ask on an empty book is not a price

**Population version:** `q269` · **Code:** `e0b8360b` (the reader) and `5c717cc5` (the guard and the
repair) · **Issue:** #4745 (closed 2026-09-11)
**Ruled by:** the standing calibration-truth bar, with the historical data repair applied under
D51(b) (backup first, one-command undo).

**What changed.** The accuracy page grades a forecast against the price we recorded when the market
opened. For a lot of Kalshi markets that "opening price" was not a price at all. If nobody had bid
anything and a single seller had left an offer at 98¢, we wrote down 98% — a number no one was
willing to pay a cent for. From this change, a lone offer on an empty book is not admitted as an
opening price, in the reducer that writes it and in the promotion step that could re-introduce it.

**What it affected.** Measured on the retained rows, not estimated.

*The symptom, before.* Sampling every resolved Kalshi leg 1-in-211 and reading each leg's earliest
recorded book:

| book shape when we recorded it | legs | price we published | how often it came true |
|---|---:|---:|---:|
| lone **offer**, nobody bidding, no trade | 659 | 0.369 | **6.2%** |
| lone **bid**, offer at 1.00 | 189 | 0.949 | **93.7%** |
| tight book | 872 | 0.341 | 33.3% |
| wide book, both sides quoted | 766 | 0.445 | 40.2% |

A lone bid grades almost perfectly. A lone offer does not, and the gap is the defect — not the
sport, not the market type. It was never a golf problem: at a published price of 0.98 or better,
hockey came true 24.9% of the time (4,575 legs), entertainment 47.1% (4,882), while tennis came true
98.6% and esports 99.5% at the same published price.

*The repair.* **34,615 rows** withdrawn from the curve, applied 2026-09-10 23:00:33Z → 23:06:44Z,
every one of them retained in `bak_4745_empty_book_openings` (verified intact 2026-09-11 10:26Z).
Undo is one command: `POST /api/admin/repairs/kalshi-empty-book-openings-restore?apply=true`.
**Nobody drops that table** — it is the only copy of what the page used to say.

*Confirmed gone.* The three-arm cohort instrument, run 2026-09-11 10:23:12Z over a 1-in-100 sample,
returns `sampled=0`. Against 34,615 repaired rows an unrepaired population would have put roughly
346 rows in that sample.

*Downstream, and worth knowing.* 6,309 of the withdrawn rows were hockey, which is most of why the
next full rebuild is predicted to fail its own publish gate on that cell (19,250 → ~12,953, −32.7%
against a 20% limit) — September has no NHL to replace them. Tracked as #5019. A correct repair can
shrink a cell below the size the gate will publish; that is the gate working, not the repair failing.

**Why.** ~16,960 reader-visible legs were published at a mean 0.904 and came true 13.1%. That is
not a small bias in a corner of the page; it is the page asserting near-certainty about things that
mostly did not happen.

---

# Execution changes that moved what was published

These did not change how a forecast is graded. They changed how the page's hourly rebuild runs —
which changes how fresh the published numbers are, and in one case invalidated the banked work and
restarted the population. A reader who noticed the page's numbers jump or stall on these dates is
looking at one of these, not at a grading change.

## 2026-09-10 — each piece of the rebuild scans only its own slot

**Code:** `da97697e` (#997, D119) · **Ruled by:** Alex, D119 = A — a scoped unlock of the frozen
rebuild file, plan reviewed first.

**What changed.** The rebuild walks the population in pieces. Each piece was scanning the whole
table and discarding what was not its own; now it scans only its own slot.

**What it affected.** Measured on the two post-release beats, `unit_ms_mean_completed` **69,015** and
**103,002** against a pre-release band of n=20, mean 105,682, sd 14,492 — a mean of **86,009**, which
passes the mean-of-2 criterion (88,825) though not the stricter prescribed one. So: a **real
speedup, materially smaller than the commit message claimed** (it predicted 8,700–45,200 ms/unit;
neither landed). Confound stated: the pre-release band was measured on pieces ~30–80 while both
post-release beats computed pieces 1–10 of a fresh generation.

**Throughput did not move** — still exactly 5 pieces per beat — because the *worst* piece sizes the
window check while the *mean* sizes the projection. This made pieces cheaper without making the
rebuild finish sooner, which is the honest way to read it.

**It also reset the bank, correctly: 80 pieces → 5.** The change rewrote one of the two functions
whose text is hashed into the staged cursor's fingerprint, so every carried piece was legitimately
invalidated. Not avoidable for that change, and not a defect.

## 2026-09-11 — the rebuild re-plans every piece, so the sixth stops falling off a cliff

**Code:** `0a17a6ff` (#5085, PR #5141, CERT-2596) · **Ruled by:** review; no Alex ruling required.
Population fingerprint `cf03093406ab564ae496b3d2ae8cc86e` preserved, so the bank survived.

**What changed.** Postgres was re-using one query plan across pieces and switching to a generic plan
after the fifth, which is why every beat completed exactly five pieces and then crawled. Each piece
now forces its own plan inside its own transaction.

**What it affected.** _Pending._ The review that approved it (CERT-2596) required a proof from
production — one completed beat finishing more than five pieces — and no beat has completed since the merge
(2026-09-11 08:34Z) that could supply it. The number goes here when a beat survives; it is not being
filled in from the expectation.

## 2026-09-06 — the rebuild's piece count may only ship at a size production has watched finish

**Code:** `5911b589` (#3536, PR #3591, review CERT-2093), restoring the piece count that the
preceding change (review CERT-2080) had cut · **Ruled by:** D80, where it is one half of an open
question that is still Alex's.

**What changed.** The hourly rebuild had been cut from 128 pieces to 17, on the reasoning that fewer,
larger pieces pay the fixed per-piece setup cost fewer times. Production refuted it on the first
clean beat and it was restored to 128, with a test that a piece count may only ship at a size
production has been watched completing.

**What it affected.** Measured on that beat (2026-09-06 15:15Z, with master held quiet 15:12–15:42Z
so nothing else could be blamed): the beat ran its full **1,350,702 ms**, banked
`units_completed_this_beat: 0`, and stopped on `window_stop: unit_too_large`. At 17 pieces each piece
was too big to finish inside the hour, so the rebuild banked nothing at all — strictly worse than the
slow-but-progressing 128.

**Why it is in this file.** It is the clearest case of the trade this ledger exists to record: no
piece count meets the freshness target, so the page's staleness is a property of the machine, not of
the method. D80 (a scoped unlock of the frozen file so each piece reads its own share, versus a
separate machine for the rebuild) remains open and remains Alex's.

---

# Not in force, or not yet measured

* **D112 — the losing days back in** (lone-claim markets admit both settlement channels). Ruled by
  Alex and amended 2026-09-10, built on `98f75b9b` (PR #4927), **not on master** — its review
  (CERT-2550) did not pass it, and it reads `diverged` against master at 2026-09-11 19:26Z. Its
  measurement exists and is large — the
  literal wording admits only one channel and yields 617/2,097 = 29.4% against a ~50% forecast, while
  both channels give 1,566/3,046 = **51.4%**, the coin flip — but a ledger entry asserts a rule that
  was **in force**, and this one never has been. It gets its entry the day it lands.
* **#4853** is a ship-order issue, not a single methodology change; its constituent fixes are entered
  here as they land.
* **CU-3 / #5275**, the shape → semantic recut, has not landed.
