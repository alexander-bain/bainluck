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
Five items were named. Two are applied in `q270`; three are resolved here.

### Applied

**1. One forecast per threshold ladder (#5305).** A lone `quantity` market whose own resolutions show
more than one winner publishes one representative rung instead of all of them. Served entry: *"A
price ladder is one forecast, not forty."*

**2. The writer bar (#5401).** The curve no longer grades a Kalshi opening that Kalshi's own writer
would have refused to record. Served entry: *"Prices nobody could have traded at."*

### Declined, with the reason

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

**4. D112 symmetric settlement channels (#997) — DEFERRED to the next bump, named and sized.**

D112 admits the lone-claim pair `all_losers` + `clean_resolution` as truth for markets with exactly
one outcome, where no sibling's price can be grading the row. Both channels are currently ineligible,
so **the present curve is not biased by their absence** — it is narrower than it could be. That is a
coverage gap, not a wrong number, and it is why deferring it leaves no known-wrong price in any cell.

It is not merely unbuilt. `98f75b9bc96e52091d1cb3295d1a1459cbc54e83` carries the predicate and its
symmetry gate; CERT-2550 blocked it because the served eligibility paths still use the shape-blind
constant, and the repair it named — wire `n_outcomes` into every served eligibility site — is an edit
to the frozen producer that moves the population again. Measured size: 3,046 lone-claim rows
realising 51.4% against a ~50% forecast (the loser-only half alone realises 29.4%, which is a
censored sample and is why the pair is admitted together or not at all).

It is deferred rather than bundled for one reason, stated plainly: a version declaration that misses
its realised move by more than its tolerance is not a re-run — `evaluate_publish` refuses, and a
refusal clears the checkpoint, so every later rebuild is binned until another deploy corrects it.
Adding a *widening* of unmeasured size to two measured *shrinks*, hours before the deploy, would put
the whole recount on a number nobody had folded. The second dark window costs ~3.3 h of rebuild,
which Alex has already priced as acceptable ("dark or stale for as long as it takes is fine"). The
declaration being right is worth more than the window.

**5. `MIN_CELL_N` on raw `n` vs `effective_n` (#5430 / #5431) — OPEN, unmeasured.**

The display floor is applied to raw `n`. Whether it should be applied to the cluster-adjusted
`effective_n` changes which cells are scored at all, in both directions, and no fold of that move
exists. It is not a known-wrong price and it is not deferred for convenience — nobody has measured
it. It is named here so its absence is on the record rather than in a handoff.

---

## Earlier versions

`q267` → `q268` (2026-08-18) was a version bump that changed **no** methodology; it existed only
because a sixteen-day build tripped the growth gate, and the same commit gave the gate the
`population_predicate_fingerprint` discriminator so that could never be the reason again.
`q268` → `q269` (2026-09-01) moved the methodology — D5 dedup, D12, D13, D21, D22, RULE E — and
removed 201,508 outcomes. Both are narrated in the header comments of
`backend/app/tasks/precompute_calibration.py`, which stay the authority for their own numbers.
