# LAT-P074 item 3 — the TTL decision, derived, with its registered prediction

**Status: HALTED for Fable, as ruled.** Nothing in this document is shipped.
`RESPONSE_CACHE_TTL_S` is still 45 and `routes/events.py` still writes
`setex(_cache_key, 45, ...)`.

Fable, 2026-08-19:

> after a clean PASS-ONLY wall read via the new endpoint, derive the TTL per
> ruling 075 — TTL ≥ measured worst pass wall + margin, margin stated — and
> bring me the number with its registered prediction (cache-entry loss goes to
> zero; staleness cost bounded and named) and halt.

---

## 1. THE NUMBER: **65 s**

| quantity | value | where it came from |
|---|---|---|
| worst measured pass wall | **53.920 s** | pass-only, n=17+6, §2 |
| quantised period at the live 10 s beat | **60 s** | `10 × ceil(53.920/10)` |
| margin | **5 s** | `SAFETY_MARGIN_S`, the module's OWN existing constant |
| **derived TTL** | **65 s** | 60 + 5 |
| Fable's literal reading (wall + margin) | 59 s | carried, and refused — see below |
| current | 45 s | |

**65, not 59 or 60, and the reason is arithmetic rather than taste.** An entry
is rebuilt once per PASS, so what it has to survive is the gap from one rebuild
to the next — the pass PERIOD — and the period is the wall **quantised up** to
the next beat fire (`quantised_period_s`, the equation LAT-P062 measured
directly). At the live 10 s beat, a 53.920 s worst wall means a 60 s period. A
59 s or 60 s TTL therefore sits **at or below the period it is supposed to
cover**, and `grade_beat_interval` returns `MARGINAL` with zero headroom at
both — precisely the "coincidence of arithmetic" `SAFETY_MARGIN_S` was written
to refuse.

```
TTL  45s -> live 10s beat: UNSAFE     P(median)=50s  P(worst)=60s
TTL  59s -> live 10s beat: MARGINAL   P(median)=50s  P(worst)=60s   <- Fable's literal number
TTL  60s -> live 10s beat: MARGINAL   P(median)=50s  P(worst)=60s
TTL  65s -> live 10s beat: SAFE       P(median)=50s  P(worst)=60s   <- the recommendation
```

**65 s is the first value at which the live beat has ever graded SAFE.** The
margin is not chosen after seeing the answer: it is the constant this module
already uses to separate SAFE from MARGINAL, reused unchanged.

---

## 2. The pass-only wall, measured — and `42.6` was wrong by 11.3 s

`MEASURED_WALL_MAX_S = 42.6` was registered as a known underestimate by
LAT-P073 §5. The number LAT-P073 reached for instead (a 44.6 s p95) was worse:
a percentile over a **mixed** distribution of real passes and ~10 ms no-ops,
and no-ops only drag a percentile down.

The clean split needed no judgement call. `warm_typeahead`'s duration history is
bimodal with a **460× gap and nothing in between**:

```
read 2026-08-20T00:15Z, GET /api/admin/celery/task-metrics/warm_typeahead
saturated 50-sample ring, 1,261 s window

  no-ops (n=33):   9 .. 71 ms
  passes (n=17):   32,852 .. 48,939 ms
```

Six further passes were sampled directly off `last_result_summary` over
00:15–00:31Z, one of which reached **53.920 s**.

```
PASS-ONLY WALL     min 32.852 s   p50 40.991 s   p95 47.862 s   max 53.920 s
NO-OP              max 0.071 s
```

### The consequence, which is why the constants were NOT swapped

Substituting the measured **median** (40.991 s) into `MEASURED_WALL_MEDIAN_S`
flips the LIVE 10 s beat from `MARGINAL` to `UNSAFE`: P(10) = 50 s, over the
45 s TTL on a **typical** pass and not merely on the tail.

That is a production finding requiring this TTL decision, not a constant edit
smuggled in on a measurement commit — ruling 075's shape, where a derivation
whose inputs have moved emits a visible refusal instead of quietly re-deriving.
So the measurement ships as `PASS_ONLY_WALL_*` with its provenance, the adopted
constants are untouched, and the consequence is **pinned by two tests** rather
than written down:

* `test_the_pass_only_measurement_grades_the_live_beat_unsafe`
* `test_the_ttl_that_returns_the_live_beat_to_safe`

Swapping the constants is the first thing to do once the TTL is ruled.

---

## 3. 🔴 THE REGISTERED PREDICTION, AND IT DOES NOT HOLD IN FULL

Fable asked for the prediction "cache-entry loss goes to zero". **Registered
honestly, it splits in two, and the second half is the finding of this window.**

### The dose-response curve, measured, six passes

`expired` is the warmer counting entries whose cache key was **already gone**
when the pass reached them — i.e. cache-entry loss a user typing that prefix
paid for. Against the measured pass period:

| pass period | `expired` (of 40) |
|---|---|
| 40.102 s | **0** |
| 49.897 s | **1** |
| 196.240 s | **40** |
| 236.937 s | **40** |
| 275.923 s | **40** |
| 294.663 s | **40** |

Monotone, and a step rather than a gradient — LAT-P063's 20-for-20 result
reproducing exactly. **Four of six passes find the ENTIRE 40-entry head dead.**

### P1 — holds. Loss goes to zero in the healthy period regime.

At 65 s, every pass with a period ≤ 60 s loses nothing. Measured: the 40.1 s and
49.9 s passes, `expired` 0 and 1. `derive_response_ttl_s` returns `SUFFICIENT`
for both.

### P2 — DOES NOT HOLD. The TTL cannot touch the stalled regime.

At 65 s, a pass arriving 196–295 s after the last one still finds all 40 entries
dead. Driving loss to zero across the **observed** distribution needs
`TTL ≥ 300 s` — a five-minute-stale typeahead, which is a different
conversation and is **not** recommended here.

`derive_response_ttl_s(measured_period_s=294.663)` returns
`INSUFFICIENT_FOR_PREDICTION`, by design: the number is real, the claim attached
to it is not, and a derivation that returns a number it knows will miss its own
prediction is the frozen-config family wearing a new coat.

### P3 — the staleness cost, bounded and named

At 65 s an entry may be up to **65 s** old instead of 45 s: **+20 s** of
worst-case staleness on typeahead suggestions. Fable's own framing prices this
at zero — *"typeahead entries being 90 s stale is invisible; typeahead going
EMPTY is not"* — and 65 is well inside 90.

There is no second cost. The TTL is a `setex` argument on the response cache; it
does not touch the beat, the pass period, `WARM_CONCURRENCY`, the run lock, or
the database. Rollback is the same one-line change in reverse.

### Honest payoff, since P2 fails

At the observed 2-of-6 healthy-regime rate, a 65 s TTL removes cache-entry loss
on roughly **a third** of passes. It is cheap, it is reversible, and it is the
first change that makes the live beat grade SAFE — but it is not the fix.

---

## 4. 🔴 What the derivation found instead: the PERIOD has regressed 4–6×

The binding quantity is the period, and it is no longer what this program
believes it to be.

| | period |
|---|---|
| LAT-P062, two production reads | 42.5 – 51.7 s |
| **LAT-P074, six production passes, 2026-08-20T00:15–00:31Z** | **40.1 – 294.7 s, p50 216.6 s** |

A 216 s median against a 45 s TTL means the warmed head is cold for roughly
**80 % of every cycle**, and #1866's own number for what a user then pays is
**1.16 – 2.29 s p50** against a `<150 ms` budget. This is the user-felt cliff
Fable promoted #1866 for, and it is deeper than the 0.4 s margin suggested.

### The mechanism is already filed, and it is bigger than its issue says

`warm-typeahead` carries **`expires: 10`** — one beat interval — and a pass runs
~47 s. Every message published during a pass is therefore discarded before the
worker can reach it, and the warmer only runs again when a message happens to
land in a ≤10 s window while the `background` pool is free. It competes for that
window with the three other long beats that also carry `expires`.

The 4/4 correlation replicated for a **third** time on this window's read, a day
after LAT-P073 found it, and still with zero false positives in either
direction:

| beat | `expires` | ratio |
|---|---|---|
| `warm_typeahead` | 10 s | **0.38** (`overruns`) |
| `warm_event_concepts` | 300 s | **0.32** (`behind`) |
| `refresh_open_commentary` | 180 s | **0.30** (`behind`) |
| `precompute_discover_candidate_base` | 120 s | **0.27** (`behind`) |
| `poll_live_prediction_markets` | none | 0.99 |
| `poll_all_odds` | none | 1.00 |

Every one of the 3 `behind` verdicts and the only sub-0.6 `overruns` verdict
carries `expires`; nothing without `expires` reads below 0.99.

**#2014 is filed as a p2 misattribution — "a scheduler verdict for a delivery
policy". The measured cost says it is #1866's mechanism.** No policy change is
proposed here: Fable ruled that #2014 does not move until the instrument reads
it directly, and the one thing still missing is a direct observation of an
expiry event. The endpoint shipped this window supplies the other half — skip
counters distinguish "wedged behind its own lock" from "never got a message",
which is the discriminator the stall diagnosis needs.

### Recommendation, stated as a comparison rather than a request

| lever | removes loss on | cost | status |
|---|---|---|---|
| TTL 45 → 65 s | ~1/3 of passes | +20 s staleness, one line | **derived, halted, Fable's call** |
| the period regression (`expires: 10`) | the other ~2/3 | unknown until diagnosed | **held on #2014's instrument** |

The TTL is worth doing and is not the fix. Both are Fable's, and this window
ships neither.

---

## 5. Provenance

* Pass-only wall + no-op ceiling: `GET /api/admin/celery/task-metrics/warm_typeahead`,
  2026-08-20T00:15Z, saturated 50-sample ring / 1,261 s window.
* Six pass summaries with `period_s` and `expired`: `last_result_summary`
  sampled at 20 s, deduped on `last_success_at`, 2026-08-20T00:19–00:31Z.
  Series: `docs/audits/latency/lat-p074-warmer-passes.jsonl`.
* Adherence correlation: `GET /api/admin/celery/schedule-adherence`,
  2026-08-20T00:3xZ, 106 graded entries.
* Code: `app/utils/typeahead_beat_budget.derive_response_ttl_s`,
  `app/utils/typeahead_pass_ring.py`, `GET /api/admin/typeahead-warmer/last`.
* Tests: `backend/tests/test_typeahead_pass_ring.py` (30), 12 mutations.

**Sample-size caveat, stated because every margin here inherits it:** the wall
maximum stands on 23 passes and the period distribution on 6. A maximum drawn
from a finite sample is a LOWER bound on the true maximum — which is exactly how
42.6 s came to be wrong by 11.3 s. The endpoint shipped this window exists so
that the next derivation reads a live distribution instead of a constant.
