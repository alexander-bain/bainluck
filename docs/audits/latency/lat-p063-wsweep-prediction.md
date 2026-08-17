# LAT-P063 §W — the WARM_CONCURRENCY sweep: REGISTERED PREDICTION, written before the measurement

**Window:** latency lane cycle 35, `pid:12080`, 2026-08-17 PDT.
**Deployed at read time:** `/api/health` `commit = 29639b78`, Heroku **v3830**, released **14:33:17 PDT**.
**Committed BEFORE the sweep runs** (ruling 050). Grade this file's table against §W2 of
`lat-p063-warmer-graded.md`; do not re-derive the bars afterwards.

---

## Why this sweep exists, and why it is not a tuning exercise

LAT-P062 priced the warmer and the number is the reason this was promoted to a headline item:

| | pre-fix (LAT-P060, W=1) | post-fix (LAT-P062, W=4) |
|---|---|---|
| per-rebuild time | ~0.95 s | **~3.1 s** (124.3 s ÷ 40) |
| pass wall | 38.0 s median | **30.9 s median** |
| DB occupancy (fraction of wall-clock under a warmer pass) | 40 % | **73 %** |
| **warmer backend-equivalents** | 0.40 | **2.9** |

Production runs at ~3 ACTIVE backends. **The warmer at W=4 is a second production workload**, and it
exists to keep 8–40 typeahead prefixes warm. `WARM_CONCURRENCY`'s docstring justifies itself on the
claim that the pass is *"I/O-WAIT bound, which is the one case where concurrency overlaps waiting
instead of multiplying work."* The measurement says otherwise: **W=4 bought 1.2× wall and cost 3.3×
per-query inflation.** Work that merely overlaps does not triple.

The mechanism I am predicting from: 40 concurrent trigram scans against a **1 GiB `shared_buffers`**
contend for the very pages they are all trying to keep resident. `ix_futures_outcomes_name_trgm`
(406 MB) + `ix_futures_name_trgm` (172 MB) are **578 MB — 56 % of the pool**, measured at a **76.5 %**
hit rate (LAT-P061). Widening the fan-out over a working set that does not fit multiplies eviction,
it does not overlap waiting. So per-query cost should rise with W, roughly linearly over this range.

Fitting the two points we have — 0.95 s at W=1, 3.1 s at W=4 — gives `per_query ≈ 0.23 + 0.72·W`,
which predicts **~1.67 s at W=2**. That fit is two points and a straight line through them; it is
stated so it can be wrong in a legible way, not because it is trusted.

## The bound that decides how far this can go, derived not chosen

`period_s` is start-to-start and the floor makes it **`period ≈ max(seconds_wall, MIN_PASS_PERIOD=30)`**.
The response cache TTL is **45 s**. So the narrowing is bounded by arithmetic rather than by taste:

> **any W whose pass wall stays under ~40 s keeps the period under the 45 s TTL with margin.**

W=1's pre-fix wall was 38.0 s. That is *inside* the bound — which is why W=1 is on the table at all
and why this sweep is worth running rather than assuming 4 is the price of a warm head.

---

## §W1 — THE PREDICTION (ruling 050)

**Method, fixed in advance:** one head resolved ONCE and reused, so every arm warms the *identical*
query list; arms run **alternating 4 / 2 / 1, three times through** (ruling 076 step 2 — an
all-A-then-all-B run hands the second arm a cache the first arm loaded); medians over the three reps;
`seconds_total` **and** `seconds_wall` graded together, because §2's whole point is that they moved
in opposite directions.

⚠️ **Stated before the numbers exist:** this runs on a one-off dyno against production while the
**live W=4 warmer keeps running every ~32 s**. Absolute times are therefore inflated by a background
load I cannot switch off, and I am not claiming them as the warmer's true isolated cost. The
background load is *constant across arms*, so the **ratios** are the measurement and the absolutes
are context. Any conclusion that needs the absolute number is out of scope here.

| # | prediction | HALT |
|---|---|---|
| **W1** | per-query mean rises **monotonically** with W: `mean(W=1) < mean(W=2) < mean(W=4)` on the three-rep medians | **non-monotonic HALTS** — the contention model is wrong, concurrency is not what inflates the work, and the docstring's I/O-wait justification is back in play and must be re-argued rather than deleted |
| **W2** | `seconds_total` at W=2 is **40–70 %** of W=4's | outside that band ⇒ the linear-in-W fit is mis-specified. Not a halt — report the shape actually measured and refit |
| **W3** | `seconds_wall` at W=2 is within **±25 %** of W=4's | **> +50 % HALTS the W=2 ship** — narrowing would be buying DB relief with head duty cycle, which is the trade #1866 already lost once |
| **W4** | `seconds_wall` at W=1 is **1.1–1.6×** W=4's, i.e. **under the ~40 s TTL bound** | **≥ 45 s HALTS the W=1 ship outright** — the period would reach the TTL and the head goes cold between passes, which is the exact defect LAT-P062 fixed |

## §W2 — THE SHIP RULE, also written before the numbers

Stated in advance so the decision is not fitted to whatever comes back:

- **Ship W=2** if W1 holds, W3 holds, and W2's `seconds_total` is materially below W=4's. Rationale:
  it roughly halves the warmer's DB occupancy for a wall cost inside the instrument's own spread.
- **Ship W=1** only if **both** W4 holds with wall comfortably under 40 s **and** W=1's `seconds_total`
  is the lowest of the three. W=1 additionally removes the `AsyncSession`-per-worker fan-out entirely,
  which is a simplification and not only a saving.
- **Ship nothing** if W1 halts. A non-monotonic result means I do not understand the cost, and
  changing a production constant I cannot explain is how the docstring got its wrong justification in
  the first place.
- **Whatever ships, `seconds_wall` is re-read post-deploy against the 45 s TTL bound**, because the
  narrowing's whole risk is on that side and it is the one number that can undo LAT-P062's gain.

## §W3 — what this sweep deliberately does NOT measure

- **The head's composition or size.** BLOCKED on #1916 — both candidate head sources are our own
  automation.
- **`REFRESH_AHEAD_SECONDS`.** Proven inert by arithmetic in LAT-P062 §2; a sweep would move a knob
  that cannot move.
- **The tail.** Narrowing the warmer frees DB occupancy, and LAT-P062 established at a 95 % CI that
  freeing **44.6 MB/s** moved the typeahead tail **not at all**. Any tail improvement here would be a
  surprise, and is explicitly **not** predicted. Option D remains the tail's fix.
