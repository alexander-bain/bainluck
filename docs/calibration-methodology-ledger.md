# Calibration methodology ledger

D134 (Alex, 2026-09-11): *"Every grading/blending/calibration calculation carries a versioned METHOD
id; a METHODOLOGY LEDGER … is kept forever and published with the accuracy page … As long as we can
inform a skeptical auditor of what changes we've made to our calculations, we can't be accused of
anything nefarious if we are only trying to make the calculations better over time."*

Two ids, and they are independent:

| id | what it versions | where it lives |
|---|---|---|
| `population_version` (`q271`) | **which rows** are scored | `precompute_calibration.py` |
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

## q271 — D112, the symmetric settlement channels (2026-09-13)

**This is the item q270's own entry said the recount was not done without.** Nothing new was added to
the scope; this is the last of the five things Alex named on 2026-09-12, and with it the "one
recount" is complete on the method side.

### Applied

**D112 — lone-claim settlement is independent truth (#997).** A market with exactly ONE captured
outcome — a single Yes/No question — has no sibling whose price could be grading it, so its
`all_losers` / `clean_resolution` settlement is the venue's own answer rather than the market's price
grading its own forecast. The pair is admitted together or not at all, and the reason is measured
rather than aesthetic: `all_losers` alone realises 617/2,097 = **29.4%** against a ~50% forecast,
which is a censored sample (every row it admits was pre-selected to be a loss), while both channels
together realise 1,566/3,046 = **51.4%**. At two or more outcomes a sibling's price does grade the
row, the leakage is real again, and nothing changes.

**This is the first population bump in the series that WIDENS.** q269 and q270 both removed rows the
new method called wrong. q271 removes nothing — it admits ~3,046 rows (an upper bound; they must
still clear every other filter) that the previous curve was simply narrower for. That direction is
why q270 could publish honestly without it: their absence was a coverage gap, never a wrong number.

### Two things this queue found that change what the q270 entry said

**1. The wiring is seven sites, not eight — and four of the five "population CTEs" must NOT be
widened.** The q270 entry named "five population CTEs, the Query-11 truth census, and the
coverage-bridge rung". Measured against the rendered SQL, four of those five cannot see a one-outcome
market at all: `bundle_price_sum`'s only consumer requires `n_outcomes >= 3`, `golf_placeholder_markets`
ends in `HAVING COUNT(*) >= 2`, `mex_field_candidates` in `HAVING COUNT(*) >= 3`, and
`mex_field_divisor` reads only markets that cleared the candidates. A lone claim contributes at most
one row, so every one of those floors excludes it by construction. Widening them would have meant
adding shape joins to aggregating CTEs — ruling 125's hazard — for exactly zero published rows. They
stay shape-blind, the floors are now asserted
(`test_d112_inert_cte_cardinality_floors`), and the stated identity with `ranked_outcomes` still
holds where it is load-bearing: for every market those scans can actually see, the two predicates are
byte-identical. There was also an EIGHTH site the q270 entry did not count — the cross-venue
fair-fight scan — which is a separate surface over a different population with no shape column in
scope, and is left alone deliberately.

**2. The renderer was not safe to negate, which is the defect the negation site existed to find.**
The q270 entry correctly flagged `truth_ineligible_source` as "the one a careless sweep would miss"
because it is a `NOT IN`. Wiring it found something worse than an omission: the substrate's rendered
predicate used a bare `n_outcomes = 1`, and the shape column arrives through a LEFT JOIN, so for a
market with no shape row the expression is NULL — and `NOT NULL` is NULL, not TRUE. An
ineligible-source row would have stopped satisfying its own rung and fallen through to be
mislabelled as something else. The shape term is now `COALESCE(n, 0) = 1`, which leaves every
positive call site answering exactly as before (a `WHERE` cannot tell NULL from FALSE) and makes the
negative one correct.

### Declared, and why the declaration has two arms

q271 is the first bump written while its own predecessor had not published: q270 merged and went live
on the web at 04:48Z on 2026-09-13, but the producer is a heavy task and the heavy app had not taken
the commit, so `/calibration` was dark and the last published artifact was still `q269`. Which
artifact q271 replaces is therefore a fact about an attended redeploy, not about this code.

The two transitions are ~12pp apart — replacing `q270` the population GROWS ~0.76%; replacing `q269`
it is q270's ~12% shrink less that widening, ~11.2%. No single declaration covers both: one band
spanning them needs ±6.0, past the 5.0 maximum, and a band that wide authorises an arbitrary change,
which is the hole the declaration exists to close. So both arms are stated, each measured against its
own baseline, and the publish gate selects the one matching the artifact it actually resolved.
Nothing is averaged and nothing is guessed. This matters more than its size suggests: a wrong
declaration is not a re-run — the gate refuses, and a refusal CLEARS THE CHECKPOINT, binning every
later rebuild until another deploy, on the very page the recount exists to repair.

### Open for Alex — one reader-visible call this queue declined to make itself

`COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` is empty again, so `/calibration` goes dark for a second
rebuild (~3.3 h) while q271 builds. **It arguably need not.** That list exists to stop the page
serving an artifact whose numbers mean something other than what the page says. For q269 and q270
the outgoing artifact really did publish prices the incoming method calls wrong. A q270 artifact
holds no price q271 calls wrong — q271 only adds rows — so serving it dated, degraded and read-only
during the rollover would mislead nobody.

It is not listed anyway, because the list's stated entry bar is a proof of *methodological identity*
and q271 changes the truth allowlist, and because the constant's own docstring says it "is not a dial
to be turned down when the dark window is inconvenient" — which is precisely the situation this queue
is in. A lane widening an entry bar in its own favour, on the page it is repairing, is what that
sentence forbids. **The question for Alex is whether a WIDENING predecessor should be admitted to
that list as a class**, which would mean no dark window on any future bump that only adds rows.

---

## Earlier versions

`q267` → `q268` (2026-08-18) was a version bump that changed **no** methodology; it existed only
because a sixteen-day build tripped the growth gate, and the same commit gave the gate the
`population_predicate_fingerprint` discriminator so that could never be the reason again.
`q268` → `q269` (2026-09-01) moved the methodology — D5 dedup, D12, D13, D21, D22, RULE E — and
removed 201,508 outcomes. Both are narrated in the header comments of
`backend/app/tasks/precompute_calibration.py`, which stay the authority for their own numbers.
