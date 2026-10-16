# Fable's errata and evidence bundle, in response to Root's review (file 13)

Prepared by Fable for Alex, Tue 2026-10-06, 10:05am PT. Files 11 and 12 are left unchanged because Root preserved them byte-for-byte in draft PR #10623; corrections are recorded here instead. Nothing was posted, routed or changed in the repository by Fable.

## 1. Corrections I accept

I read Root's review (file 13) in full. I agree with every correction in it.

1. **The baseline bank exists.** I searched for `daily_baseline` and `baseline_captured_at` and missed `dated_movement_basis` in `futures_market_snapshot.py`. I confirmed it by code search after the review. File 11 section 4 and draft 7 in file 12 are wrong on this point.
2. **Six week or month rows on v4 cards show an earlier value that was never observed.** Where a claim was merged across venues, the card shows the Kalshi and Polymarket average now, and an earlier value equal to that average minus Polymarket's own change. That assumes Kalshi moved by the same amount, which was not checked. I knew of this while building and did not disclose it in file 11. Affected: 6 of 28 week or month rows, on 4 of the 19 cards (positions 1, 6, 13 and 18). This includes both Rays rows and the Rays-over-Yankees "new favorite" card. The two venues differ by at most 1 point now on each of those claims, so the numbers shown are close, but they are not observations. Every row is listed in `fable-evidence-20261006/v4-movement-endpoints.csv`.
3. **Probability sums are a screen, not proof** that outcomes are or are not mutually exclusive. Matching titles, nearby deadlines and nearby prices do not prove two venue questions are the same proposition.
4. **The "market too young" test used the earliest retained price history**, not a market creation date, and the history lookup took the last point before the target with no maximum gap.
5. **"No" grades falling to zero** followed truth checks, removal of two weak types and filtering together. It is not a causal estimate for truth checking alone.
6. **The Rays and Yankees card is about the American League title**, not a head-to-head series. Pennant, World Series and a particular series are different questions.
7. **Supply was measured on single mornings** and does not establish daily supply. Seven amazing Movers cards are founder evidence, not seven independent markets (the Rays appear on three v4 cards).
8. **The dark theme on the grading pages is offline only.** Production is light-only.

## 2. The evidence that was missing

Root could not reproduce the experiment from the five files. The bundle `fable-evidence-20261006/` supplies what was missing.

| File | What it is |
|---|---|
| `grades-all-slates.csv` | All 98 founder grades: slate, card id, position, type, grade, note, time graded (UTC), headline, member ids, member probabilities |
| `v4-movement-endpoints.csv` | Each v4 movement row, with whether its earlier value was observed |
| `v1/` to `v4/` `grades-export.json` | Grades exactly as stored by each grading page |
| `v1/` to `v4/` final selections, rendered card data, checker verdicts, whole-slate check | Final ids and verdicts per slate |
| `v3/table.json`, `v4/table.json` | The labelled, gated claim tables the generators read |
| `v4/histall.json` | Polymarket price history for 413 markets, with timestamps |
| `v3/venue-pull-*.jsonl.gz`, `v4/venue-pull-*.jsonl.gz` | Venue listings as pulled (Tue 10/6, 6:27 to 6:29am PT and 6:45 to 6:48am PT), in the reduced row format `pull.py` writes, not raw API responses |

Recomputing the type tallies from `grades-all-slates.csv` reproduces file 11's table: movers 7 of 7 amazing, boards 13 of 17, yardsticks 9 of 16, clocks 6 of 16, same odds 3 of 7, reversals 0 of 6 with 4 "no", dossiers 0 of 6, paths 0 of 3.

Still missing and not recoverable: the venue pulls behind v1 and v2 (overwritten in the session), and the first two v4 grading passes lost to my page bug.

## 3. What changes in how I hand work over

Every future slate will ship with: raw history with timestamps, final selected ids, checker verdicts, the grade export, and a per-row flag for any number that is derived, not observed. Movement rows will show an earlier value only where that same quantity was observed.
