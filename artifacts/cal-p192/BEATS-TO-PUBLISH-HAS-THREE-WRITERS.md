# CAL-P192 (#2052) — `staged:beats_to_publish` has three writers, and the frozen one's `-1` is clamped to `0`

**Session:** CAL-P192, 2026-09-01. **Branch:** `program/calibration-190-the-rebuild-survives-a-deploy`.
**Pillar:** TRUTH. **Ship it serves:** the calibration rebuild's published curve — this is the
instrument that says whether it will ever get there. **Test-only; nothing under `app/` touched.**

---

## 0. One paragraph

P191 asked *"two writers, one key — which one wins, and do they agree on what it means?"* and parked
it as the successor question. This session **ran the sweep it implies**, across every
`record_stage` / `record_gauge` / `record_stage_outcome` call site under `app/`: **45 distinct keys,
three with more than one writer, every one of them mixing the two write rules.** The new finding is
`staged:beats_to_publish`, which has **three** writers — and the frozen module emits the `-1`
catastrophe sentinel through `record_stage`, whose first line is `ms = max(0, int(duration_ms))`.
**The sentinel becomes `0`, which is the exact integer the sibling writer uses for "nothing remains,
it publishes this beat".** The two most opposite states of the rebuild render as the same number.
The clamp is **latent**, because the gauge writer normally lands last — but that ordering is
measurable, not assumed, and the paths where it does not hold are already gauged because they happen.

---

## 1. The sweep

`grep`-then-AST over `app/`, counting only calls whose first positional argument is a statically
renderable key. Forwarding sites (a bare `name` variable passed through) are **counted, not
skipped** — a forwarder is the one way a fourth collision could enter unseen.

| keys written | 45 |
| keys with >1 writer | **3** (plus 2 forwarders) |
| collisions mixing `record_stage` + `record_gauge` | **3 of 3** |

| key | writers | do they agree on meaning? |
|---|--:|---|
| `staged:units_this_beat` | 2 | ❌ banked vs attempts — **P191** |
| `staged:unit_ms_mean` | 2 | ❌ same divisor split, one key over — **same defect instance** |
| `staged:beats_to_publish` | **3** | ❌ mixed-mean vs completed-mean, **and the sentinel is destroyed** |

That 3-of-3 is the structural point. **No collision here is like-for-like.** Two `record_gauge`
writers would merely disagree on a value; a `record_stage` landing *after* a `record_gauge` **sums
them into a number neither writer computed**. Order is load-bearing and nothing enforces it.

---

## 2. The three writers

1. **`precompute_calibration._record_convergence_projection:4467`** (frozen, ruling 009) —
   `record_stage`, projecting over the **mixed** mean it computes locally as
   `unit_ms_this_beat / ran_this_beat`.
2. **`calibration_main_build._record_staged_rate:1588`** — `record_gauge(…, 0)` when
   `remaining == 0`. **This is the success value: the build publishes this beat.**
3. **`calibration_main_build._record_staged_rate:1621`** — `record_gauge` of the **completed**-mean
   projection, or **`-1`**.

`-1` is not "unknown". **Three separate docstrings say so in nearly the same words** —
`calibration_main_build:1618`, `precompute_calibration:4465`, and `PhasePlan.unit_projection`
(`beats_remaining`) — it is *"a whole beat cannot hold one unit"*, the worst fact the build can
report. It is a convention asserted in prose at three sites and **enforced at none**.

---

## 3. The defect

```python
def record_stage_outcome(self, name, duration_ms, *, completed):
    ms = max(0, int(duration_ms))          # <-- right for durations, fatal for a sentinel
    self.stages[name] = self.stages.get(name, 0) + ms
```

Measured, both directions:

| write | stored |
|---|--:|
| `record_stage("staged:beats_to_publish", -1)` | **0** |
| `record_gauge("staged:beats_to_publish", -1)` | **-1** |
| `record_gauge(…, 4)` then `record_stage(…, 9)` | **13** — a projection neither writer made |

So writer 1's catastrophe reads as writer 2's success, and **nothing else in the payload separates
them** — `stage_counts` records *that* it fired, never *what it said*.

---

## 4. Why it has never been seen — and exactly when it would be

Writer 3 runs on the terminal path and lands **last**, overwriting writer 1 before anyone reads.

🟢 **That ordering is measured, not assumed.** Via the sibling key that has both writers: the live
`2026-09-01T16:32:11.447482Z` ledger publishes `staged:units_this_beat` = **7** = attempts. The
frozen writer contributes banked (**5**) through `record_stage`. Had it landed *second*, the stored
value would be `5 + 7 = 12`. **Seeing 7 fixes the order for both keys**, since the writes sit in the
same pair of functions.

The clamp therefore surfaces exactly when `_record_staged_rate` **returns before** `:1588`/`:1621`:

- `calibration_main_build:1400` — the durable convergence snapshot read is not ok / stale
- `:1404` — payload not a dict · `:1408` — `committed_units` not a list · `:1418` — it raised

**Those paths are gauged (`staged:convergence_reason:*`) precisely because they happen.** On such a
beat the ledger publishes `beats_to_publish: 0` while the truth is `-1`, and
`calibration_beat_gauge_sampler.OPERATIONAL_GAUGES` carries that `0` to an operator.

The one path that *cannot* reach it: `:1582` (`mean_ms is None`, no unit ran). Writer 1 only fires
when `ran_this_beat > 0`, which guarantees a unit-stage observation, so `mean_ms` is not `None`.

---

## 5. 🔴 A stale comment worth deleting when the freeze lifts

`precompute_calibration:4370` states the projection is skipped on every beat, *"which is why
`staged:beats_to_publish` is absent from every ledger."*

**The live ledger contradicts it.** `stage_counts['staged:beats_to_publish'] = 1`, and `record_gauge`
never touches `stage_counts` — so that `1` **can only be the frozen writer**. The unit loop now exits
normally via the window stop (`staged:window_stop:units_cancelling: 1`) rather than throwing, so
writer 1 fires **every beat**. The comment describes a world that ended.

---

## 6. What was NOT done, and why

🔴 **No fix.** Choosing which writer owns the key — or giving `record_stage` a signed variant, or
moving the sentinel out of band — changes a gauge the sampler and five graders read. **That is a
fold's call under ruling 134, not a build lane's.** Parked as **`P192-1`**.

🔴 **Not deployed, not merged.** Test-only, so `_main_input_fingerprint()` is unmoved
(`e2040f90154fae876f0fb65f5abf74c3`, re-verified *after* the file was added) and the branch stays
inert under the D-G freeze.

---

## 7. Guards

`backend/tests/test_beats_to_publish_sentinel_clamp_p192.py` — **16 tests, 3.07 s.** They
**characterize** current behaviour; they do not assert it is right.

Six groups: the sweep (incl. a fourth-collision tripwire and a forwarder-count tripwire) · the clamp
· order-is-load-bearing, with the live beat as the ordering witness · the frozen writer did fire ·
blast radius into the sampler · the convention is prose-only.

**Proven non-vacuous by mutation, each in an rsync copy, never the live tree:**

| mutation | result |
|---|---|
| add a 4th colliding writer for `staged:units_completed_this_beat` | ❌ sweep **FAILS** as designed |
| delete `max(0, …)` from `record_stage_outcome` | ❌ **3 clamp tests FAIL** |

The scan **raises** on any key it cannot render rather than skipping it — and it *did*, on first run,
against the `IfExp` at `calibration_main_build:1614`. It was taught to read both branches. A source
scan that silently skips what it does not understand reports "no new collisions" for a file it never
read, which is the failure mode this file exists to catch one level down.

---

## 8. Gates

| gate | result |
|---|---|
| `test_beats_to_publish_sentinel_clamp_p192.py` | **16 passed**, exit 0 |
| + P191 + `test_staged_rate_projection_1680.py` + `test_startup.py` | **42 passed**, exit 0 |
| `_main_input_fingerprint()` after the add | `e2040f90154fae876f0fb65f5abf74c3` — **unmoved** |
| `git diff --name-only 7d066c50 origin/master \| grep -i calib` | empty, exit 1 — **ALL-CLEAR** |

## 9. State at close

`origin/master` `35c50d48`, unmoved this session. Live beat still `16:32:11.447482Z` — **no new beat
landed**; `units_banked` 45/128, `served_units` 0, `published: false`. Published curve unchanged for
a **twenty-seventh** session (`generated_at 2026-08-31T04:37:36Z`). ETA `09-02T08:30–09:30Z`,
not re-derived.
