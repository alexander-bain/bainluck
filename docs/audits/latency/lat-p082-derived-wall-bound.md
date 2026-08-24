# A DERIVED wall bound for `warm_typeahead` — design note, no code

**LAT-P082, 2026-08-23. Fable's item 5:** *"the derived-bound design note for the TTL question
(your sampled method is exhausted — noise at 110 % of headroom is a closed door, write up the
derived alternative, no code)."*

Nothing here changes behaviour. It is a design note and it ends at a decision Fable and Alex own.

---

## 1. Why the sampled method is exhausted — and it is not a matter of sampling harder

`MEASURED_WALL_MAX_S` has been re-derived four times, and each derivation proved the previous one
too low:

| window | value | correction |
|---|---|---|
| LAT-P063 | 42.6 s | — |
| LAT-P074 | 53.920 s | +11.32 |
| LAT-P075 | 61.282 s | +7.36 |
| LAT-P079 | 66.365 s | +5.08 |

LAT-P079 did the honest thing available to it: it stopped setting a point estimate, argued a
margin from the decay of those corrections (r ≈ 0.69, remaining tail ≈ 11.3 s, true max ≈ 77.7 s),
and labelled it an extrapolation from four points rather than a bound.

**But the exhaustion is structural, not statistical, and naming it is the whole point of this
note:**

> **A sampled maximum is a LOWER bound on the true maximum. The TTL question needs an UPPER
> bound. No number of samples converts one into the other.**

Every additional pass can only ever move `MEASURED_WALL_MAX_S` **up**. A window that observes no
new maximum has not shown the wall is bounded; it has shown that this window did not see the bad
case. So the instrument answers "at least this bad" forever, while the question being asked is
"never worse than what?".

Fable's "noise at 110 % of headroom" is the same fact in the other units. The live headroom is
`RESPONSE_CACHE_TTL_S − MEASURED_WALL_MAX_S = 65 − 66.365 = −1.365 s`, and the per-cycle
correction to the max has been 5–11 s. The correction term is larger than the quantity it is
correcting. That is a closed door: no read taken with this instrument can distinguish safe from
unsafe, because the instrument's own step size exceeds the margin it is measuring.

---

## 2. The derived alternative — the bound is already in the code, unenforced and unread

A pass is not an opaque duration. It is a **bounded work-stealing pool over a bounded head, with a
hard per-item timeout**, and all four quantities are constants this repo owns:

| symbol | meaning | where | value today |
|---|---|---|---|
| `N` | head size — items in a pass | `resolve_head(..., limit)` / ring `head_n` | **40** |
| `W` | pool width = session count | `_warm_head_concurrently`, `width = max(1, concurrency)` | **4** |
| `T` | per-item ceiling | `asyncio.wait_for(..., PER_QUERY_TIMEOUT_SECONDS)` | **10 s** |
| `TTL` | the cache the pass is filling | `RESPONSE_CACHE_TTL_S` | **65 s** |

`_warm_head_concurrently` is a shared-cursor pool: `W` workers pull from one iterator until it is
exhausted, one item in flight per worker (a hard invariant, because an `AsyncSession` is not safe
for concurrent use). That is **greedy list scheduling**, and greedy list scheduling has a closed-
form makespan bound:

```
    wall  <=  S / W  +  max_item          (Graham)
    S     <=  N * T                       (every item is timeout-bounded)

    ==>   WALL_BOUND  =  (N * T) / W  +  T
```

Substituting today's constants:

```
    WALL_BOUND = (40 * 10) / 4 + 10 = 100 + 10 = 110 s
```

**110 s is a bound, not an estimate.** It does not depend on a distribution, a sample size, a
horizon, or a quiet night. It holds on the worst day the system can have while its own timeout is
enforced.

### What it settles immediately, and permanently

```
    WALL_BOUND (110 s)  >  RESPONSE_CACHE_TTL_S (65 s)
```

**A single pass CAN outlast the cache it is filling. By construction. This was never a question
sampling was going to answer** — and it has now cost four cycles of trying, each of which produced
a number that was correct, honest, and unable to decide anything.

Note what this does *not* claim. The bound is loose: the observed max (66.365 s) is 60 % of it, and
it should be, because a bound that equals the observation is a bound that has stopped bounding. A
bound and an estimate are different instruments for different questions, and the four-cycle
failure was reaching for the estimate when the question wanted the bound.

---

## 3. Where the bound is currently a LIE, and it must be stated before it is used

`WALL_BOUND` is exact only for work that is actually inside the timeout. In `_warm_one`, it is
not all of it. Per item, outside `asyncio.wait_for`:

* a `TTL` read on the cache key (`ttl_before`);
* a `DELETE` of the cache key (`_drop_cached`), skipped only when the TTL read proved no key.

Both are synchronous Redis calls. `get_redis_client()` is bounded by default at a **5 s socket +
5 s connect timeout** (gotcha #39, and the reason that default exists at all), so the honest
per-item ceiling is:

```
    C  =  T  +  R * r        R = bounded Redis round-trips outside the timeout (2)
                             r = the client's socket timeout (5 s)
       =  10 + 10  =  20 s

    WALL_BOUND_STRICT = (N * C) / W + C = (40 * 20) / 4 + 20 = 220 s
```

Two bounds, and the gap between them is the design question:

* **`WALL_BOUND` = 110 s** — what the pass costs when Redis is healthy. The operative number.
* **`WALL_BOUND_STRICT` = 220 s** — what it can cost when Redis is degraded but not down. The
  number a *safety* argument has to use, because "Redis is slow" is exactly the condition under
  which the warmer matters most.

**The prologue Redis calls are outside the timeout that was supposed to bound the item.** That is
a defect in the shape of the code rather than in any constant, and it is worth fixing before the
bound is relied on, because a bound with a hole in it is worse than no bound — it invites the
comfortable number.

---

## 4. What makes this worth having: the bound is a LEVER, the sample was not

The sampled max moves only when production is unlucky. The derived bound moves when a constant
moves, and it moves deterministically — so the safety condition can be solved rather than waited
for.

Safety condition:

```
    (N * T) / W  +  T   <=   TTL
```

Solving for each lever with the other three held at today's values:

| lever | today | threshold for structural safety at TTL = 65 s | cost of moving it |
|---|---|---|---|
| `T` per-item timeout | 10 s | **T ≤ 5.9 s** | a slow query is abandoned sooner; more `timeout` outcomes, fewer warmed terms |
| `N` head size | 40 | **N ≤ 22** | 18 fewer warmed terms; the cold-rate work of #1866 is directly at stake |
| `W` pool width | 4 | **W ≥ 8** | 8 concurrent `AsyncSession`s per pass against a shared connection pool, on a `--concurrency=2` worker holding ~91 % of one slot already |
| `TTL` | 65 s | **TTL ≥ 110 s** | a staler answer served for longer; already raised 45 → 65 once (LAT-P075, Fable GO ruling 4) |

Four exact thresholds, all computable today, none requiring another observation window. That is
the difference this note is arguing for: **the sampled method could not even tell us we had a
problem; the derived method tells us the size of every available fix.**

Two things the table makes visible that no sampling round did:

* **`W ≥ 8` is the only lever that costs no product surface** — it does not shorten the head or
  stale the cache. It costs connections on a worker that is already the constrained resource
  (LAT-P076's occupancy census), so it is a trade between two measured scarcities rather than a
  free win. That is a real decision and it is now stated as one.
* **`T ≤ 5.9 s` is startlingly close to today's measured behaviour.** LAT-P081 recorded a
  real query at 4.7–10.4 s straddling the 10 s timeout and ranked 1 in real traffic, so cutting
  `T` to 5.9 s would begin abandoning the head's own slowest legitimate member. The lever exists;
  it is not free either.

---

## 5. What this note proposes, and what it explicitly does not

**Proposed — evidence and design only, per "no fix without its own gate":**

1. Replace `MEASURED_WALL_MAX_S` **as the safety input** with a derived `WALL_BOUND(N, W, T)`,
   computed from the constants rather than pinned from observation. Keep the sampled maximum, and
   keep publishing it — it is the right instrument for "is the beat getting worse", which is a
   trend question and genuinely wants a sample. It is the wrong instrument for "can this ever
   exceed the TTL", which is a safety question and wants a bound. **Two questions, two
   instruments, and the four-cycle failure was one instrument answering both.**
2. Move the two prologue Redis calls inside the per-item timeout, so `WALL_BOUND` and
   `WALL_BOUND_STRICT` converge and the bound stops having a hole in it.
3. Whatever ships, the gate is a **mutation** and not an assertion, for the reason LAT-P079 already
   paid for on M9: `assert flag == (max > ttl)` cannot tell a hardcoded `True` from a computed one.
   A derived bound must be shown to VARY with each of `N`, `W`, `T` — four parameterised cases,
   one per lever, each proving the bound moves in the right direction.

**Explicitly NOT proposed here:**

* **Any change to `N`, `W`, `T` or `TTL`.** This note computes thresholds; choosing among four
  levers that each cost something real is Fable's and Alex's call, and picking one inside the
  window that derived the arithmetic is choosing rather than measuring.
* **Withdrawing LAT-P079's margin.** `WALL_MAX_MARGIN_S = 11.3` remains the right treatment of the
  *sampled* series and its argument stands. This note says the series was answering the wrong
  question, not that it answered its own question badly.
* **Any beat-interval move.** `beat_schedule_change: false`, and the quantiser argument of
  doctrine clause 15 is untouched — the bound derived here is about a single pass's wall, which is
  an input to the period, never a substitute for it.

---

## 6. One line, if only one survives

**A sampled maximum is a lower bound and the TTL question needs an upper one — so the four
consecutive corrections were not a measurement getting better, they were the wrong instrument
being read more carefully.** The system already enforces a per-item timeout over a bounded head at
a fixed width, which is an upper bound sitting unused in the code, and it says 110 s against a
65 s TTL.
