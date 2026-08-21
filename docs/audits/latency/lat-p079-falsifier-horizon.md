# LAT-P079 — the falsifier could not see its own subjects, and graded before its own horizon

Cycle 51. Issues **#2071**, **#1609**, **#1866**, **#2072**. Branch `program/latency-72`,
stacked on the unmerged `-71`.

---

## 0. Phase 0, and it deletes two of the queue's four items before they start

| clock | reading | consequence |
|---|---|---|
| build (`/api/health`) | `0c7ccdf2`, up **28 min** | ≥6 h user-felt read impossible |
| worker (`heroku ps`) | all six dynos up **2026-08-21 09:09:01 PT**, 28 min | ≥6 h worker read impossible |
| `-71` merged? | **NO** — `merge-base --is-ancestor 5bd98dc8 origin/master` fails | #1866's fix is not live |
| `head_source` on the live ring | `redis:search:trending:24h` | **the fix is not live, confirmed from the INSTRUMENT** |

So **item 1 (grade #1866's P1–P4) is REFUSED**, per its own acceptance criterion: *"If
`head_source` is still `redis:search:trending:24h`, the fix is not live and nothing below is
gradeable. Say so and stop; do not grade a null."* The 14× head-membership gap (0.235 s in-head
vs 3.350 s out-of-head) therefore **remains the user-felt number**, unchanged from LAT-P078.

And **item 4 (R2 at a ≥6 h worker horizon) is not obtainable** for the fourth cycle running.
v3881→v3882 was a 17.8 h gap that LAT-P078 consumed; v3882 restarted every dyno 28 min before
this window opened. Per item 4's own instruction the sampler was started **at Phase 0** rather
than planned for later — `/tmp/lat79-horizon-series.jsonl`, 5-minute cadence, capturing the ring,
the falsifier, both movers read directly, and the deployed commit, so a crossing is captured
whenever it happens and a mid-window deploy is *visible in the series* rather than inferred.

---

## 1. 🔴 THE HEADLINE — the movers were never read, so `samples: 0` was a constant

The staged fix for the missing horizon gate was *"`movers[*].samples == 0` ⇒ `INCONCLUSIVE`"*.
Before implementing it, the payload was checked against production. The movers reported:

```json
"successes_24h": null,  "failures_24h": null,  "samples": 0
```

**`null`, not `0`.** A task that had genuinely never run would report `0` from the counter. `null`
is the signature of a key that was never fetched. Read directly, at the same instant:

| task | metrics name | successes_24h | failures_24h | samples |
|---|---|---|---|---|
| `backfill_market_shapes` | `market_shape_backfill` | **29** | 2 | **50** |
| `precompute_backfill_progress` | `precompute_backfill_progress` | **44** | 0 | **50** |

The route built its observation dict from `{b.metrics_name for b in PRE_MOVE_BASELINE}` — the
seven **protected** beats — and then interrogated that same dict about the two **movers**, which
are not in it and never were. `movers[*].samples` was `0` **by construction, permanently,
whatever the movers were doing.**

**Two consequences, and the second is the reason this is the headline.**

1. **LAT-P078's conclusion was wrong.** It read `samples == 0` and wrote *"neither moved task has
   run on `heavy` at all"*. The number is a constant. Its verdict — that HOLD was not a pass —
   survives on its other evidence (three of seven observed p50s equalling their own baselines to
   three decimals), and that evidence is sufficient on its own. The mover clause is withdrawn.
2. **The staged fix would have created the mirror defect.** Against the unrepaired read,
   `movers[*].samples == 0` is **never false**. Shipping it would have turned a gate that could
   not go red into a gate that could not go green — identical bytes on the dashboard, opposite
   meaning, same wrong-gate class, minted by the fix for that very class. This is why Fable's
   directive requires the disjoint-baseline repair *in the same pass*: a falsifier that cannot
   observe its subjects satisfies nobody.

`READ_SET` is now the union of protected beats and movers, and
`test_the_panel_reads_its_own_subjects` asserts the containment. A source-shape guard,
`test_the_route_reads_the_full_read_set_not_just_the_baseline`, asserts the ROUTE uses it — the
defect lived in the route, so a module constant alone would not prevent its return.

The sampler records both readings side by side in every record, which is the artifact:

```
2026-08-21T17:04:11Z  falsifier HOLD | panel samples [0, 0] | DIRECT runs [33, 46]
```

---

## 2. The horizon gate — and it is EXACT, not estimated

### 2.1 What was wrong

`recent_durations_ms` is a 50-deep ring; `successes_24h` is a 24 h counter. Seven minutes after a
move, both are ~99.5 % pre-move data. `INCONCLUSIVE` fired only when *nothing* could be graded; it
never fired when *everything* was graded **against pre-move data**, which is the common case for
any read taken after a deploy.

### 2.2 The first design, and why it was not good enough

The first implementation derived a lower bound on post-move runs from the 24 h counter: the
counter's window lies wholly after the move only once `age ≥ 24 h`, and before then it supplies
**no bound at all** (every one of those runs could predate the change). Correct, and it is
retained as `post_move_runs_lower_bound`.

But replaying real production observations through it exposed the cost. At a **hypothetical 25 h**
horizon the protected beats' rings would still be only:

| beat | post-move share of its ring at +25 h | time to a majority |
|---|---|---|
| `precompute_calibration_main` | 36 % | ~2.9 days |
| `compute_fair_fight_comparison` | 4.9 % | ~20 days |
| `precompute_source_intelligence` | 4.5 % | ~22 days |
| `compute_time_horizon_calibration` | 2.3 % | ~43 days |

So the honest gate would have reported `INCONCLUSIVE` **for weeks** — leaving ruling 110's grant
unwatched, which is the one thing the ruling says must not happen (*"cheap to grant and cheap to
revoke; what it is not is safe to grant unwatched"*).

### 2.3 The fix: the stamps were already there and were being thrown away

`_push_duration` writes `f"{duration_ms}|{int(ts)}"`. `get_task_metrics` **parsed the timestamp
and discarded it**, exposing only the durations and an aggregate window. So every "did this sample
postdate X?" question in the codebase had to be answered by estimate from a 24 h counter — for a
fact sitting in the data.

`recent_durations_at` is now exposed: newest-first, **positionally aligned** with
`recent_durations_ms`, and `None` for the pre-LAT-P040 bare form. Alignment is the load-bearing
half — the old parse appended stamps only when present, so a single legacy entry would have
shifted every later stamp onto the wrong duration. Pinned by
`test_a_legacy_unstamped_entry_holds_its_position_as_None`.

The falsifier now **grades on the post-move samples alone**, once there are
`MIN_POST_MOVE_SAMPLES = 8` of them. No ring turnover is required and no majority is needed,
because the pre-move samples are no longer in the statistic. Eight is a judgement, stated: it is
where the median stops being one observation wearing a statistic's name, and where a single
outlier cannot carry it across a threshold as generous as 1.25×.

The 24 h-counter path survives as the **documented fallback** for an unstamped ring — which is a
different fact from "no post-move samples" and is labelled as such in the verdict's reason string
(#53).

### 2.4 Verified against the real payload

The same production bytes that produced `HOLD`, replayed through the repaired grader
(`docs/audits/latency/lat-p079-falsifier-replay.json`):

```
BEFORE:  HOLD          "4 of 7 watched beats graded, none degraded"
AFTER:   INCONCLUSIVE  "4 of 7 watched beats are still PRE-HORIZON 0.7h after the
                        routing change — their p50s are drawn mostly from pre-move
                        samples, so grading them would compare the distribution
                        against itself. This is NOT evidence the move is safe."
```

### 2.5 The mirror defect is tested for, explicitly

`test_the_horizon_gate_CLEARS_and_is_not_a_gate_that_can_never_go_green` — same observations,
later clock, verdict must change `INCONCLUSIVE → HOLD`. And
`test_a_pre_horizon_beat_cannot_fire_a_spurious_revert_either`: the horizon test runs **before**
the ratio, so a pre-horizon beat cannot produce a false REVERT either. The gate protects the grant
from false revocation exactly as it protects the calibration lane from a false clean bill.

⚠️ This was the **fourth** instance of "a gate that cannot go red" in this program, and the
attempt to fix it nearly minted the **fifth**. Fable's instruction to treat the pattern as the
finding is the correct reading: the recurring shape is *an instrument reporting confidently about
something it never measured*, and it is the same shape as gotcha #53 one level up.

---

## 3. Item 2 — ruling 110's P1 and P2 are RETIRED, by name, with the arithmetic

LAT-P077 §4 registered four predictions for the `heavy` move, to be graded at a ≥6 h horizon.

| # | prediction | disposition |
|---|---|---|
| **P1** | period p95 falls below 200 s (from 292.7 s) | 🔴 **RETIRED** |
| **P2** | passes-with-loss falls below 20 % (from 24 %) | 🔴 **RETIRED** |
| **P3** | period p50 does NOT materially move (the control) | **STANDS** |
| **P4** | the movers' 24 h run counts rise toward schedule (31/72, 45/96) | **STANDS, and PROMOTED** |

**Why P1 and P2 are retired, and it is not only that the null already meets them.** LAT-P078
measured 90.6 s and 19 % with the routing **not deployed** — so both thresholds were already
satisfied pre-move and would have been credited to the intervention. That alone disqualifies them.

But re-deriving them against a same-horizon null does not rescue them either, and the arithmetic
says why. Period p95 has been measured at **176.5 s, 292.7 s, 90.6 s** and **105.6–116.5 s** in
this window — a between-window spread of **3.2×**. The predicted effect is `background` shedding
**~19 % of one of two slots**, i.e. utilisation ~0.90 → ~0.81, which queueing arithmetic turns
into roughly a 2× change in mean wait. **A statistic whose between-window spread exceeds the
effect being measured cannot discriminate that effect at one window per arm.** Re-deriving the
threshold would produce a number that still could not fail for the right reason.

So the honest disposition is retirement, not re-derivation, and the replacements are chosen for
**exactness** rather than for reading well:

* **P4 is promoted to primary.** It was always the only discriminating member of the set — the
  movers' 24 h run counts are exact integers, not percentiles, and the predicted change is large
  (31→72, 45→96). It is now **computed in the payload** (`movers[*].p4` ∈ `rose` /
  `flat_or_fell` / `pre_horizon` / `unreadable`) against `MOVER_PRE_MOVE`, pinned from the ruling.
  It **can fail**: if the counts do not move, the starvation story behind ruling 110 was wrong.
* **P5 (new):** at a horizon where the falsifier is no longer `pre_horizon`, its verdict is
  `HOLD`. This can fail in two distinct ways — `REVERT` (the grant is revoked) and, since this
  commit, `INCONCLUSIVE` (the instrument cannot speak, which is explicitly not a pass).

`test_p4_can_pass_and_can_fail` asserts both directions; `test_p4_is_gated_by_the_same_horizon_as_everything_else`
asserts it is not gradeable minutes after the move, because a 24 h counter read then is a fact
about yesterday.

**First P4 reading, and it is `pre_horizon` as it should be:** 33 and 46 runs against pre-move
31 and 45, at a 0.9 h horizon whose counters straddle the move. Directionally flat; not gradeable;
recorded as not gradeable.

---

## 4. Item 3 — `MEASURED_WALL_MAX_S` re-derived, and it retracts a result of this lane's

Owed for three cycles. The constant read **53.920 s** against a measured **66.365 s**.

| cycle | value | correction |
|---|---|---|
| LAT-P063 | 42.6 s | — |
| LAT-P074 | 53.920 s | +11.32 |
| LAT-P075 | 61.282 s | +7.36 |
| LAT-P078 | **66.365 s** | +5.08 |

**The margin is argued, per ruling 075.** The corrections decay geometrically at a stable ratio
(7.36/11.32 = 0.650; 5.08/7.36 = 0.690). At r = 0.69 the remaining tail sums to **11.3 s**, so the
true maximum is estimated at **~77.7 s**. `WALL_MAX_MARGIN_S = 11.3` records that. It is an
extrapolation from four points, labelled as one; what it is good for is refusing a fifth point
estimate, since each of the last three cycles needed a correction larger than any margin below it.

🔴 **The consequence is a retraction.** At the honest wall the live 10 s beat grades **MARGINAL,
not SAFE**: P(10) = 10 × ceil(66.365/10) = **70 s** against a **65 s** response TTL. LAT-P075's
*"the grader's default answer for the live 10 s beat is SAFE for the first time in this program's
history"* is **WITHDRAWN** — it was a property of a stale constant, not of production. Its test is
renamed to what it now pins.

**Not** retracted: the TTL 45 → 65 raise. It was ratified on an explicitly stated MARGINAL grade
and it still bought real headroom.

**The old guard was the wrong-gate defect again.** `assert MEASURED_WALL_MAX_S <
RESPONSE_CACHE_TTL_S` stayed green for three cycles only because the constant it guarded was
stale. It is replaced by a **derived** `wall_max_exceeds_response_ttl()`, currently `True`.

---

## 5. P4's sizing does NOT confirm — Fable's "one favourable sample" is not replicated

The handoff carried a favourable sizing: one pass over the exact 20 query-log terms the fix will
warm, *"cold mean 2.250 s, max 4.672 s, all 20 summing to 28.8 s"*, concluding the swap is
**"wall-neutral to wall-favourable"**. Fable asked for its production confirmation. Taken, same
probe, same 20 terms, same instrument:

| | n | mean | p50 | max | **total** | cold |
|---|---|---|---|---|---|---|
| sample 1 (LAT-P078, 15:47Z) | 20 | 1.441 s | 1.535 s | 4.672 s | **28.8 s** | **12 / 20** |
| sample 2 (LAT-P079, 16:5xZ) | 20 | 2.204 s | 1.583 s | **10.385 s** | **44.1 s** | **20 / 20** |

🔴 **It does not confirm, and the reason is a defect in the first sample that the report's own
number half-discloses.** Sample 1's *cold mean* of 2.250 s was correctly computed and correctly
labelled — but only **12 of its 20 terms were cold**. The other 8 were served at 0.220–0.234 s
because they were in the trending head at that moment. **The 28.8 s total is therefore not a cold
total**, and the total is precisely the quantity P4 depends on: whether the pass wall rises. At
all-cold the same 20 terms cost **44.1 s, +53 %**.

Further, on this sample:

* **`masters winner` is the pathological term now, not `ballon d'or`.** 10.385 s here, 4.672 s in
  sample 1; re-probed three times → **6.143 s**, then 0.358 s and 0.340 s (the route's own 65 s
  response cache, not the warmer). So it is genuinely **4.7–10.4 s cold**, it straddles
  `PER_QUERY_TIMEOUT_SECONDS = 10`, and it is **rank 1 in real traffic**.
* **`ballon d'or` (#1619) still does not reproduce its 12.1 s** — 1.729 s and 1.768 s across the
  two samples. That part of the handoff holds.

**Verdict: the sizing is UNDERPOWERED, not refuted.** Two samples of 20 disagree by more than the
effect being sized. **P4 must be read from production after `-71` deploys; it must not be
predicted from either sample.** If it fails, the mitigation is `DEFAULT_HEAD_SIZE` or
`_QUERY_LOG_SHARE`, **never** a revert of the loop-break — which is strictly correct, costs
nothing, and whose reversal would restore the closed head while looking like a fix.

And the risk is now larger than the handoff sized it: the wall max is **66.365 s against a 65 s
TTL before the change** (§4), so P4 opens with **no margin at all**.

---

## 6. Verification

**305 focused tests** across the touched suites, `PYTEST_EXIT_CODE: 0`
(`test_heavy_routing_falsifier` 45, `test_typeahead_beat_budget` 34, `test_typeahead_pass_ring` 36,
`test_typeahead_warmer`, `test_schedule_adherence_wiring` 39, `test_gotcha_numbering`,
`test_product_brain_integrity`).

**9 mutations. 8 caught at exit 1; 1 SURVIVED and is reported, not quietly re-run.** Every
mutation was verified to have APPLIED before its run — a mutation that fails to apply reports
green and is not a catch.

| # | mutation | result |
|---|---|---|
| M1 | stamped-path horizon refusal deleted | exit 1 (2 tests) |
| M2 | route reverts to reading only the protected beats (**the original defect**) | exit 1 |
| M3 | absent mover rendered as `samples: 0` | exit 1 |
| M4 | counter bound ignores the 24 h straddle | exit 1 (5 tests) |
| M5 | unstamped entries counted as post-move | exit 1 |
| M6 | `now_epoch` given a default | exit 1 |
| M7 | stamp list skips `None` (misalignment) | exit 1 |
| M8 | wall max reverted to the stale 53.920 | exit 1 (5 tests) |
| M9 | `WALL_MAX_EXCEEDS_RESPONSE_TTL` hard-coded `True` | 🔴 **SURVIVED**, then exit 1 |

🔴 **M9 is a finding about the test.** The first version made the flag a bare constant with
`assert flag == (MEASURED_WALL_MAX_S > RESPONSE_CACHE_TTL_S)`. When the computed answer is *also*
`True`, that assertion cannot tell a derivation from a constant that agrees with it — so the test
claimed to pin "derived" and did not. Rewritten as a parameterised function exercised **off its
defaults** (`(70,65) → True`, `(60,65) → False`, `(65,65) → False`); the mutation then caught.
Same class as LAT-P078's M6.

---

## 7. Owed

- **#1866 P1–P4** — refused this cycle, fix not deployed. P4 first, and it opens with no margin.
- **Ruling 110's falsifier at a real horizon** — `pre_horizon` is the honest answer today. The
  first gradeable read arrives when a protected beat accumulates 8 post-move samples; on the
  current cadence `precompute_calibration_main` (~21 runs/day) reaches that in ~9 h.
- **R2 at a ≥6 h WORKER horizon** — defeated a fourth time by a mid-window deploy. Sampler running.
- **#2072** — filed, not fixed. Deliberately: it is a second behaviour change to the trending
  zset while #1866's first one is still ungraded.
