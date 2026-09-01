# CAL-P188 (#1978, #2052) — the fence is held up by ONE observation, and it ages out tonight

**Session:** CAL-P188, 2026-09-01, ~12:00–13:00Z / ~05:00–06:00 am PT
**Lane:** calibration (build lane, idle on the build board by roadmap — ruling 134)
**Shipped code:** none. D-G's default freeze on calibration-source deploys holds and was honoured.

---

## 0. THE ONE PARAGRAPH

P187 found that the beat-gauge instrument drops three gauges that qualify its unit cost. That was
right, and it was an undercount. **The producer writes 33 keys into the phase ledger every beat and
the sampler captures 18 — fifteen are dropped, every beat, irreversibly.** Among the dropped are the
four gauges CAL-P163 built for exactly one purpose: to say *why* a unit was cancelled and *how tight
the fence was*. Reading them live off `durable_state_snapshots` on two consecutive beats answers,
six beats early and with the opposite attribution, the question this lane had scheduled for beat 12:
**the fence repair deployed and is working; the plateau at 5 completions/beat is the fence sitting
318,735 ms BELOW the window the beat had available**, and all four cancellations across the two
beats died within 531 ms of it. Worse, and this is the part nothing captured could ever have shown:
**that fence is held up by a single completed unit from the `2026-08-31T18:37:31Z` beat, and the
24-beat ring it lives in ages out in ~7 beats — approximately `2026-09-01T19:30–20:30Z` tonight** —
at which point the fence mechanically tightens from 353,754 ms to ~238,667 ms. The four-times-
confirmed `09-02T08:30–09:30Z` ETA has a dated, mechanical risk tonight that no prior session could
see, because the gauge that reveals it is the one the instrument throws away.

---

## 1. WHAT IS DROPPED — the census, measured

Live ledger (`durable_state_snapshots`, identity `calibration:main:phase_ledger`), beat
`2026-09-01T12:32:56.924818Z`: **33 keys.**
Sampler capture (`select_gauges`, `calibration_beat_gauge_sampler.py:167-177`): a hand-maintained
`REQUIRED_DISCLOSURE_GAUGES` (9, derived) + `OPERATIONAL_GAUGES` (9, hand-maintained) + one prefix
sweep (`staged:convergence_reason:`).

Census over the full retained ring (`?full=true`, 168 observations): **exactly 18 distinct gauge
keys have EVER been captured.** The prefix sweep has never fired once in 168 beats.

**The 15 dropped, classified.** The classification matters more than the count — most are
recoverable from what *is* captured, and saying so is what makes the rest load-bearing.

| dropped key | recoverable from the captured set? |
|---|---|
| `staged:served_reason:no_served_units` / `:no_digest_map` / `:unstamped` | ✅ **yes** — `served_units` is captured and distinguishes all three states. Redundant. |
| `staged:drift_coverage_reason:no_digest_map` | ✅ **yes** — its path early-returns, so `units_drift_checkable`/`_uncheckable` go absent and land in `gauges_missing_required`. Has never fired in 168 beats. |
| `staged:rate_reason:no_unit_ran` | ✅ **yes** — `units_this_beat: 0` is captured. Redundant. |
| `staged:cursor_reason:resumable` | ✅ **yes** — `cursor_resume` is captured. |
| `rss:peak_mb`, `rss:at:{stage}` | ➖ out of scope for this instrument. |
| `read:futures_generation`, `read:futures_unit` | ➖ raw stage timings. |
| `staged:units_partition`, `staged:window_stop:units_cancelling` | 🟡 low value, but not reconstructable. |
| `staged:prior_unit_ms`, `staged:prior_unit_reason:unmeasured` | 🔴 **NO** — a carried value. |
| `staged:unit_ms_mean_completed`, `staged:unit_cost_reason:no_unit_completed`, `staged:beats_basis:*` | 🔴 **NO** — P187's three. Confirmed. |
| **`staged:unit_bound_ms:{phase}`** | 🔴 **NO — and this one is load-bearing.** |
| **`staged:unit_bound_headroom_ms:{phase}`** | 🔴 **NO — and this one is load-bearing.** |
| **`staged:unit_cancelled_after_ms`, `staged:unit_cancelled:{chunk.key}`** | 🔴 **NO.** |
| **`staged:unit_worst_carried_ms:{phase}`, `staged:unit_worst_reason:unmeasured:{phase}`** | 🔴 **NO — this is the ring that sets the fence.** |

**The loss is irreversible and the endpoint's own docstring says so.**
`admin_cohort.py:637`: *"`calibration:main:phase_ledger` is overwritten every beat, so without this
ring the bound's descent is observable only by something that happened to be watching at the time."*
A dropped gauge survives ~45 minutes and is then gone. The sampler ring is the sole durable record.

**CAL-P163 wrote the reason it built the four, at the site
(`calibration_main_build.py:722-728`):** *"say WHICH evidence bounded this unit, and how far the
bound sits from the window that was actually available. Without this pair, a cancelled unit records
only that it was cancelled — the same ledger entry whether the fence was 100 ms too tight or 600 s
too tight, and those call for opposite responses. The sixteen-beat pin this fix addresses cost a day
to attribute for exactly that reason."*
**That is the state the lane was in.** The scheduled beat-12 verdict reads one bit
(`units_completed_this_beat` still 5 ⇒ "the repair FAILED"). The gauges that say *by how much* are
written every beat and discarded.

---

## 2. THE FENCE, MEASURED LIVE — n=2, two consecutive beats

Read directly off `durable_state_snapshots`, not the sampler.

| gauge | beat `11:32:41.930811Z` (5th post-repair) | beat `12:32:56.924818Z` (6th) |
|---|--:|--:|
| `staged:unit_bound_ms:futures` (**the fence**) | **353,754** | **353,754** |
| `staged:unit_bound_headroom_ms:futures` (**window left UNSPENT**) | **318,735** | **304,577** |
| `staged:unit_worst_carried_ms:futures` (**the ring max**) | **255,836** | **255,836** |
| `staged:unit_cancelled:<key>` (unit 1) | 353,843 | 353,840 |
| `staged:unit_cancelled:<key>` (unit 2) | 353,915 | 354,285 |
| `staged:unit_ms_mean_completed` (**the real unit cost**) | 63,406 | 65,284 |
| `staged:unit_ms_mean` (**published; contaminated**) | 146,396 | 147,789 |
| `staged:unit_ms_worst` (this beat's worst completion) | 80,828 | 85,957 |
| `staged:prior_unit_ms` | 61,023 | 63,406 |
| `units_this_beat` / `completed` / `cancelled` | 7 / 5 / 2 | 7 / 5 / 2 |
| `units_banked` | 20 | 25 |

**Three findings, each measured:**

**(a) All four cancellations are FENCE kills, not window kills.** 353,840 / 353,843 / 353,915 /
354,285 against a fence of 353,754 — the widest miss is **531 ms**. Nothing ambiguous survives here.

**(b) The beat cancels while holding ~5 minutes it never spends.** `unit_bound_headroom_ms` is
`remaining_ms − timeout_ms` at the moment the bound was set: **318,735 ms and 304,577 ms of window
were available and withheld from the unit by the fence.** `statement_timeout_for_unit` returns
`min(phase_bound, unit_bound)` and the unit bound is binding by ~5 minutes on both beats.
`staged:window_stop:units_cancelling: 0` — the beat did not run out of time. It stopped on
`STAGED_UNIT_MAX_CANCELLATIONS = 2`.

**(c) The published unit cost overstates the real one by 2.3×.** P187's trap 22, now with the
completed-only figure beside it on the same beat: **146,396 vs 63,406**, and **147,789 vs 65,284**.

**The fence reproduces exactly from first principles**, which is what licenses the projection in §3:
```
worst_basis = measured_unit_worst_ms × BUDGET_SAFETY = 255,836 × 1.5      = 383,754
mean_basis  = prior_unit_ms × STAGED_UNIT_OVERRUN_FACTOR = 61,023 × 4.0   = 244,092
basis       = max(...)                                                    = 383,754
fence       = basis − STATEMENT_INNER_MARGIN_MS = 383,754 − 30,000        = 353,754  ✓ EXACT
```
(`calibration_phase_ledger.py`: `BUDGET_SAFETY=1.5:245`, `STAGED_UNIT_OVERRUN_FACTOR=4.0:322`,
`STATEMENT_INNER_MARGIN_MS=30_000:241`, `_statement_timeout_for`, `statement_timeout_for_unit`.)

---

## 3. 🔴 THE DATED PREDICTION — the fence tightens ~`09-01T19:30–20:30Z` tonight

`UNIT_WORST_WINDOW = 24` beats, and its own docstring is explicit that this cuts both ways:
*"It still ages out — a genuinely cheaper population reclaims the fence in a day."*
`load_phase_measurements` (`calibration_main_build.py:1137`) folds it in as **`max(ring)`**.

Scanning the captured 168-beat series of `staged:unit_ms_worst` (**this beat's own worst COMPLETED
unit** — see the correction in §4), the last 24 beats are:

```
08-31 18:37:31   250,681   <-- THE ONLY OBSERVATION HOLDING THE FENCE UP
08-31 19:42:39   146,637
08-31 21:30 → 09-01 11:32   84,791 / 76,208 / 80,018 / 49,268 / 137,773 / 179,111 /
                            93,078 / (none) / 159,410 / 87,591 / 52,737 / 53,126 /
                            103,882 / 85,448 / 80,828
09-01 12:32       85,957
```

**One observation — 250,681 ms at `08-31T18:37:31Z` — is the ring max.** Every other beat in the
window is between 49,268 and 179,111 ms; the last six are all ≤ 103,882 ms.

**17 beats have elapsed since it was recorded. It leaves the 24-beat ring in ~7 beats.** At the
current ~1 beat/hour that is **approximately `2026-09-01T19:30–20:30Z` tonight.**

When it does, the ring max falls to the next in-window observation and the fence recomputes:

| ring max | fence = max×1.5 − 30,000 |
|--:|--:|
| 255,836 (now) | **353,754** |
| 179,111 (next in window) | **238,667** |
| ~86,000 (if the ring refills from the current regime) | **99,000** |

**Why this matters more than the number.** The two units that cancel today need >354 s; a tighter
fence does not make them worse. The hazard is the units that currently *complete* between the new
fence and the old one — and the ring proves such units exist, because 250,681 and 179,111 ms
completions are both inside the current window. Each one that starts cancelling is removed from the
completion ring, which lowers the ring max, which tightens the fence again. **That is precisely the
CAL-P163 ratchet, and it is scheduled to re-arm tonight.**

**This lands on the same beat as the directive's beat-12 checkpoint (~18:30Z).** A drop in
`units_completed_this_beat` observed around then would be attributed by the scheduled reading to
*"the fence repair failed"*. On this evidence that attribution would be **wrong**: the repair is in
force and exact, and the cause would be the ring aging out.

⚠️ **Confidence and its limits.** The mechanism, the constants and the arithmetic are verified
exactly. **The date is ±2 beats and rests on a reconstruction**: the carried ring reads 255,836
while the best captured in-window observation is 250,681, so the ring holds at least one completion
the sampler never captured. Beat spacing is also not exactly hourly (gaps at 20:xx and 04:19 in the
window above). **Treat `19:30–20:30Z` as the centre of a ±2-beat band, not a deadline.**

**Falsifier, pre-registered:** if `staged:unit_bound_ms:futures` is still 353,754 at
`09-01T22:30Z`, this projection is wrong and the ring holds an observation I could not see.

---

## 4. CORRECTION TO THE CARRIED DIRECTIVE

The correction table in directives 953/954 carries:

> `unit_ms_worst` = worst unit of this beat → **NO — fed from the carried `UNIT_WORST_WINDOW` ring.**

**That is wrong, and it is the trap-23 class biting the trap's own author.** There are TWO keys:

- **`staged:unit_ms_worst`** — `precompute_calibration.py:4457` records `int(worst_unit_ms)`, the
  beat-local variable initialised to `0.0` at `:4607`. **It IS this beat's own worst completed
  unit.** Captured, 148/168.
- **`staged:unit_worst_carried_ms:{phase}`** — `calibration_main_build.py:737`, from
  `measured_unit_worst_ms(phase)`, i.e. `max(ring)` over `UNIT_WORST_WINDOW`. **This is the carried
  ring.** **Dropped — never captured, 0/168.**

The two were conflated because only one of them is visible in the artifact. Live proof on one beat:
`unit_ms_worst = 85,957` and `unit_worst_carried_ms:futures = 255,836` — same beat, same phase.
**The correction is load-bearing**: §3's dating is only possible once `unit_ms_worst` is read as a
per-beat series.

---

## 5. 🟢 OPERATIONAL FINDING — the ledger is readable ~13 minutes before the sampler

`calibration:main:phase_ledger` is a row in `durable_state_snapshots` and is therefore reachable
from `POST /api/admin/db-query`. Beats land ~:32; the sampler writes ~:45–:48. **Reading the ledger
directly gets the beat ~13 minutes earlier AND gets all 33 keys instead of 18.**

```sql
SELECT k, payload->'stages'->>k AS v
FROM durable_state_snapshots, jsonb_object_keys(payload->'stages') AS k
WHERE identity='calibration:main:phase_ledger' ORDER BY k
```
Check freshness first with `SELECT updated_at FROM durable_state_snapshots WHERE identity=...`.

⚠️ **It is a single overwritten row — there is no history.** One beat only, and it is destroyed at
the next. This complements the sampler ring; it does not replace it. **A session that wants a
dropped gauge must read it inside the beat's own hour or lose it forever.**

---

## 6. WHY NOTHING WAS BUILT

The repair is small and known: add the load-bearing keys to `OPERATIONAL_GAUGES`, and give
`select_gauges` prefix sweeps for `staged:unit_bound_`, `staged:unit_cancelled`,
`staged:unit_worst_` and the reason families, instead of one hand-maintained tuple plus one prefix.
It is capture-only and cannot affect the build.

**It is not queued, for two reasons, and both are the rules working rather than an excuse.**

1. **Ruling 134.** This is instrumentation for the measurement lane. It has no user-visible ship, so
   a build lane does not run it. Parked as `P188-1`.
2. **D-G.** The default is (a) freeze on calibration-source deploys until the page unfreezes itself.
   `calibration_beat_gauge_sampler.py` is calibration source. **The freeze held again this session
   and this lane did not test it.**

**The cost of waiting is bounded and now known: 15 gauges per beat, ~1 beat/hour.** Against that,
§5 gives any session the full 33 keys on demand for the current beat — so the capture gap is a
history gap, not a visibility gap, and nothing is blocked on the fix.

---

## 7. WHAT THIS SESSION DID NOT MEASURE

- **Whether the two cancelling units are the SAME two each beat.** The keys differ across the two
  beats (`2ef60c20…`/`8f51d074…` then `0083c993…`/`2c26d1c6…`), which suggests they are not a fixed
  pair — but four samples over two beats cannot establish the population, and
  `staged:unit_cancelled:{chunk.key}` is dropped so there is no history to scan. **Unknown.**
- **What those units actually cost.** They were killed at the fence, so their true duration is
  censored at >354 s. A lower bound is all that exists, by construction.
- **Whether the ring holds an uncaptured observation above 250,681.** The 255,836 carried value says
  it does. Not resolvable from the captured set — §3's ±2-beat band is exactly this uncertainty.
