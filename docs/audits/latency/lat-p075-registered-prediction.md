# LAT-P075 — REGISTERED PREDICTION (written BEFORE the discriminating measurement)

Registered 2026-08-19 ~20:00 PDT, before `/tmp/lat75-period-series.jsonl` had a single sample.
Discipline per Fable's LAT-P074 ruling: register before you measure, so a failed prediction is
visible rather than quietly absorbed.

## What is being discriminated

The period regression (42.5–51.7 s → 40.1–547.2 s) has two candidate mechanisms:

* **(A) run-lock contention** — beat fires, message arrives, task finds the run lock held by the
  still-running previous pass, and skips. Recorded as `skips.by_reason.lock`.
* **(B) `expires: 10` discard (#2014)** — beat fires, message is published, no worker slot is free
  within 10 s, broker discards it. The task **never runs**, so it records **nothing at all** —
  not a pass, not a skip. Invisible from the consumer side except as an absence.

Both produce a long gap between successful passes. They are distinguished by what happens to
`skips.total` **during** the gap.

## The predictions

**P1 — the stall signature is ABSENCE, not contention.**
During a stall longer than the pass wall (gap > ~65 s, so the lock is provably free for the tail
of it), `skips.total` will be **FLAT** across that tail. Concretely: for at least one gap ≥ 120 s,
`skips.total` will increase by **0** over the final ≥ 60 s of the gap.
*Confirms (B). Falsified if skips climb steadily through the whole gap — that would be (A), a
wedged/long-TTL lock, and #2014's attribution would be WRONG.*

**P2 — skips arrive only while a pass is in flight.**
`skips.total` increases by roughly `wall / interval` ≈ 4–6 per completed pass, and by ~0 otherwise.

**P3 — the vanished-fire fraction is large and matches the ratio.**
`starts / expected_fires` ≈ 0.25–0.36. Of a 10 s beat's fires, **≥ 60 %** never start at all:
they are neither passes nor skips. Cross-check already in hand from `recent_durations_ms`
(50 starts in 1981 s vs 198 expected = 0.25; 21 long ≥ 39 s = real passes, 29 short ≤ 250 ms =
lock skips).

**P4 — this is NOT the TTL's problem and the ratified 65 s does not move it.**
The fix must restore *delivery*, not extend *staleness*.

## Registered risk to the ratified TTL — flagged, not acted on

`PASS_ONLY_WALL_MAX_S = 53.920` was the basis for TTL = 65 s. The endpoint, now deployed and read
for the first time, reports **`seconds_wall.max = 61.282 s`** over 23 passes — 7.36 s above the
value the derivation used, exactly the "a maximum from a finite sample is a lower bound" failure
that already made `42.6` wrong by 11.3 s once.

65 − 61.282 = **3.72 s of headroom**, against a stated `SAFETY_MARGIN_S`. I predict 65 s will
**still grade SAFE but with materially less margin than the derivation claimed**, and that the
honest statement to Fable is that the ratified number survives on a thinner margin than the number
he ratified it on. TTL derivation is CLOSED by ruling 4 — this is a disclosure, not a re-derivation,
and I am not spending a cycle on it.
