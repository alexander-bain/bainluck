# RULING 123 — A baseline describes the regime we run in

date: 2026-08-23
author: Fable (directive to the latency program, LAT-P082; pasted and reviewed by Alex)
issues: #2102, #1609, #2110, #1545
amends: ruling 110 (the pinned `PRE_MOVE_BASELINE`), ruling 119 (its evidence, restated)

## The ruling

Ruling 110's straddling baseline is **RE-PINNED, entirely from post-v3874 samples.**

Fable, verbatim:

> the ruling-110 straddling baseline is RE-PINNED, entirely from post-v3874 samples. The
> step is dated and deliberate (CAL-P078's rolling re-stage); a baseline must describe the
> regime we run in. State in the ruling which regime each of the seven now pins.

The general clause, which survives deleting its case: **a baseline is a claim about the
system we run in.** If the system stepped between the pin and today, the pin describes a
system that no longer exists, and the ratio it produces is a constant wearing a
measurement's clothes. It does not converge with more samples. It does not decay. It reads
the same number forever, and it reads it with the full authority of an instrument.

## The case

`precompute_calibration_main` was pinned at **p50 214.7 s / p95 1302.1 s / max 1357.2 s**.

Those three numbers cannot describe one population. A median of 214.7 s is a value from
the beat as it ran before 2026-08-20; a p95 of 1302.1 s and a max of 1357.2 s are values
from the beat as it has run since. #2102 found the boundary and dated it exactly:
**v3874 (`724fd22c`, 2026-08-20 10:45:57 PDT)** carried CAL-P078's rolling re-stage, whose
own commit message records `units_this_beat` going from 0 to every-unit, and the beat
stepped **7.74×** across it — regime A p50 163.2 s (n=7), regime B p50 1263.3 s (n=43).
Confirmed in the phase ledger to the millisecond: 8 units × 141,283 ms = 1,130,264 ms of
`read:futures_unit`, 86 % of the run.

So between 3 and 24 of the 50 samples behind that pin were already in the slow regime when
it was taken. The pin was a **mixture statistic across a regime boundary**, and it read
**6.05×** against the perfectly healthy beat on 2026-08-23 — over `DEGRADE_P50_RATIO`, so
the panel returned **REVERT**, so ruling 110's conditional grant stood revoked by an
artefact.

**A falsifier stuck on REVERT is exactly as unwatched as one stuck on HOLD.** That is the
symmetry ruling 110 turns on, and the reason this is a ruling rather than a constant edit:
LAT-P079 already had to withdraw a staged fix whose condition was *never false*, and this
is the same failure with the sign flipped.

## The re-pin, and why the source is an artefact rather than production

**`app.tasks.precompute_calibration_main` → p50 1187.8 s / p95 1396.4 s / max 1397.8 s,
n = 22, min 140.2 s.**

Drawn from `docs/audits/latency/lat-p081-gate1-pcm-ring.json` — LAT-P081's byte-pinned
ring, captured 2026-08-22T15:51Z — restricted to samples that are **both post-v3874 and
pre-routing-change**. Regime B, before ruling 110's move.

The double restriction is the whole design, and the reason a live read could not supply it:

* **post-v3874** is Fable's instruction and gives the regime we run in;
* **pre-move** is what keeps the falsifier a falsifier. A baseline re-derived from
  production today is the change grading itself, and this beat's ring has now rolled
  completely over — the oldest live sample is 2026-08-21T14:38Z and **48 of 50 are
  post-move**. Restricting today's ring to regime B ∩ pre-move yields **n = 2**.

The window where both conditions hold is 22.4 hours wide and it has already passed. It
survives in exactly one committed artefact, which is the argument for committing artefacts.

## Which regime each of the seven now pins

Every baseline now carries a `regime` field — a field rather than a paragraph, so the
endpoint prints it and `test_every_baseline_declares_which_regime_it_pins` fails when a
beat cannot answer. Cross-checked 2026-08-23 by splitting each live ring at v3874:

| beat | regime | evidence |
|---|---|---|
| `precompute_calibration_main` | **B, pre-move — RE-PINNED** | 7.74× dated step at v3874; old pin was a mixture |
| `compute_calibration_prices` | single | pre 537.9 s (n=31) vs post 550.2 s (n=12). Excluded anyway, on its own 540 s budget |
| `compute_time_horizon_calibration` | single | pre 302.0 s (n=32) vs post 301.4 s (n=12) — 0.2 % apart |
| `compute_fair_fight_comparison` | single | pre 147.2 s (n=32) vs post 160.8 s (n=12) — inside its own spread |
| `precompute_source_intelligence` | single, **and it is the one MOVING** | pre 17.4 s (n=32) vs post 26.7 s (n=12), +53 %. That window contains the ROUTING move, so this is a candidate signal, not a regime problem |
| `snapshot_coverage_metrics` | single | pre 480.1 s (n=8) vs post 480.2 s (n=3). Weakest evidence in the set, and unchanged |
| `precompute_backfill_winners_status` | single, **but UNVERIFIABLE from today's ring** | rolled fully over (50 of 50 post-v3874); the pre-arm no longer exists to compare against. Pin retained; live p50 is 1.04× it — an argument from the absence of a jump, not from a comparison |

One of the seven straddled. Six pin a single regime, and one of those six can only say so
by the absence of a step rather than by a comparison — recorded as such, because "I checked
and it did not move" and "I could not check" are different claims and this program has paid
for rendering them the same (gotcha #53).

## What this ruling does NOT do

It does not certify the routing, and it does not clear ruling 110's condition.

With the artefact removed, the panel **still reads REVERT** — on one beat, and a different
one. `precompute_source_intelligence` grades **1.53×** (post-move p50 26.8 s against its
pinned 17.5 s, 8 post-move samples). Ruling 119's control test was applied to it before
this was written, and **the control does NOT fire**: the pre-move arm of the same ring
reads 17.5 s against the pinned 17.5 s = **1.00×**. So unlike the reading ruling 119 voided,
this one is attributable on ruling 119's own standard.

That is escalated, not executed, and the reasons are stated so the escalation can be
refused: the whole post-move sample set lies inside the pre-move envelope, the p95 FELL
(32.6 s → 31.0 s), n is 8, and the absolute move is nine seconds on a beat that runs four
times a day. Set against ruling 110's own accounting, `DEGRADE_P50_RATIO = 1.25` is a pure
ratio with no absolute floor, so it fires at **+4.4 s** on this beat and would need **+297 s**
on the beat a user-facing page actually waits on — 67× more sensitive to the beat that
matters least. Loosening that threshold was explicitly out of scope for the window that
found it (#2102), and it is out of scope here for the same reason: the lane that just
rebuilt an instrument should not also be the one deciding its first verdict is wrong.

## What P4 says, now that it can be read at all

Corrected in the same window (#2110): both movers are running at **~100 % of schedule** —
`backfill_market_shapes` 73.8/day against 72 scheduled, `precompute_backfill_progress`
96.5/day against 96, rate-corrected against each counter's own 9.1 h and 10.2 h window.
Before the move they ran 31 of 72 and 45 of 96.

**Ruling 110's central prediction — "they are starved rather than idle" — is CONFIRMED.**
The old instrument reported both as `flat_or_fell`, i.e. FAILED, while they sat at schedule.

That is also the mechanism behind the finding above rather than a separate fact: this
module's own header predicted that `heavy` could inherit more than `background` sheds, and
movers going from 45 % of schedule to 100 % is what that looks like. The cost showing up on
the fastest heavy beat's median is the predicted cost arriving, which makes the trade
legible: `background` relieved and two starved backfills running in full, against +9 s on
`precompute_source_intelligence`'s median.
