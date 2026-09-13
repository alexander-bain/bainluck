# Calibration methodology ledger

D134 (Alex, 2026-09-11): *"Every grading/blending/calibration calculation carries a versioned METHOD
id; a METHODOLOGY LEDGER … is kept forever and published with the accuracy page … As long as we can
inform a skeptical auditor of what changes we've made to our calculations, we can't be accused of
anything nefarious if we are only trying to make the calculations better over time."*

Two ids, and they are independent:

| id | what it versions | where it lives |
|---|---|---|
| `population_version` (`q270`) | **which rows** are scored | `precompute_calibration.py` |
| `SCORING_POLICY_VERSION` (`m1`) | **how a cell is judged** — bars, `MIN_CELL_N`, `SIGMA_GATE` | `calibration_scoring.py` |

Entries that CHANGED a published number are in `CALIBRATION_CORRECTIONS`, served on
`/api/calibration` and rendered on the accuracy page in plain English — that is the copy an auditor
or a reader sees, and it is the primary record. **This file carries what the served log cannot: the
decisions NOT to change a calculation, and why.** A method we considered and declined is part of the
method.

---

## q270 — the one recount (2026-09-12)

Alex, 2:10PM PT: *"We've known for a while what the right way was to calculate the remaining
subcohorts that are stopping us from being done; can we just do it the right way and be done?"*
Five items were named. Two are applied in `q270`; two are declined here with their reasons; one is
sequenced behind this bump because the code dependency runs that way, and the recount is not done
until it lands.

### Applied

**1. One forecast per threshold ladder (#5305).** A lone `quantity` market whose own resolutions show
more than one winner publishes one representative rung instead of all of them. Served entry: *"A
price ladder is one forecast, not forty."*

**2. The writer bar (#5401).** The curve no longer grades a Kalshi opening that Kalshi's own writer
would have refused to record. Served entry: *"Prices nobody could have traded at."*

### Not applied — each with its reason

Two of these three are declined on the method. The third (D112) is not declined at all: it is owed,
and it is sequenced. **This section is the record of what q270 does not yet carry, so nothing in it
should be read as "the recount is finished".**

**3. Big-field normalisation for `kalshi/golf` and `kalshi/entertainment` — SUBSUMED, not exempted.**

The proposal was to divide a big field's per-event prices by their sum, because the sum ran far above
1. Measurement says the sum was not a normalisation problem: it was the fabricated openings. With the
writer bar applied, `kalshi/golf` goes 0.762 → **0.954** won-per-implied (board control 0.982) and
`kalshi/entertainment` 0.828 → 1.089. A field still inflated by its own construction could not land
next to the control after a cut that only removes rows.

Normalising anyway would have been the wrong calculation twice over. It divides a 137-leg field of
fabricated 0.95s down to ~0.007 each, so **the cell reads fixed while the page keeps publishing
prices nobody quoted** — the appearance of a repair, standing in for one. And this board already
refuses to normalise a non-partition **by name**: the mutually-exclusive normalisation of 2026-07-10
touches "only genuine single-winner partitions", and the esports-bundle entry of 2026-07-12 says a
cumulative ladder's prices "neither sum to ~1.0 (can't be normalized)". Dividing a set of independent
binaries by their sum invents a forecast nobody made. Normalisation stays where exclusivity is
**proved**.

**4. D112 symmetric settlement channels (#997) — SEQUENCED behind this bump, not exempted. The
recount is not done until it lands.**

D112 admits the lone-claim pair `all_losers` + `clean_resolution` as truth for markets with exactly
one outcome, where no sibling's price can be grading the row. Both channels are currently ineligible,
so **the present curve is not biased by their absence** — it is narrower than it could be. That is a
coverage gap, not a wrong number, which is why q270 publishing without it leaves no known-wrong price
in any cell. It is not a methodological exemption and must not be read as one.

It is not merely unbuilt. `98f75b9bc96e52091d1cb3295d1a1459cbc54e83` carries the predicate, the
`calibration_truth_eligible_sql(n_outcomes_col=…)` renderer that writes the source half and the
shape half as one unit, and the symmetry gate. CERT-2550 blocked it because the served eligibility
paths still use the shape-blind constant. Measured size: 3,046 lone-claim rows realising 51.4%
against a ~50% forecast (the loser-only half alone realises 29.4%, which is a censored sample and is
why the pair is admitted together or not at all).

**The declaration band is NOT the reason, and an earlier draft of this entry said it was.** That
draft called the widening "unmeasured" and argued it would put q270 outside its own tolerance. The
arithmetic refutes it: 3,046 rows is an *upper* bound — those rows must still clear every other q270
filter, and any Polymarket share of them does not touch a Kalshi-arm declaration at all — so the
widening moves the realised drop by at most 3,046 / 399,618 = **0.76 pp**, taking 11.68–12.33% to
10.92–11.57% against a declared 12.0 ± 5.0 (7.0–17.0). It is inside the band by an order of
magnitude, and it is *less than half* the 1.61 pp the Polymarket ladder half already carries under
this same declaration as bounded-rather-than-folded. A reason that does not survive its own
arithmetic is worse on this ledger than no reason, so it is struck rather than quietly edited.

**The real constraint is a code dependency, and it runs the other way.** The lone-claim predicate
needs a per-market outcome count in scope at the served eligibility sites, and the main population
scan acquires one only *with* q270: the `market_result_shape` join that #5305's ladder arm adds
(`mrs_lad.n_outcomes`) does not exist on master — zero occurrences — so on master there is nothing
for the shape half to read. Wiring D112 first would mean building the shape join twice, and building
it concurrently would stack two open change sets on one frozen producer, which the lane rules
forbid. So the order is forced, not chosen: q270 lands, then D112 wires the eligibility sites onto
the join q270 already put there. There are seven, and they are not all the same shape: five
population CTEs, the Query-11 truth census, and — the one a careless sweep would miss — the
coverage-bridge rung `truth_ineligible_source`, which is a **negation** (`NOT IN`). Widening the
five without it would leave the bridge telling a reader that a row the curve now grades has an
ineligible truth source. The second dark window (~3.3 h) is inside what Alex priced ("dark or stale
for as long as it takes is fine").

**5. `MIN_CELL_N` on raw `n` vs `effective_n` (#5430 / #5431) — DECLINED. Raw `n` is correct, and
the question is decidable from the board's own contract without measuring anything.**

An earlier draft of this entry called this OPEN and unmeasured, on the assumption that choosing
between the two floors needs a fold. It does not. The two reasons are already written into the code
this entry is about.

*The floor is a scope-matching device, not a noise control.* `MIN_CELL_N = 1000` is pinned to the
payload's own disclosure floor `min_category_outcomes` so that "the score's scope and the page's
scope are the same set" — and the scorecard already publishes `floor_matches_payload` on the wire
for the sole purpose of shouting if the two ever drift apart, because "if these ever disagree the
category cut and the cell cut are scoring different populations". Moving the score's floor to
`effective_n` while the page keeps disclosing on raw `n` would not be a refinement; it would
deliberately break the identity the board ships a flag to protect, and the scorecard would start
grading a set the reader cannot see.

*The clustering correction is already applied, once, in the right place.* `effective_n` is not an
independent measurement — it is `n / variance_ratio_vs_board`, and that ratio is
`(se_bootstrap / se_row)²`, derived from the very standard error `sigma_measured` already uses.
Correlation structure therefore already decides whether a cell is QUEUED, through `SIGMA_GATE` on
the measured SE. A floor on `effective_n` would apply the same correction a second time, at a stage
whose job is a different question.

*And it would not even be conservative.* `variance_ratio_vs_board` can fall below 1 — a cell whose
bootstrap SE is tighter than the row formula's — so `effective_n` can exceed `n`. Such a floor would
not merely hide small cells more aggressively; it would also admit cells the page declines to
disclose. Both directions are wrong, for the same reason: the floor's job is the page's scope.

What is genuinely open is the floor's **value**, not its quantity, and that is not this board's
ruling to make: 1,000 follows `min_category_outcomes`, which is tunable at runtime through the Redis
key `calibration:min_category_outcomes` with no deploy. Move the page's disclosure floor and the
score follows it by construction.

---

## Earlier versions

`q267` → `q268` (2026-08-18) was a version bump that changed **no** methodology; it existed only
because a sixteen-day build tripped the growth gate, and the same commit gave the gate the
`population_predicate_fingerprint` discriminator so that could never be the reason again.
`q268` → `q269` (2026-09-01) moved the methodology — D5 dedup, D12, D13, D21, D22, RULE E — and
removed 201,508 outcomes. Both are narrated in the header comments of
`backend/app/tasks/precompute_calibration.py`, which stay the authority for their own numbers.
