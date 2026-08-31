# CAL-P144 — class B is not a rebuild condition, and the last good beat cleared it by 7.3 seconds

**TL;DR.** `B_DIAGNOSTICS_TRUTH_CENSUS` was named from its error text. This session
measured its *mechanism* over 168 beats and it is not what the D13/D22 ordering note
says it is:

1. 🔴 **The census runs on EVERY beat.** `carried` never once contains `diagnostics`
   in 168 beats — the reuse path the code offers is never taken. Exposure is
   continuous, not occasional.
2. 🔴 **`window_left_ms` is a residual, not a reserve.** The futures staging loop
   stops when one more *unit* won't fit and reserves nothing for the phases after
   it. The leftover is bounded by one unit's cost (141k–451k ms observed), so it
   lands under the census's ~88 s need on **20 of 137 gauged beats — a flat 14.6%
   per-beat hazard**.
3. 🔴 **The hazard is NOT coupled to rebuild progress.** `r(units_done,
   window_left_ms) = +0.041`. The directive's premise — that D13 is dangerous
   because it "manufactures ~10 heavy rebuild beats, which is the exact condition
   the class-B timeout fires under" — is **measured false as stated**. The ordering
   conclusion survives on different arithmetic (§4).
4. **The predictor is exact on the freeze window: 14 gauged beats, 14 agreements,
   0 disagreements**, including both class-B misses and all twelve CLEAN beats.
5. 🔴 **Three of those twelve clean beats cleared by 4.3 s, 4.6 s and 7.3 s.** The
   freeze window did not merely lose two beats to class B; it *survived ten more
   on seconds*.

Nothing was landed. `git diff backend/` is empty; the freeze holds.

---

## 1. The mechanism, end to end

`read:truth_census` is one statement inside `PHASE_DIAGNOSTICS`, which runs after
`PHASE_FUTURES`. Its DB backstop is not a constant — `statement_timeout_for()` in
`app/utils/calibration_phase_ledger.py:1321` returns

```
    min( phase budget , _statement_timeout_for(remaining_ms) )
    where remaining_ms = PHASE_DEADLINE_MS (1,380,000) − elapsed
    and   _statement_timeout_for(r) = r − min(30_000, r // 10)
```

So the census's timeout is *whatever the futures phase left behind*. The producer
banks that exact quantity every beat as the gauge `staged:window_left_ms`
(`precompute_calibration.py:3183`), and CAL-P084's beat-gauge sampler keeps ~7 days
of them under `calibration:beat_gauge_history`. **That is the only reason this was
measurable at all** — `calibration:main:phase_ledger` holds one row and is
overwritten hourly, so the bound a dead beat ran under would otherwise be gone.
CAL-P084 was built for a different question and paid for this one.

Validation that the gauge is the right quantity: on beat 16 the gauge reads
**106,157 ms** and the value recomputed from the phase ledger
(`1,380,000 − 1,273,786` futures) is **106,214 ms** — a 57 ms difference, which is
the unmeasured overhead between the two records.

## 2. Why the residual is so often too small — the root cause

`window_left_ms` is written at exactly one place: the staging loop's exit branch,
where `_unit_fits_in_window(remaining_ms, worst_unit_ms, prior_unit_ms)` returns
False (`precompute_calibration.py:3174`). That predicate asks **whether one more
UNIT fits**. It has no term for the phases that must follow it.

The consequence is structural, not incidental: the loop keeps taking units until
one doesn't fit, so the leftover is by construction *less than one unit's cost* —
and a unit costs 141k–451k ms (median 264k) in this same history. The census needs
~98k ms of window to get a ~88k ms bound. A residual drawn from that range clears
it about 85% of the time, which is precisely what is observed.

**This is the sentence the fix should be written against:** the loop reserves
nothing for the work it knows comes after it.

## 3. The evidence

`census-window-margin.py` / `.txt` (exit 0), 168 beats, 137 gauged:

```
   bound BELOW census need    n=  20  failed= 15 ( 75%)  complete=  1  cancelled=  4
   bound ABOVE census need    n= 117  failed= 44 ( 38%)  complete= 61  cancelled= 12
   per-beat hazard p = 20/137 = 0.146
```

`window-beat-margins.py` / `.txt` (exit 0) — the blind check. The freeze-window
classes were assigned from `task-metrics.last_error` *before* this gauge was ever
read, so agreement is evidence and not a fit:

```
   4  2026-08-30T02:38:29 B_DIAGNOSTICS_TRUTH_CENSUS    29367   26431   -61853  class B
  15  2026-08-30T13:42:18 B_DIAGNOSTICS_TRUTH_CENSUS    81542   73388   -14896  class B
  ...
  gauged beats 14   model agrees 14   disagrees 0   ungauged 2
```

Beat 4 is worth calling out: CAL-P143's `WINDOW-REPORT.md` recorded it as *"may have
been the same class and cannot be recovered."* It both **was** the same class (the
log carries a live attribution, `attribution_gap_s = 0.119`) and is now explained —
29.4 s of window for an 88.3 s statement, a 62-second shortfall.

**The margins on the beats that lived:**

```
   beat 11: cleared by 4272 ms (4.3 s)
   beat  8: cleared by 4618 ms (4.6 s)
   beat 16: cleared by 7258 ms (7.3 s)
```

## 4. 🔴 What this does to the D13 → D22 ordering

The directive's stated reason to order them is **measured false**: rebuild-heavy
beats are not more exposed (`r = +0.041`; median `window_left` is 216 s / 220 s /
239 s across early / mid / late rebuild buckets). Class B is a flat tax on every
beat.

**The ordering conclusion survives anyway, on better arithmetic.** D13 moves
`_calibration_population_ctes`, which is hashed into `_main_input_fingerprint`, so
landing it discards the bank and forces ~10 rebuild beats. Those beats are not
*individually* riskier — but they are ~10 **more** independent draws at p = 0.146:

```
     P(>=1 class-B miss in 10 beats) = 79.4%
     P(>=1 class-B miss in 15 beats) = 90.6%
```

So: **D22 first, or both on one deploy** — the same conclusion the directive
reaches, for a reason that is true. Landing D13 alone is an ~80% chance of buying a
class-B miss during its own rebuild.

## 5. 🔴 D22 is the right safety net and it is not the cure

D22 wraps the census in `soft_stage`, so a timeout no longer kills the publish.
That is correct and should land. But it does not make the census *run*: on the
~15% of beats where the window is too small, the class becomes
`census_observed = false` instead of a dead beat. D22's own design already handles
that honestly — the degraded value is `None`, never `{}` — so the outcome is
"unobserved", not "no violation". Good.

The **cure** is a reserve term in `_unit_fits_in_window`: stop staging units while
enough window remains for the phases that follow. That is a change to the frozen
file and it is **not proposed here** — no exception was requested and none should
be. It is written down so that whoever answers D22 knows the safety net and the
cure are different changes, and that taking the net does not close the hole.

Sizing it, so the option is costed rather than gestured at: a reserve of ~98,000 ms
would have cost the staging loop **at most one unit on 20 of 137 beats** and zero
units on the other 117, because on those 117 the residual already exceeded the
reserve. The rebuild would run ~15% of beats one unit shorter in exchange for the
census never being cancelled.

## 6. What this queue did NOT do

* **Landed nothing.** `git diff backend/` empty; `precompute_calibration.py`
  unchanged. D13, D21 and D22 remain Alex's and ungranted.
* **Did not restart the watcher.** `pgrep` first, as the directive requires: pids
  3016/3019 alive with 10h+ uptime and zero restarts. Two watchers corrupt the log.
* **Did not re-baseline.** §4's arithmetic is one more reason not to: a window
  opened before D22 lands measures the defect.
* **Did not extend the missing-loser census.** Four cells are exact, 45 are PARKED
  as CAL-P122-1, and the directive is explicit that nothing currently needs them
  (ruling 134 — measurement belongs to the measurement lane).
* **Did not measure the census's cost distribution.** `read:truth_census` is banked
  in the phase ledger, which holds ONE beat; the beat-gauge sampler does not capture
  it. So 88,284 ms is a single observation and §4 of `census-window-margin.txt` is a
  sensitivity sweep rather than a confidence interval. **Adding
  `read:truth_census` to `OPERATIONAL_GAUGES` would make it a distribution** — that
  is a one-tuple change in `calibration_beat_gauge_sampler.py` (not frozen), and it
  is appended to PARKED-MEASUREMENTS rather than done here, because no named ship
  is waiting on it.

## Evidence

| file | what |
|---|---|
| `census-window-margin.py` / `.txt` | §1–3 — the mechanism over 137 gauged beats, exit 0 |
| `window-beat-margins.py` / `.txt` | §3 — the blind check on the freeze window, 14/14, exit 0 |
| `window-log-snapshot.jsonl` | the CAL-P140 log as it stood at hand-off (16 beats) |
| `gate.txt` | §7 — `pytest -k "calibration or bookmaker or ladder"`, exit code on its own line |
