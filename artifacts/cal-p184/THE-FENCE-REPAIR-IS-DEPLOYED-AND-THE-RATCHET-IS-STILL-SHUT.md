# CAL-P184 — the falsifier held, and the repair for the thing it measures is deployed and inert

**2026-09-01, 09:39–10:00Z / 02:39–03:00 am PT.** Branch `program/calibration-168-rank1-baseball`
@ `2f28aa30` (merged as `2aac5843`). No code written, nothing pushed, no cert staged.

---

## 1. The falsifier resolved: the 5-units/beat rate HOLDS. The ETA stands.

Directive `949` Item 3.1 registered a one-curl falsifier. It has an answer.

| | |
|---|---|
| new beat | `2026-09-01T09:34:34.99952Z` (sampled into the artifact at `09:45:07Z`) |
| `input_fingerprint` | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged. No fifth reset.** |
| `staged:units_banked` | **10** |
| predicted by P183's rate | 5 × 2 beats since `08:31Z` = **10** ✅ |
| `served_units` / `served_at` / `terminal` | `0` / absent / `cancelled` — graded on the right keys (CAL-P169(a)) |

**The `09-02T08:30–09:30Z` completion estimate stands. D-G's corrected ~25–26 h cost is confirmed,
not corrected again.** The rate has now held for **27 consecutive beats with zero variance.**

Cadence note: `08:31:38Z → 09:34:34Z` is 62.9 min, slightly above the 60.0-min median. Immaterial to
the band.

---

## 2. 🔴 P183 killed the right hypothesis. The ratchet is the documented root cause.

Directive `949` Item 2 lists three hypotheses as dead, the third being:

> *"the `worst_unit_ms` bound is a tightening ratchet"* (mechanism real in source, consequence
> disproven by the data)

**That is backwards, and the repo says so in its own source.** `calibration_phase_ledger.py:275-321`
— the `STAGED_UNIT_OVERRUN_FACTOR` docstring, amended by **CAL-P163 (#1978) on 2026-08-31** — states
the mechanism as established fact:

> **The reference is therefore computed exclusively from the units that survived it, and it ratchets
> one way:** cancel the expensive units, the completed mean falls, the bound tightens, more
> expensive units cancel. Survivorship bias inside a fence.

and then names, six days before P183 rediscovered it as "unexplained", the identical signature:

> Measured, on the producer's own ring, 2026-08-31. **The ratchet closed at 06:37Z and stayed closed
> for sixteen consecutive beats, every one of them identical: 5 units completed, 7 attempted, 2
> cancelled, terminal `cancelled`, nothing published. Before it, 11-14 units per beat and `complete`
> terminals.**

That is P183's "58% throughput collapse", already diagnosed. P183's *measurement* was right and its
dating (`08-31T05:32Z` deploy `6043c1c0`) is compatible with the docstring's `06:37Z` first-closed
beat. Only the verdict — *dead hypothesis* — was wrong.

The same docstring also pre-empts the #2052 framing:

> And it was NOT the phase budget. That beat's `futures` phase held 1,188,617 ms of
> `measured_elastic_cut` and spent 878,583 — it stopped 310 s short of its own budget and 501 s
> short of the window, with `_unit_fits_in_window` never firing. **A budget you do not reach is not
> what is capping you.**

---

## 3. 🔴🔴 THE PAYLOAD: the repair is deployed, and three beats in it has moved nothing.

The repair exists, is this lane's own work, and shipped.

| | |
|---|---|
| repair | `PhaseLedger.statement_timeout_for_unit` — take the **looser** of `mean × STAGED_UNIT_OVERRUN_FACTOR` and `max(observed completions) × BUDGET_SAFETY` (`calibration_phase_ledger.py:1511-1566`), plus `_bootstrap_worst_history` for the pre-ring upgrade path (`calibration_main_build.py:1014-1108`) |
| commits | `832a5b2a` CAL-P163 · `2753a44c` CAL-P167 (repairing CERT-637) |
| entered master | merge **`76b2b454`** (CERT-657, subject `8258395c`) at **`09-01T06:18:27Z`** |
| first release containing it | **v3970 `c3143bc2`, deployed `09-01T06:54:25Z`** (verified: v3969 `1cf5be34` does **not** contain `76b2b454`; v3970/v3971/v3972 all do) |

**Every beat since that release:**

| beat | attempted | completed | cancelled | `unit_ms_worst` | `elapsed_ms` | terminal |
|---|--:|--:|--:|--:|--:|---|
| `07:31:29Z` | 7 | 5 | 2 | 52,737 | 989,078 | cancelled |
| `08:31:38Z` | 7 | 5 | 2 | 53,126 | 997,944 | cancelled |
| `09:34:34Z` | 7 | 5 | 2 | **103,882** | 1,174,681 | cancelled |

**Three for three, the exact signature the repair was written to break.**

The ring is not dead — `unit_ms_worst` nearly doubled (52,737 → 103,882 ms), so the fence *is*
widening on its own evidence, exactly as designed. **It has bought zero additional units.** Beat
elapsed rose 19% over the same three beats for the same five units.

**Honest bound on this claim:** three beats is early. CAL-P167's own docstring says the seed "ages
out" over a `UNIT_WORST_WINDOW = 24` ring and is "a floor for one day, not a permanent widening", so
the repair is entitled to more than three beats. What is *not* explained by earliness is that the
triple `(7, 5, 2)` is bit-identical across a code-regime boundary.

**The check that settles it, for whoever reads this next:** the repair deployed at `06:54Z`. If
`units_completed_this_beat` is still **5** at the twelfth post-repair beat (~`09-01T18:30Z`), the
repair has failed in production and #1978's fence work needs a second pass. If it climbs above 5,
the repair is working slowly and the `09-02T08:30–09:30Z` ETA becomes **too pessimistic**.

---

## 4. 🆕 PROVEN: the beat ends on the cancellation CAP, never on the window.

This is what P183's Trap 14 ("`window_left_ms` is present-only-on-window-stop; absence is a
FINDING") was pointing at. Here is the finding.

`STAGED_UNIT_MAX_CANCELLATIONS = 2` (`calibration_phase_ledger.py:341`). The unit loop `break`s the
beat the moment the second unit cancels at its own backstop. `staged:window_left_ms` has exactly one
writer — the window-stop branch — so if the beat exited at the cap, that gauge cannot exist.

**Across all 168 sampled beats:**

| stop signature | beats |
|---|--:|
| `units_cancelled == 2` **and** `window_left_ms` ABSENT | **25 / 25** |
| `units_cancelled == 1` and `window_left_ms` present | 13 / 14 |
| `window_left_ms` present, no cancellations (clean window stop) | 103 |

The correlation is total. **Every beat that reaches two cancellations exits at the cap with the
window question never asked** — and *every* beat in the collapsed regime reaches two.

### Why this matters beyond bookkeeping

**#2052's live remedy — widening the 22.5-minute statement-timeout wall — cannot help.** The beat is
not reaching that wall; it is quitting at a cancellation counter first. A wider phase window buys
nothing while `units_cancelled` pins at 2. This does not make #2052 wrong about the wall existing;
it makes the wall the *wrong lever right now*.

It also explains the shape of the waste without needing P183's inference: the two cancelled units are
not a side-effect of running out of time, they are the *reason the beat stops*, and a wider fence
(§3) makes each one **more expensive** rather than less frequent — which is precisely what the rising
`elapsed_ms` in §3's table shows.

---

## 5. Two more gauge names, confirmed and corrected

- ✅ **P182 was RIGHT and should not be re-litigated.** `staged:unit_ms_mean` really is the mixed
  mean. Source, `calibration_main_build.py:1563-1568`: *"`unit_ms_mean` above averages over every
  unit the beat TIMED, including the one cancelled at the deadline, so it is the right number for
  attributing elapsed time and the wrong one for costing a unit."*
- 🆕 **`staged:unit_ms_mean_completed` is the honest one, it is recorded, and the sampler drops it**
  (`calibration_main_build.py:1577`; absent from all 168 observations). So are
  `staged:unit_cancelled_after_ms` and `staged:unit_cancelled:{chunk.key}` — **the latter names the
  blocking unit by key.** This is exactly P182-2 / P183-2, now with the three specific gauge names
  that would end the guesswork. Still a two-line change to
  `calibration_beat_gauge_sampler.py:170`'s list. Parked, not built (ruling 134).

⚠️ **Do not read `unit_ms_worst` as the worst unit of the beat.** Post-repair it is fed from the
carried `UNIT_WORST_WINDOW` ring, not from this beat's completions. Arithmetic that treats it as
"max completed this beat" does not close.

---

## 6. What this session did NOT do

No code, no push, no cert, no deploy — D-G's default **(a) freeze** binds and a calibration-source
deploy would reset the 27-beat rebuild. Remote verified == local via `git ls-remote`
(`2f28aa30`). No probe worktree created. Rank 1/2/3/6 remain built, merged and deployed; nothing on
the burn-down board is both ruled and unbuilt.

🟢 **Worth stating plainly: a ledger-only fix would NOT reset the rebuild.** Verified at
`precompute_calibration.py:6558-6568` — `_main_input_fingerprint()` hashes `inspect.getsource` of
exactly four functions (`compute_calibration_payload`, `_calibration_population_ctes`,
`_virtual_market_ctes`, `_main_futures_sql`), all defined in `precompute_calibration.py`, plus
`REPRESENTATIVE_TIE_AUTHORITY` and `COVERAGE_CENSUS_ENABLED` by value. Its own docstring states the
rule: *"hashing a function's source covers that function, never what it calls."* So
`calibration_phase_ledger.py`, `calibration_main_build.py` and `calibration_beat_gauge_sampler.py`
are **outside the digest**, and D-G's freeze — worded against
`backend/app/tasks/precompute_calibration.py` — does not cover them.

**That is a fact for Alex, not a licence taken.** This lane did not act on it. Note the caveat that
goes with it: a deploy still restarts the dyno, so it can interrupt an in-flight beat — but banked
units are durable in the cursor, so the cost is at most the current beat, not the 27 banked units.
CERT-657 itself moved the fingerprint because its branch also touched one of the four hashed
functions; the fence repair merely rode along.
