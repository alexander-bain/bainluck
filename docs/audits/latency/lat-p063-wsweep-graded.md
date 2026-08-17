# LAT-P063 §W2 — the W-sweep, MEASURED: three rows pass, the ship is REFUSED anyway, and the refusal is the useful result

**Graded against** `lat-p063-wsweep-prediction.md`, committed at `804f143d` **before any arm ran**.
**Method as registered:** one head resolved once and reused; arms alternating **4 / 2 / 1 × 3**;
`seconds_total` and `seconds_wall` graded together. **9 arms, 8 of them rebuilding all 40 entries.**
Raw: `lat-p063-wsweep2-arms.json`.

---

## §W2.0 — The first sweep was WRONG, and catching it is why there was a second

The first run (`lat_p063_wsweep_*`) produced a beautifully monotonic per-query series — 0.912 s at
W=1, 2.331 s at W=2, 3.972 s at W=4 — which is exactly the answer the prediction expected. **It was
an artefact of the instrument and it would have shipped a narrowing on a number that measured
nothing.**

The arms ran 4 s apart; `_warm_one` skips any entry whose TTL exceeds `REFRESH_AHEAD_SECONDS = 35`.
So each arm inherited the previous arm's fresh keys and **the arms did not do the same work**: W=4
rebuilt 40, W=2 rebuilt 22, **W=1 rebuilt 8**. The "per-query mean" divided by `n = 40` in every arm,
so the W=1 figure was 32 near-zero skips diluting 8 real rebuilds. Normalised per *rebuild* the same
data reads **3.97 / 4.24 / 4.56** — flat in W, and rising with **time** rather than concurrency.

The second sweep forces every arm to rebuild by passing `refresh_ahead = 10**6`, and reports
`fresh` so the fix is visible in the artifact rather than asserted. `fresh: 0` on all nine arms.

**This is the same failure class as ruling 076's**: a number that looks like a comparison, produced
by two arms that were not doing comparable work. The planner-cost gate compared two statements; the
first sweep compared two workloads. Both pass their own arithmetic and neither measures the thing.

## §W2.1 — The measurement

| rep | W | wall (s) | total (s) | rebuilt | wall/rebuild | **DB-work/rebuild** |
|---|---|---|---|---|---|---|
| 1 | 4 | 73.2 | 276.3 | 35 | 2.092 | 7.896 |
| 2 | 2 | 78.0 | 155.1 | 40 | 1.949 | 3.876 |
| 3 | 1 | 115.2 | 115.2 | 40 | 2.880 | 2.880 |
| 4 | 4 | 45.8 | 177.6 | 40 | 1.145 | 4.440 |
| 5 | 2 | 52.2 | 102.9 | 40 | 1.305 | 2.573 |
| 6 | 1 | 121.2 | 121.2 | 40 | 3.029 | 3.029 |
| 7 | 4 | 57.2 | 218.6 | 38 | 1.506 | 5.752 |
| 8 | 2 | 74.8 | 149.2 | 40 | 1.869 | 3.730 |
| 9 | 1 | 55.2 | 55.2 | 40 | 1.380 | 1.380 |

**Medians over three reps, normalised per rebuild** (rebuild counts differ on two arms, so raw walls
are not comparable and are not compared):

| W | wall/rebuild | DB-work/rebuild | vs W=4: wall | vs W=4: DB work |
|---|---|---|---|---|
| 1 | **2.880** | **2.880** | **1.91×** | **0.50×** |
| 2 | **1.869** | **3.730** | **1.24×** | **0.65×** |
| 4 | **1.506** | **5.752** | 1.00× | 1.00× |

| # | prediction | measured | verdict |
|---|---|---|---|
| **W1** | per-query cost rises monotonically with W | **2.880 < 3.730 < 5.752** | ✅ **PASS** |
| **W2** | `seconds_total` at W=2 is 40–70 % of W=4 | **64.8 %** | ✅ **PASS** |
| **W3** | `seconds_wall` at W=2 within ±25 % of W=4 | **+24.1 %** | ✅ **PASS — by 0.9 points** |
| **W4** | `seconds_wall` at W=1 is 1.1–1.6× W=4, under the ~40 s bound | **1.91×**, scaled live **61.6 s** | ❌ **FAIL — and HALTS the W=1 ship** |

**W1 passing settles the docstring question the directive asked about.** `WARM_CONCURRENCY`'s comment
justifies itself on the pass being *"I/O-WAIT bound, which is the one case where concurrency overlaps
waiting instead of multiplying work."* Work that merely overlaps does not get **1.9× more expensive
per unit** going from W=1 to W=4. The contention model is right and the docstring's stated reason is
wrong — **but the docstring's conclusion turns out to be right anyway**, for the reason in §W2.2.

## §W2.2 — Why the ship is REFUSED even though W=2's three rows passed

By the letter of my own registered ship rule — *"Ship W=2 if W1 holds, W3 holds, and W2's
`seconds_total` is materially below W=4's"* — **W=2 ships.** All three hold.

**I am refusing it, and the conflict is a gap in my own pre-registration rather than a change of
mind.** Three paragraphs above that ship rule, the same document derives the bound that actually
governs:

> `period ≈ max(seconds_wall, MIN_PASS_PERIOD = 30)` against a **45 s** TTL, so **any W whose pass
> wall stays under ~40 s keeps the period under the TTL with margin.**

Scaling W=2's measured **1.24×** onto the live warmer's pre-sweep median wall of **32.2 s** gives
**40.0 s** — *exactly* at the bound, not under it. And the median is the wrong statistic against a
hard threshold: this window measured live W=4 walls spanning **29.4–42.6 s** (n=13). Scaled by 1.24
that band becomes **36.5–52.8 s**, and **the upper half of it is over the TTL.**

**What makes that decisive rather than cautious is Item 0 row 4, measured this same window:** across
20 passes, **every** pass with `period_s > 45` lost entries (up to 39 of 40) and **not one** pass
under 45 s lost any — 20 for 20. Crossing the TTL does not degrade the head gradually. It empties it.
So W=2 would trade a 35 % cut in warmer DB work for a pass that breaches the TTL on its bad minutes,
and the bad minutes are precisely when the head matters.

My ship rule's conditions were about DB cost and wall *central tendency*. It never said the wall
*distribution* must clear the TTL, and it should have. **The bound wins, because the bound is what
protects the gain Item 0 just measured.**

**Verdict: SHIP NOTHING. `WARM_CONCURRENCY = 4` stays, and its docstring gets a corrected reason,
not a corrected value.**

## §W2.3 — The answer to what the directive actually asked

> *"A warmer that costs three backends to save the head is a trade Alex should see priced."*

**Priced, and the price is not discretionary.** The concurrency is not padding — it is what holds the
pass wall under the response TTL. The sweep says W=4 buys a **1.91×** shorter pass than W=1 and a
**1.24×** shorter pass than W=2, and the TTL is 45 s against a live wall already at 32 s. **There is
no cheaper W that keeps the head warm.**

One further measurement sharpens this, and it argues the same way: **concurrency's benefit GROWS with
load.** On the two lightest-load arms (reps 4 and 9) W=1's wall/rebuild was 1.380 against W=4's 1.145
— only **1.21×**. On the heaviest (reps 1, 3, 6) it was 2.880–3.029 against 2.092 — **1.38–1.45×**.
A narrower warmer would look fine in the quiet minutes and fail in the busy ones, which is the
opposite of the robustness a warmer exists to provide.

**So the warmer's 2.9 backend-equivalents are not reducible by tuning. They are reducible only by
removing the need for the warmer** — and that is Option D
(`lat-p063-option-d-mechanism-and-prediction.md`), which replaces a **688.6 MB** trigram surface with
a **~140 MB** one that stays resident without anything holding it there. **The W-sweep's real result
is that it closes the last cheap alternative to Option D.**

## §W2.4 — Honest limits, and what would settle W=2

- **Absolute times are inflated** and were declared so in advance: every arm ran on a one-off dyno
  while the live W=4 warmer kept running, so the database saw up to 8 concurrent warmer sessions. The
  **ratios** are the measurement; the 40.0 s figure is a ratio scaled onto a separately-measured live
  wall, not a direct reading. Cross-check that it is not nonsense: my W=4 arm measured **45.8 s** and
  the live warmer's concurrent wall median was **44.7 s** — the instrument agrees with the thing it
  is modelling to within 2.5 %.
- **n = 3 per arm, with a 2.2× spread inside the W=1 arm** (1.380 to 3.029). That spread is load, not
  noise in the timer, but it is wide enough that W=2's +24.1 % has a real interval around it.
- **W=2 is not refuted, it is unproven against the bound.** What would settle it: a paired sweep with
  the **live warmer paused** (so the wall is the real one rather than a scaled estimate), **n ≥ 5**
  per arm, graded on the wall's **p95 against 45 s** rather than its median against 40 s. That needs
  a pause switch the warmer does not have, which is itself a small, honest ask.
- **Not measured, deliberately:** the tail. Narrowing frees DB occupancy, and LAT-P062 established at
  95 % CI that freeing 44.6 MB/s moved the typeahead tail not at all.
