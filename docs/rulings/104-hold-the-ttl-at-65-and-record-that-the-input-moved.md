# RULING 104 — Hold the typeahead TTL at 65 s, and record that its input moved

date: 2026-08-20
author: Alex (via Fable directive 2026-08-20)
issues: #1866

**HOLD 65.** The typeahead response-cache TTL stays at the ratified 65 s. `MARGINAL` is the
honest grade for it and is recorded as the grade. The foreclosure on re-deriving the TTL
upward stands. **The TTL was never the repair.**

## What was ruled on, stated so it cannot be read as an oversight

LAT-P075 shipped TTL 45 → 65 under GO ruling 4, and disclosed in the same commit that the
number's own input had moved between derivation and shipping:

| | value | n |
|---|---|---|
| derived from | `PASS_ONLY_WALL_MAX_S = 53.920` | 17 |
| first read of the deployed instrument | **61.282 s** | 26 |

At 53.920 the grader returns SAFE, which is what the ratification cites. At 61.282 the same
grader returns **MARGINAL**; 75 s would be SAFE.

**That move was seen, reported, and ruled on. It is not smoothed and it is not a defect in the
ratification.** The premise changed after the decision and the decision holds anyway, which is a
different thing from a decision taken on a premise nobody checked. This ruling exists so that a
future window reading `MARGINAL` beside a ratified 65 does not conclude the ratification was
stale and "fix" it.

## Why holding is right even though 75 would grade SAFE

Because the grade is not the objective. Reaching SAFE by raising the TTL buys head-cold
coverage by serving staler entries, and the arithmetic says it cannot buy much: at the measured
period distribution the time-weighted head-cold rate is 49.7 % at TTL 45 and 38.9 % at TTL 65.
**Zeroing it needs TTL ≥ 553 s.** A TTL chosen to survive a regressed period is a decision to
serve stale data in place of fixing the period, and it converges on that answer by increments,
each of which looks locally reasonable.

The binding defect is the **period** — p95 176.5 s, max 326.3 s against the cliff — and the
period's cause is capacity on the `background` queue. The TTL is a mitigation with a ceiling,
and it has been raised to that ceiling's useful edge. Further movement is the wrong lever
applied harder.

## The general clause

**A sampled maximum is a lower bound, and a threshold derived from one inherits that.** This is
the third time in this program a sampled max proved low: 42.6 → 53.9 → 61.3. A margin over a
sampled max is not a safety margin; it is a bet that the sample saw the tail. State the margin,
state that the input is a lower bound, and do not treat a later upward revision as a regression
in the estimate — it is the estimator behaving as designed.

## What is pinned

- `test_the_ring_wall_grades_the_ratified_ttl_marginal` goes red if anyone edits
  `RING_WALL_MAX_S` down, or re-derives the TTL upward to reach SAFE.
- The TTL derivation is **CLOSED**. It is not this lane's to chase and not the next window's to
  re-open. A window that believes it should be re-opened brings the case to Alex; it does not
  bring a new number.
