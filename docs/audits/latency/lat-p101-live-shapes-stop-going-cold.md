# LAT-P101 — the live Sports tab stops going cold once a minute (#2236)

**Ship:** a person who opens the Sports tab while a game is in progress no longer
waits **2.6–4.6 seconds** for it, roughly once every ninety seconds, at random.

Pre-registration and frozen prediction: `lat-p101-2236-prereg.md`.
Raw production baseline: `lat-p101-2236-prefix-sawtooth.txt`.

---

## 1. What was wrong

Two changes shipped 2026-08-27, both correct, and their **product** was a defect
neither could see.

* **#2216 / q412r** (`b71e2c0d`, v3910) — a feed payload containing a live card
  is capped at `ttl 30 / stale 60`. Past 60 s it is REBUILT, not served older.
  This is the fix Alex's stale-score report asked for: a 330 s-old live score
  printed as current is the app lying quietly.
* **LAT-P099** (`e4c87d52`, v3911) — enrolls the native Sports shape in the
  pre-warm, hosted inside the every-**120 s** `precompute_discover_candidate_base`
  beat.

`120 > 60`. The warmed key dies a full minute before its next chance to be
refreshed, so the warm rail **structurally cannot** keep a live shape warm — and
it reports success on every pass, because it genuinely does warm the key. It
just warms one that is already gone by the time it matters.

The 60 lived in `app/utils/feed_cache.py`. The 120 lived in
`app/tasks/__init__.py`'s beat schedule. **Nothing in the codebase compared
them**, and neither author could have been warned. That, and not the sawtooth,
is the defect class this cycle closes.

## 2. The measurement, before the fix

Slug `56dbbfa5` (current master, contains both halves), uptime > 900 s so outside
the post-deploy window. Anonymous `GET /api/feed`, no `x-session-id`. 6 minutes,
10 s interval, 31 samples per shape, via the new
`backend/scripts/measure_live_feed_sawtooth.py`.

| shape | live | **MISS** | warm p50 | cold misses (ms) | max score age |
|---|---|---|---|---|---|
| `limit=50&mode=sports` (native) | 31/31 | **4/31** | 608 ms | 2,606 · 2,768 · 3,513 · **4,558** | **56.5 s** |
| `limit=20&mode=sports` (web) | 31/31 | **4/31** | 382 ms | 895 · 1,108 · 1,892 · **2,315** | **58.6 s** |

The cycle, read straight off the capture:

```
t+26  hit        age 23.5s
t+37  stale_hit  age 34.3s
t+48  stale_hit  age 45.2s
t+59  stale_hit  age 56.5s      <- the ceiling, reached
t+73  MISS       3,513 ms       <- somebody pays
t+85  hit        age 12.8s
```

Every sample carried `cache.live: true`, `ttl 30`, `stale_ttl 60`, so #2216 is
firing exactly as designed and this is a live-containing payload, not a quiet
night. **The `max_age` of 56.5 / 58.6 s is the key running out, not being
refreshed.** One user in roughly eight waits seconds for a tab that serves
everyone else in 0.4 s.

⚠️ **The cold number is 2–3x worse than #2236 itself recorded** (1.0–1.5 s, with
one 14.4 s). Not a contradiction — a different hour, different DB buffer state,
and the issue's own first sample was 14.4 s. Both readings are in the record. The
frozen prediction grades on the **presence** of misses, not their duration,
precisely because duration moves with conditions nobody controls.

⚠️ **The first capture attempt is recorded rather than discarded.** It was a
shell loop whose per-sample subprocess overhead made its `t+` column
untrustworthy against wall clock, and it was cut off before the hole appeared.
Its cache states and cold timings stand — those are read from headers and from
`cache.built_at`, not from the loop's clock — but its cadence does not, which is
why the instrument was rewritten as a script that can be re-run identically after
the deploy.

## 3. The fix — an invariant, not a number

The period is now declared in `app/utils/feed_cache.py`, **three lines under the
ceiling it must respect**, and the arithmetic binding them is a function rather
than a comment:

```
FEED_LIVE_REPUBLISH_PERIOD_S (40) + FEED_LIVE_REPUBLISH_BUDGET_S (20)
    <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS (60)
```

A pass fires at t=0 and publishes a payload whose stale mirror dies at t=60. The
next pass fires at t=40 and may burn its entire 20 s budget before publishing.
Even then it lands at t=60. **The budget is not headroom — it is the second term
of the invariant**, which is why widening it is a change to the correctness
argument and goes red.

`test_a_republish_pass_lands_before_the_previous_one_expires` fails on every way
of reintroducing #2236: lengthening the period (M1), shortening the ceiling
underneath it (M2), or widening the budget (M3).

The new beat `prewarm-live-feed-shapes` republishes **only the shapes the last
warm observed to be live**, through the same `_prewarm_feed_shape` the 120 s pass
uses. One writer, so the warmed key cannot drift from the read key (LAT-P001's
defect) and the live ceiling cannot be applied twice differently (#2216's).
Liveness is a Redis hash written by that shared warmer in **both** directions, so
a shape that stops being live leaves the set on its own and no separate expiry
logic exists to get wrong.

**Off-hours the pass is one `HGETALL` and one `SETEX`.** That is what makes a 40 s
beat affordable next to a 120 s pass measured at p50 9.8 s.

## 4. The finding this cycle produced that was not in the issue

**`background` would have made the fix partially inert, and inert in the silent
way.**

The invariant assumes the pass *starts* at its period. `app/tasks/__init__.py`
documents `background` as having **~one effective slot for ~45 beats** ("price a
new background beat against one slot, never two"); a 26-sample census measured
**90 % slot occupancy**; and `app/utils/typeahead_beat_budget.py` says ordinary
co-tenant bursts produce **multi-minute waits**. A pass that starts two minutes
late publishes nothing in time — the key already expired and the user already
paid. And the beat would have reported success on every pass it eventually ran,
which is #2236's own failure signature reproduced one layer down.

So the task is on **`realtime`**, whose stated purpose is *"high-frequency tasks
driving user-visible live game data. Never blocked by batch jobs."* Both routing
surfaces say so, because beat `options` override `task_routes` and a disagreement
makes the queue depend on how the task was published.

The background census is **unmoved** — re-derived from the assembled schedule,
never by delta (#1910): explicit **57**, fall-through **45**, total **102**.

## 5. What the mutation battery found that the tests did not say

16 mutations, each restored from a byte-exact backup and verified with `cmp`
before the next one ran. (LAT-P100's first battery restored with a pathspec that
matched nothing, so seven mutations stacked; this one uses absolute paths and
aborts the whole run on a failed restore.) The first pass came back **14 red, 2
green — and both green rows were real holes.**

**M10 — the starvation guard was testing nothing.** It asserted
`deadline >= BUDGET/N` while driving the pass with an *instant* fake warm, so
`budget_left` never fell — and `deadline_s = budget_left` (the exact defect)
hands every target the whole 20 s, which clears a 4 s floor comfortably. A
starvation test whose targets consume nothing cannot observe starvation. Now in
two halves: the first target must get *exactly* its fair share, and the
adversarial every-target-eats-its-slice case is simulated over the allocator
directly.

**M16 — nothing guarded the `expires` bound's existence.** The standing
`test_1609_warmer_beats_carry_an_expires_bound` asserts that every beat *listed*
in `_EXPIRING_WARMER_BEATS` has a bound; it cannot notice a beat that is simply
absent from the list. Deleting this beat's entry was green across every suite.
**A guard over the members of a set is not a guard over membership** — that is
the transferable half, and it applies to every allowlist in this repo.

Both are recorded here rather than quietly fixed, because the shape is the
lesson: a guard can be red-proof-*shaped* and still be asserting nothing, and the
only thing that showed it was mutating the code it claimed to protect.

### The battery, after the repair — 16 of 16 red

| mutation | red | guard |
|---|---|---|
| M1 period back to 120 | 1 | the #2236 invariant |
| M2 ceiling shortened to 45 | 2 | the invariant + #2216's own ceiling pin |
| M3 budget widened to 30 | 2 | the invariant + the limit ladder |
| M4 beat restates the period as a literal | 1 | the two-files arrangement |
| M5 hard limit 60 > period | 1 | overlapping passes |
| M6 warmer stops recording liveness | 1 | the live set is written by the writer |
| M7 not-live shapes are never cleared | 1 | the set converges in both directions |
| M8 live-set read fails open to every shape | 1 | direction of failure |
| M9 pass ignores the live set | **6** | the selection is the cost control |
| M10 naive shared budget | 1 | gotcha #34, on the new budget |
| M11 idle pass writes no report | 1 | gotcha #53 |
| M12 only its own kill switch honoured | 1 | "the rail is off" must mean the rail |
| M13 bytes labels not decoded | 1 | a silent no-op that reads as a quiet night |
| M14 beat falls back to `background` | 1 | §4 |
| M15 routing surfaces disagree | 1 | §4 |
| M16 `expires` bound removed | 1 | membership, not members |

## 6. Gates

| | result | exit |
|---|---|---|
| **full backend suite** `pytest tests/ -q` | see READY token | |
| `tests/test_feed_live_prewarm.py` (new, 22 tests) | 22 passed | **0** |
| `tests/test_tasks_wiring.py` (beat wiring, gotcha #12) | 33 passed | **0** |
| `tests/test_typeahead_beat_budget.py` (background census) | passed, census unmoved | **0** |
| `tests/test_feed_prewarm.py` | 33 passed | **0** |
| `tests/test_feed_live_cache_ceiling.py` (#2216's own suite) | 22 passed | **0** |
| `tests/test_startup.py` (mandatory smoke) | 4 passed | **0** |
| `ruff` on the 2 new files | clean | **0** |
| `ruff` on the 3 modified app/test files | **zero NEW findings** vs `git show HEAD:` (4 pre-existing in `tasks/__init__.py`, 24 in `test_tasks_wiring.py`) | — |
| `black --check` on the 2 new files | unchanged | **0** |

⚠️ **The first full-suite run went red and the red was correct.**
`test_the_background_queue_carries_102_beats_and_45_are_fall_through` failed at
`58 == 57` when the beat was still on `background`. That guard's own docstring
reserves the case, and it is the only test in the repo that would have noticed.
It is now green because the beat moved to `realtime` (§4) — **not** because the
census was edited to accommodate it.

## 7. Frontend / iOS gates

Not run and not owed: zero frontend files, zero iOS files touched.

## 8. Deploy checks owed

The frozen prediction and its bars are in `lat-p101-2236-prereg.md` §5. In short:
after uptime > 300 s and one 120 s pass, re-run

```
source ~/.claude/.env
python3 backend/scripts/measure_live_feed_sawtooth.py --minutes 6 --interval 10
```

and grade **B1/B2 zero `miss` after the first sample on both sports shapes**,
**B3 the ceiling still enforced** (`live: true`, `ttl 30`, `stale 60`), **B4
max score age ≤ 60 s**, **B5 `prewarm_live_feed_shapes` has `successes_24h > 0`**.

⚠️ **A window in which no sample reports `cache.live: true` grades NOTHING**, in
either direction — the script says so in its own summary and refuses to claim a
result. A quiet night produces `ttl 60 / stale 300` payloads the 120 s pass has
always covered, and a clean zero-miss run under those conditions would be a
measurement of the *old* code working as designed.

Also owed: read `bainluck:precompute:feed_live_prewarm:last` once to confirm
`live_labels` is non-empty during a live game, and confirm `realtime` queue depth
stays at 0.
