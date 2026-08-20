# LAT-P073 — the `warm-typeahead` publish-side gate: THE PLAN

**Fable's LAT-P073 item 2:** *"is_due() publish-side gate: bring me the PLAN — it lives inside
gotcha #39's blast radius (beat scheduling loop), so it ships only through pre-cert with a
kill-switch and a registered halt on cache-entry loss. The 2.4s wall-to-TTL gap says this and the
TTL are the only levers; I want the gate first."*

This is the plan. It is **not** the wiring: nothing in this cycle changes production behaviour,
`beat_schedule_change` is **false**, and the pre-cert artifact
(`app/utils/typeahead_publish_gate.py` + 28 tests, 6 mutations all caught) is imported by its test
suite and by nothing else — with a tripwire test that fails if anyone changes that.

---

## 0. The headline, up front: the plan is READY but the gate is BLOCKED, and not on itself

The design is settled, certified and safe. **It still may not ship, because the halt Fable
requires cannot currently be registered against any production-readable signal.** §6 is that
finding. The next step is not "wire the gate"; it is "make the warmer's pass result readable" —
about a day's work, and it is the precondition for this and for the TTL lever alike.

**That is not a delay, it is the same discipline that produced the refusal Fable accepted in
ruling (a).** A halt you cannot observe is not a halt; it is a sentence in a document.

---

## 1. What changed under the plan since it was staged — READ THIS BEFORE COSTING IT

The queue staged this gate against **"~82 % of fires are no-ops"** and **"6.00 msg/min"**.
Production, read 2026-08-19T23:30Z and replicated at 23:37Z, says the second number is nominal and
the first is stale. Full workings in
`docs/audits/latency/lat-p073-stamp-arm-and-the-expires-finding.md` §3; the two facts that change
this plan's arithmetic:

1. **`deliveries` counts EXECUTIONS, not publishes.** `record_task_delivery` is wired to celery's
   `task_prerun` (`tasks/redis_state.py`). `warm_typeahead` shows **858 deliveries in 21,322 s =
   2.41/min** against a nominal 6.00/min publish rate.
2. **The missing ~60 % is `expires`, and that is now measured rather than supposed.** The set of
   beats reading `ratio < 0.6` is *exactly* the set carrying `expires` — 4 of 4, both directions,
   across 72 rate-armed entries, replicated on two independent reads. Every non-expiring beat reads
   0.99–1.00, **including `poll_live_prediction_markets`, whose p95 (81.6 s) is longer than
   `warm_typeahead`'s (44.6 s)** — so it is not "long tasks fall behind", it is `expires`
   specifically. The background queue was 0–2 deep throughout, so it is not list backlog either.

**Consequence for this plan, stated plainly: the gate is worth less than it was staged at, and it
is worth something different.** It cannot remove 82 % of no-op executions, because `expires`
already removes most of them. What it removes is **queue occupancy spent on messages that will be
discarded unexecuted** — which is #1609's actual subject.

---

## 2. The design

A `celery.schedules.schedule` subclass on the `warm-typeahead` beat entry, whose `is_due()`
consults the warmer's own `_LAST_PASS_START_KEY` **in the beat process, before publishing**.

```
class FloorGatedSchedule(schedule):
    def is_due(self):
        due, next_check = super().is_due()          # 1. the ordinary 10s schedule
        if not due:
            return schedstate(False, next_check)
        age, kill = _read_gate_inputs()             # 2. ONE bounded MGET, or (None, False)
        d = should_publish(                         # 3. the pure decision — already certified
            age_since_last_pass_s=age,
            consecutive_suppressions=self._suppressed,
            enabled=_ENV_ENABLED and not kill,
        )
        self._suppressed = d.consecutive_suppressions
        return schedstate(d.publish, min(next_check, d.next_check_s))
```

Everything policy-shaped is already in `app/utils/typeahead_publish_gate.should_publish`, tested to
exhaustion off-process. The wiring adds exactly two things that can fail: an MGET, and a `min()`.

**Why suppression is safe** — the full argument is in the module docstring and is proved as a
simulation over the whole measured wall range (`test_the_gate_never_removes_a_fire_that_could_have_started_a_pass`).
In one line: `_warm_typeahead` admits a pass only when `now - last_pass_start >= 30`, so a fire
below that floor **cannot** start a pass and suppressing it removes nothing.

**Why the run lock is deliberately NOT consulted.** Gating on `_LOCK_KEY` too would cut ~80 % of
publishes instead of ~40 %. It is refused for exactly the reason LAT-P072 refused 60 s: the lock can
be released between the beat's read and the worker's, so suppressing on it costs a real opportunity
in the *ordinary* regime — and one lost opportunity is +1 beat interval, which takes today's 50 s
period to 60 s, over the measured 45 s cliff. **The aggressive version is arithmetically attractive
and unsafe. This is the version that survives its own measurement.**

---

## 3. The three hazards the queue named, and what each costs

### Hazard 1 — gotcha #39, one level above where that gotcha was written

`is_due()` runs inside the beat process's scheduling loop. A synchronous Redis client with no socket
timeout there freezes **the scheduler itself** — every beat in the system, not just this one.

- Use `get_redis_client()`, which is bounded by default (5 s socket + connect). **Never** a raw
  `redis.from_url`; `test_redis_state.py` already has a CI guard for `tasks/`, and the wiring must
  extend that guard to cover the beat-schedule module.
- **5 s is still far too long to hold a 10 s scheduling loop.** The wiring must pass an explicit
  `socket_timeout=0.25`: this read is one MGET against a local-region Redis, so 250 ms is ~100×
  the expected latency and a full 40× under the beat period. A timeout that cannot fire inside the
  loop's own period is not a bound.
- Wrap the read so that **every** exception returns `(None, False)` — the fail-open input.

### Hazard 2 — FAIL OPEN, and prove it

A Redis that does not answer must **publish**. Proved in both directions and mutated:

| mutation | caught by |
|---|---|
| M1 unknown age → suppress | `test_unknown_age_publishes...` ×2 |
| M4 kill switch demoted below fail-open | `test_kill_switch_reports_disabled_even_when_the_age_is_unknown` |

M4 **survived the first pass of the suite** and the gap was real: both branches publish, so nothing
failed, and the only casualty was the reason label — an operator who had just killed the gate would
have seen `age_unknown` and gone hunting a Redis fault. The test was added and M4 now fails.

The asymmetry that justifies fail-open: suppressing wrongly empties the typeahead head and is
invisible on every instrument this program has; publishing wrongly costs one 10 ms no-op.

### Hazard 3 — `is_due()` must stay cheap and must not lie about `next_check`

`next_check_s` is capped at one beat interval inside the pure function
(`test_next_check_is_never_longer_than_one_beat`, mutation M5), and the wiring takes `min()` with
celery's own value, so the gate can only ever ask to be checked **sooner**.

### Hazard 4 — NOT in the queue, and it is the one fail-open does not cover

Fail-open handles Redis *erroring*. It does not handle Redis answering **and lying**: a future-dated
stamp from a clock-skewed dyno keeps the age below the floor forever. Every individual decision is
locally correct and the warmer stops permanently — which on the adherence surface is
indistinguishable from a quiet period.

The guard is a **consecutive-suppression fuse**, derived rather than chosen:
`ceil(MIN_PASS_PERIOD_S / BEAT_INTERVAL_S) = 3`. A legitimate suppression run is exactly the floor
long; one more than that is a stuck input, and the gate publishes through it. It costs nothing when
healthy, because a healthy run never reaches it (`test_fuse_never_fires_during_a_healthy_run`).

---

## 4. The kill switch — two independent switches, on purpose

| switch | transport | flips in | survives |
|---|---|---|---|
| durable | env var `TYPEAHEAD_PUBLISH_GATE=off` on the beat dyno | a restart | a Redis flush |
| instant | Redis key `bainluck:typeahead_warmer:publish_gate_off` (presence = off) | one `SET` | a dyno restart |

Two, because each covers the other's failure. A Redis-only switch is erased by a flush, silently
re-enabling a gate somebody deliberately killed. An env-only switch needs a dyno restart, which is
not a kill switch during an incident.

The instant switch costs **nothing extra**: it is the second key in the same `MGET` that fetches the
age, so it is one round trip either way. Absence means enabled, so **every** Redis failure —
unreachable, timeout, flushed — lands on today's behaviour rather than on a gate nobody chose.

---

## 5. Registered predictions — before building, graded after

Against the baseline measured 2026-08-19T23:30Z and replicated 23:37Z.

| # | quantity | today | predicted with the gate | how it is graded |
|---|---|---|---|---|
| P1 | **pass period** | 42.5–51.7 s | **UNCHANGED** — this is the halt, not a target | warmer pass result `period_s` |
| P2 | published msg/min | 6.00 nominal | **3.2–3.7** (a 39–47 % cut) | *no instrument today — see §6* |
| P3 | executions/min (`deliveries`) | 2.41 | **flat or UP** | `schedule-adherence` |
| P4 | `warm_typeahead` ratio | 0.39–0.40 | **UP**, toward 0.6+ | `schedule-adherence` |
| P5 | cached entries lost per pass | 0 | **0** — the halt | warmer pass result `expired` |

**P3 and P4 are the interesting ones and they are deliberately counter-intuitive.** Publishing
*fewer* messages should make *more* of them execute, because the ones removed are the ones
currently occupying prefetch slots and expiring. If the gate cuts publishes and the ratio does not
move, the `expires` mechanism is not what §1 measured it to be, and the finding — not the gate —
is what needs revisiting.

**Halt:** any movement in the measured pass period (P1), or any pass reporting lost cached entries
(P5). Both are LAT-P063's 20-for-20 result: crossing the 45 s TTL does not degrade the head
gradually, it empties it.

---

## 6. 🔴 THE BLOCKING PRECONDITION — the halt has no instrument

**Fable requires "a registered halt on cache-entry loss". That signal is not readable in production
today.** Checked, not assumed:

- The warmer's pass result carries exactly the right field — `expired`, computed as
  `[r for r in results if r.get("ttl_before") == _TTL_NO_KEY]`, i.e. entries whose cache key was
  **gone** when the pass reached them. That is cache-entry loss, precisely.
- **It is returned by the task and logged, and nothing else.** There is no admin endpoint for the
  warmer: the live OpenAPI has exactly one `typeahead` path, `/api/events/typeahead`. And
  `heroku logs` is EPERM-blocked from an agent session, so the log is not reachable either.
- **The obvious proxy is also unavailable.** A MISS costs 1.16–2.29 s p50 (#1866), so a jump in
  `/api/events/typeahead` p50 would be the user-visible form. But that endpoint is **not** in
  `always_sampled_endpoints` (only `/api/feed` is) and produced **zero samples in the last hour** on
  `/api/admin/latency-stats`. A proxy with no samples cannot fire a halt.
- P2 is likewise ungraded: **nothing counts publishes.** `deliveries` is `task_prerun`. The gate's
  own headline number would be unmeasurable after shipping.

**So the ordering is forced, and it is not the ordering the queue assumed:**

1. **First** — persist the warmer's last pass result to Redis and expose it read-only
   (`GET /api/admin/typeahead-warmer/last`: `period_s`, `expired`, `rebuilt`, `fresh`,
   `seconds_wall`, `terminal`). Small, no beat change, no behaviour change. This makes P1 and P5
   readable and therefore makes the halt real.
2. **Then, in the same change or the next** — count publishes in `is_due()` itself, which is the
   only place a publish is observable. This makes P2 gradeable and, as a side effect, gives #1996
   the publish-side numerator it has never had.
3. **Only then** — wire the gate, with both kill switches, and grade §5.

**Shipping the gate before step 1 would mean running an intervention whose halt condition cannot
be observed** — which is the shape this program has refused twice (LAT-P071's `celery-debug`
grading, LAT-P072's 60 s beat). It is refused a third time here, in advance.

---

## 7. Rollback

Three levels, cheapest first: `SET bainluck:typeahead_warmer:publish_gate_off 1` (instant, no
deploy); `TYPEAHEAD_PUBLISH_GATE=off` + beat restart (durable); revert the beat entry to the plain
`10.0` schedule (a one-line diff, since the subclass wraps rather than replaces the schedule). No
migration, no data to unwind — the gate writes nothing.

---

## 8. What this plan does NOT propose

- **Any beat-interval change.** Refused on measurement by LAT-P072, guarded by
  `test_live_beat_interval_is_not_unsafe`, and accepted in full by Fable's ruling (a).
- **Gating on the run lock.** §2 — it cuts twice as much and crosses the cliff.
- **Touching the 45 s TTL.** Fable ruled the gate first; the TTL is the other lever and needs its
  own registered prediction. §1's measurement makes it *more* urgent, not less — see the audit doc
  §5 on the wall now reaching 44.6 s against a 45 s cliff.
- **Shipping anything this cycle.** `beat_schedule_change: false`, `migration_slot: none`.
