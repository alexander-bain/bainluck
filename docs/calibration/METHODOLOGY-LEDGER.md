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

## Reproducing a past grade

We keep the *evidence* (prices, snapshots, resolutions), not the old verdicts. So an auditor
re-grades by checking out the sha in the entry's **Code** row and running it against the retained
evidence for that period. That is what D134 means by "the old method stays runnable" — the rule is
recoverable from version control, and the inputs it consumed are still in the database.

---

<!--
SEEDING IS INCOMPLETE. D134 asks for one entry per methodology change since ruling 009, and this
file currently carries ONE. Do not read the absence of an entry as the absence of a change.

Still to be written up (Fable's list, 2026-09-11 11:17am PT):
  * D80
  * D112 (as amended)
  * D119
  * #4745  (empty-book openings; backup table `bak_4745_empty_book_openings`)
  * #4853's fixes
  * #5141
  * the shape -> semantic recut (CU-3 / #5275), when it lands

Each needs its "what it affected" row MEASURED rather than recalled, which is why they are not
being back-filled from memory here. Whoever writes one: take the row counts from the artifact or
rebuild that accompanied the change, and say so.
-->

> **This ledger is not yet fully seeded.** It currently carries one entry. Several earlier
> methodology changes (D80, D112 as amended, D119, #4745, #4853, #5141) still need entries, and each
> needs its measured effect rather than a remembered one. See the comment above this line.

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
