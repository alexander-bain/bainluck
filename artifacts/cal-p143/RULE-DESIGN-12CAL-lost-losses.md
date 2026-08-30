# 12-CAL / D13 — the lost-losses repair, PRE-BUILT

**Status: built, verified, NOT applied.** Ruling 009 freezes
`backend/app/tasks/precompute_calibration.py`; nothing in this session wrote to it
(`git diff backend/` is empty, the file's md5 is unchanged). Answering D13 "yes" is now
`bash artifacts/cal-p143/land-12cal.sh` plus a gate run, not a design session.

**TL;DR.** The repair is two conjuncts in one CTE. The population it restores is
100% losses, so it makes the published headline **worse** — that is the whole reason
it is Alex's call and not a lane's. Two things this pre-build found that the ask did
not know:

1. 🔴 **Landing 12-CAL discards the staged futures bank.** `_calibration_population_ctes`
   is hashed into `_main_input_fingerprint`, and a fingerprint change is
   `REASON_INPUT_FINGERPRINT` — the code's own words: *"THE one that fires in practice
   ... costs every banked unit."* The next ~10 beats become full-rebuild beats, which is
   precisely the condition under which the class-B diagnostics timeout kills a publish
   (calibration-912's measurement: at the failed beat the rebuild took 6 units and left
   29 s of window; either side it took 4–5 and left 283–396 s). **So D13 and D22 are
   ordered: land D22 first, or landing D13 spends the next freeze window on itself.**
2. 🔴 **The restored class is invisible to both rails that police fabricated losses**,
   because both require `n_outcomes >= 2` — see §4. It is a bounded, nameable hazard,
   not a blocker, and the bound is stated rather than hand-waved.

---

## 1. What 12-CAL is, in one paragraph

Kalshi sells standalone yes/no claims. When one comes true, the calibration page shows it
as a forecast that was right. **When it doesn't come true, the page drops it** — not for
want of data: the exchange told us, we stored it, and the row sits graded a loss with the
exchange named as the source. `clean_vms` filters virtual markets on `has_winner >= 1`, and
`has_winner` is counted over the VIRTUAL MARKET, so a grouped market is carried by any
winner in its group while a **lone claim** — one market, one captured outcome, ungrouped —
has nobody to carry it and publishes if and only if it won.

Measured by CAL-P122 on `kalshi/entertainment`: **432 authoritative graded losses dropped,
395 winners kept** — a class the page reports as 100% correct at an average price of 0.59.

## 2. The repair

`artifacts/cal-p143/12cal-lost-losses.patch` — validated with `git apply --check`, exit 0.

```sql
clean_vms AS (
    SELECT * FROM vm_stats
    WHERE eligible >= 1
      AND (
            has_winner >= 1
         OR (market_count = 1 AND total_outcomes = 1
             AND graded >= 1)
      )
),
```

with one new column in `vm_stats`:

```sql
COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS graded,
```

**Why three conjuncts and not "delete the gate".** Deleting `has_winner >= 1` outright
would admit every virtual market that graded nobody — Queue 299 rung 1's UNKNOWN-truth
class, 26,627 outcomes over 1,894 markets by the published census's own count. The arm is
written so the repair **defers to rung 1** rather than replacing it: a ≥2-outcome vm that
graded nobody still fails this predicate, and `no_winner_markets` still removes it
downstream. Each conjunct has a named failure mode, and the guard suite pins all three:

| conjunct | what dropping it would admit |
|---|---|
| `market_count = 1` | grouped virtual markets whose winner we simply failed to capture |
| `total_outcomes = 1` | multi-outcome captures that graded nobody — rung 1's class |
| `graded >= 1` | rows nothing ever graded, published as confident losses |

**`graded` is not the complement of `has_winner`.** `is_winner` is nullable with a False
default, so "not a winner" spans a graded loss and a row nothing ever wrote (gotcha #21 and
the `is_winner is nullable DEFAULT false` note). Until this arm, no predicate in the chain
had to tell them apart, because a vm with no winner never survived to be asked.

**Measured cost of the `graded` conjunct: 0 rows on the newest 1.2 M outcome ids** —
19,127 truth-eligible rows, **0** with `is_winner IS NULL`. It is fail-closed defence, not
a filter that is doing work today. Board-wide it is unmeasured: the unbounded scan times
out on the row path, and the chunked command is parked (§8).

## 3. The restored rows really are losses — re-verified this session

CAL-P122's reviewer note said *"the whole finding rests on it"*, so it was re-read rather
than inherited. `backend/app/tasks/backfill_winners.py:411-419` and `:5809-5815` both write

```sql
UPDATE futures_outcomes SET is_winner = false, resolution_source = 'api_settlement', ...
```

as **one** statement, keyed on the tickers Kalshi's settlement API returned with
`result = 'no'`. There is no path in either phase that stamps `api_settlement` on a row
without deciding its side in the same UPDATE. The rows where an affirmative grade is *not*
available are excluded a step earlier by the truth-eligibility allowlist — 139
`clean_resolution`, 59 NULL, 37 `all_losers`, none of them in the 432.

## 4. 🔴 The hazard nobody had named: this class is invisible to both fabricated-loss rails

`kalshi_fabricated_loss.py` exists because of a real defect: before `d59c9374`
(deployed **2026-08-14 16:59:38 UTC**) a Kalshi `result` of `""` or `"scalar"` was written
as `is_winner = false, resolution_source = 'api_settlement'` — *"a fabricated claim wearing
the strongest badge we issue"*. Two predicates police that class, and **both are scoped to
markets with at least two captured outcomes**:

```
no_winner_markets          n_outcomes >= 2 AND win_count = 0
POPULATION_HAVING_SQL      COUNT(*) >= 2 AND ... = 0 AND all api_settlement
```

A **one-outcome** market fabricated the same way is caught by neither. Today that does not
matter, because `clean_vms` deletes it for having no winner. After the repair it publishes.

**This is a bound, not a blocker, and here is the bound.** The exposure is (a) confined to
Kalshi, (b) confined to legs written before 2026-08-14 16:59:38 UTC — the forward defect is
fixed and `gradeable_winner` now refuses to write — and (c) split by Kalshi's measured
74–86 day market-data retention (`app/utils/kalshi_retention.py`, gotcha #35): legs still
inside retention are re-verifiable leg-by-leg against the venue by the existing rail, and
legs past it are not, by anyone, ever.

**The companion this implies** (not built here, and deliberately not queued on its own
account — it inherits this ship): widen the retraction rail's population from
`COUNT(*) >= 2` to `COUNT(*) >= 1` so the one-outcome class becomes reachable by the
instrument that already knows how to judge it. It writes `ungradeable_result`, which is
truth-INELIGIBLE, so a retraction removes the row from the curve — the correction is
available in the direction that matters.

## 5. 🔴 What landing costs, and why it is coupled to D22

`_main_input_fingerprint` hashes the SOURCE of `_calibration_population_ctes`. This patch
changes that source, so on the first beat after deploy:

```
input_fingerprint != expected  ->  INVALIDATE / REASON_INPUT_FINGERPRINT
                               ->  every banked futures unit is discarded
```

The window log for this cycle shows what that costs: a fresh census promotion leaves
`rebuild_units_banked: 0` against `units_banked: 128` and `beats_to_publish: 10`. Ten heavy
beats is ten chances for the class-B diagnostics timeout, which spent this window's third
and last miss at beat #15 (`13:42:18Z`). **Order matters: D22 then D13.** If both are
answered at once they can ride one deploy — the fingerprint is invalidated once either way,
which is an argument for landing them together rather than a day apart.

## 6. Regression controls

`artifacts/cal-p143/test_calibration_lost_losses_12cal.py` — lands at
`backend/tests/`. It is **RED against the producer as it stands and GREEN against the
patched one**, and that is proved rather than asserted:
`artifacts/cal-p143/verify-12cal-suite.py` rebuilds the patched producer as a scratch copy
under `/tmp`, imports it under its own module name, and runs the suite's own assertion
function against both chains. Output in `suite-verification.txt`, exit 0.

```
  live chain still carries the bare vm-level winner gate
  RED  on the live chain, as it must be
  GREEN on the patched chain
  boundary table: 6 cases
  census arm == producer arm on all 9 (market_count, total_outcomes)
  VERDICT: PRE-BUILD VERIFIED
```

The guard that matters most is `test_the_restored_arm_is_exactly_the_censuss_defect_arm`:
the class the instrument calls `B_lone_claim` and the class the producer now publishes are
held to **one** definition, over all nine (market_count, total_outcomes) combinations. If
they ever drift, the measured 432 stops being the number that lands.

Two guards exist purely so the landing cannot be quiet: `test_landing_invalidates_the_banked_futures_units`
(§5 must have been read) and `test_the_declared_movement_is_an_addition_of_losses` (ruling
054 — rows UP, restored-class win rate 0.0, headline ECE worse-or-equal).

## 7. The declared movement (ruling 054) — and the one direction that is NOT declarable

🔴 **The sentence that has held 12-CAL since CAL-P122 — "its recommended fix makes the
headline WORSE, which is why it has sat" — is cell-dependent, and on the second cell
measured it is false.** `polymarket/economics` goes 3.90 → **3.68**, better by 0.22, while
`kalshi/entertainment` goes 5.21 → 6.30, worse by 1.09. Two cells, two sources, opposite
signs. Full measurement and what it does to 13-CAL: `GENERALITY-12CAL.md`.

So the declaration is: rows UP (certain), restored-class win rate 0.0 (certain by
construction), **headline ECE direction UNKNOWN — measure it on the first curve after the
deploy, do not predict it.** The guard pins that as the declared value rather than a
direction, because declaring a direction here would be declaring a guess.


| | on `kalshi/entertainment`, the one cell measured exactly |
|---|---|
| the class today | 395 rows, ECE 32.48, gap **−32.48**, 100.0% winners |
| the class restored | 827 rows, ECE 21.09, gap **+11.60**, 47.8% winners |
| the cell today | 8,418 rows, ECE 5.21, gap +1.04 |
| the cell restored | 8,850 rows, ECE **6.30**, gap +3.53 |

**The gap reverses sign.** The page says this class was under-priced by a third; the truth
is over-priced by 11.6. And the holdout says it is live and accelerating — **60** dropped
rows in the OLD half against **372** in the NEW (split at `market_id 13096338`, the
published population's own row-balanced median).

Board-wide the movement is an ADDITION of an unknown number of 100%-loss rows. It is not
extrapolated here: §8.

## 8. What is NOT measured, and the exact command for each

* **The board-wide size of the restored class.** PARKED as CAL-P122-1 and still parked —
  ruling 134 puts a census on the measurement lane, and this session ran only the two cells
  that decide 13-CAL (§9). Per cell:
  `python3 backend/scripts/calibration_missing_loser_census.py --source S --category C --out ...`
* **The `graded` conjunct board-wide.** `SELECT COUNT(*) FROM futures_outcomes WHERE is_winner IS NULL AND resolution_source IN <eligible>` times out on the row path; run it chunked on
  `fo.id` (the newest 1.2 M ids were run here and returned 0).
* **The pre-2026-08-14 share of the restored class** (§4's hazard). Needs the vm chain plus
  `last_updated < '2026-08-14T16:59:38Z'`; the census script is the right host for it.

## 9. Generality — does the repair matter beyond rank 8?

See `GENERALITY-12CAL.md` in this directory: the same census, run this session on
`polymarket/esports` and `kalshi/economics` — the two cells whose banked designs cannot land
until 13-CAL is answered, and 13-CAL cannot be answered before 12-CAL.

## 10. Landing steps

```bash
bash artifacts/cal-p143/land-12cal.sh          # applies the patch + installs the suite
cd backend && python3 -m pytest tests/test_calibration_lost_losses_12cal.py \
                                tests/test_calibration_missing_loser_census_p122.py -v
```

`test_calibration_missing_loser_census_p122.py::test_clean_vms_still_carries_the_vm_level_winner_gate`
pins the DEFECT, and its own docstring says what to do when the defect goes: *"If that is a
deliberate repair, this instrument is obsolete and must be retired, not left printing
zeros."* **The patch inverts that guard rather than deleting it** — same CTE, same reading,
now asserting the bare gate is gone and the lone-claim arm is present — so the suite that
found the defect is the suite that holds the repair. That is hunk 3 of the patch, not a
step the operator has to remember.

`land-12cal.sh` prints the gates instead of running them (gotcha #124: a gate this script
ran is a gate nobody read) and refuses outright if the frozen file is already dirty.
