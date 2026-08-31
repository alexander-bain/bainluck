# CAL-P144 — class B is not what we told Alex it was, and the last good beat cleared it by 7.3 seconds

**TL;DR.** D13 and D22 are still unanswered, so nothing landed and the freeze holds.
The budget went to the one thing that was both free and decision-shaped: `read:truth_census`
was banked hourly by an instrument built for a different question, so the *mechanism* of
class B was measurable without a single new heavy query. Four findings:

1. 🔴 **The stated reason to order D13 behind D22 is measured false.** Class B is not a
   rebuild condition — `r(units_done, window_left_ms) = +0.041` over 137 beats. **The
   ordering conclusion survives on different arithmetic** and is now stronger: D13 forces
   ~10 rebuild beats, each an independent draw at a flat **p = 0.146**, so landing D13
   alone is a **79% chance** of buying a class-B miss during its own rebuild.
2. 🔴 **Root cause, one line:** the futures staging loop stops when one more *unit* won't
   fit and **reserves nothing** for the diagnostics phase after it. `window_left_ms` is a
   residual bounded by one unit's cost (141k–451k ms), and the census needs ~98k of it.
3. **The predictor is exact on the freeze window — 14 gauged beats, 14 agreements, 0
   disagreements**, and it is a *blind* check: the classes were attributed from
   `task-metrics.last_error` before this gauge was ever read. It also explains beat #4,
   which CAL-P143 recorded as unrecoverable.
4. 🔴 **Three CLEAN beats cleared by 4.3 s, 4.6 s and 7.3 s.** The window did not merely
   lose two beats to class B; it survived ten more on seconds.

Plus two instrument defects found by running the instruments: `refusal-register.py`'s live
path had **never executed**, and its headline example is no longer true.

`git diff backend/` is empty. `precompute_calibration.py` is untouched. No freeze exception
was requested or taken.

---

## 1. The finding — `CLASS-B-ROOT-CAUSE.md`

The full write-up is its own document. The shape of it:

`read:truth_census` is one statement in `PHASE_DIAGNOSTICS`, which runs after
`PHASE_FUTURES`. Its DB backstop is not a constant — it is
`_statement_timeout_for(PHASE_DEADLINE_MS − elapsed)`, i.e. **whatever the futures phase
left behind**. The producer banks exactly that quantity every beat as
`staged:window_left_ms`, and CAL-P084's beat-gauge sampler keeps ~7 days of them.

**That sampler is why this session cost almost nothing.** `calibration:main:phase_ledger`
holds one row and is overwritten hourly, so the bound a dead beat ran under would otherwise
be gone forever. CAL-P084 was built to stop a *descent* from depending on a leftover shell
process; it paid for a question nobody had asked yet.

Validation the gauge is the right quantity: beat 16's gauge reads **106,157 ms**; recomputed
from the phase ledger (`1,380,000 − 1,273,786`) it is **106,214 ms**. 57 ms apart.

```
   bound BELOW census need    n=  20  failed= 15 ( 75%)  complete=  1  cancelled=  4
   bound ABOVE census need    n= 117  failed= 44 ( 38%)  complete= 61  cancelled= 12
   per-beat hazard p = 20/137 = 0.146
```

## 2. 🔴 Two things this corrects in CAL-P143's hand-off

* **"D13 manufactures ~10 heavy rebuild beats, which is the exact condition the class-B
  timeout fires under."** The premise is false; the conclusion is right. Rebuild-heavy
  beats are *not* more exposed (median `window_left` 216 s / 220 s / 239 s across early /
  mid / late rebuild). They are simply **more beats**, and every beat is a 1-in-7 draw.
  The corrected argument is in `alex-inbox/calibration-914`.
* **"Beat #4 … cannot be recovered."** It both was recovered — the log carries a live
  attribution, `attribution_gap_s = 0.119` — and is now *explained*: 29.4 s of window for
  an 88.3 s statement, a 62-second shortfall.

## 3. 🔴 D22 is the right safety net and it is not the cure

D22 stops the timeout killing the publish. It does **not** make the census run: on ~15% of
beats it will record `census_observed = false` instead. That is correct, and D22's design
already refuses to render it as "no violation" (the degraded value is `None`, never `{}`).

The **cure** is a reserve term in `_unit_fits_in_window` — stop staging units while enough
window remains for the phases that follow. **It is not proposed and not built:** it changes
the frozen file, and no exception was requested. It is costed in the finding doc so the
option is a decision rather than a gesture: a ~98,000 ms reserve would have cost at most one
unit on 20 of 137 beats and nothing on the other 117.

## 4. Instrument defects found by running the instruments

* 🔴 **`refusal-register.py`'s live path had never run.** It invoked the scorecard with no
  arguments; the scorecard *requires* `--live` or `--payload`, so it exited 2 with empty
  stdout. The register read neither the return code nor stderr, parsed `""` into `{}`,
  rendered **every** refusal as OFF THE BOARD, invented three holes and exited 4 — maximally
  alarming output from a total absence of data. CAL-P143's exit 0 came from passing
  `--scorecard` and masked it. Fixed in `cal-p144/refusal-register.py`: pass `--live`, refuse
  on non-zero exit, and refuse a zero-cell parse separately (gotcha #124 + #53).
* 🔴 **The register's headline example is no longer true.** CAL-P143 built the
  refusal-vs-hold argument on `polymarket/tech` having *left* the board. Re-read live it is
  **back at rank 19** with 5,411 excess — the absence was a property of the render P143
  parsed. The principle stands and now has no live example; the note says so, because board
  membership **oscillates**, which is a better argument for the design than a one-way
  departure ever was.
* Both refusals whose numbers CAL-P143 re-measured now carry a `sharpened_by` citation —
  notably `polymarket/economics`, where the next reader would otherwise size the repair off
  **508** instead of **78** (the raw-base-rate-is-not-a-repair-size lesson, one cell over).

## 5. The window, and what was deliberately not done

Beat #16 arrived and classified CLEAN; the log stands at **13 clean / 16**, still
arithmetically lost (12 + 9 = 21 < 22 was already decided). The watcher was verified single
before anything else ran — `pgrep` first, pids 3016/3019, 10 h uptime, zero restarts. **Not
re-baselined**, and §1 is one more reason: a window opened before D22 lands measures the
defect.

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted; CAL-P143's pre-builds are
  still applied nowhere.
* **Did not extend the missing-loser census.** Four cells exact, 45 PARKED as CAL-P122-1,
  and the directive is explicit that nothing needs them (ruling 134).
* **Did not measure the census's cost distribution** — 88,284 ms is *one* observation, so
  §4 of `census-window-margin.txt` is a sensitivity sweep (8.0%–24.8% over 60k–120k ms), not
  a confidence interval. The fix is one tuple entry in a non-frozen file; parked as
  **CAL-P144-1** because D22's answer turns on the hazard being materially non-zero, which
  14/14 already establishes — not on the percentile.

## 6. Gate

`pytest -k "calibration or bookmaker or ladder"` → **2964 passed, 24 skipped, EXIT CODE: 0**
(`gate.txt`, exit code on its own line per gotcha #124). Zero backend files changed.
`ruff check artifacts/cal-p144/*.py` — all checks passed; `py_compile` OK.

## Evidence

| file | what |
|---|---|
| `CLASS-B-ROOT-CAUSE.md` | §1–3 — the mechanism, the root cause, the corrected D13 ordering, D22's limit |
| `census-window-margin.py` / `.txt` | the hazard over 137 gauged beats + the sensitivity sweep, exit 0 |
| `window-beat-margins.py` / `.txt` | the blind check on the freeze window — 14/14, exit 0 |
| `refusal-register.py` / `.txt` | §4 — live path fixed, two citations added, tech corrected, exit 0 |
| `window-log-snapshot.jsonl` | the CAL-P140 log at hand-off (16 beats) |
| `gate.txt` | §6 |
